import typer, asyncio, urllib.parse
from typing import List, Optional
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from dazn_navigator2.services.explorer import DaznExplorer, ContentTile
from dazn_navigator2.auth.token_refresh import PROFILE_DIR
from dazn_navigator2.services.extractor import HeadlessExtractor
from dazn_navigator2.utils.formatters import print_events_table, export_to_json, export_to_csv

app = typer.Typer(help="Naviga contenuti DAZN.")
console = Console()


def run_async(coro):
    from dazn_navigator2.main import run_async as _main_run_async
    return _main_run_async(coro)


async def _show_categories_menu(explorer: DaznExplorer):
    """Menu esplorazione completo organizzato per categorie tematiche e singoli sport/campionati."""
    CATEGORIES = [
        ("🏆 Calcio: Campionati & Prossimi Turni", [
            ("SerieA", "🇮🇹 Serie A Enilive (Partite, Replay & Prossimo Turno)"),
            ("SerieB", "🇮🇹 Serie BKT (Tutte le partite & Calendario)"),
            ("LaLiga", "🇪🇸 LALIGA EA SPORTS & HYPERMOTION"),
            ("LigaPortugal", "🇵🇹 Liga Portugal Betclic"),
            ("Football", "⚽ Tutto il Calcio (Palinsesto Completo)"),
        ]),
        ("🏀 Basket & Volley", [
            ("Basketball", "🏀 Basket (Eurolega, Serie A UnipolSai, Qualificazioni)"),
            ("Volleyball", "🏐 Pallavolo (Campionati & Coppe Europee)"),
        ]),
        ("🏈 NFL & Sport USA", [
            ("NFL", "🏈 NFL Game Pass, RedZone & NFL Live"),
            ("AmericanFootball", "🏈 Football Americano NCAA"),
            ("Baseball", "⚾ MLB Baseball"),
        ]),
        ("🥊 Boxe & Arti Marziali (UFC/MMA)", [
            ("Boxing", "🥊 Match Boxe Live, Replay & Prossimi Eventi"),
            ("MMA", "🥋 MMA, UFC & Arti Marziali"),
        ]),
        ("🏎️ Motori & Ciclismo & Altri Sport", [
            ("Motorsport", "🏎️ Motori & Gare"),
            ("Cycling", "🚴 Ciclismo & Grandi Giri"),
            ("Tennis", "🎾 Tennis"),
            ("Darts", "🎯 Darts (Freccette)"),
            ("Snooker", "🎱 Snooker"),
            ("RugbyUnion", "🏉 Rugby"),
        ]),
        ("🎬 Rubriche, Documentari & Originals", [
            ("Originals", "🎬 DAZN Originals & Approfondimenti"),
            ("Documentaries", "📽️ Documentari"),
        ]),
    ]

    while True:
        console.print("\n[bold magenta]── ESPLORA PER SPORT & CATEGORIE ──[/bold magenta]")
        for idx, (cat_name, subs) in enumerate(CATEGORIES, 1):
            console.print(f"[bold cyan]{idx}.[/bold cyan] {cat_name} [dim]({len(subs)} sottocategorie)[/dim]")
        console.print("[bold cyan]0.[/bold cyan] ⬅ Torna al menu precedente")

        c = Prompt.ask("\nScegli una categoria", default="0").strip()
        if c == "0" or not c:
            break
        if c.isdigit() and 1 <= int(c) <= len(CATEGORIES):
            cat_name, subs = CATEGORIES[int(c) - 1]
            while True:
                console.print(f"\n[bold yellow]── {cat_name} ──[/bold yellow]")
                for s_idx, (s_id, s_title) in enumerate(subs, 1):
                    console.print(f"[bold cyan]{s_idx}.[/bold cyan] {s_title}")
                console.print("[bold cyan]0.[/bold cyan] ⬅ Torna alle categorie")
                
                sub_c = Prompt.ask("\nScegli", default="0").strip()
                if sub_c == "0" or not sub_c:
                    break
                if sub_c.isdigit() and 1 <= int(sub_c) <= len(subs):
                    target_id, target_title = subs[int(sub_c) - 1]
                    await _show_tiles(explorer, target_id, target_title)
        else:
            console.print("[red]Scelta non valida[/red]")


async def _show_section_menu(explorer: DaznExplorer):
    while True:
        console.print("\n[bold magenta]── NAVIGAZIONE COMPLETA DAZN ──[/bold magenta]")
        
        menu = """[bold cyan]1.[/bold cyan]  🔴 Eventi Live (In Diretta)
[bold cyan]2.[/bold cyan]  ⏮️ Contenuti VOD & Replay (CatchUp)
[bold cyan]3.[/bold cyan]  📺 Canali Lineari (DAZN TV, Eurosport, ecc.)
[bold cyan]4.[/bold cyan]  🏆 Esplora per Sport & Categorie (Calcio, Basket, NFL, Boxe, Motori...)
[bold cyan]5.[/bold cyan]  📅 Guida TV & Palinsesto
[bold cyan]6.[/bold cyan]  🔍 Cerca un Evento
[bold cyan]0.[/bold cyan]  ⬅ Indietro"""
        
        console.print(menu)

        choice = Prompt.ask("\nScegli un'opzione", default="0").strip().upper()

        if choice == "0":
            break
        elif choice == "1":
            await _show_tiles(explorer, "Live", "Eventi Live")
        elif choice == "2":
            await _show_tiles(explorer, "Catchup", "Contenuti VOD (On-Demand)")
        elif choice == "3":
            await _show_tiles(explorer, "epg", "Canali Lineari (DAZN TV)")
        elif choice == "4":
            await _show_categories_menu(explorer)
        elif choice == "5":
            await _show_tiles(explorer, "Livetvschedule", "Guida TV & Palinsesto")
        elif choice == "6" or choice == "C":
            await _search_menu(explorer)
        else:
            console.print("[red]Scelta non valida[/red]")

def is_tile_locked(tile: ContentTile) -> bool:
    """Verifica dinamicamente se l'evento richiede abbonamento a pagamento (es. Serie A, LaLiga, ecc.) o se è Free/Gratis."""
    raw = tile.raw if isinstance(getattr(tile, 'raw', None), dict) else {}
    
    # Dump testuale completo del tile in minuscolo
    import json as _json
    raw_str = _json.dumps(raw).lower()

    # 1. Se è esplicitamente contrassegnato come gratuito / free
    is_free = False
    if raw.get("IsFree") is True or raw.get("Free") is True:
        is_free = True
    elif any(k in raw_str for k in ['"free"', '"gratis"', 'accesso gratuito', '"is_free": true']):
        is_free = True

    # Se è un contenuto gratuito (es. sintesi free, canali gratuiti), è sbloccato
    if is_free:
        return False

    # 2. Tutti i match di campionati a pagamento (Serie A, Serie B, La Liga, Coppe, Qualificazioni) richiedono abbonamento
    # Se l'account non ha un piano a pagamento attivo, mostriamo 🔒
    comp_name = str(raw.get("Competition", {}).get("Title", "")).lower()
    sport_name = str(raw.get("Sport", {}).get("Title", "")).lower()
    title_name = str(tile.title or "").lower()

    paid_competitions = [
        "serie a", "serie b", "laliga", "liga portugal", "fiba", "qualificazioni",
        "euroleague", "eurocup", "nfl", "boxing", "ufc", "americas", "european"
    ]
    if any(k in comp_name or k in title_name or k in sport_name for k in paid_competitions):
        return True

    # 3. Proprietà di accesso negativo o paywall
    for key in ["isentitled", "userhasaccess", "hasaccess", "issubscribed", "entitled"]:
        if f'"{key}": false' in raw_str:
            return True

    for key in ["georestricted", "territoryblocked", "isppv", "paymentrequired", "locked", "paywall"]:
        if f'"{key}": true' in raw_str:
            return True

    return False


async def _show_tiles(explorer: DaznExplorer, section_id: str, section_title: str, tiles: List[ContentTile] = None):
    if tiles is None:
        console.print(f"\n[bold cyan]Caricamento: {section_title}...[/bold cyan]")
        tiles = await explorer.get_tiles(section_id)

    if not tiles:
        console.print(f"[yellow]Nessun contenuto trovato in '{section_title}'.[/yellow]")
        return

    page_size = 20
    current_page = 0
    total_pages = (len(tiles) + page_size - 1) // page_size

    while True:
        start = current_page * page_size
        end = min(start + page_size, len(tiles))
        page_tiles = tiles[start:end]

        title = section_title if total_pages <= 1 else f"{section_title} (Pagina {current_page + 1}/{total_pages})"
        n = len(page_tiles)
        console.print(f"\n[bold]{title}[/bold] - [green]{n} contenuti[/green]")

        is_linear = section_id in ("LinearChannels", "epg") or "Canali Lineari" in section_title
        is_nav = section_id == "Sport" or "Tutti gli Sport" in section_title or all(t.tile_type == "Navigation" for t in page_tiles)

        tile_table = Table(show_header=True, header_style="bold cyan")
        if is_nav:
            tile_table.add_column("#", justify="right", style="cyan")
            tile_table.add_column("Sezione", style="white")
            tile_table.add_column("Tipo", style="yellow")
        elif is_linear:
            tile_table.add_column("#", justify="right", style="cyan")
            tile_table.add_column("Canale", style="white")
            tile_table.add_column("Tipo", style="yellow")
        else:
            tile_table.add_column("#", justify="right", style="cyan")
            tile_table.add_column("Titolo", style="white")
            tile_table.add_column("Data/Ora", style="green")
            tile_table.add_column("Tipo", style="yellow")
            tile_table.add_column("Sport", style="blue")
            tile_table.add_column("Competizione", style="magenta")

        for i, t in enumerate(page_tiles, start + 1):
            raw = t.raw if isinstance(t.raw, dict) else {}

            if is_nav:
                tile_table.add_row(str(i), t.title, "Sezione")
            elif is_linear:
                tile_table.add_row(str(i), t.title, "Live TV")
            else:
                start_raw = raw.get("Start") or raw.get("DisplayDate") or ""
                ora = _fmt_date(start_raw)
                sport = raw.get("Sport", {})
                if isinstance(sport, dict):
                    sport = sport.get("Title", "")
                comp = raw.get("Competition", {})
                if isinstance(comp, dict):
                    comp = comp.get("Title", "")
                tile_table.add_row(str(i), t.title, ora, t.tile_type, str(sport), str(comp))

        console.print(tile_table)

        console.print("\n[dim]'D' per dettagli, o:[/dim]")
        nav_hint = ""
        if current_page > 0:
            nav_hint += " 'P' indietro"
        if current_page < total_pages - 1:
            nav_hint += " 'N' avanti"
        console.print(f"[dim]{nav_hint} - Invio per tornare alle sezioni[/dim]")

        try:
            choice = Prompt.ask("Scelta", default="").strip().upper()
        except (KeyboardInterrupt, Exception):
            import os
            os._exit(0)

        if not choice:
            break
        if choice == "N" and current_page < total_pages - 1:
            current_page += 1
            continue
        if choice == "P" and current_page > 0:
            current_page -= 1
            continue
        if choice == "D":
            idx = Prompt.ask("Numero del tile per dettagli", default="")
            if idx.isdigit():
                i = int(idx) - 1
                if 0 <= i < len(tiles):
                    details = await explorer.get_item_details(tiles[i])
                    console.print(f"\n[bold cyan]Dettagli:[/bold cyan] {tiles[i].title}")
                    console.print(f"  ID: {details.get('Id', 'N/A')}")
                    console.print(f"  Sport: {details.get('Sport', {}).get('Title', 'N/A')}")
                    console.print(f"  Competizione: {details.get('Competition', {}).get('Title', 'N/A')}")
                    console.print(f"  Inizio: {details.get('Start', 'N/A')}")
                    console.print(f"  Durata: {details.get('Duration', 'N/A')} minuti")
            continue

        indices = []
        for p in choice.split():
            if p.isdigit():
                idx = int(p) - 1
                if 0 <= idx < len(tiles):
                    indices.append(idx)

        if not indices:
            continue

        await _handle_selected(explorer, tiles, indices)


async def _handle_selected(explorer: DaznExplorer, tiles: list, indices: list):
    from dazn_navigator2.settings import get_setting
    from dazn_navigator2.cli.events_cmds import console
    risultati = []
    download_mp4 = get_setting("download_vod_mp4")
    for idx in indices:
        tile = tiles[idx]
        if explorer.is_navigation(tile):
            console.print(f"\n[cyan]Esploro: {tile.title}...[/cyan]")
            subtiles = await explorer.get_navigation_tiles(tile)
            if subtiles:
                await _show_tiles(explorer, tile.id, tile.title, subtiles)
            else:
                console.print(f"[yellow]Nessun contenuto in '{tile.title}'.[/yellow]")
            continue
        raw = getattr(tile, 'raw', {})
        asset_id = tile.asset_id or raw.get("AssetId") or raw.get("Id") or tile.id
        if asset_id and ":" in asset_id:
            asset_id = asset_id.split(":")[-1]
        
        # Se l'evento non ha un AssetId diretto (es. evento futuro ComingSoon/EventId), estrai l'EventId
        if not asset_id or asset_id == raw.get("EventId"):
            event_id = raw.get("EventId") or asset_id
            if event_id:
                try:
                    details = await explorer.get_item_details(tile)
                    asset_id = details.get("AssetId") or details.get("Id") or asset_id
                    if ":" in str(asset_id):
                        asset_id = str(asset_id).split(":")[-1]
                except Exception:
                    pass

        import time
        t0 = time.time()
        console.print(f"\n[cyan]Estrazione: {tile.title}...[/cyan]")
        ext = HeadlessExtractor()
        result = await ext.estrai(str(PROFILE_DIR), asset_id, tile.title)
        if not result.get("ok"):
            console.print(f"[bold red]Fallito: {tile.title} - {result.get('error', 'Errore')}[/bold red]")
            heal = Prompt.ask("\n[bold yellow]Vuoi avviare il Fix problemi (Auto-Riparazione)?[/bold yellow] (s/N)", default="n").strip().lower()
            if heal == "s":
                from dazn_navigator2.services.self_healing import run_doctor
                healed = await run_doctor()
                if healed:
                    console.print("\n[cyan]Riprovo l'estrazione con i nuovi parametri calibrati...[/cyan]")
                    result = await ext.estrai(str(PROFILE_DIR), asset_id, tile.title)
        
        # Se il download VOD MP4 è abilitato, scarica automaticamente
        if download_mp4 and result.get("ok"):
            try:
                await _download_mp4_vod(tile.title, result)
            except Exception as e:
                console.print("[yellow]Download MP4 non riuscito: {}[/yellow]".format(e))
        
        t_build = time.time()
        info = _build_entry(tile, result)
        console.print(f"[dim yellow]⏱ Tempo cifratura/salvataggio: {time.time() - t_build:.2f}s[/dim yellow]")
        if info:
            risultati.append(info)
    if risultati:
        _print_batch(risultati)
        from dazn_navigator2.cli.eventi_cmds import pubblica
        pubblica("dazn2: estrazione %s" % ", ".join(e['name'] for _, e, _, _ in risultati))

async def _download_mp4_vod(title: str, result: dict):
    """Scarica il VOD in MP4 se l'impostazione è abilitata."""
    import shutil
    from subprocess import Popen, PIPE, run
    from pathlib import Path
    
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg non trovato nel sistema.")
    
    # Usa l'ext_url per lo stream con token già inserito
    mpd_url = result.get("ext_url") or result.get("mpd_url") or ""
    if not mpd_url:
        raise RuntimeError("URL MPD non disponibile.")
    
    dest_dir = Path.home() / "DAZN_DOWNLOADS"
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = dest_dir / (title + ".mp4")
    
    cmd = [
        ffmpeg_path,
        "-i", mpd_url,
        "-c", "copy",
        "-f", "mp4",
        str(output_path),
        "-y"
    ]
    
    console.print("[cyan]Download MP4 in corso per: {}[/cyan]".format(title))
    console.print("[dim]Output: {}[/dim]".format(output_path))
    console.print("[dim]Progresso: scaricamento in corso...[/dim]")
    
    process = Popen(cmd, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)
    
    # Track progress from ffmpeg stderr
    while True:
        output = process.stderr.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            line = output.strip()
            if line.startswith('frame=') or line.startswith('time='):
                import re
                m = re.search(r'time=(\d+:\d+:\d+\.\d+)', line)
                if m:
                    time_str = m.group(1)
                    console.print("[yellow]Progress: {}[/yellow]".format(time_str), end='\r')
    
    process.wait()
    returncode = process.returncode
    
    if returncode == 0:
        console.print("[green]Download completato: {}[/green]".format(output_path))
        console.print("[dim]File salvato in: {}[/dim]".format(output_path))
    else:
        # Also try to get ffmpeg's error message
        try:
            stderr_output = process.stderr.read() if process.stderr else ""
            console.print("[red]Errore download: code {}[/red]".format(returncode))
            if stderr_output:
                console.print("[dim]Messaggio ffmpeg: {}[/dim]".format(stderr_output[:200]))
        except:
            console.print("[red]Errore download: code {}[/red]".format(returncode))


def _image_url(img) -> str:
    """Converte il campo image in URL discovery v3 identico al formato richiesto."""
    if isinstance(img, dict):
        img_id = img.get("Id", "")
        if img_id:
            return f"https://image.discovery.indazn.com/eu/v3/eu/none/{img_id}/fill/none/top/none/100/1280/720/png/image"
        return ""
    return str(img) if img else ""


_WARP_CACHE = None

def _is_cloudflare_warp() -> bool:
    """Rileva se la connessione attuale passa per Cloudflare (WARP / AS13335)."""
    import urllib.request, json
    urls = [
        "http://ip-api.com/json/",
        "https://ipinfo.io/json"
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                combined = (str(data.get('as', '')) + ' ' +
                            str(data.get('org', '')) + ' ' +
                            str(data.get('isp', ''))).lower()
                if 'cloudflare' in combined or 'warp' in combined or 'as13335' in combined:
                    return True
                return False
        except Exception:
            continue
    return False


def detect_warp_from_stream(url: str = "", title: str = "") -> bool:
    """Riconosce se uno stream è Cloudflare WARP o Standard.
    - Tutti gli stream HLS (.m3u8) o Acestream sono SEMPRE Standard (non-WARP).
    - Gli stream DASH (.mpd) vengono verificati tramite il token JWT (ASN 13335) o la connessione WARP attiva.
    """
    import base64, json, re
    url_clean = (url or '').strip().lower()
    title_clean = (title or '').strip().upper()

    # 1. HLS (.m3u8) o flussi non-DASH sono SEMPRE standard
    if '.m3u8' in url_clean or ('http' in url_clean and '.mpd' not in url_clean and '@eyj' not in url_clean):
        return False

    # 2. Analisi del token JWT incorporato nel link MPD (es. @eyJ... o dazn-token=eyJ...)
    m = re.search(r'[@/=](eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)', url or '')
    if m:
        token = m.group(1)
        try:
            parts = token.split('.')
            payload_b64 = parts[1]
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
            asns = payload.get('asn', [])
            if isinstance(asns, list):
                if any(str(a) == '13335' for a in asns):
                    return True
                if len(asns) > 0:
                    # Ha un ASN specificato che NON è 13335 (es. TIM, Fastweb, Vodafone) -> Standard (non-WARP)
                    return False
        except Exception:
            pass

    # 3. Se nel titolo c'era esplicitamente (WARP)
    if '(WARP)' in title_clean:
        return True

    # 4. Fallback: verifica se la connessione attuale del PC è su Cloudflare WARP
    return _is_cloudflare_warp()


def _build_entry(tile: ContentTile, result: dict):
    """Estrae i dati, salva l'evento e ritorna (comp, entry, scadenza) o None."""
    import re
    if not result.get("ok"):
        console.print(f"[bold red]Fallito: {tile.title} - {result.get('error', 'Errore sconosciuto')}[/bold red]")
        return None
    titolo = result.get('titolo', tile.title)
    mpd_url = result['mpd_url']
    dazn_token = result.get('dazn_token', '')
    
    # Rileva ASN da stream o token
    is_warp = detect_warp_from_stream(url=dazn_token or mpd_url, title=titolo)
    if is_warp:
        if "(WARP)" not in titolo:
            titolo = f"{titolo} (WARP)"
    else:
        # Se non è WARP, rimuovi qualsiasi residuo di (WARP) dal titolo
        titolo = re.sub(r'\s*\(WARP\)\s*', ' ', titolo, flags=re.IGNORECASE).strip()
            
    logo = _image_url(tile.image)

    keys_str = ','.join(result.get('keys', []))
    dazn_token = result.get('dazn_token', '')
    mpd_url = result['mpd_url']
    
    # Inserimento token nel path (@token/...) come richiesto dall'addon
    if dazn_token:
        if "://" in mpd_url:
            proto, rest = mpd_url.split("://", 1)
            if "/" in rest:
                host, path = rest.split("/", 1)
                mpd_auth = f"{proto}://{host}/@{dazn_token}/{path}"
            else:
                mpd_auth = f"{proto}://{rest}/@{dazn_token}"
        else:
            mpd_auth = mpd_url
    else:
        mpd_auth = mpd_url

    raw = getattr(tile, 'raw', {}) or {}
    comp = raw.get('Competition', {})
    if isinstance(comp, dict):
        comp_title = comp.get('Title', '') or 'Eventi'
    else:
        comp_title = str(comp) or 'Eventi'
    
    from dazn_navigator2.settings import get_setting
    entry = {
        'name': titolo,
        'image': logo,
        'start': raw.get('Start') or '',
        'end': raw.get('End') or '',
        'mpd': mpd_auth,
        'key': keys_str,
    }
    # UA nel JSON: controllato separatamente per curl e headless
    engine = get_setting("extraction_engine")
    ua_key = "include_ua_headless" if engine == "headless" else "include_ua_curl"
    if result.get("ua") and get_setting(ua_key):
        entry['ua'] = result['ua']

    from dazn_navigator2.cli.eventi_cmds import add_event
    add_event(comp_title, entry)
    from dazn_navigator2.services.playlist_ed import token_expiry
    return comp_title, entry, token_expiry(dazn_token), result.get('ext_url', '')


def _print_batch(risultati):
    """Stampa un unico JSON con tutti gli eventi estratti + riepilogo scadenze."""
    import json as _json
    from datetime import datetime
    raggruppato = {}
    
    from dazn_navigator2.settings import get_setting
    for _, entry, _, ext_url in risultati:
        if ext_url and get_setting("print_extension_link"):
            console.print(f"\n[bold cyan]Link Estensione ({entry['name']}):[/bold cyan]\n[green]{ext_url}[/green]")
    console.print("")
    
    for comp, entry, _, _ in risultati:
        raggruppato.setdefault(comp, []).append(entry)
    console.print(_json.dumps(raggruppato, indent=3))
    
    for comp, entry, scadenza, _ in risultati:
        if scadenza is not None:
            scad_str = scadenza.strftime('%d/%m/%Y %H:%M')
            stato = '[green]✓[/green]' if scadenza > datetime.now() else '[red]SCADUTO[/red]'
        else:
            scad_str = 'non determinabile'
            stato = '[yellow]?[/yellow]'
        console.print("")
        console.print(f"[bold]{entry['name']}[/bold] {stato}")
        console.print(f"Scadenza link: {scad_str}")


def _fmt_date(d: str) -> str:
    if not d:
        return ""
    from datetime import datetime
    try:
        clean = d[:19].replace("T", " ")
        dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m %H:%M")
    except:
        return d[:10]


async def _search_menu(explorer: DaznExplorer):
    query = Prompt.ask("\n[bold cyan]Cerca[/bold cyan] (lascia vuoto per tornare)")
    if not query:
        return

    console.print(f"[cyan]Cerco: '{query}'...[/cyan]")
    results = await explorer.search(query)

    if not results:
        console.print("[yellow]Nessun risultato.[/yellow]")
        return

    tiles = results
    page_size = 20
    current_page = 0
    total_pages = (len(tiles) + page_size - 1) // page_size

    while True:
        start = current_page * page_size
        end = min(start + page_size, len(tiles))
        page_tiles = tiles[start:end]

        console.print(f"\n[bold]Risultati per '{query}'[/bold] - [green]{len(tiles)} trovati[/green]")
        t = Table(show_header=True, header_style="bold cyan")
        t.add_column("#", justify="right", style="cyan", width=4)
        t.add_column("Titolo", style="white")
        t.add_column("Tipo", style="yellow")
        for i, tl in enumerate(page_tiles, start + 1):
            t.add_row(str(i), tl.title, tl.tile_type)
        console.print(t)

        nav = ""
        if current_page > 0:
            nav += " 'P' indietro"
        if current_page < total_pages - 1:
            nav += " 'N' avanti"
        console.print(f"[dim]{nav} - 'D' dettagli - Invio per tornare[/dim]")

        choice = Prompt.ask("Scelta", default="").strip().upper()
        if not choice:
            break
        if choice == "N" and current_page < total_pages - 1:
            current_page += 1
            continue
        if choice == "P" and current_page > 0:
            current_page -= 1
            continue
        if choice == "D":
            idx = Prompt.ask("Numero per dettagli", default="")
            if idx.isdigit():
                i = int(idx) - 1
                if 0 <= i < len(tiles):
                    details = await explorer.get_item_details(tiles[i])
                    console.print(f"\n[bold cyan]Dettagli:[/bold cyan] {tiles[i].title}")
                    console.print(f"  ID: {details.get('Id', 'N/A')}")
                    console.print(f"  Tipo: {details.get('Type', 'N/A')}")
            continue

        indices = []
        for p in choice.split():
            if p.isdigit():
                idx = int(p) - 1
                if 0 <= idx < len(tiles):
                    indices.append(idx)
        if indices:
            await _handle_selected(explorer, tiles, indices)


@app.command("naviga")
def naviga():
    """Esplora la home page e tutte le sezioni."""
    async def _run():
        explorer = DaznExplorer()
        try:
            await _show_section_menu(explorer)
        finally:
            await explorer.close()
    run_async(_run())


@app.command("cerca")
def search(query: str = typer.Argument("", help="Testo da cercare")):
    """Cerca contenuti su DAZN."""
    async def _run():
        explorer = DaznExplorer()
        try:
            if query:
                tiles = await explorer.search(query)
                if tiles:
                    await _show_tiles(explorer, "search", f"Risultati per '{query}'", tiles)
                else:
                    console.print("[yellow]Nessun risultato.[/yellow]")
            else:
                await _show_section_menu(explorer)
        finally:
            await explorer.close()
    run_async(_run())


async def navigate():
    """Avvia direttamente il menu categorie e sport (usato da main menu)."""
    explorer = DaznExplorer()
    try:
        await _show_categories_menu(explorer)
    finally:
        await explorer.close()

async def quick_navigate(section_id: str, section_title: str):
    explorer = DaznExplorer()
    try:
        await _show_tiles(explorer, section_id, section_title)
    finally:
        await explorer.close()

async def quick_search():
    explorer = DaznExplorer()
    try:
        await _search_menu(explorer)
    finally:
        await explorer.close()



