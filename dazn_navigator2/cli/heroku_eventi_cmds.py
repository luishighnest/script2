"""Modulo per importare eventi live, partite e canali da Herokuapp (MandraKodi) in test.json (categoria EVENTI).

Supporta:
- Last Minute & Canali Live (A1A103)
- Serie A & Match Italiani (A1A134C)
- Partite del giorno (A1A115 / A1A122)
- Canali Live MPD & Sport (A1A134F)
- Live Now per Sport (A1A170)
- Ricerca istantanea per squadra o evento (es. 'Roma', 'Lecce', 'DAZN', 'Sky', 'Zona')
"""

import json
import re
import base64
import urllib.parse
import requests
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from dazn_navigator2.cli.eventi_cmds import add_event, pubblica
from dazn_navigator2.cli.aggiungi_cmds import parse_evento_da_link, DEFAULT_UA, CATEGORIA_EVENTI

console = Console()

HEROKU_BASE = 'https://test34344.herokuapp.com/filter.php'
HEROKU_UA = 'Kodi/19.0 (Windows NT 10.0; Win64; x64) App_Bitness/64 Version/19.0-Matrix'

ENDPOINTS_MAP = {
    "1": ("Last Minute (Eventi & Canali Live)", "A1A103"),
    "2": ("Serie A & Grandi Match", "A1A134C"),
    "3": ("Partite Internazionali (Platin / Ace)", "A1A115"),
    "4": ("Partite & Canali Sport (M3U8 / FHD)", "A1A122"),
    "5": ("Tutti i Canali Live MPD (Eurosport/Club/Sport)", "A1A134F"),
    "6": ("Tutti gli Eventi Aggregati (Tutti i server)", "ALL")
}

def _clean_title(raw_title: str) -> str:
    """Rimuove codici colore da Kodi, parentesi e il loro contenuto, ed eventuali orari."""
    # 1. Rimuovi tag colore Kodi
    t = re.sub(r'\[/?[cC][oO][lL][oO][rR][^\]]*\]', '', raw_title or '')
    t = t.replace('[CR]', ' ')
    # 2. Rimuovi parentesi tonde e quadre e tutto il loro contenuto
    t = re.sub(r'\([^)]*\)', '', t)
    t = re.sub(r'\[[^\]]*\]', '', t)
    # 3. Rimuovi orari (es. 18:45, 18.45, Ore 20:45)
    t = re.sub(r'\b(?:ore\s*)?[0-2]?[0-9][.:][0-5][0-9](?:[.:][0-5][0-9])?\b', '', t, flags=re.IGNORECASE)
    # 4. Pulisci spazi multipli e punteggiatura residua ai bordi
    t = re.sub(r'\s+', ' ', t).strip(' -:|./,')
    return t

def _decode_stream_item(it: dict) -> dict:
    """Estrae titolo, mpd/url, key e thumbnail da un item MandraKodi."""
    raw_title = it.get("title", "")
    clean_title = _clean_title(raw_title)
    thumb = it.get("thumbnail", "")

    if not raw_title or clean_title.startswith("==="):
        return None

    link = it.get("link")
    myres = it.get("myresolve")

    mpd_url = ""
    key_val = ""
    res_type = ""

    if myres:
        if "@@" in myres:
            res_type, payload = myres.split("@@", 1)
        elif ":" in myres:
            res_type, payload = myres.split(":", 1)
        else:
            res_type, payload = "resolve", myres

        try:
            dec = base64.b64decode(payload).decode('utf-8')
            if "|" in dec:
                p = dec.split("|")
                mpd_url = p[0]
                key_val = p[1] if len(p) > 1 else ""
            else:
                mpd_url = dec
        except Exception:
            mpd_url = payload

    elif link and link != "ignore":
        if "|" in link:
            p = link.split("|")
            mpd_url = p[0]
            key_val = p[1] if len(p) > 1 else ""
        elif link.startswith("aHR0"):
            try:
                dec = base64.b64decode(link).decode('utf-8')
                if "|" in dec:
                    p = dec.split("|")
                    mpd_url = p[0]
                    key_val = p[1] if len(p) > 1 else ""
                else:
                    mpd_url = dec
            except Exception:
                mpd_url = link
        else:
            mpd_url = link
    else:
        return None

    if not mpd_url:
        return None

    stream_type = "Acestream" if mpd_url.startswith("acestream") else ("DASH (MPD)" if ".mpd" in mpd_url else "HLS (M3U8)")

    return {
        "title": clean_title,
        "mpd": mpd_url,
        "key": key_val,
        "thumbnail": thumb,
        "stream_type": stream_type,
        "resolver": res_type
    }

def fetch_from_endpoint(num_test: str):
    """Scarica e decodifica tutti gli eventi da un numTest."""
    try:
        url = f"{HEROKU_BASE}?numTest={num_test}"
        r = requests.get(url, headers={'User-Agent': HEROKU_UA}, timeout=10)
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
        results = []
        for it in items:
            decoded = _decode_stream_item(it)
            if decoded:
                results.append(decoded)
        return results
    except Exception:
        return []

def importa_eventi_da_heroku():
    console.print("\n[bold cyan]═══ IMPORTA EVENTI E PARTITE LIVE DA HEROKU ═══[/bold cyan]")
    console.print("[bold yellow]Seleziona la lista da consultare:[/bold yellow]")
    for k, (desc, _) in ENDPOINTS_MAP.items():
        console.print(f"[cyan]{k}.[/cyan] {desc}")
    console.print("[cyan]C.[/cyan] Cerca Partita / Squadra (es. 'Roma', 'Lecce', 'DAZN', 'Zona')")
    console.print("[cyan]0.[/cyan] Indietro")

    scelta_menu = Prompt.ask("\nScegli un'opzione", default="1").strip().upper()
    if scelta_menu == "0":
        return

    events = []
    if scelta_menu == "C":
        query = Prompt.ask("Inserisci squadra o parola chiave", default="").strip().lower()
        if not query:
            console.print("[red]Ricerca vuota.[/red]")
            return
        console.print(f"[cyan]Ricerca in corso per '{query}' su tutti i server Heroku...[/cyan]")
        all_evs = []
        for code in ["A1A103", "A1A134C", "A1A115", "A1A122", "A1A134F"]:
            all_evs.extend(fetch_from_endpoint(code))
        seen = set()
        for ev in all_evs:
            if query in ev['title'].lower() and ev['title'] not in seen:
                seen.add(ev['title'])
                events.append(ev)
    elif scelta_menu == "6":
        console.print("[cyan]Scaricamento aggregato in corso...[/cyan]")
        seen = set()
        for code in ["A1A103", "A1A134C", "A1A115", "A1A122", "A1A134F"]:
            for ev in fetch_from_endpoint(code):
                if ev['title'] not in seen:
                    seen.add(ev['title'])
                    events.append(ev)
    elif scelta_menu in ENDPOINTS_MAP:
        desc, code = ENDPOINTS_MAP[scelta_menu]
        console.print(f"[cyan]Scaricamento da Heroku ({desc})...[/cyan]")
        events = fetch_from_endpoint(code)
    else:
        console.print("[red]Opzione non valida.[/red]")
        return

    if not events:
        console.print("[yellow]Nessun evento trovato per la selezione.[/yellow]")
        return

    console.print(f"\n[bold green]✔ Trovati {len(events)} eventi/flussi disponibili![/bold green]\n")

    table = Table(title="Eventi Trovati", show_header=True, header_style="bold magenta")
    table.add_column("N°", style="bold cyan", width=4)
    table.add_column("Titolo Evento / Canale", style="bold")
    table.add_column("Formato", style="yellow")
    table.add_column("DRM / Chiave", style="dim")

    for idx, ev in enumerate(events, 1):
        has_key = "ClearKey OK" if ev["key"] else ("In Chiaro" if ev["stream_type"] != "Acestream" else "-")
        table.add_row(str(idx), ev["title"], ev["stream_type"], has_key)

    console.print(table)

    scelta_ev = Prompt.ask("\nInserisci i numeri da aggiungere a test.json (es. '1 3', 'tutti', o '0' per annullare)", default="0").strip().lower()
    if scelta_ev == "0" or not scelta_ev:
        return

    to_import = []
    if scelta_ev == "tutti":
        to_import = events
    else:
        for p in scelta_ev.split():
            if p.isdigit() and 1 <= int(p) <= len(events):
                to_import.append(events[int(p) - 1])

    if not to_import:
        console.print("[red]Nessun numero valido selezionato.[/red]")
        return

    from dazn_navigator2.cli.events_cmds import detect_warp_from_stream

    imported_count = 0
    for ev in to_import:
        console.print(f"\n[bold yellow]Configurazione evento:[/bold yellow] {ev['title']}")
        default_title = ev['title']
        full_stream_url = ev['mpd']

        if detect_warp_from_stream(url=full_stream_url, title=default_title):
            if "(WARP)" not in default_title:
                default_title = f"{default_title} (WARP)"
        else:
            default_title = re.sub(r'\s*\(WARP\)\s*', ' ', default_title, flags=re.IGNORECASE).strip()

        final_title = default_title

        full_raw = f"{ev['mpd']}|{ev['key']}" if ev['key'] else ev['mpd']
        entry = parse_evento_da_link(full_raw, final_title)
        
        if not entry:
            entry = {
                'name': final_title,
                'image': ev.get('thumbnail') or '',
                'start': '',
                'end': '',
                'mpd': ev['mpd'],
                'key': ev['key'],
                'ua': DEFAULT_UA,
                'type': 'evento'
            }

        add_event(CATEGORIA_EVENTI, entry)
        console.print(f"[green]✔ Aggiunto a '{CATEGORIA_EVENTI}': {entry['name']}[/green]")
        imported_count += 1

    if imported_count > 0:
        pubblica(f"dazn2: importati {imported_count} eventi live da Heroku in EVENTI")
        console.print(f"\n[bold green]✔ Operazione completata! {imported_count} eventi salvati e sincronizzati con il Sito Web (API).[/bold green]")
