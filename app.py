import asyncio
import json
import os
import sys
from pathlib import Path
from flask import Flask, render_template, jsonify, request, Response, session

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from dazn_navigator2.cli.eventi_cmds import _load, _save, add_event
from dazn_navigator2.services.explorer import DaznExplorer
from dazn_navigator2.services.extractor import HeadlessExtractor
from dazn_navigator2.services.browser import BrowserManager

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dazn-secret-auth-key-2026")

PROFILES_CONFIG_FILE = BASE_DIR / "profiles_config.json"

# Mappa password -> ID profilo
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
    p = cfg.get(profile_id, {}).get("chrome_profile_path") or session.get("chrome_profile_path", "chrome_profile")
    path_obj = Path(p)
    if not path_obj.is_absolute():
        path_obj = BASE_DIR / path_obj
    return str(path_obj)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/session", methods=["GET"])
def check_session():
    if "user_profile_id" in session:
        pid = session["user_profile_id"]
        pname = session.get("user_profile_name", "Profilo")
        cfg = load_profiles_config()
        saved_path = cfg.get(pid, {}).get("chrome_profile_path")
        return jsonify({
            "logged_in": True,
            "profile_id": pid,
            "profile": pname,
            "chrome_profile_set": bool(saved_path),
            "chrome_profile_path": saved_path or ""
        })
    return jsonify({"logged_in": False})

@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json() or {}
    password = body.get("password", "").strip()

    if password in PROFILES:
        prof = PROFILES[password]
        pid = prof["id"]
        session["user_profile_id"] = pid
        session["user_profile_name"] = prof["name"]
        
        cfg = load_profiles_config()
        saved_path = cfg.get(pid, {}).get("chrome_profile_path")
        
        return jsonify({
            "ok": True,
            "profile_id": pid,
            "profile": prof["name"],
            "chrome_profile_set": bool(saved_path),
            "chrome_profile_path": saved_path or ""
        })
    return jsonify({"ok": False, "error": "Password non corretta"}), 401

@app.route("/api/set-profile-path", methods=["POST"])
def set_profile_path():
    if "user_profile_id" not in session:
        return jsonify({"ok": False, "error": "Non autenticato"}), 401

    pid = session["user_profile_id"]
    body = request.get_json() or {}
    p_path = body.get("chrome_profile_path", "").strip()
    if not p_path:
        p_path = "chrome_profile"

    # Salva in modo permanente nel file profiles_config.json
    cfg = load_profiles_config()
    if pid not in cfg:
        cfg[pid] = {}
    cfg[pid]["chrome_profile_path"] = p_path
    save_profiles_config(cfg)

    session["chrome_profile_path"] = p_path

    return jsonify({
        "ok": True,
        "profile": session.get("user_profile_name", pid),
        "chrome_profile_path": p_path
    })

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

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
