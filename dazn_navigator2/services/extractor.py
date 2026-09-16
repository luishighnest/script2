"""Estrazione headless: riusa il browser attivo, chiama Playback API, estrae chiavi DRM."""

import sys, json, re, asyncio, subprocess, base64, os, uuid as _uuid

from pathlib import Path

from playwright.async_api import async_playwright
from rich.console import Console

console = Console(safe_box=True, highlight=False)



WIDEVINE_SID = bytes.fromhex("edef8ba979d64acea3c827dcd51d21ed")

CDP_PORT = 9222



# Preferisce il .wvd incluso nel progetto, poi cerca sul desktop e path noti

_WVD_LOCAL = Path(__file__).resolve().parent.parent.parent / "device.wvd"

WVD_PATH = str(_WVD_LOCAL) if _WVD_LOCAL.exists() else None

for scan_path in ([] if WVD_PATH else [r"./", r"C:\Users\user\Desktop\l3-keys-main\l3-keys-main", r"C:\Users\user\Desktop\2225908683", r"C:\Users\user\Desktop"]):

    for root, dirs, files in os.walk(scan_path):

        for f in files:

            if f.lower().endswith(".wvd"):

                WVD_PATH = os.path.join(root, f)

                break

        if WVD_PATH: break

    if WVD_PATH: break



DEVICE_ID_FILE = Path(__file__).resolve().parent.parent.parent / "chrome_profile" / "device_id.txt"





# Sessione HTTP globale persistente con connection pooling
_GLOBAL_SESSION = None
_CACHED_SERVICES = {}
_CACHED_CDM = None

async def _get_http_session():
    global _GLOBAL_SESSION
    try:
        cur_loop = asyncio.get_running_loop()
    except RuntimeError:
        cur_loop = None
    sess_loop = getattr(_GLOBAL_SESSION, "_loop", None)
    if _GLOBAL_SESSION is None or (cur_loop is not None and sess_loop is not None and sess_loop != cur_loop):
        from curl_cffi.requests import AsyncSession
        _GLOBAL_SESSION = AsyncSession(impersonate="chrome131")
    return _GLOBAL_SESSION

class HeadlessExtractor:

    def __init__(self):
        self.result = {}

    def _device_id(self):
        if DEVICE_ID_FILE.exists():
            return DEVICE_ID_FILE.read_text().strip()
        did = _uuid.uuid4().hex
        DEVICE_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEVICE_ID_FILE.write_text(did)
        return did

    def _read_jwt_from_disk(self, profile_dir: Path) -> str:
        if not profile_dir or not Path(profile_dir).exists():
            return ""
        import re, time, base64 as _b64
        p = Path(profile_dir)
        leveldb_dirs = [
            p / "Default" / "Local Storage" / "leveldb",
            p / "Local Storage" / "leveldb",
            p / "leveldb"
        ]
        candidates = []
        for ldir in leveldb_dirs:
            if ldir.exists():
                for f in sorted(list(ldir.glob("*.ldb")) + list(ldir.glob("*.log")), key=lambda x: x.stat().st_mtime, reverse=True):
                    try:
                        data = f.read_bytes()
                        if b"MISL.authToken" in data:
                            tokens = re.findall(rb'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', data)
                            for tok_b in tokens:
                                tok = tok_b.decode('ascii', errors='ignore')
                                try:
                                    parts = tok.split('.')
                                    pad = parts[1] + '=' * (-len(parts[1]) % 4)
                                    payload = json.loads(_b64.b64decode(pad))
                                    exp = payload.get('exp', 0)
                                    candidates.append((exp, tok))
                                except Exception:
                                    pass
                    except Exception:
                        pass
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            # Ritorna il token con scadenza più recente
            return candidates[0][1]
        return ""

    async def _get_page_and_jwt(self, profile_dir=None):
        """Recupera il page object e JWT dal BrowserManager o direttamente dal profilo."""
        import base64 as _b64
        from dazn_navigator2.services.browser import get_browser, set_active_profile_dir
        if profile_dir:
            set_active_profile_dir(Path(profile_dir))

        b = await get_browser()
        jwt = await b.evaluate("localStorage.getItem('MISL.authToken')")
        if not jwt or not jwt.startswith("eyJ"):
            await b.ensure_session()
            jwt = await b.evaluate("localStorage.getItem('MISL.authToken')")

        # Fallback se evaluate non trova il token nel DOM (es. document SecurityError)
        if not jwt or not jwt.startswith("eyJ"):
            jwt = self._read_jwt_from_disk(profile_dir)

        if not jwt or not jwt.startswith("eyJ"):
            raise RuntimeError("JWT non trovato nel profilo DAZN. Assicurati che l'account sia loggato nel profilo.")

        try:
            parts = jwt.split(".")
            pad = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(_b64.b64decode(pad))
            did_jwt = payload.get("deviceId", "")
            if did_jwt:
                self._real_device_id = did_jwt
        except Exception:
            pass

        if not getattr(self, "_real_device_id", None):
            try:
                stored_did = await b.evaluate("localStorage.getItem('MISL.deviceId') || localStorage.getItem('dazn.deviceId')")
                if stored_did:
                    self._real_device_id = stored_did
            except Exception:
                pass

        return b.page, jwt

    async def _chiama_api(self, url, jwt, method="GET", body_obj=None, page=None, cdn_token=None):
        import json
        from dazn_navigator2.settings import get_setting
        engine = get_setting("extraction_engine")
        
        dev_id = getattr(self, "_real_device_id", None) or self._device_id()

        headers = {
            "authorization": f"Bearer {jwt}",
            "x-dazn-device": dev_id,
            "content-type": "application/json",
            "accept": "*/*",
            "origin": "https://www.dazn.com",
            "referer": "https://www.dazn.com/",
        }
        if cdn_token:
            headers["dazn-token"] = cdn_token
        
        # Se l'utente ha scelto la modalità Headless puro
        if engine == "headless" and page:
            try:
                body_str = json.dumps(body_obj) if body_obj else "null"
                headers_str = json.dumps(headers)
                js_code = f"""
                async () => {{
                    const opts = {{ method: "{method}", headers: {headers_str} }};
                    if ({body_str} !== null) opts.body = JSON.stringify({body_str});
                    const resp = await fetch("{url}", opts);
                    if (!resp.ok) return {{ok: false, status: resp.status}};
                    const text = await resp.text();
                    return {{ok: true, status: resp.status, body: text, type: resp.headers.get("content-type") || "", fallback: true}};
                }}
                """
                res = await page.evaluate(js_code)
                if res.get("ok"):
                    return res
            except Exception:
                pass

        # Modalità Veloce (curl_cffi con Sessione persistente)
        try:
            from curl_cffi.requests import AsyncSession
            client = await _get_http_session()
            if method == "POST":
                resp = await client.post(url, headers=headers, json=body_obj, timeout=10)
            else:
                resp = await client.get(url, headers=headers, timeout=10)
            
            if resp.status_code < 400:
                return {"ok": True, "status": resp.status_code, "body": resp.text, "type": resp.headers.get("content-type", ""), "fallback": False}
            
            # Se la risposta HTTP dà errore, fallback su page.evaluate nativo dal browser
            if page:
                try:
                    js_code = """
                    async ({url, method, headers, body}) => {
                        try {
                            const clean_headers = {...headers};
                            delete clean_headers['origin'];
                            delete clean_headers['referer'];
                            delete clean_headers['user-agent'];
                            const opts = { method: method, headers: clean_headers };
                            if (body !== null) opts.body = JSON.stringify(body);
                            const resp = await fetch(url, opts);
                            const text = await resp.text();
                            return {ok: resp.ok, status: resp.status, body: text, type: resp.headers.get("content-type") || "", fallback: true};
                        } catch(e) {
                            return {ok: false, error: e.name + ': ' + e.message};
                        }
                    }
                    """
                    res = await page.evaluate(js_code, {"url": url, "method": method, "headers": headers, "body": body_obj})
                    if res and res.get("ok"):
                        return res
                except Exception:
                    pass
            return {"ok": False, "status": resp.status_code, "body": resp.text}
        except Exception as e:
            if page:
                try:
                    js_code = """
                    async ({url, method, headers, body}) => {
                        try {
                            const clean_headers = {...headers};
                            delete clean_headers['origin'];
                            delete clean_headers['referer'];
                            delete clean_headers['user-agent'];
                            const opts = { method: method, headers: clean_headers };
                            if (body !== null) opts.body = JSON.stringify(body);
                            const resp = await fetch(url, opts);
                            const text = await resp.text();
                            return {ok: resp.ok, status: resp.status, body: text, type: resp.headers.get("content-type") || "", fallback: true};
                        } catch(e) {
                            return {ok: false, error: e.name + ': ' + e.message};
                        }
                    }
                    """
                    res = await page.evaluate(js_code, {"url": url, "method": method, "headers": headers, "body": body_obj})
                    if res and res.get("ok"):
                        return res
                except Exception as ex:
                    return {"ok": False, "error": str(ex)}
            return {"ok": False, "error": str(e)}

    async def estrai(self, profile_dir, asset_id, titolo="") -> dict:
        """Estrae MPD, PSSH, licenza e chiavi in modo istantaneo."""
        global _CACHED_SERVICES, _CACHED_CDM
        self.result = {"ok": False, "mpd_url": None, "pssh": None, "keys": None, "ext_url": None, "error": None}

        if not WVD_PATH:
            self.result["error"] = "File .wvd non trovato."
            return self.result

        import time
        _t = time.time()
        page, jwt = await self._get_page_and_jwt(profile_dir)
        console.print(f"[dim]  -> 1. Get JWT: {time.time() - _t:.2f}s[/dim]")

        # Startup API (chiamata solo se non già in cache)
        if not _CACHED_SERVICES.get("Playback"):
            _t = time.time()
            startup_url = "https://startup.core.indazn.com/misl/v5/Startup"
            startup_body = {"LandingPageKey":"", "Languages":"it", "Platform": getattr(self, "_test_platform", "web"), "Manufacturer":"", "PromoCode":"", "CountryCode":"it"}
            startup_r = await self._chiama_api(startup_url, jwt, method="POST", body_obj=startup_body, page=page)
            console.print(f"[dim]  -> 2. Startup API: {time.time() - _t:.2f}s[/dim]")
            
            if not startup_r.get("ok"):
                err_sd = startup_r.get("error") or startup_r.get("body") or f"HTTP {startup_r.get('status', 'sconosciuto')}"
                self.result["error"] = f"Startup API fallita: {err_sd}"
                return self.result

            sd = json.loads(startup_r["body"]).get("ServiceDictionary", {})
            ver = json.loads(startup_r["body"]).get("Version", "v3")

            def _svc(key):
                entry = sd.get(key, {})
                if isinstance(entry, str):
                    return entry.replace("{version}", ver)
                if isinstance(entry, dict):
                    for v in sorted(entry.get("Versions", {}), key=lambda x: int(x[1:]) if x[1:].isdigit() else 0, reverse=True):
                        sp = entry["Versions"][v].get("ServicePath", "")
                        if sp: return sp
                return ""

            _CACHED_SERVICES = {k: _svc(k) for k in ("Rails","Rail","Playback","Epg","GetCompetitionsForEpg","Search","ContentItem","Event")}

        playback_svc = _CACHED_SERVICES.get("Playback")
        if not playback_svc:
            playback_svc = "https://api.playback.indazn.com/v5/Playback"

        # Playback API (country e countryCode impostati esplicitamente a 'it')
        _t = time.time()
        qs = f"AssetId={asset_id}&PlayerId=test&DrmType=WIDEVINE&Platform=web&Format=MPEG-DASH&LanguageCode=it&country=it&CountryCode=it&Model=N/A&Secure=true&Manufacturer=Web&PlayReadyInitiator=false&MtaLanguageCode=it&AppVersion=9.42.0&capabilities=mta"
        pb_url = f"{playback_svc}?{qs}"

        pb_r = await self._chiama_api(pb_url, jwt, page=page)

        # Se riceve 401 o 403: rigenera JWT e/o invalida cache endpoint e riprova
        if not pb_r.get("ok") and pb_r.get("status") in (401, 403):
            from dazn_navigator2.services.browser import get_browser
            b = await get_browser()
            # 403 può indicare anche endpoint cambiato: svuota cache e richiama Startup
            if pb_r.get("status") == 403:
                _CACHED_SERVICES.clear()
            try:
                await b.page.goto("https://www.dazn.com/it-IT/home", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
            except Exception:
                pass
            page, jwt = await self._get_page_and_jwt(profile_dir)
            # Se cache svuotata (403), richiama Startup per endpoint fresco
            if not _CACHED_SERVICES.get("Playback"):
                startup_url = "https://startup.core.indazn.com/misl/v5/Startup"
                startup_body = {"LandingPageKey":"", "Languages":"it", "Platform": getattr(self, "_test_platform", "web"), "Manufacturer":"Web", "PromoCode":""}
                startup_r = await self._chiama_api(startup_url, jwt, method="POST", body_obj=startup_body, page=page)
                if startup_r.get("ok"):
                    sd2 = json.loads(startup_r["body"]).get("ServiceDictionary", {})
                    ver2 = json.loads(startup_r["body"]).get("Version", "v3")
                    def _svc2(key):
                        entry = sd2.get(key, {})
                        if isinstance(entry, str):
                            return entry.replace("{version}", ver2)
                        if isinstance(entry, dict):
                            for v in sorted(entry.get("Versions", {}), key=lambda x: int(x[1:]) if x[1:].isdigit() else 0, reverse=True):
                                sp = entry["Versions"][v].get("ServicePath", "")
                                if sp: return sp
                        return ""
                    _CACHED_SERVICES.update({k: _svc2(k) for k in ("Rails", "Rail", "Playback", "Epg", "GetCompetitionsForEpg", "Search", "ContentItem", "Event")})
                    playback_svc = _CACHED_SERVICES.get("Playback") or "https://api.playback.indazn.com/v5/Playback"
                    pb_url = f"{playback_svc}?{qs}"
            pb_r = await self._chiama_api(pb_url, jwt, page=page)

        console.print(f"[dim]  -> 3. Playback API: {time.time() - _t:.2f}s[/dim]")

        if not pb_r.get("ok"):
            err_detail = pb_r.get("error") or pb_r.get("body") or f"HTTP {pb_r.get('status', 'sconosciuto')}"
            try:
                err_json = json.loads(pb_r.get("body", "{}"))
                odata = err_json.get("odata.error", {})
                code = odata.get("code")
                msg = odata.get("message", {}).get("value", "")
                if code == 10803 or "Eligibility" in msg:
                    err_detail = "Contenuto non incluso nel tuo abbonamento o evento terminato (Eligibility not allowed)."
                elif msg:
                    err_detail = f"{msg} (Codice: {code})"
            except Exception:
                pass
            self.result["error"] = f"Playback API: {err_detail}"
            return self.result

        pb = json.loads(pb_r["body"])
        pbd = pb.get("PlaybackDetails") or []
        if not pbd:
            self.result["error"] = "Nessun PlaybackDetails nella risposta."
            return self.result

        det = pbd[0]
        mpd_url_original = det.get("ManifestUrl", "")
        la_url = det.get("LaUrl", "")
        cdn_tok = det.get("CdnToken", {})
        cdn_name = cdn_tok.get("Name", "") if cdn_tok else ""
        cdn_value = cdn_tok.get("Value", "") if cdn_tok else ""

        if not mpd_url_original or not la_url:
            self.result["error"] = "MPD o License URL mancanti."
            return self.result

        self.result["mpd_url"] = mpd_url_original
        
        from dazn_navigator2.settings import get_setting
        engine = get_setting("extraction_engine")

        if engine == "headless" and page:
            ua = await page.evaluate("navigator.userAgent")
        else:
            # Recupera l'esatto User-Agent usato da curl_cffi per garantire che l'hash 'ua' nel dazn-token coincida
            client = await _get_http_session()
            ua = getattr(client, "_user_agent", None) or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        
        self.result["ua"] = ua
        dazn_token = cdn_value if cdn_value else jwt

        # Fetch MPD (con CdnToken in URL + header)
        _t = time.time()
        fetch_mpd_url = mpd_url_original
        if cdn_value:
            sep = "&" if "?" in fetch_mpd_url else "?"
            fetch_mpd_url = f"{fetch_mpd_url}{sep}{cdn_name}={cdn_value}"

        # Fetch MPD: la CDN DAZN valida il dazn-token confrontando l'User-Agent.
        # Evitiamo header UA incoerenti per evitare Forbidden-680 (401).
        client = await _get_http_session()
        mpd_hdrs = {
            "origin": "https://www.dazn.com",
            "referer": "https://www.dazn.com/",
            "dazn-token": dazn_token,
            "accept": "*/*"
        }
        try:
            r_mpd_resp = await client.get(fetch_mpd_url, headers=mpd_hdrs, timeout=10)
            if r_mpd_resp.status_code == 200:
                mpd_r = {"ok": True, "status": 200, "body": r_mpd_resp.text}
            else:
                # Fallback via browser
                if page:
                    mpd_r = await page.evaluate(
                        """async ({url, token}) => {
                            try {
                                const r = await fetch(url, { headers: { "dazn-token": token } });
                                return { ok: r.ok, status: r.status, body: await r.text() };
                            } catch(e) { return { ok: false, error: e.message }; }
                        }""",
                        {"url": fetch_mpd_url, "token": dazn_token}
                    )
                else:
                    mpd_r = {"ok": False, "status": r_mpd_resp.status_code, "body": r_mpd_resp.text}
        except Exception as e:
            mpd_r = {"ok": False, "error": str(e)}

        console.print(f"[dim]  -> 4. Fetch MPD: {time.time() - _t:.2f}s[/dim]")

        if not mpd_r.get("ok"):
            err_detail = mpd_r.get('body', '') or mpd_r.get('error', '')
            self.result["error"] = f"Fetch MPD: {mpd_r.get('status','?')} - Dettaglio server: {err_detail}"
            console.print(f"[bold red]  [Dettaglio Errore MPD][/bold red] Status: {mpd_r.get('status')} | Risposta Server: {err_detail}")
            return self.result

        _t = time.time()
        import xml.etree.ElementTree as ET
        for el in ET.fromstring(mpd_r["body"]).iter():
            if el.tag.endswith("}pssh"):
                b64 = (el.text or "").strip()
                if b64 and base64.b64decode(b64)[12:28] == WIDEVINE_SID:
                    self.result["pssh"] = b64
                    break

        if not self.result["pssh"]:
            self.result["error"] = "PSSH Widevine non trovato nel MPD."
            return self.result

        from pywidevine import PSSH, Cdm, Device
        if _CACHED_CDM is None:
            _CACHED_CDM = Cdm.from_device(Device.load(WVD_PATH))

        cdm = _CACHED_CDM
        sess = cdm.open()
        chal = cdm.get_license_challenge(sess, PSSH(base64.b64decode(self.result["pssh"])))

        dev_id = getattr(self, "_real_device_id", None) or self._device_id()
        lic_hdrs = {
            "content-type": "application/octet-stream",
            "origin": "https://www.dazn.com",
            "referer": "https://www.dazn.com/",
            "authorization": f"Bearer {jwt}",
            "x-brand": "DAZN",
            "x-daznid": dev_id,
            "x-correlation-id": str(_uuid.uuid4()),
        }
        console.print(f"[dim]  -> 5. PSSH + Challenge CDM: {time.time() - _t:.2f}s[/dim]")

        _t = time.time()
        # License request: usiamo il browser context page con gli header specifici
        js_lic_code = """async ({url, headers, body}) => {
            try {
                const r = await fetch(url, {method:"POST", headers, body: new Uint8Array(body)});
                if (!r.ok) {
                    const txt = await r.text();
                    return {ok: false, status: r.status, statusText: r.statusText, bodyText: txt, headers: Object.fromEntries(r.headers.entries())};
                }
                const buf = await r.arrayBuffer();
                const bytes = new Uint8Array(buf);
                let binary = '';
                for (let i = 0; i < bytes.byteLength; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                return {ok: true, status: r.status, body: btoa(binary)};
            } catch(e) {
                return {ok: false, error: e.name + ': ' + e.message};
            }
        }"""
        lic_hdrs_clean = {
            "content-type": "application/octet-stream",
            "authorization": f"Bearer {jwt}",
            "x-brand": "DAZN",
            "x-daznid": dev_id,
            "x-correlation-id": str(_uuid.uuid4()),
        }

        lr = None
        if page:
            try:
                lr = await page.evaluate(js_lic_code, {"url": la_url, "headers": lic_hdrs_clean, "body": list(chal)})
            except Exception as ex:
                lr = {"ok": False, "error": f"Browser evaluate exception: {ex}"}

        if not lr or not lr.get("ok"):
            # Tentativo con client HTTP curl_cffi
            client = await _get_http_session()
            try:
                lic_resp = await client.post(la_url, headers=lic_hdrs, data=chal, timeout=10)
                if lic_resp.status_code == 200:
                    lr = {"ok": True, "body": base64.b64encode(lic_resp.content).decode("ascii")}
                else:
                    status_err = lic_resp.status_code
                    body_err = lic_resp.text
                    lr = {
                        "ok": False,
                        "status": status_err,
                        "bodyText": body_err,
                        "headers": dict(lic_resp.headers),
                        "browser_res": lr
                    }
            except Exception as e:
                if not lr:
                    lr = {"ok": False, "error": str(e)}

        if not lr or not lr.get("ok"):
            err_msg = f"Licenza: {lr.get('status','?')} - Motivo: {lr.get('statusText', '')} {lr.get('bodyText', '')[:300]} {lr.get('error', '')}".strip()
            self.result["error"] = err_msg
            console.print(f"[bold red]  [Dettaglio Errore Licenza DRM][/bold red]")
            console.print(f"    * Status HTTP: [bold yellow]{lr.get('status')}[/bold yellow]")
            if lr.get("statusText"):
                console.print(f"    * Status Text: {lr.get('statusText')}")
            if lr.get("bodyText"):
                console.print(f"    * Corpo Risposta Server: [dim]{lr.get('bodyText')[:400]}[/dim]")
            if lr.get("error"):
                console.print(f"    * Errore Exception: [red]{lr.get('error')}[/red]")
            if lr.get("headers"):
                server_hdr = lr.get("headers", {}).get("server") or lr.get("headers", {}).get("Server")
                cf_id = lr.get("headers", {}).get("x-amz-cf-id")
                console.print(f"    * Server: {server_hdr} (CF-ID: {cf_id})")
            cdm.close(sess)
            return self.result

        cdm.parse_license(sess, base64.b64decode(lr["body"]))
        keys = [f"{k.kid.hex}:{k.key.hex()}" for k in cdm.get_keys(sess) if k.type == "CONTENT"]
        cdm.close(sess)
        console.print(f"[dim]  -> 6. Licenza DRM: {time.time() - _t:.2f}s[/dim]")

        if not keys:

            self.result["error"] = "Nessuna chiave CONTENT."

            return self.result



        import urllib.parse

        self.result["keys"] = keys

        kid_hex, key_hex = keys[0].split(":")

        ck = urllib.parse.quote(base64.b64encode(json.dumps({kid_hex: key_hex}).encode()).decode())

        hdrs_b64 = urllib.parse.quote(base64.b64encode(json.dumps({

            "user-agent": ua, "referer": "https://www.dazn.com/",

            "origin": "https://www.dazn.com", "dazn-token": dazn_token,

        }).encode()).decode())



        self.result["ext_url"] = (

            "extension://opmeopcambhfimffbomjgemehjkbbmji/pages/player.html#"

            f"{mpd_url_original}&ck={ck}&headers={hdrs_b64}"

        )

        self.result["kodi_url"] = f"{fetch_mpd_url}&ck={ck}&headers={hdrs_b64}"

        self.result["dazn_token"] = dazn_token

        self.result["cdn_name"] = cdn_name

        self.result["ok"] = True

        self.result["titolo"] = titolo



        return self.result







