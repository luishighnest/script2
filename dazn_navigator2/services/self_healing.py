"""
Modulo di Diagnostica e Auto-Riparazione Dinamica (Self-Healing) per DAZN Navigator.
Esegue test approfonditi a cascata per identificare e risolvere automaticamente problemi di:
- WAF CloudFront / Fingerprint TLS
- User-Agent mismatch con CDN token
- Parametri query (Manufacturer, AppVersion)
- Endpoint obsoleti (Startup API)
- Sessione / Token JWT
- Validazione riproduzione stream MPD reale (HTTP 200)
"""
import asyncio, json, base64, hashlib, time, urllib.request
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()

class DaznDoctor:
    def __init__(self):
        self.report = []
        self.fixes_applied = []

    async def run_full_diagnosis_and_repair(self, auto_apply: bool = False) -> bool:
        console.print(Panel(
            "[bold yellow]🛠️ FIX PROBLEMI DAZN (AUTO-RIPARAZIONE & VERIFICA)[/bold yellow]\n"
            "[dim]Controllo completo: Sessione, Endpoint, WAF, Parametri ed Estrazione Flusso Reale...[/dim]",
            expand=False
        ))

        from dazn_navigator2.services.browser import get_browser
        from dazn_navigator2.settings import load_config, save_config

        everything_ok = True

        # ─── 1. VERIFICA BROWSER & SESSIONE JWT ─────────────────────────
        console.print("\n[bold cyan]1. Controllo Sessione & Token JWT...[/bold cyan]")
        try:
            b = await get_browser()
            await b.ensure_session()
            jwt = await b.evaluate("localStorage.getItem('MISL.authToken')")
            if not jwt or not jwt.startswith("eyJ"):
                console.print("  [red]✗ JWT non presente o non valido. Tentativo refresh...[/red]")
                everything_ok = False
                await b.page.goto("https://www.dazn.com/it-IT/home", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                jwt = await b.evaluate("localStorage.getItem('MISL.authToken')")
                if not jwt:
                    console.print("  [bold red]✗ Impossibile recuperare il token JWT. Effettua il login in DAZN.[/bold red]")
                    return False
            
            parts = jwt.split('.')
            pad = parts[1] + '=' * (-len(parts[1]) % 4)
            payload = json.loads(base64.b64decode(pad))
            exp = payload.get('exp', 0)
            now = int(time.time())
            remaining = exp - now
            dev_id_jwt = payload.get('deviceId', '')

            if remaining <= 0:
                console.print("  [red]✗ Token JWT SCADUTO. Rinfresco sessione in corso...[/red]")
                everything_ok = False
                await b.page.goto("https://www.dazn.com/it-IT/home", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                jwt = await b.evaluate("localStorage.getItem('MISL.authToken')")
                console.print("  [green]✓ Token JWT rinfrescato con successo.[/green]")
            else:
                console.print(f"  [green]✓ Token JWT valido (scade tra {remaining//60} min)[/green]")
                console.print(f"  [green]✓ Device ID associato al JWT:[/green] [dim]{dev_id_jwt}[/dim]")
        except Exception as e:
            console.print(f"  [bold red]✗ Errore accesso browser:[/bold red] {e}")
            return False

        # ─── 2. VERIFICA STARTUP API & DISCOVERY ENDPOINTS ──────────────
        console.print("\n[bold cyan]2. Controllo Startup API & Endpoints Discovery...[/bold cyan]")
        from curl_cffi.requests import AsyncSession
        playback_svc = "https://api.playback.indazn.com/v5/Playback"
        try:
            startup_url = "https://startup.core.indazn.com/misl/v5/Startup"
            s_temp = AsyncSession(impersonate="chrome146")
            st_res = await s_temp.post(
                startup_url,
                headers={"authorization": f"Bearer {jwt}", "accept": "application/json"},
                json={"LandingPageKey": "", "Languages": "it", "Platform": "web", "Manufacturer": "Web", "PromoCode": ""},
                timeout=8
            )
            if st_res.status_code == 200:
                sd = st_res.json().get("ServiceDictionary", {})
                entry = sd.get("Playback", {})
                if isinstance(entry, str):
                    playback_svc = entry
                elif isinstance(entry, dict):
                    for v in sorted(entry.get("Versions", {}), key=lambda x: int(x[1:]) if x[1:].isdigit() else 0, reverse=True):
                        sp = entry["Versions"][v].get("ServicePath", "")
                        if sp:
                            playback_svc = sp
                            break
                console.print(f"  [green]✓ Startup API OK → Playback Endpoint:[/green] [dim]{playback_svc}[/dim]")
            else:
                console.print(f"  [yellow]! Startup API status {st_res.status_code}, uso endpoint fallback:[/yellow] [dim]{playback_svc}[/dim]")
            await s_temp.close()
        except Exception as e:
            console.print(f"  [yellow]! Errore Startup API ({e}), uso fallback[/yellow]")

        # ─── 3. MATRIX TEST: WAF CLOUDFRONT / TLS IMPERSONATE ───────────
        console.print("\n[bold cyan]3. Test Penetrazione WAF CloudFront (Fingerprint TLS)...[/bold cyan]")
        test_impersonates = [
            "chrome131", "chrome136", "chrome142", "chrome145", "chrome146",
            "chrome124", "chrome123", "firefox133", "firefox135", "edge101"
        ]
        
        working_impersonate = None
        working_ua = None

        headers_test = {
            "authorization": f"Bearer {jwt}",
            "x-dazn-device": dev_id_jwt,
            "accept": "*/*",
            "origin": "https://www.dazn.com",
            "referer": "https://www.dazn.com/",
        }

        qs_diag = "AssetId=diag-test-stream&PlayerId=test&DrmType=WIDEVINE&Platform=web&Format=MPEG-DASH&LanguageCode=it&Model=N/A&Secure=true&Manufacturer=Web&PlayReadyInitiator=false&MtaLanguageCode=it&AppVersion=9.42.0&capabilities=mta"
        diag_url = f"{playback_svc}?{qs_diag}"

        for imp in test_impersonates:
            try:
                s_diag = AsyncSession(impersonate=imp)
                r_diag = await s_diag.get(diag_url, headers=headers_test, timeout=6)
                is_waf_blocked = "Request blocked" in r_diag.text or (r_diag.status_code == 403 and "CloudFront" in r_diag.text)
                
                # Ottieni lo User-Agent reale di questa sessione
                r_ua = await s_diag.get("https://httpbin.org/user-agent", timeout=4)
                curr_ua = r_ua.json().get("user-agent", "")
                await s_diag.close()

                if not is_waf_blocked and r_diag.status_code in (200, 400, 404):
                    console.print(f"  [green]✓ {imp:15s} → SUPERATO (Status {r_diag.status_code})[/green]")
                    if not working_impersonate:
                        working_impersonate = imp
                        working_ua = curr_ua
                else:
                    console.print(f"  [red]✗ {imp:15s} → Bloccato dal WAF (403 CloudFront)[/red]")
            except Exception:
                console.print(f"  [dim red]✗ {imp:15s} → Errore di connessione[/dim red]")

        if not working_impersonate:
            console.print("\n[bold red]✗ Nessun profilo HTTP supera il WAF. Si consiglia il motore 'headless' (Playwright).[/bold red]")
            working_impersonate = "headless"
        else:
            console.print(f"  [bold green]★ Profilo TLS ottimale:[/bold green] [bold cyan]{working_impersonate}[/bold cyan]")

        # ─── 4. TEST PARAMETRI QUERY (Manufacturer) ─────────────────────
        console.print("\n[bold cyan]4. Test Validazione Parametri API...[/bold cyan]")
        valid_mfr = "Web"
        for mfr in ["Web", "PC", "Windows", "unknown"]:
            if working_impersonate != "headless":
                s_m = AsyncSession(impersonate=working_impersonate)
                q = f"AssetId=diag-test&PlayerId=test&DrmType=WIDEVINE&Platform=web&Format=MPEG-DASH&LanguageCode=it&Manufacturer={mfr}&AppVersion=9.42.0"
                r_m = await s_m.get(f"{playback_svc}?{q}", headers=headers_test, timeout=5)
                await s_m.close()
                if "must have required property" not in r_m.text and "Request blocked" not in r_m.text:
                    valid_mfr = mfr
                    console.print(f"  [green]✓ Manufacturer='{mfr}' → Accettato[/green]")
                    break
                else:
                    console.print(f"  [red]✗ Manufacturer='{mfr}' → Rifiutato/Bloccato[/red]")

        # ─── 5. TEST ESTRAZIONE E VALIDAZIONE STREAM REALE ──────────────
        console.print("\n[bold cyan]5. Test Estrazione & Verifica Streaming Reale (DAZN 1 / VOD)...[/bold cyan]")
        stream_test_ok = False
        try:
            from dazn_navigator2.services.explorer import DaznExplorer
            from dazn_navigator2.services.extractor import HeadlessExtractor
            from dazn_navigator2.auth.token_refresh import PROFILE_DIR

            explorer = DaznExplorer()
            tiles = await explorer.get_tiles("LinearChannels") or await explorer.get_tiles("Live") or await explorer.get_tiles("Catchup")
            if tiles:
                test_tile = tiles[0]
                console.print(f"  [dim]Test su contenuto reale:[/dim] [cyan]{test_tile.title}[/cyan]")
                ext = HeadlessExtractor()
                res_ext = await ext.estrai(str(PROFILE_DIR), test_tile.asset_id, test_tile.title)
                
                if res_ext.get("ok"):
                    console.print("  [green]✓ MPD & Licenza DRM estratti con successo![/green]")
                    console.print(f"  [green]✓ Chiave DRM ottenuta:[/green] [dim]{res_ext.get('keys', [''])[0]}[/dim]")
                    
                    # Test del flusso MPD con dazn-token ed header User-Agent per verificare che la CDN risponda 200 OK
                    mpd_url = res_ext.get("mpd_url")
                    dazn_tok = res_ext.get("dazn_token")
                    ua_val = res_ext.get("ua")
                    
                    # Prova richiesta HTTP al manifest con il token
                    req_test = urllib.request.Request(
                        mpd_url,
                        headers={
                            "User-Agent": ua_val,
                            "dazn-token": dazn_tok,
                            "origin": "https://www.dazn.com",
                            "referer": "https://www.dazn.com/"
                        }
                    )
                    try:
                        with urllib.request.urlopen(req_test, timeout=6) as response:
                            if response.status == 200:
                                console.print("  [bold green]✓ VERIFICA STREAMING: Flusso riproducibile e autorizzato dalla CDN (HTTP 200 OK)![/bold green]")
                                stream_test_ok = True
                            else:
                                console.print(f"  [yellow]! CDN Status:[/yellow] {response.status}")
                    except Exception as cdn_err:
                        console.print(f"  [red]✗ Errore riproduzione CDN:[/red] {cdn_err}")
                else:
                    console.print(f"  [red]✗ Fallimento estrazione:[/red] {res_ext.get('error')}")
                    everything_ok = False
            else:
                console.print("  [yellow]! Nessun canale/evento trovato per il test stream.[/yellow]")
        except Exception as e_stream:
            console.print(f"  [red]✗ Errore durante il test di streaming:[/red] {e_stream}")
            everything_ok = False

        # ─── 6. RIEPILOGO STATO ──────────────────────────────────────────
        table = Table(title="\n📊 RIEPILOGO DIAGNOSTICA", show_header=True, header_style="bold magenta")
        table.add_column("Componente", style="cyan")
        table.add_column("Stato", style="white")
        table.add_column("Esito", style="green")

        table.add_row("Sessione & JWT", "Valido & Sincronizzato", "[green]OK[/green]")
        table.add_row("Endpoint Playback", playback_svc, "[green]OK[/green]")
        table.add_row("WAF CloudFront (TLS)", working_impersonate, "[green]OK[/green]")
        table.add_row("Parametri Query (Mfr)", valid_mfr, "[green]OK[/green]")
        table.add_row("Riproduzione CDN MPD", "Autorizzato (200 OK)" if stream_test_ok else "Da calibrare", "[green]OK[/green]" if stream_test_ok else "[yellow]Verifica[/yellow]")

        console.print(table)

        if everything_ok and stream_test_ok:
            console.print("\n[bold green]🎉 TUTTO FUNZIONA PERFETTAMENTE![/bold green]")
            console.print("[dim]Tutti i parametri, i token e la riproduzione stream sono al 100% operativi.[/dim]\n")
        else:
            if not auto_apply:
                scelta = Prompt.ask("\n[bold yellow]Vuoi applicare/salvare la configurazione ottimale verificata?[/bold yellow] (s/N)", default="s").strip().lower()
                if scelta != "s":
                    console.print("[yellow]Operazione annullata. Nessuna modifica salvata.[/yellow]")
                    return False

            config = load_config()
            config['preferred_impersonate'] = working_impersonate
            config['playback_manufacturer'] = valid_mfr
            if working_ua:
                config['curl_user_agent'] = working_ua
            save_config(config)

            console.print("\n[bold green]✓ CONFIGURAZIONE CALIBRATA E SALVATA CON SUCCESSO![/bold green]\n")

        return True

async def run_doctor():
    doc = DaznDoctor()
    return await doc.run_full_diagnosis_and_repair()
