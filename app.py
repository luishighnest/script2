import asyncio
import json
import os
import sys
import shutil
from pathlib import Path
from flask import Flask, render_template, jsonify, request, Response, session, redirect, url_for

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from dazn_navigator2.cli.eventi_cmds import _load, _save, add_event
from dazn_navigator2.services.explorer import DaznExplorer
from dazn_navigator2.services.extractor import HeadlessExtractor
from dazn_navigator2.services.browser import BrowserManager

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dazn-secret-auth-key-2026")

PROFILES_CONFIG_FILE = BASE_DIR / "profiles_config.json"
UPLOAD_PROFILES_DIR = BASE_DIR / "saved_profiles"
UPLOAD_PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# 2 Profili con password dedicate
PROFILES = {
    "mpd": {"id": "mpd", "name": "Profilo MPD"},
    "pz8": {"id": "pz8", "name": "Profilo PZ8"}
}

def load_profiles_config():
    if PROFILES_CONFIG_FILE.exists():
        try:
            return json.loads(PROFILES_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_profiles_config(data):
    PROFILES_CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def _image_url(img) -> str:
    if isinstance(img, dict):
        img_id = img.get("Id", "")
        if img_id:
            return f"https://image.discovery.indazn.com/eu/v3/eu/none/{img_id}/fill/none/top/none/100/1280/720/png/image"
        return ""
    return str(img) if img else ""

def get_active_chrome_profile(profile_id):
    cfg = load_profiles_config()
    p = cfg.get(profile_id, {}).get("chrome_profile_path")
    if p:
        path_obj = Path(p)
        if not path_obj.is_absolute():
            path_obj = BASE_DIR / path_obj
        if path_obj.exists():
            return str(path_obj)
    return str(BASE_DIR / "chrome_profile")

@app.route("/")
def home():
    if "user_profile_id" in session:
        return redirect("/script")
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        password = request.form.get("password", "").strip()
        if password in PROFILES:
            prof = PROFILES[password]
            session["user_profile_id"] = prof["id"]
            session["user_profile_name"] = prof["name"]
            return redirect("/script")
        return render_template("login.html", error="Password non valida. Riprova.")
    
    if "user_profile_id" in session:
        return redirect("/script")
    return render_template("login.html")

@app.route("/script")
def script_page():
    if "user_profile_id" not in session:
        return redirect("/login")

    pid = session["user_profile_id"]
    pname = session.get("user_profile_name", "Profilo")
    cfg = load_profiles_config()
    saved_path = cfg.get(pid, {}).get("chrome_profile_path")
    
    has_folder = False
    if saved_path:
        p_obj = Path(saved_path)
        if not p_obj.is_absolute():
            p_obj = BASE_DIR / p_obj
        has_folder = p_obj.exists() and any(p_obj.iterdir()) if p_obj.exists() else False

    return render_template(
        "script.html",
        profile_name=pname,
        chrome_profile_set=has_folder,
        chrome_profile_path=saved_path or "Nessuna cartella configurata"
    )

@app.route("/logout")
def logout_action():
    session.clear()
    return redirect("/login")

# API PER GESTIONE CARICAMENTO CARTELLA
@app.route("/api/upload-profile-folder", methods=["POST"])
def upload_profile_folder():
    if "user_profile_id" not in session:
        return jsonify({"ok": False, "error": "Non autenticato"}), 401

    files = request.files.getlist("files[]")
    paths = request.form.getlist("paths[]")

    if not files or not paths:
        return jsonify({"ok": False, "error": "Nessun file ricevuto dalla cartella"}), 400

    pid = session["user_profile_id"]
    profile_dest = UPLOAD_PROFILES_DIR / f"profile_{pid}"

    if profile_dest.exists():
        try:
            shutil.rmtree(profile_dest)
        except Exception:
            pass
    profile_dest.mkdir(parents=True, exist_ok=True)

    for file_obj, rel_path in zip(files, paths):
        parts = Path(rel_path).parts
        if len(parts) > 1:
            clean_rel = Path(*parts[1:])
        else:
            clean_rel = Path(parts[0])

        target_file = profile_dest / clean_rel
        target_file.parent.mkdir(parents=True, exist_ok=True)
        file_obj.save(str(target_file))

    rel_profile_str = str(profile_dest.relative_to(BASE_DIR))
    cfg = load_profiles_config()
    if pid not in cfg:
        cfg[pid] = {}
    cfg[pid]["chrome_profile_path"] = rel_profile_str
    save_profiles_config(cfg)

    return jsonify({
        "ok": True,
        "profile": session.get("user_profile_name", pid),
        "chrome_profile_path": rel_profile_str
    })

@app.route("/api/events", methods=["GET"])
def get_saved_events():
    if "user_profile_id" not in session:
        return jsonify({"error": "Non autenticato"}), 401
    return jsonify(_load())

@app.route("/api/live", methods=["GET"])
def get_live_events():
    if "user_profile_id" not in session:
        return jsonify({"error": "Non autenticato"}), 401

    async def _fetch():
        explorer = DaznExplorer()
        tiles = await explorer.get_live_tiles()
        items = []
        for t in tiles:
            raw = t.raw or {}
            sport = raw.get("Sport", {})
            if isinstance(sport, dict):
                sport = sport.get("Title", "")
            comp = raw.get("Competition", {})
            if isinstance(comp, dict):
                comp = comp.get("Title", "")

            items.append({
                "id": t.id,
                "asset_id": t.asset_id or t.id,
                "title": t.title,
                "sport": sport,
                "competition": comp,
                "image": _image_url(t.image),
                "tile_type": t.tile_type
            })
        return items

    try:
        data = asyncio.run(_fetch())
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/extract", methods=["POST"])
def extract_stream():
    if "user_profile_id" not in session:
        return jsonify({"ok": False, "error": "Non autenticato"}), 401

    pid = session["user_profile_id"]
    body = request.get_json() or {}
    asset_id = body.get("asset_id") or body.get("id")
    title = body.get("title", "Evento")

    if not asset_id:
        return jsonify({"ok": False, "error": "asset_id mancante"}), 400

    target_profile_dir = get_active_chrome_profile(pid)

    async def _do_extract():
        ext = HeadlessExtractor()
        res = await ext.estrai(target_profile_dir, asset_id, title)
        if res.get("ok"):
            entry = {
                "name": res.get("titolo", title),
                "start": "",
                "manifest": res.get("mpd_url", ""),
                "keys": ",".join(res.get("keys", [])),
                "logo": "",
                "license_url": res.get("la_url", "")
            }
            add_event("Eventi Live", entry)
        return res

    try:
        result = asyncio.run(_do_extract())
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/playlist.m3u", methods=["GET"])
def generate_m3u():
    data = _load()
    lines = ["#EXTM3U"]
    for comp, items in data.items():
        for ev in items:
            name = ev.get("name", "Evento")
            logo = ev.get("logo", "")
            mpd = ev.get("manifest", "")
            keys = ev.get("keys", "")
            
            props = f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" group-title="{comp}",{name}'
            if keys:
                lines.append(f'#KODIPROP:inputstream.adaptive.license_key={keys}')
            lines.append(props)
            lines.append(mpd)
    
    return Response("\n".join(lines), mimetype="audio/x-mpegurl")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
