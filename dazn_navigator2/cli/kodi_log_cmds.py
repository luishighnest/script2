import os
import re
import base64
import json
import urllib.parse
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt

from dazn_navigator2.cli.eventi_cmds import add_event, pubblica
from dazn_navigator2.cli.aggiungi_cmds import CATEGORIA_EVENTI

console = Console()

def get_kodi_log_path() -> Path:
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        p = Path(appdata) / 'Kodi' / 'kodi.log'
        if p.exists():
            return p
    home = Path.home()
    candidates = [
        home / 'AppData' / 'Roaming' / 'Kodi' / 'kodi.log',
        Path(r'C:\Users\user\AppData\Roaming\Kodi\kodi.log')
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]

def extract_from_kodi_log():
    log_path = get_kodi_log_path()
    if not log_path.exists():
        console.print(f"[red]File kodi.log non trovato in: {log_path}[/red]")
        return None

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        console.print(f"[red]Errore durante la lettura di kodi.log: {e}[/red]")
        return None

    mpd_url = None
    kid = None
    key = None
    ua = None

    # 1. Scansione prioritaria: cerca il blocco base64 risolto (che contiene sia MPD che KID:KEY)
    for line in reversed(lines):
        m_mandra = re.search(r'(?:MyResolver:[^-\n\r]+-\s*|parIn=)([A-Za-z0-9%+/=]{60,})', line)
        if m_mandra:
            raw_b64 = m_mandra.group(1).strip()
            if '%' in raw_b64:
                raw_b64 = urllib.parse.unquote(raw_b64)
            try:
                decoded = base64.b64decode(raw_b64).decode('utf-8', errors='ignore')
                if '.mpd' in decoded:
                    if '|' in decoded:
                        parts = decoded.split('|')
                        cand_mpd = parts[0].strip()
                        raw_k = parts[1].strip()
                        if ':' in raw_k:
                            kp = raw_k.split(':')
                            kid = kp[0].strip()
                            key = kp[1].strip()
                            mpd_url = cand_mpd
                            break
                    elif not mpd_url:
                        mpd_url = decoded.strip()
            except Exception:
                pass

        if not ua:
            m_ua = re.search(r'MANDRA_RESOLVE:\s*UA:\s*([^\n\r]+)', line)
            if m_ua:
                raw_ua = m_ua.group(1).strip()
                ua = urllib.parse.unquote(raw_ua)

    # 2. Fallback: se non ancora trovato MPD o chiavi
    if not mpd_url:
        for line in reversed(lines):
            m_vp = re.search(r'VideoPlayer::OpenFile:\s*(https?://[^\s]+\.mpd[^\s]*)', line)
            if m_vp:
                mpd_url = m_vp.group(1).strip()
                break

    if not (kid and key):
        for line in reversed(lines):
            m_keys = re.search(r'([0-9a-fA-F]{32}):([0-9a-fA-F]{32})', line)
            if m_keys:
                kid = m_keys.group(1).strip()
                key = m_keys.group(2).strip()
                break

    if not mpd_url:
        console.print("[red]Nessun link MPD trovato nei log recenti di Kodi.[/red]")
        return None

    return {
        'mpd': mpd_url,
        'kid': kid,
        'key': key,
        'ua': ua
    }

def run_kodi_log_extraction():
    console.print("\n[bold magenta]=== ESTRAZIONE DA KODI.LOG ===[/bold magenta]")
    log_path = get_kodi_log_path()
    console.print(f"[dim]Lettura log: {log_path}[/dim]")

    data = extract_from_kodi_log()
    if not data:
        return

    mpd_url = data['mpd']
    kid = data['kid']
    key = data['key']
    ua = data.get('ua')

    # Unione MPD e ClearKey: ?ck=base64(json) o &ck=...
    if kid and key:
        ck_dict = {kid: key}
        ck_json = json.dumps(ck_dict, separators=(',', ':'))
        ck_b64 = base64.b64encode(ck_json.encode('utf-8')).decode('utf-8')
        ck_param = urllib.parse.quote(ck_b64, safe='')
        
        separator = '&' if '?' in mpd_url else '?'
        full_united_link = f"{mpd_url}{separator}ck={ck_param}"
        key_str = f"{kid}:{key}"
    else:
        full_united_link = mpd_url
        key_str = ""

    console.print("\n[bold green]Link generato:[/bold green]")
    console.print(f"[cyan]{full_united_link}[/cyan]\n")

    if key_str:
        console.print(f"[dim]Chiave ClearKey:[/dim] [yellow]{key_str}[/yellow]")
    if ua:
        console.print(f"[dim]User-Agent:[/dim] [dim]{ua}[/dim]")

    # Chiede il titolo dell'evento
    titolo = Prompt.ask("\nInserisci il titolo dell'evento", default="").strip()
    if not titolo:
        console.print("[yellow]Operazione annullata: nessun titolo specificato.[/yellow]")
        return

    from dazn_navigator2.cli.events_cmds import detect_warp_from_stream
    if detect_warp_from_stream(url=mpd_url, title=titolo):
        if "(WARP)" not in titolo:
            titolo = f"{titolo} (WARP)"
    else:
        titolo = re.sub(r'\s*\(WARP\)\s*', ' ', titolo, flags=re.IGNORECASE).strip()

    entry = {
        'name': titolo,
        'image': 'https://image.discovery.indazn.com/eu/v3/eu/none/dazn_default_cover.jpg',
        'start': '',
        'end': '3000-01-01T00:00:00Z',
        'mpd': mpd_url,
        'key': key_str,
        'ua': ua or '',
        'type': 'canale'
    }

    add_event(CATEGORIA_EVENTI, entry)
    console.print("\n[green]✓ Evento aggiunto con successo a '%s': %s[/green]" % (CATEGORIA_EVENTI, entry['name']))
    pubblica("dazn2: aggiunto da kodi.log '%s' a EVENTI" % entry['name'])
