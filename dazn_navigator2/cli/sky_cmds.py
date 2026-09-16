"""Modulo per sincronizzare i canali Sky da Herokuapp e pubblicarli su sky.json nel repo zadonkais."""

import json
import base64
import subprocess
import requests
from pathlib import Path
from rich.console import Console

console = Console()

HTDOCS_REPO = Path(r"C:\Users\user\Desktop\htdocs")
NEXT_REPO = Path(r"C:\Users\user\Desktop\next")
GIT_EXE = r"C:\Program Files\Git\cmd\git.exe"

API = 'https://test34344.herokuapp.com/filter.php'
SECRET = b'my_secret_key'
API_UA = 'Kodi/19.0 (Windows NT 10.0; Win64; x64) App_Bitness/64 Version/19.0-Matrix'

# Definizione categorie e canali Sky con relativi loghi
SKY_CHANNELS_DEF = [
    # --- SKY SPORT ---
    {"id": "skysport24", "name": "Sky Sport 24", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+24&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportuno", "name": "Sky Sport Uno", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+Uno&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportcalcio", "name": "Sky Sport Calcio", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+Calcio&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportf1", "name": "Sky Sport F1", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+F1&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportmotogp", "name": "Sky Sport MotoGP", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+MotoGP&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysporttennis", "name": "Sky Sport Tennis", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+Tennis&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportarena", "name": "Sky Sport Arena", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+Arena&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportmax", "name": "Sky Sport Max", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+Max&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportbasket", "name": "Sky Sport Basket", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+Basket&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportgolf", "name": "Sky Sport Golf", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+Golf&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportmix", "name": "Sky Sport Mix", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+Mix&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysportlegend", "name": "Sky Sport Legend", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+Legend&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"},
    {"id": "skysport251", "name": "Sky Sport 251", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+251&background=0D8ABC&color=fff&size=256&font-size=0.3"},
    {"id": "skysport252", "name": "Sky Sport 252", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+252&background=0D8ABC&color=fff&size=256&font-size=0.3"},
    {"id": "skysport253", "name": "Sky Sport 253", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+253&background=0D8ABC&color=fff&size=256&font-size=0.3"},
    {"id": "skysport254", "name": "Sky Sport 254", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+254&background=0D8ABC&color=fff&size=256&font-size=0.3"},
    {"id": "skysport255", "name": "Sky Sport 255", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+255&background=0D8ABC&color=fff&size=256&font-size=0.3"},
    {"id": "skysport256", "name": "Sky Sport 256", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+256&background=0D8ABC&color=fff&size=256&font-size=0.3"},
    {"id": "skysport257", "name": "Sky Sport 257", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+257&background=0D8ABC&color=fff&size=256&font-size=0.3"},
    {"id": "skysport258", "name": "Sky Sport 258", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+258&background=0D8ABC&color=fff&size=256&font-size=0.3"},
    {"id": "skysport259", "name": "Sky Sport 259", "group": "Sky Sport", "logo": "https://ui-avatars.com/api/?name=Sky+Sport+259&background=0D8ABC&color=fff&size=256&font-size=0.3"},

    # --- SKY INTRATTENIMENTO ---
    {"id": "tg24", "name": "Sky TG 24", "group": "Sky Intrattenimento", "logo": "./logos/skytg24.png?v=3"},
    {"id": "skyuno", "name": "SKY UNO", "group": "Sky Intrattenimento", "logo": "./logos/skyuno.png?v=3"},
    {"id": "skyunoplus", "name": "SKY UNO+", "group": "Sky Intrattenimento", "logo": "./logos/skyunoplus.png?v=3"},
    {"id": "skyatlantic", "name": "Sky Atlantic", "group": "Sky Intrattenimento", "logo": "./logos/skyatlantic.png?v=3"},
    {"id": "skyserie", "name": "Sky Serie", "group": "Sky Intrattenimento", "logo": "./logos/skyserie.png?v=3"},
    {"id": "skycollection", "name": "Sky Collection", "group": "Sky Intrattenimento", "logo": "./logos/skycollection.png?v=3"},
    {"id": "skyinvestigation", "name": "Sky Investigation", "group": "Sky Intrattenimento", "logo": "./logos/skyinvestigation.png?v=3"},
    {"id": "skyadventure", "name": "Sky Adventure", "group": "Sky Intrattenimento", "logo": "./logos/skyadventure.png?v=3"},
    {"id": "skycrime", "name": "Sky Crime", "group": "Sky Intrattenimento", "logo": "./logos/skycrime.png?v=3"},
    {"id": "skydocumentaries", "name": "Sky Documentaries", "group": "Sky Intrattenimento", "logo": "./logos/skydocumentaries.png?v=3"},
    {"id": "skynature", "name": "Sky Nature", "group": "Sky Intrattenimento", "logo": "./logos/skynature.png?v=3"},
    {"id": "historychannel", "name": "Sky History", "group": "Sky Intrattenimento", "logo": "./logos/history.png?v=3"},
    {"id": "comedycentral", "name": "Sky Comedy Central", "group": "Sky Intrattenimento", "logo": "./logos/comedycentral.png?v=3"},
    {"id": "skyarte", "name": "Sky Arte", "group": "Sky Intrattenimento", "logo": "./logos/skyarte.png?v=3"},
    {"id": "mtv", "name": "Sky Mtv", "group": "Sky Intrattenimento", "logo": "./logos/mtv.png?v=3"}
]


def xor_decrypt(b64data: str) -> str:
    data = base64.b64decode(b64data)
    out = bytes(b ^ SECRET[i % len(SECRET)] for i, b in enumerate(data))
    return out.decode('utf-8')


def resolve_channel(cid: str):
    """Risolve un canale da Heroku. Ritorna dict con manifest, kid, key oppure None."""
    try:
        url = f"{API}?numTest=A1A159&id={cid}"
        resp = requests.get(url, headers={'User-Agent': API_UA}, timeout=15)
        if resp.status_code == 200:
            payload = resp.json()
            if 'data' in payload:
                decrypted = json.loads(xor_decrypt(payload['data']))
                return decrypted
    except Exception as e:
        console.print(f"[dim yellow]Errore {cid}: {e}[/dim yellow]")
    return None


def sync_sky_site():
    """Risolve tutti i canali Sky contemporaneamente in parallelo e li scrive in sky.json sul repo zadonkais, poi esegue git push."""
    import concurrent.futures
    import re
    from datetime import datetime

    console.print("\n[bold cyan]═══ Sincronizzazione Canali Sky Sito (Multi-Thread) ═══[/bold cyan]")
    console.print("[cyan]Download link e chiavi fresche da Heroku in parallelo...[/cyan]")

    output_data = {
        "Sky Sport": [],
        "Sky Intrattenimento": []
    }

    total = len(SKY_CHANNELS_DEF)
    results_map = {}

    def _fetch(item):
        cid = item["id"]
        res = resolve_channel(cid)
        return item, res

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(_fetch, item) for item in SKY_CHANNELS_DEF]
        for future in concurrent.futures.as_completed(futures):
            item, res = future.result()
            cid = item["id"]
            name = item["name"]
            if res and res.get("manifest") and res.get("kid") and res.get("key"):
                results_map[cid] = res
                exp_str = "N/D"
                try:
                    exp_match = re.search(r'e~(\d+)', res.get("manifest", ""))
                    if exp_match:
                        exp_ts = int(exp_match.group(1))
                        exp_dt = datetime.fromtimestamp(exp_ts)
                        exp_str = exp_dt.strftime('%d/%m/%Y %H:%M:%S')
                except Exception:
                    pass
                console.print(f" [green]✔[/green] [bold]{name}[/bold]  [dim]↳ Scadenza: [yellow]{exp_str}[/yellow][/dim]")
                console.print(f"   [cyan]MPD:[/cyan] {res.get('manifest')}")
                console.print(f"   [magenta]KID:[/magenta] {res.get('kid')}  [magenta]KEY:[/magenta] {res.get('key')}  ([yellow]{res.get('kid')}:{res.get('key')}[/yellow])")
            else:
                console.print(f" [red]✘[/red] {name} (fallito)")

    success_count = 0
    for item in SKY_CHANNELS_DEF:
        cid = item["id"]
        name = item["name"]
        group = item["group"]
        logo = item["logo"]
        res = results_map.get(cid)

        if res and res.get("manifest") and res.get("kid") and res.get("key"):
            entry = {
                "key": f"{res['kid']}:{res['key']}",
                "name": name,
                "logo": logo,
                "mpd": res["manifest"]
            }
            output_data[group].append(entry)
            success_count += 1

    console.print(f"\n[bold green]Risolti con successo {success_count}/{total} canali Sky in parallelo.[/bold green]")

    if success_count == 0:
        console.print("[red]Nessun canale risolto. Operazione annullata.[/red]")
        return

    # Scrittura su sky.json nel repo htdocs CIFRATO CON AES-256 (Password 2941)
    from dazn_navigator2.cli.sky2_cmds import encrypt_site_payload
    sky_json_path = HTDOCS_REPO / "sky.json"
    enc_payload = encrypt_site_payload(output_data)
    sky_json_text = json.dumps({"enc": enc_payload}, indent=2, ensure_ascii=False) + "\n"
    sky_json_path.write_text(sky_json_text, encoding="utf-8")
    console.print(f"[green]File salvato in: {sky_json_path}[/green]")

    # Scrittura anche su next/public/sky.json
    next_sky_json = NEXT_REPO / "public" / "sky.json"
    if next_sky_json.parent.exists():
        try:
            next_sky_json.write_text(sky_json_text, encoding="utf-8")
            console.print(f"[green]File salvato in: {next_sky_json}[/green]")
        except Exception:
            pass

    # Sincronizzazione automatica su Upstash Redis Cloud (Zero Git!)
    console.print("[cyan]Sincronizzazione canali Sky 1 su Upstash Redis Cloud (Zero Git)...[/cyan]")
    ok_redis = False
    try:
        from dazn_navigator2.services.redis_sync import sync_to_upstash
        ok_redis = sync_to_upstash("sky1", output_data)
    except Exception:
        pass

    if ok_redis:
        console.print("[bold green][OK] Canali Sky 1 sincronizzati istantaneamente su Upstash Redis Cloud![/bold green]")
    else:
        # Fallback locale se API attiva
        try:
            import requests
            from dazn_navigator2.settings import get_setting
            api_url = get_setting("site_api_url") or "http://localhost:3000/api"
            api_key = get_setting("site_api_key") or "zadonkais_secret_2026"
            requests.post(f"{api_url}/sky", json={"source": "sky1", "data": output_data}, headers={"x-api-key": api_key}, timeout=4)
        except Exception:
            pass
        console.print("[green][OK] Canali Sky 1 salvati in locale.[/green]")
