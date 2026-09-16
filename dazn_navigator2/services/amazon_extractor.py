"""Estrazione eventi Amazon Prime Video: MPD + chiavi Widevine tramite Amazon license server."""

import asyncio
import base64
import json
import re
import uuid as _uuid
from pathlib import Path

from playwright.async_api import async_playwright
from rich.console import Console

console = Console()

WIDEVINE_SID = bytes.fromhex("edef8ba979d64acea3c827dcd51d21ed")

# Usa lo stesso .wvd del progetto DAZN
_WVD_LOCAL = Path(__file__).resolve().parent.parent.parent / "device.wvd"
WVD_PATH = str(_WVD_LOCAL) if _WVD_LOCAL.exists() else None

AMAZON_PROFILE_DIR = Path(__file__).resolve().parent.parent.parent / "amazon_profile"

_AMAZON_CDM = None
_AMAZON_SESSION = None


async def _get_amazon_http_session():
    global _AMAZON_SESSION
    if _AMAZON_SESSION is None:
        from curl_cffi.requests import AsyncSession
        _AMAZON_SESSION = AsyncSession(impersonate="chrome131")
    return _AMAZON_SESSION


class AmazonExtractor:
    """Estrae MPD e chiavi DRM da eventi Amazon Prime Video."""

    def __init__(self):
        self.result = {}
        self._page = None
        self._context = None
        self._playwright = None

    async def _start_browser(self):
        """Avvia il browser con il profilo Amazon salvato."""
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(AMAZON_PROFILE_DIR),
            headless=True,
            channel="msedge",
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

    async def _stop_browser(self):
        if self._playwright:
            await self._playwright.stop()
        self._context = None
        self._page = None
        self._playwright = None

    async def get_amazon_events(self) -> list:
        """
        Naviga su primevideo.com e ritorna la lista di eventi live/sport disponibili.
        Ogni evento è un dict con: title, url, asset_id, image.
        """
        events = []
        try:
            await self._start_browser()
            # Naviga sulla sezione sport/live di Prime Video
            sport_urls = [
                "https://www.primevideo.com/categories/sports",
                "https://www.primevideo.com/live-tv",
                "https://www.primevideo.com",
            ]

            seen_ids = set()
            for sport_url in sport_urls:
                try:
                    await self._page.goto(sport_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(4)

                    # Estrai tutti i link agli eventi/titoli visibili
                    items = await self._page.evaluate("""
                    () => {
                        const results = [];
                        const links = document.querySelectorAll('a[href]');
                        const seen = new Set();
                        links.forEach(a => {
                            const href = a.getAttribute('href') || '';
                            if (!href.includes('/detail/') && !href.includes('/gp/video/') && !href.includes('/region/')) return;
                            
                            let title = a.getAttribute('aria-label') || '';
                            if (!title) {
                                const img = a.querySelector('img');
                                if (img) title = img.getAttribute('alt') || '';
                            }
                            if (!title) {
                                title = a.innerText || '';
                            }
                            title = title.replace(/\\n/g, ' ').trim();
                            if (!title || title.length < 3 || title.toLowerCase().includes('condizioni') || title.toLowerCase().includes('privacy')) return;

                            const m = href.match(/([0-9A-Z]{10,})/);
                            const id = m ? m[1] : href;

                            if (!seen.has(id)) {
                                seen.add(id);
                                let img = '';
                                const imgEl = a.querySelector('img');
                                if (img) img = imgEl.getAttribute('src') || '';
                                results.push({
                                    title: title.substring(0, 100),
                                    asset_id: id,
                                    url: href.startsWith('http') ? href : 'https://www.primevideo.com' + href,
                                    image: img
                                });
                            }
                        });
                        return results;
                    }
                    """)
                    for item in items:
                        if item["asset_id"] not in seen_ids:
                            seen_ids.add(item["asset_id"])
                            events.append(item)
                    if len(events) >= 15:
                        break
                except Exception as e:
                    pass

        except Exception as e:
            console.print(f"[red]Errore browser Amazon: {e}[/red]")
        finally:
            await self._stop_browser()

        return events

    async def _intercept_mpd_and_license(self, page, event_url: str, asset_id: str = "") -> dict:
        """
        Intercetta MPD e Licenza sia tramite chiamate dirette all'API di playback di Amazon
        (GetPlaybackResources) sia navigando e cliccando sul player.
        """
        captured = {"mpd": None, "license_url": None, "license_headers": {}, "aws_session": None}

        # Estrai ASIN dall'URL se non fornito
        asin = asset_id
        if not asin:
            m = re.search(r'([0-9A-Z]{10,})', event_url)
            if m:
                asin = m.group(1)

        async def on_request(request):
            url = request.url
            # Intercetta MPD manifest
            if (".mpd" in url or "manifest" in url) and ("amazon" in url or "pv-cdn" in url or "cloudfront" in url):
                if captured["mpd"] is None:
                    captured["mpd"] = url
                    m = re.search(r'aws\.sessionId=([^&]+)', url)
                    if m:
                        captured["aws_session"] = m.group(1)

            # Intercetta richiesta licenza esatta:
            # Durante la riproduzione il player invia una POST binaria per la licenza Widevine
            if request.method == "POST":
                ct = (request.headers.get("content-type") or "").lower()
                # Se è una chiamata al server licenze o ha content-type binario/drm
                is_lic_url = any(x in url.lower() for x in ("licens", "widevine", "/cdp/", "drm", "key")) and not any(bad in url.lower() for bad in ("usage", "clickstream", "report", "telemetry", "event", "log"))
                if is_lic_url or "octet-stream" in ct:
                    if captured["license_url"] is None and not any(bad in url.lower() for bad in ("usage", "clickstream", "report", "telemetry", "event")):
                        captured["license_url"] = url
                        captured["license_headers"] = dict(request.headers)

        # Hook su EME (Encrypted Media Extensions) nel browser per catturare la licenza
        try:
            await page.add_init_script("""
            (() => {
                window.__widevine_captured = { challenge: null, license: null, lic_url: null, keys: [] };

                // Intercetta generateRequest per catturare la challenge nativa del browser
                if (window.MediaKeySession) {
                    const origGen = MediaKeySession.prototype.generateRequest;
                    MediaKeySession.prototype.generateRequest = function(initDataType, initData) {
                        try {
                            window.__widevine_captured.initData = Array.from(new Uint8Array(initData));
                        } catch(e) {}
                        return origGen.apply(this, arguments);
                    };

                    const origUpdate = MediaKeySession.prototype.update;
                    MediaKeySession.prototype.update = function(response) {
                        try {
                            if (response && response.byteLength > 50) {
                                window.__widevine_captured.license = Array.from(new Uint8Array(response));
                            }
                        } catch(e) {}
                        return origUpdate.apply(this, arguments);
                    };
                }
                
                // Intercetta fetch per identificare la chiamata esatta di licenza e il corpo restituito
                const origFetch = window.fetch;
                window.fetch = async function(...args) {
                    const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
                    const resp = await origFetch.apply(this, args);
                    try {
                        const ct = (resp.headers.get('content-type') || '').toLowerCase();
                        const isLic = (url.includes('widevine') || url.includes('license') || ct.includes('octet-stream'))
                                      && !url.includes('getplaybackresources')
                                      && !url.includes('usage')
                                      && !url.includes('clickstream')
                                      && !url.includes('report')
                                      && !url.includes('log');
                        if (isLic) {
                            const clone = resp.clone();
                            const buf = await clone.arrayBuffer();
                            if (buf && buf.byteLength > 50) {
                                window.__widevine_captured.fetched_bytes = Array.from(new Uint8Array(buf));
                                window.__widevine_captured.lic_url = url;
                            }
                        }
                    } catch(e) {}
                    return resp;
                };
            })();
            """)
        except Exception:
            pass

        page.on("request", on_request)

        try:
            # 1. Naviga all'evento
            await page.goto(event_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(3)

            # 2. Chiamata diretta dall'interno del browser (usa i cookie e token già vivi) all'API di Playback di Amazon
            if asin:
                console.print(f"[dim]  → Interrogazione diretta API Playback Amazon per ASIN: {asin}...[/dim]")
                api_res = await page.evaluate("""
                async (titleId) => {
                    try {
                        const payload = {
                            "deviceType": "AOAGZA014O5RE",
                            "operatingSystemName": "Windows",
                            "operatingSystemVersion": "10.0",
                            "deviceModel": "WebPlayer",
                            "appVersion": "1.0.0",
                            "titleId": titleId,
                            "consumptionType": "Streaming",
                            "desiredResources": ["CatalogMetadata", "PlaybackUrls", "DrmLicense", "PlaybackSettings"],
                            "supportedDrmKeySystems": ["widevine"],
                            "videoMaterialType": "Feature",
                            "deviceProtocol": "HTTPS"
                        };
                        const endpoints = [
                            '/gp/video/api/getPlaybackResources',
                            'https://atv-ps-eu.primevideo.com/cdp/catalog/GetPlaybackResources',
                            'https://atv-ps-eu.amazon.com/cdp/catalog/GetPlaybackResources'
                        ];
                        for (const ep of endpoints) {
                            try {
                                const r = await fetch(ep + '?titleId=' + titleId + '&consumptionType=Streaming&desiredResources=PlaybackUrls,DrmLicense&videoMaterialType=Feature&supportedDrmKeySystems=widevine', {
                                    method: 'GET',
                                    headers: {'Accept': 'application/json'}
                                });
                                if (r.ok) {
                                    const data = await r.json();
                                    return data;
                                }
                            } catch(e) {}
                        }
                    } catch(e) {}
                    return null;
                }
                """, asin)

                if api_res and isinstance(api_res, dict):
                    # Cerca URL manifest e license URL nel risultato
                    urls_info = api_res.get("playbackUrls", {}) or api_res.get("playbackResources", {})
                    manifests = urls_info.get("urlSets", {}) or urls_info.get("audioVideoUrls", {})
                    for k, v in (manifests.items() if isinstance(manifests, dict) else []):
                        if isinstance(v, dict) and "url" in v and ".mpd" in str(v["url"]):
                            captured["mpd"] = v["url"]
                            break

                    # Cerca license URL reale di Amazon per Widevine
                    lic_info = urls_info.get("drmLicenseUrls", {}) or urls_info.get("licenseUrls", {}) or api_res.get("drmLicenseUrls", {})
                    for k, v in (lic_info.items() if isinstance(lic_info, dict) else []):
                        if "widevine" in str(k).lower() and str(v).startswith("http"):
                            captured["license_url"] = str(v)
                            break
                    if not captured["license_url"] and "widevine2LicenseUrl" in urls_info:
                        captured["license_url"] = urls_info["widevine2LicenseUrl"]

            # 3. Avvia SEMPRE il player reale in pagina per far scattare l'hook EME con la licenza decrittata
            console.print("[dim]  → Avvio player in pagina per cattura licenza EME...[/dim]")
            selectors = [
                'a[href*="/playback/"]',
                'a[href*="/watch/"]',
                '[data-testid="play-button"]',
                'button[aria-label*="Guarda"]',
                'button[aria-label*="Play"]',
                'button[aria-label*="Riproduci"]',
                'a[aria-label*="Guarda"]',
                'a[aria-label*="Riproduci"]',
                '.dv-dp-node-playback',
                '.playButton'
            ]
            for s in selectors:
                try:
                    el = await page.query_selector(s)
                    if el:
                        await el.click(force=True)
                        await asyncio.sleep(4)
                        break
                except Exception:
                    pass

            await asyncio.sleep(4)

        except Exception as e:
            console.print(f"[dim]Navigazione: {e}[/dim]")

        return {
            "mpd_url": captured["mpd"],
            "license_url": captured["license_url"],
            "license_headers": captured["license_headers"],
            "aws_session_id": captured["aws_session"],
        }

    async def estrai(self, event_url: str, titolo: str = "", asset_id: str = "") -> dict:
        """
        Estrae MPD, PSSH e chiavi DRM da un evento Amazon Prime Video.
        Apre il browser con il profilo Amazon, intercetta le richieste e ottiene le chiavi.
        """
        global _AMAZON_CDM

        self.result = {
            "ok": False, "mpd_url": None, "pssh": None,
            "keys": None, "ext_url": None, "error": None,
            "titolo": titolo
        }

        if not WVD_PATH:
            self.result["error"] = "File .wvd non trovato."
            return self.result

        if not AMAZON_PROFILE_DIR.exists():
            self.result["error"] = "Profilo Amazon non trovato. Esegui il login Amazon prima."
            return self.result

        asin = asset_id
        if not asin:
            m = re.search(r'([0-9A-Z]{10,})', event_url)
            if m:
                asin = m.group(1)

        import time
        _t = time.time()
        console.print(f"[dim]  → Avvio browser Amazon headless...[/dim]")

        try:
            await self._start_browser()
        except Exception as e:
            self.result["error"] = f"Errore avvio browser Amazon: {e}"
            return self.result

        try:
            # Intercetta MPD e license URL
            console.print(f"[dim]  → Navigazione evento: {titolo}[/dim]")
            captured = await self._intercept_mpd_and_license(self._page, event_url, asset_id=asset_id)

            mpd_url = captured["mpd_url"]
            license_url = captured["license_url"]
            license_headers_base = captured["license_headers"]
            aws_session_id = captured["aws_session_id"]

            if not mpd_url:
                # Fallback: prova a estrarre direttamente dal DOM/JS
                console.print("[dim]  → MPD non intercettato, provo estrazione dal DOM...[/dim]")
                mpd_url = await self._page.evaluate("""
                () => {
                    // Cerca in tutti gli script inline o variabili globali
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const m = s.textContent.match(/["'](https?:[^"']*\\.mpd[^"']*)/);
                        if (m) return m[1];
                    }
                    // Cerca nei performance entries
                    const entries = performance.getEntriesByType('resource');
                    for (const e of entries) {
                        if (e.name.includes('.mpd') || (e.name.includes('manifest') && e.name.includes('amazon'))) {
                            return e.name;
                        }
                    }
                    return null;
                }
                """)

            if not mpd_url:
                self.result["error"] = "MPD URL non trovato. Prova a cliccare play sull'evento nel browser."
                await self._stop_browser()
                return self.result

            self.result["mpd_url"] = mpd_url
            console.print(f"[dim]  → MPD trovato: {time.time() - _t:.2f}s[/dim]")

            # Ottieni il contenuto del MPD
            _t = time.time()
            client = await _get_amazon_http_session()
            mpd_resp = await client.get(mpd_url, timeout=15)
            if mpd_resp.status_code >= 400:
                self.result["error"] = f"Fetch MPD: HTTP {mpd_resp.status_code}"
                await self._stop_browser()
                return self.result

            mpd_content = mpd_resp.text
            console.print(f"[dim]  → Fetch MPD: {time.time() - _t:.2f}s[/dim]")

            # Estrai PSSH Widevine dal MPD
            _t = time.time()
            import xml.etree.ElementTree as ET
            try:
                for el in ET.fromstring(mpd_content).iter():
                    if el.tag.endswith("}pssh"):
                        b64 = (el.text or "").strip()
                        if b64:
                            try:
                                raw = base64.b64decode(b64)
                                if raw[12:28] == WIDEVINE_SID:
                                    self.result["pssh"] = b64
                                    break
                            except Exception:
                                pass
            except Exception as e:
                self.result["error"] = f"Parsing MPD fallito: {e}"
                await self._stop_browser()
                return self.result

            if not self.result["pssh"]:
                self.result["error"] = "PSSH Widevine non trovato nel MPD."
                await self._stop_browser()
                return self.result

            console.print(f"[dim]  → PSSH estratto: {time.time() - _t:.2f}s[/dim]")

            # Costruisci la challenge Widevine
            _t = time.time()
            from pywidevine import PSSH, Cdm, Device
            if _AMAZON_CDM is None:
                _AMAZON_CDM = Cdm.from_device(Device.load(WVD_PATH))
            cdm = _AMAZON_CDM
            sess = cdm.open()
            chal = cdm.get_license_challenge(sess, PSSH(base64.b64decode(self.result["pssh"])))

            # Header licenza Amazon (estratti dall'intercettazione o costruiti)
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            try:
                ua = await self._page.evaluate("navigator.userAgent")
            except Exception:
                pass

            # Prepara gli header Amazon per la licenza
            lic_headers = {
                "content-type": "application/octet-stream",
                "origin": "https://www.primevideo.com",
                "referer": "https://www.primevideo.com/",
                "user-agent": ua,
            }
            # Copia header catturati dall'intercettazione (più accurati)
            for k, v in license_headers_base.items():
                k_low = k.lower()
                if k_low in ("x-amzn-requestid", "x-amzn-request-id", "amzndtid",
                              "amznpn", "amznpv", "x-amz-access-token"):
                    lic_headers[k] = v

            # Aggiungi aws.sessionId se catturato
            if aws_session_id:
                lic_headers["x-amz-session-id"] = aws_session_id

            # Determina il vero License Server Amazon Widevine
            # 1. Se catturato dal player reale
            if captured.get("license_url") and not any(bad in captured["license_url"].lower() for bad in ("usage", "clickstream", "report", "telemetry")):
                license_url = captured["license_url"]
            else:
                # Prime Video Web Player usa l'endpoint con query params di sessione o il proxy relativo
                sess_param = f"&sessionId={aws_session_id}" if aws_session_id else ""
                license_candidates = [
                    f"https://atv-ps-eu.primevideo.com/cdp/widevine/license?asin={asin}&deviceType=AOAGZA014O5RE{sess_param}",
                    f"https://atv-ps-eu.amazon.com/cdp/widevine/license?asin={asin}&deviceType=AOAGZA014O5RE{sess_param}",
                    f"https://atv-ps-eu.primevideo.com/cdp/licence?asin={asin}&deviceType=AOAGZA014O5RE{sess_param}",
                    "https://www.primevideo.com/gp/video/api/getLicense"
                ]
                license_url = license_candidates[0]

            console.print(f"[dim]  → Challenge CDM pronta: {time.time() - _t:.2f}s[/dim]")
            console.print(f"[dim]  → License URL: {license_url}[/dim]")

            # Richiesta licenza tramite browser (più affidabile con i cookie Amazon)
            _t = time.time()
            try:
                lr = await self._page.evaluate(
                    """async ({url, headers, body, asin, sess}) => {
                        const candidates = [
                            url,
                            `/gp/video/api/getLicense`,
                            `https://atv-ps-eu.primevideo.com/cdp/widevine/license?asin=${asin}&deviceType=AOAGZA014O5RE${sess ? '&sessionId=' + sess : ''}`,
                            `https://atv-ps-eu.amazon.com/cdp/widevine/license?asin=${asin}&deviceType=AOAGZA014O5RE${sess ? '&sessionId=' + sess : ''}`
                        ];
                        for (const targetUrl of candidates) {
                            try {
                                const resp = await fetch(targetUrl, {
                                    method: "POST",
                                    headers: headers,
                                    body: new Uint8Array(body)
                                });
                                if (resp.ok) {
                                    const buf = await resp.arrayBuffer();
                                    return {ok: true, status: resp.status, body: btoa(String.fromCharCode(...new Uint8Array(buf)))};
                                }
                            } catch(e) {}
                        }
                        return {ok: false, status: 404};
                    }
                    """,
                    {"url": license_url, "headers": lic_headers, "body": list(chal), "asin": asin, "sess": aws_session_id}
                )
                if not lr.get("ok"):
                    # Controlla se abbiamo intercettato l'endpoint esatto durante il fetch del player
                    lic_url_real = await self._page.evaluate("() => window.__widevine_captured?.lic_url || null")
                    if lic_url_real:
                        console.print(f"[dim cyan]  → Invio challenge CDM direttamente a lic_url catturato: {lic_url_real}[/dim cyan]")
                        lr = await self._page.evaluate(
                            """async ({url, headers, body}) => {
                                try {
                                    const r = await fetch(url, {
                                        method: "POST",
                                        headers: headers,
                                        body: new Uint8Array(body)
                                    });
                                    if (r.ok) {
                                        const buf = await r.arrayBuffer();
                                        return {ok: true, body: btoa(String.fromCharCode(...new Uint8Array(buf)))};
                                    }
                                } catch(e) {}
                                return {ok: false};
                            }""",
                            {"url": lic_url_real, "headers": lic_headers, "body": list(chal)}
                        )

                if lr.get("ok"):
                    lic_data = base64.b64decode(lr["body"])
                    try:
                        # Se è incapsulato in JSON
                        j = json.loads(lic_data.decode('utf-8', errors='ignore'))
                        if isinstance(j, dict):
                            for key in ("widevine2License", "license", "widevine"):
                                val = j.get(key)
                                if isinstance(val, dict) and "license" in val:
                                    lic_data = base64.b64decode(val["license"])
                                    break
                                elif isinstance(val, str):
                                    lic_data = base64.b64decode(val)
                                    break
                    except Exception:
                        pass
                    cdm.parse_license(sess, lic_data)
                    keys = [f"{k.kid.hex}:{k.key.hex()}" for k in cdm.get_keys(sess) if k.type == "CONTENT"]
                    cdm.close(sess)
                    console.print(f"[dim]  → Licenza Amazon (browser): {time.time() - _t:.2f}s[/dim]")
                else:
                    # Controlla se l'hook EME nel player ha catturato una licenza binaria o bytes
                    hooked_lic = await self._page.evaluate("() => window.__widevine_captured?.fetched_bytes || window.__widevine_captured?.license || null")
                    if hooked_lic and len(hooked_lic) > 10:
                        raw_bytes = bytes(hooked_lic)
                        console.print(f"[dim green]  → Licenza estratta dall'hook ({len(raw_bytes)} bytes)[/dim green]")
                        lic_to_parse = raw_bytes
                        try:
                            json_obj = json.loads(raw_bytes.decode('utf-8', errors='ignore'))
                            for key in ("widevine2License", "license", "widevine"):
                                val = json_obj.get(key) if isinstance(json_obj, dict) else None
                                if isinstance(val, dict) and "license" in val:
                                    lic_to_parse = base64.b64decode(val["license"])
                                    break
                                elif isinstance(val, str):
                                    lic_to_parse = base64.b64decode(val)
                                    break
                        except Exception:
                            pass

                        try:
                            cdm.parse_license(sess, lic_to_parse)
                        except Exception:
                            pass

                        all_keys = cdm.get_keys(sess)
                        keys = [f"{k.kid.hex}:{k.key.hex()}" for k in all_keys if getattr(k, 'type', '') == 'CONTENT']
                        if not keys and all_keys:
                            keys = [f"{k.kid.hex}:{k.key.hex()}" for k in all_keys if hasattr(k, 'kid') and hasattr(k, 'key')]
                        cdm.close(sess)
                    else:
                        cdm.close(sess)
                        self.result["error"] = f"Licenza Amazon: endpoint non ha risposto con licenza valida"
                        await self._stop_browser()
                        return self.result
            except Exception as e:
                cdm.close(sess)
                self.result["error"] = f"Errore licenza: {e}"
                await self._stop_browser()
                return self.result

            if not keys:
                self.result["error"] = "Nessuna chiave CONTENT dalla licenza Amazon."
                await self._stop_browser()
                return self.result

            self.result["keys"] = keys
            self.result["ua"] = ua
            self.result["ok"] = True

            # Costruisci ext_url per il player extension
            import urllib.parse
            kid_hex, key_hex = keys[0].split(":")
            ck = urllib.parse.quote(base64.b64encode(json.dumps({kid_hex: key_hex}).encode()).decode())
            hdrs_b64 = urllib.parse.quote(base64.b64encode(json.dumps({
                "user-agent": ua,
                "referer": "https://www.primevideo.com/",
                "origin": "https://www.primevideo.com",
            }).encode()).decode())

            self.result["ext_url"] = (
                "extension://opmeopcambhfimffbomjgemehjkbbmji/pages/player.html#"
                f"{mpd_url}&ck={ck}&headers={hdrs_b64}"
            )
            self.result["kodi_url"] = f"{mpd_url}&ck={ck}&headers={hdrs_b64}"

        except Exception as e:
            self.result["error"] = f"Errore generale: {e}"

        finally:
            await self._stop_browser()

        return self.result
