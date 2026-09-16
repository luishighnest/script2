"""Estrazione headless: riusa il browser attivo, chiama Playback API, estrae chiavi DRM."""

import sys, json, re, asyncio, subprocess, base64, os, uuid as _uuid

from pathlib import Path

from playwright.async_api import async_playwright
from rich.console import Console

console = Console()



WIDEVINE_SID = bytes.fromhex("edef8ba979d64acea3c827dcd51d21ed")

CDP_PORT = 9222



# Preferisce il .wvd incluso nel progetto, poi cerca nel percorso corrente o desktop utente
_WVD_LOCAL = Path(__file__).resolve().parent.parent.parent / "device.wvd"
WVD_PATH = str(_WVD_LOCAL) if _WVD_LOCAL.exists() else None

if not WVD_PATH:
    user_desktop = Path.home() / "Desktop"
    search_roots = [Path.cwd(), _WVD_LOCAL.parent]
    if user_desktop.exists():
        search_roots.append(user_desktop)
    for scan_path in search_roots:
        if not scan_path.exists():
            continue
        for root, dirs, files in os.walk(scan_path):
            for f in files:
                if f.lower().endswith(".wvd"):
                    WVD_PATH = os.path.join(root, f)
                    break
            if WVD_PATH:
                break
        if WVD_PATH:
            break



DEVICE_ID_FILE = Path(__file__).resolve().parent.parent.parent / "chrome_profile" / "device_id.txt"





# Sessione HTTP globale persistente con connection pooling
_GLOBAL_SESSION = None
_CACHED_SERVICES = {}
_CACHED_CDM = None

async def _get_http_session():
    global _GLOBAL_SESSION
    if _GLOBAL_SESSION is None:
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

    async def _get_page_and_jwt(self):
        """Recupera il page object e JWT dal BrowserManager già attivo."""
        import base64 as _b64
        from dazn_navigator2.services.browser import get_browser
        b = await get_browser()
        jwt = await b.evaluate("localStorage.getItem('MISL.authToken')")
        if not jwt or not jwt.startswith("eyJ"):
            await b.ensure_session()
            jwt = await b.evaluate("localStorage.getItem('MISL.authToken')")
        if not jwt or not jwt.startswith("eyJ"):
            raise RuntimeError("JWT non trovato nel browser attivo.")

        # Estrae il deviceId direttamente dal payload JWT (sempre coincide con quello DAZN)
        try:
            parts = jwt.split(".")
            pad = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(_b64.b64decode(pad))
            did_jwt = payload.get("deviceId", "")
            if did_jwt:
                self._real_device_id = did_jwt
        except Exception:
            pass

        # Fallback: prova localStorage se il JWT non contiene deviceId
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
            
            # Se la risposta HTTP dà errore, fallback rapido su page.evaluate
            if page:
                try:
                    js_code = """
                    async ({url, method, headers, body}) => {
                        const opts = { method: method, headers: headers };
                        if (body !== null) opts.body = JSON.stringify(body);
                        const resp = await fetch(url, opts);
                        const text = await resp.text();
                        return {ok: resp.ok, status: resp.status, body: text, type: resp.headers.get("content-type") || "", fallback: true};
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
                        const opts = { method: method, headers: headers };
                        if (body !== null) opts.body = JSON.stringify(body);
                        const resp = await fetch(url, opts);
                        const text = await resp.text();
                        return {ok: resp.ok, status: resp.status, body: text, type: resp.headers.get("content-type") || "", fallback: true};
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
        page, jwt = await self._get_page_and_jwt()
        console.print(f"[dim]  → 1. Get JWT: {time.time() - _t:.2f}s[/dim]")

        # Startup API (chiamata solo se non già in cache)
        if not _CACHED_SERVICES.get("Playback"):
            _t = time.time()
            startup_url = "https://startup.core.indazn.com/misl/v5/Startup"
            startup_body = {"LandingPageKey":"", "Languages":"it", "Platform": getattr(self, "_test_platform", "web"), "Manufacturer":"", "PromoCode":""}
            startup_r = await self._chiama_api(startup_url, jwt, method="POST", body_obj=startup_body, page=page)
            console.print(f"[dim]  → 2. Startup API: {time.time() - _t:.2f}s[/dim]")
            
            if not startup_r.get("ok"):
                self.result["error"] = f"Startup API fallita: {startup_r.get('status','?')}"
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

        # Playback API
        _t = time.time()
        qs = f"AssetId={asset_id}&PlayerId=test&DrmType=WIDEVINE&Platform=web&Format=MPEG-DASH&LanguageCode=it&Model=N/A&Secure=true&Manufacturer=Web&PlayReadyInitiator=false&MtaLanguageCode=it&AppVersion=9.41.0-hotfix.1.645&capabilities=mta"
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
            page, jwt = await self._get_page_and_jwt()
            # Se cache svuotata (403), richiama Startup per endpoint fresco
            if not _CACHED_SERVICES.get("Playback"):
                startup_url = "https://startup.core.indazn.com/misl/v5/Startup"
                startup_body = {"LandingPageKey": "", "Languages": "it", "Platform": getattr(self, "_test_platform", "web"), "Manufacturer": "", "PromoCode": ""}
                startup_r2 = await self._chiama_api(startup_url, jwt, method="POST", body_obj=startup_body, page=page)
                if startup_r2.get("ok"):
                    sd2 = json.loads(startup_r2["body"]).get("ServiceDictionary", {})
                    ver2 = json.loads(startup_r2["body"]).get("Version", "v3")
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

        console.print(f"[dim]  → 3. Playback API: {time.time() - _t:.2f}s[/dim]")

        if not pb_r.get("ok"):
            self.result["error"] = f"Playback API: {pb_r.get('status','?')}"
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

        if engine == "headless" and page:
            mpd_r = await page.evaluate(
                """({url, headers}) =>
                    fetch(url, {headers})
                        .then(async r => ({ok: r.ok, status: r.status, body: await r.text()}))
                        .catch(e => ({ok: false, error: e.message}))
                """,
                {"url": fetch_mpd_url, "headers": {"dazn-token": dazn_token, "user-agent": ua, "referer": "https://www.dazn.com/"}}
            )
        else:
            mpd_r = await self._chiama_api(fetch_mpd_url, jwt, method="GET", page=page, cdn_token=dazn_token)
        console.print(f"[dim]  → 4. Fetch MPD: {time.time() - _t:.2f}s[/dim]")

        if not mpd_r.get("ok"):
            self.result["error"] = f"Fetch MPD: {mpd_r.get('status','?')}"
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
            "content-type": "application/octet-stream", "origin": "https://www.dazn.com",
            "referer": "https://www.dazn.com/", "user-agent": ua,
            "x-brand": "DAZN", "x-daznid": dev_id, "x-correlation-id": str(_uuid.uuid4()),
        }
        console.print(f"[dim]  → 5. PSSH + Challenge CDM: {time.time() - _t:.2f}s[/dim]")

        _t = time.time()
        # License request diretta e ultra-veloce
        if engine == "headless" and page:
            fixture_url = f"https://www.dazn.com/it-IT/fixture/{asset_id}"
            try:
                await page.goto(fixture_url, wait_until="commit", timeout=5000)
            except Exception:
                pass

            lr = await page.evaluate(
                """({url, headers, body}) =>
                    fetch(url, {method:"POST", headers, body: new Uint8Array(body)})
                        .then(async r => ({ok: r.ok, status: r.status, body: btoa(String.fromCharCode(...new Uint8Array(await r.arrayBuffer())))}))
                        .catch(e => ({ok: false, error: e.message}))
                """,
                {"url": la_url, "headers": lic_hdrs, "body": list(chal)}
            )

            if not lr.get("ok"):
                self.result["error"] = f"Licenza: {lr.get('status','?')}"
                cdm.close(sess)
                return self.result

            cdm.parse_license(sess, base64.b64decode(lr["body"]))
            keys = [f"{k.kid.hex}:{k.key.hex()}" for k in cdm.get_keys(sess) if k.type == "CONTENT"]
            cdm.close(sess)
        else:
            # MODALITA' VELOCE (curl_cffi / Direct HTTP)
            client = await _get_http_session()
            try:
                lic_resp = await client.post(la_url, headers=lic_hdrs, data=chal, timeout=10)
                if lic_resp.status_code == 200:
                    lr = {"ok": True, "body": lic_resp.content}
                else:
                    lr = {"ok": False, "status": lic_resp.status_code}
            except Exception as e:
                lr = {"ok": False, "error": str(e)}

            if not lr.get("ok"):
                # Fallback immediato nel browser se Direct HTTP riceve 403/errore
                if page:
                    try:
                        lr_fb = await page.evaluate(
                            """({url, headers, body}) =>
                                fetch(url, {method:"POST", headers, body: new Uint8Array(body)})
                                    .then(async r => ({ok: r.ok, status: r.status, body: btoa(String.fromCharCode(...new Uint8Array(await r.arrayBuffer())))}))
                                    .catch(e => ({ok: false, error: e.message}))
                            """,
                            {"url": la_url, "headers": lic_hdrs, "body": list(chal)}
                        )
                        if lr_fb and lr_fb.get("ok"):
                            lr = {"ok": True, "body": base64.b64decode(lr_fb["body"])}
                    except Exception:
                        pass

            if not lr.get("ok"):
                self.result["error"] = f"Licenza: {lr.get('status','?')} - {lr.get('error', '')}"
                cdm.close(sess)
                return self.result

            cdm.parse_license(sess, lr["body"])
            keys = [f"{k.kid.hex}:{k.key.hex()}" for k in cdm.get_keys(sess) if k.type == "CONTENT"]
            cdm.close(sess)
        console.print(f"[dim]  → 6. Licenza DRM: {time.time() - _t:.2f}s[/dim]")

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







