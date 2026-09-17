import asyncio
import json
import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path
from flask import Flask, render_template, jsonify, request, Response, session, redirect, url_for

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Protezione per esecuzione nascosta/senza console (es. pythonw o script VBS)
if sys.stdout is None:
    try:
        sys.stdout = open(BASE_DIR / "flask.log", "a", encoding="utf-8", buffering=1)
    except Exception:
        import io
        sys.stdout = io.StringIO()
if sys.stderr is None:
    try:
        sys.stderr = open(BASE_DIR / "flask.log", "a", encoding="utf-8", buffering=1)
    except Exception:
        import io
        sys.stderr = io.StringIO()

import threading
from dazn_navigator2.cli.eventi_cmds import _load, _save, add_event
from dazn_navigator2.services.explorer import DaznExplorer
from dazn_navigator2.services.extractor import HeadlessExtractor
from dazn_navigator2.services.browser import BrowserManager

# Event loop persistente su thread dedicato per evitare 'Future attached to a different loop'
_ASYNC_LOOP = None
_ASYNC_THREAD = None
_LOOP_LOCK = threading.Lock()

def _start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def run_async(coro, timeout=90):
    global _ASYNC_LOOP, _ASYNC_THREAD
    with _LOOP_LOCK:
        if _ASYNC_LOOP is None or not _ASYNC_LOOP.is_running():
            _ASYNC_LOOP = asyncio.new_event_loop()
            _ASYNC_THREAD = threading.Thread(target=_start_background_loop, args=(_ASYNC_LOOP,), daemon=True)
            _ASYNC_THREAD.start()
    future = asyncio.run_coroutine_threadsafe(coro, _ASYNC_LOOP)
    return future.result(timeout=timeout)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dazn-secret-auth-key-2026")

PROFILES_CONFIG_FILE = BASE_DIR / "profiles_config.json"
UPLOAD_PROFILES_DIR = BASE_DIR / "saved_profiles"
UPLOAD_PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# Profili con password dedicate
PROFILES = {
    "pz8": {"id": "pz8", "name": "Profilo PZ8"},
    "prova": {"id": "prova", "name": "Profilo Test"},
    "mpd": {"id": "mpd", "name": "Profilo MPD"}
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

def sync_to_github(commit_msg: str):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        token_file = BASE_DIR / "github_token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        print("[Git Sync] GITHUB_TOKEN non configurato, sync su repo saltato.")
        return False, "GITHUB_TOKEN non trovato"

    repo_url = f"https://x-access-token:{token}@github.com/luishighnest/script2.git"

    try:
        subprocess.run(["git", "config", "user.name", "Render Auto-Sync"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "config", "user.email", "render-sync@users.noreply.github.com"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "add", "saved_profiles", "profiles_config.json", "dazn_event.json", "dazn_event_*.json"], cwd=str(BASE_DIR), check=True)
        
        # Commit se ci sono cambiamenti
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(BASE_DIR))
        if diff.returncode != 0:
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(BASE_DIR), check=True)
            subprocess.run(["git", "push", repo_url, "HEAD:main"], cwd=str(BASE_DIR), check=True)
            print("[Git Sync] Salvataggio permanente su GitHub completato con successo!")
            return True, "Sync completato"
        return True, "Nessun cambiamento da committare"
    except Exception as e:
        print(f"[Git Sync Error] {e}")
        return False, str(e)

def _image_url(img) -> str:
    if isinstance(img, dict):
        img_id = img.get("Id", "")
        if img_id:
            return f"https://image.discovery.indazn.com/eu/v3/eu/none/{img_id}/fill/none/top/none/100/1280/720/png/image"
        return ""
    return str(img) if img else ""

def _build_mpd_auth(mpd_url: str, dazn_token: str) -> str:
    """Inserisce il token nel path (@token/...) come richiesto dall'addon e dal formato dazn11."""
    if not dazn_token or not mpd_url:
        return mpd_url
    if "/@" in mpd_url:
        return mpd_url
    if "://" in mpd_url:
        proto, rest = mpd_url.split("://", 1)
        if "/" in rest:
            host, path = rest.split("/", 1)
            return f"{proto}://{host}/@{dazn_token}/{path}"
        return f"{proto}://{rest}/@{dazn_token}"
    return mpd_url

def _format_tile_item(t):
    raw = getattr(t, 'raw', {}) or {}
    sport = raw.get("Sport", {})
    if isinstance(sport, dict):
        sport = sport.get("Title", "")
    elif sport:
        sport = str(sport)
    else:
        sport = ""

    comp = raw.get("Competition", {})
    if isinstance(comp, dict):
        comp = comp.get("Title", "")
    elif comp:
        comp = str(comp)
    else:
        comp = ""

    return {
        "id": t.id,
        "asset_id": getattr(t, 'asset_id', None) or t.id,
        "title": t.title,
        "sport": sport,
        "competition": comp or "Eventi",
        "image": _image_url(t.image),
        "tile_type": t.tile_type,
        "start": raw.get("Start") or "",
        "end": raw.get("End") or "",
    }

def get_active_chrome_profile(profile_id):
    cfg = load_profiles_config()
    p = cfg.get(profile_id, {}).get("chrome_profile_path")
    if p:
        path_obj = Path(p)
        if not path_obj.is_absolute():
            path_obj = BASE_DIR / path_obj
        if path_obj.exists():
            return str(path_obj)
    # Fallback predefinito alla cartella salvata per id
    fallback_dir = UPLOAD_PROFILES_DIR / f"profile_{profile_id}"
    if fallback_dir.exists():
        return str(fallback_dir)
    return str(BASE_DIR / "chrome_profile")

def _current_pid():
    return session.get("user_profile_id")

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
    else:
        fallback_dir = UPLOAD_PROFILES_DIR / f"profile_{pid}"
        if fallback_dir.exists() and any(fallback_dir.iterdir()):
            has_folder = True
            saved_path = str(fallback_dir.relative_to(BASE_DIR))

    return render_template(
        "script.html",
        profile_name=pname,
        chrome_profile_set=has_folder,
        chrome_profile_path=saved_path or "Nessun profilo caricato"
    )

@app.route("/logout")
def logout_action():
    session.clear()
    return redirect("/login")

# API PER UPLOAD ZIP DEL CHROME PROFILE CON AUTO-PUSH SU GITHUB
@app.route("/api/upload-profile-zip", methods=["POST"])
def upload_profile_zip():
    if "user_profile_id" not in session:
        return jsonify({"ok": False, "error": "Non autenticato"}), 401

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Nessun file inviato"}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename or not uploaded_file.filename.lower().endswith(".zip"):
        return jsonify({"ok": False, "error": "Formato non supportato. Seleziona un file .zip"}), 400

    pid = session["user_profile_id"]
    profile_dest = UPLOAD_PROFILES_DIR / f"profile_{pid}"

    if profile_dest.exists():
        try:
            shutil.rmtree(profile_dest)
        except Exception:
            pass
    profile_dest.mkdir(parents=True, exist_ok=True)

    zip_path = profile_dest / "temp_profile.zip"
    uploaded_file.save(str(zip_path))

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(profile_dest)
        zip_path.unlink(missing_ok=True)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Errore durante l'estrazione dello zip: {e}"}), 500

    subdirs = [p for p in profile_dest.iterdir() if p.is_dir()]
    final_dir = profile_dest
    if len(subdirs) == 1 and not any(p.is_file() for p in profile_dest.iterdir()):
        final_dir = subdirs[0]

    rel_profile_str = str(final_dir.relative_to(BASE_DIR))
    cfg = load_profiles_config()
    if pid not in cfg:
        cfg[pid] = {}
    cfg[pid]["chrome_profile_path"] = rel_profile_str
    save_profiles_config(cfg)

    # SINCRONIZZA AUTOMATICAMENTE SU GITHUB PERMANENTEMENTE
    git_ok, git_msg = sync_to_github(f"persist: aggiorna chrome_profile per {pid}")

    return jsonify({
        "ok": True,
        "profile": session.get("user_profile_name", pid),
        "chrome_profile_path": rel_profile_str,
        "github_sync": git_ok,
        "github_msg": git_msg
    })

@app.route("/api/events", methods=["GET"])
def get_saved_events():
    if "user_profile_id" not in session:
        return jsonify({"error": "Non autenticato"}), 401
    return jsonify(_load(_current_pid()))

@app.route("/api/events/rename", methods=["POST"])
def rename_saved_event():
    if "user_profile_id" not in session:
        return jsonify({"ok": False, "error": "Non autenticato"}), 401
    body = request.get_json() or {}
    comp = body.get("comp")
    index = body.get("index")
    new_name = (body.get("new_name") or "").strip()
    if not comp or index is None or not new_name:
        return jsonify({"ok": False, "error": "Parametri non validi"}), 400
    
    data = _load(_current_pid())
    if comp in data and 0 <= int(index) < len(data[comp]):
        data[comp][int(index)]["name"] = new_name
        _save(data, _current_pid())
        sync_to_github(f"edit: rinomina evento {new_name} ({_current_pid()})")
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Evento non trovato"}), 404

@app.route("/api/events/delete", methods=["POST"])
def delete_saved_event():
    if "user_profile_id" not in session:
        return jsonify({"ok": False, "error": "Non autenticato"}), 401
    body = request.get_json() or {}
    if body.get("all"):
        _save({}, _current_pid())
        sync_to_github(f"edit: cancellati tutti gli eventi ({_current_pid()})")
        return jsonify({"ok": True})
    
    comp = body.get("comp")
    index = body.get("index")
    if not comp or index is None:
        return jsonify({"ok": False, "error": "Parametri mancanti"}), 400
    
    data = _load(_current_pid())
    if comp in data and 0 <= int(index) < len(data[comp]):
        del data[comp][int(index)]
        if not data[comp]:
            del data[comp]
        _save(data, _current_pid())
        sync_to_github(f"edit: rimosso evento da {comp} ({_current_pid()})")
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Evento non trovato"}), 404

@app.route("/api/events/sort", methods=["POST"])
def sort_saved_events():
    if "user_profile_id" not in session:
        return jsonify({"ok": False, "error": "Non autenticato"}), 401
    from dazn_navigator2.cli.eventi_cmds import _iter_entries, _sort_key
    data = _load(_current_pid())
    entries = list(_iter_entries(data))
    if not entries:
        return jsonify({"ok": True})
    
    ordinato = sorted(entries, key=_sort_key)
    nuovo_data = {}
    for _, comp, _, ev_ in ordinato:
        nuovo_data.setdefault(comp, []).append(ev_)
    _save(nuovo_data, _current_pid())
    sync_to_github(f"edit: eventi riordinati per data ({_current_pid()})")
    return jsonify({"ok": True})

@app.route("/api/live", methods=["GET"])
def get_live_events():
    if "user_profile_id" not in session:
        return jsonify({"error": "Non autenticato"}), 401

    async def _fetch():
        explorer = DaznExplorer()
        tiles = await explorer.get_tiles("Live")
        items = [_format_tile_item(t) for t in tiles]
        await explorer.close()
        return items

    try:
        data = run_async(_fetch(), timeout=45)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/vod", methods=["GET"])
def get_vod_events():
    if "user_profile_id" not in session:
        return jsonify({"error": "Non autenticato"}), 401

    async def _fetch():
        explorer = DaznExplorer()
        tiles = await explorer.get_tiles("Catchup")
        items = [_format_tile_item(t) for t in tiles]
        await explorer.close()
        return items

    try:
        data = run_async(_fetch(), timeout=45)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/linear", methods=["GET"])
def get_linear_channels():
    if "user_profile_id" not in session:
        return jsonify({"error": "Non autenticato"}), 401

    async def _fetch():
        explorer = DaznExplorer()
        tiles = await explorer.get_tiles("epg")
        if not tiles:
            tiles = await explorer.get_tiles("LinearChannels")
        items = [_format_tile_item(t) for t in tiles]
        await explorer.close()
        return items

    try:
        data = run_async(_fetch(), timeout=45)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/search", methods=["GET"])
def search_events():
    if "user_profile_id" not in session:
        return jsonify({"error": "Non autenticato"}), 401

    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    async def _fetch():
        explorer = DaznExplorer()
        tiles = await explorer.search(q)
        items = [_format_tile_item(t) for t in tiles]
        await explorer.close()
        return items

    try:
        data = run_async(_fetch(), timeout=45)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/diagnose")
def diagnose():
    import time as _time
    now = _time.time()
    from dazn_navigator2.services.extractor import PROXY_WORKER, _CACHED_SERVICES
    results = {
        "_proxy_worker": PROXY_WORKER,
        "_playback_endpoint": _CACHED_SERVICES.get("Playback", ""),
    }
    for pid in PROFILES:
        profile_dir = Path(get_active_chrome_profile(pid))
        auth_file = profile_dir / "auth_token.json"
        info = {"profile_dir": str(profile_dir), "auth_file_exists": auth_file.exists()}
        if auth_file.exists():
            try:
                data = json.loads(auth_file.read_text(encoding="utf-8"))
                tok = data.get("jwt", "")
                ext = HeadlessExtractor.__new__(HeadlessExtractor)
                pl = ext._decode_jwt_payload(tok) if tok.startswith("eyJ") else None
                if pl:
                    remaining = int(pl.get("exp", 0) - now)
                    info["country"] = pl.get("country")
                    info["exp"] = pl.get("exp")
                    info["remaining_seconds"] = remaining
                    info["valid_it"] = pl.get("country") == "it" and remaining > 0
                    info["device_id"] = (pl.get("deviceId") or "")[:40]
                else:
                    info["token_parse_error"] = True
            except Exception as e:
                info["error"] = str(e)
        results[pid] = info
    return jsonify(results)

@app.route("/api/extract", methods=["POST"])
def extract_stream():
    if "user_profile_id" not in session:
        return jsonify({"ok": False, "error": "Non autenticato"}), 401

    pid = session["user_profile_id"]
    body = request.get_json() or {}
    asset_id = body.get("asset_id") or body.get("id")
    title = body.get("title", "Evento")
    image = body.get("image", "")
    competition = (body.get("competition") or "").strip()
    start = body.get("start") or ""
    end = body.get("end") or ""

    if not asset_id:
        return jsonify({"ok": False, "error": "asset_id mancante"}), 400

    target_profile_dir = get_active_chrome_profile(pid)

    async def _do_extract():
        nonlocal competition, start, end
        # Fallback metadata se start/end/competition non passati
        if not start or not end or not competition or competition in ("Eventi Live", "Eventi"):
            try:
                from dazn_navigator2.services.extractor import _get_http_session
                client = await _get_http_session()
                ci_url = f"https://contentitem.discovery.indazn.com/eu/v1/contentitem?Id={asset_id}"
                r_ci = await client.get(ci_url, timeout=4)
                if r_ci.status_code == 200:
                    ci_data = r_ci.json()
                    item = ci_data.get("ContentItem") or ci_data.get("Event") or ci_data
                    if not start:
                        start = item.get("Start") or ""
                    if not end:
                        end = item.get("End") or ""
                    if not competition or competition in ("Eventi Live", "Eventi"):
                        c = item.get("Competition")
                        if isinstance(c, dict):
                            competition = c.get("Title") or competition
                        elif c:
                            competition = str(c)
            except Exception:
                pass

        if not competition:
            competition = "Eventi"

        ext = HeadlessExtractor()
        res = await ext.estrai(target_profile_dir, asset_id, title)
        if res.get("ok"):
            mpd_url = res.get("mpd_url", "")
            dazn_token = res.get("dazn_token", "")
            mpd_auth = _build_mpd_auth(mpd_url, dazn_token)
            keys_str = ",".join(res.get("keys", []))
            ua_str = res.get("ua", "")
            logo = image or _image_url(res.get("image"))

            entry = {
                "name": res.get("titolo", title),
                "image": logo,
                "start": start,
                "end": end,
                "mpd": mpd_auth,
                "key": keys_str,
                "ua": ua_str,
                # Campi per retrocompatibilità Kodi / m3u / estensione
                "manifest": mpd_auth,
                "keys": keys_str,
                "logo": logo,
                "license_url": res.get("la_url", ""),
                "ext_url": res.get("ext_url", ""),
                "kodi_url": res.get("kodi_url", "")
            }
            add_event(competition, entry, _current_pid())
            sync_to_github(f"extract: salvato evento {title} ({_current_pid()})")
            res["mpd_url"] = mpd_auth
            res["mpd_auth"] = mpd_auth
            res["entry"] = entry
            res["competition"] = competition
        return res

    try:
        result = run_async(_do_extract(), timeout=90)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/playlist.m3u", methods=["GET"])
def generate_m3u():
    data = _load(_current_pid())
    lines = ["#EXTM3U"]
    for comp, items in data.items():
        for ev in items:
            name = ev.get("name", "Evento")
            logo = ev.get("logo") or ev.get("image", "")
            mpd = ev.get("mpd") or ev.get("manifest", "")
            keys = ev.get("key") or ev.get("keys", "")
            
            props = f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" group-title="{comp}",{name}'
            if keys:
                lines.append(f'#KODIPROP:inputstream.adaptive.license_key={keys}')
            lines.append(props)
            lines.append(mpd)
    
    return Response("\n".join(lines), mimetype="audio/x-mpegurl")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
