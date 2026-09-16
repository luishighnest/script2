"""Genera guida_tv_sky.json per il sito zadonkais usando esattamente la stessa
EPG XMLTV dell'addon Kodi (stessa sorgente, stesso filtro canali Sky e stessi orari
in formato 'Ora HH:MM titolo' + programma successivo). Nessuna immagine, solo testo."""

import gzip
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from rich.console import Console

console = Console()

HTDOCS_REPO = Path(r"C:\Users\user\Desktop\htdocs")
NEXT_REPO = Path(r"C:\Users\user\Desktop\next")
GIT_EXE = r"C:\Program Files\Git\cmd\git.exe"

EPG_URL = 'https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz'
API_UA = 'Kodi/19.0 (Windows NT 10.0; Win64; x64) App_Bitness/64 Version/19.0-Matrix'
EPG_KEEP_HOURS = 6

# Stesso mapping cid -> nome/categoria del sito in sky_cmds.SKY_CHANNELS_DEF
from dazn_navigator2.cli.sky_cmds import SKY_CHANNELS_DEF

# Nomi display dell'addon (SKY_DEFS, default.py:315) usati per i candidati EPG.
# Diversi dal nome sito: History vs Sky History, Comedy Central vs Sky Comedy Central,
# MTV vs Sky Mtv, Sky Uno vs SKY UNO...
SKY_DEFS_NAMES = {
    'tg24': 'Sky TG 24',
    'skyuno': 'Sky Uno',
    'skyunoplus': 'Sky Uno +1',
    'skyatlantic': 'Sky Atlantic',
    'skyserie': 'Sky Serie',
    'skycollection': 'Sky Collection',
    'skyinvestigation': 'Sky Investigation',
    'skyadventure': 'Sky Adventure',
    'skycrime': 'Sky Crime',
    'skydocumentaries': 'Sky Documentaries',
    'skynature': 'Sky Nature',
    'historychannel': 'History',
    'comedycentral': 'Comedy Central',
    'skyarte': 'Sky Arte',
    'mtv': 'MTV',
    'skysportuno': 'Sky Sport Uno',
    'skysport24': 'Sky Sport 24',
    'skysportarena': 'Sky Sport Arena',
    'skysportbasket': 'Sky Sport Basket',
    'skysportcalcio': 'Sky Sport Calcio',
    'skysportf1': 'Sky Sport F1',
    'skysportgolf': 'Sky Sport Golf',
    'skysportlegend': 'Sky Sport Legend',
    'skysportmax': 'Sky Sport Max',
    'skysportmix': 'Sky Sport Mix',
    'skysportmotogp': 'Sky Sport MotoGP',
    'skysporttennis': 'Sky Sport Tennis',
}


def _epg_candidates(cid):
    """Replica _epg_candidates dell'addon (default.py:1764), ordinati
    deterministicamente: nome base, poi hd/fhd/ultra hd, poi varianti extra."""
    cands = [cid.lower()]
    disp = SKY_DEFS_NAMES.get(cid, '')
    if disp:
        cands.append(' '.join(disp.lower().split()))
    if cid == 'tg24':
        cands.append('sky tg24')
    if cid == 'mtv':
        cands.append('mtv hd')
        cands.append('mtv music')
    if cid.startswith('skysport'):
        rest = re.match(r'^skysport(.+)$', cid)
        rest = rest.group(1) if rest else ''
        base = 'sky sport ' + rest
        cands.append(base)
        cands += [base + ' hd', base + ' fhd', base + ' ultra hd']
    return cands


def _want_set():
    """Set di tutti i candidati EPG, come `want` dell'addon."""
    want = set()
    for citem in SKY_CHANNELS_DEF:
        want |= set(_epg_candidates(citem['id']))
    return want


def _epg_dt(val):
    """Converte il timestamp XMLTV nell'orario locale come fa l'addon (_epg_dt: UTC + 2h)."""
    if not val:
        return None
    m = re.match(r'(\d{14})', val)
    if not m:
        return None
    try:
        s = m.group(1)
        return datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]),
                        int(s[8:10]), int(s[10:12]), int(s[12:14])) + timedelta(hours=2)
    except ValueError:
        return None


def _epg_parse(raw):
    """Replica _epg_parse dell'addon (default.py:1799): tiene solo i canali Sky del sito."""
    root = ET.fromstring(raw)
    want = _want_set()
    chmap = {}
    for ch in root.findall('channel'):
        chid = (ch.get('id') or '').lower()
        if not chid:
            continue
        chmap.setdefault(chid, chid)
        for dn in ch.findall('display-name'):
            nm = ' '.join((dn.text or '').split()).lower()
            if nm:
                chmap.setdefault(nm, chid)
    keep = set()
    for k, v in chmap.items():
        if k in want or v in want:
            keep.add(v)
    progs = {}
    oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_win = oggi - timedelta(hours=12)
    end_win = oggi + timedelta(days=2)
    for p in root.findall('programme'):
        chid = (p.get('channel') or '').lower()
        if chid not in keep:
            continue
        s = _epg_dt(p.get('start'))
        e = _epg_dt(p.get('stop'))
        if not s or not e:
            continue
        if e < start_win or s > end_win:
            continue
        t = p.find('title')
        title = ' '.join((t.text or '').split()) if t is not None else ''
        progs.setdefault(chid, []).append((s, e, title))
    for chid in progs:
        progs[chid].sort(key=lambda x: x[0])
    return {'chmap': chmap, 'progs': progs}


def _epg_chid(cid, epg):
    """Replica _epg_chid dell'addon (default.py:1920)."""
    if not epg:
        return None
    for c in _epg_candidates(cid):
        if c in epg['chmap']:
            return epg['chmap'][c]
    return None


def _sky_name(cid):
    """Nome canale come appare in sky.json."""
    for c in SKY_CHANNELS_DEF:
        if c['id'] == cid:
            return c['name']
    return cid


def _sky_categoria(cid):
    """Categoria del sito: 'Sport' o 'Intrattenimento'."""
    for c in SKY_CHANNELS_DEF:
        if c['id'] == cid:
            return 'Sport' if c['group'] == 'Sky Sport' else 'Intrattenimento'
    return 'Sport'


def _build_programmi(cid, epg):
    """Lista programmi in formato sito [{ora, titolo, descrizione, immagine}] per il giorno corrente."""
    chid = _epg_chid(cid, epg)
    if not chid:
        return []
    progs = epg['progs'].get(chid, [])
    if not progs:
        return []
    oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    giorno = oggi
    domani = oggi + timedelta(days=1)
    out = []
    for s, e, title in progs:
        if not title:
            continue
        if s < giorno or s >= domani:
            continue
        out.append({
            'ora': '%02d:%02d' % (s.hour, s.minute),
            'titolo': title,
            'descrizione': '',
            'immagine': ''
        })
    return out


def sync_guida_site():
    """Scarica l'XMLTV dell'addon, ricostruisce guida_tv_sky.json solo coi canali sky.json
    e lo pubblica sul repo zadonkais. Nessuna pubblicazione se il feed non e' disponibile."""
    console.print("\n[bold cyan]═══ Guida TV Sky sito (EPG addon) ═══[/bold cyan]")

    try:
        r = requests.get(EPG_URL, timeout=90, headers={'User-Agent': API_UA})
        r.raise_for_status()
        raw = r.content
    except Exception as e:
        console.print(f"[red]Errore download XMLTV da epgshare01: {e}[/red]")
        return

    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass

    try:
        epg = _epg_parse(raw)
    except Exception as e:
        console.print(f"[red]Errore parsing XMLTV: {e}[/red]")
        return

    # Preserva le voci NON-Sky presenti nella guida attuale (es. DAZN 1).
    # Un'eventuale vecchia voce con vecchio nome (es. "MTV", "Comedy Central") crea
    # collisioni col matching per sottostringa del sito -> NON va preservata.
    sky_norm = {c['name'].lower().replace(' ', '') for c in SKY_CHANNELS_DEF}
    guide_path = HTDOCS_REPO / 'guida_tv_sky.json'
    existing = []
    if guide_path.exists():
        try:
            existing = json.loads(guide_path.read_text(encoding='utf-8'))
        except Exception:
            existing = []

    def _is_sky_like(name):
        n = (name or '').lower().replace(' ', '')
        if not n:
            return True
        for sn in sky_norm:
            if n == sn or n in sn or sn in n:
                return True
        return False

    nuova = []
    for entry in existing:
        if isinstance(entry, dict) and not _is_sky_like(entry.get('canale', '')):
            nuova.append(entry)

    aggiunti = 0
    for c in SKY_CHANNELS_DEF:
        programmi = _build_programmi(c['id'], epg)
        entry = {
            'canale': c['name'],
            'categoria': _sky_categoria(c['id']),
            'programmi': programmi,
            'aggiornato': datetime.now().strftime('%H:%M')
        }
        nuova.append(entry)
        aggiunti += 1

    nuova.sort(key=lambda x: (x.get('categoria', ''), x.get('canale', '')))

    nuova_json_text = json.dumps(nuova, indent=2, ensure_ascii=False)
    guide_path.write_text(nuova_json_text, encoding='utf-8')
    console.print(f"[green]Guida TV generata: {len(nuova)} canali ({aggiunti} Sky) in {guide_path}[/green]")

    # Scrittura anche su next/public/guida_tv_sky.json
    next_guide_path = NEXT_REPO / "public" / "guida_tv_sky.json"
    if next_guide_path.parent.exists():
        try:
            next_guide_path.write_text(nuova_json_text, encoding='utf-8')
            console.print(f"[green]Guida TV salvata anche in: {next_guide_path}[/green]")
        except Exception:
            pass

    n_con = sum(1 for x in nuova if x.get('programmi'))
    console.print(f"[cyan]Canali con programmi oggi: {n_con}[/cyan]")

    # Sincronizzazione automatica su Upstash Redis Cloud (Zero Git!)
    console.print("[cyan]Sincronizzazione Guida TV su Upstash Redis Cloud (Zero Git)...[/cyan]")
    ok_redis = False
    try:
        from dazn_navigator2.services.redis_sync import sync_to_upstash
        ok_redis = sync_to_upstash("guida", nuova)
    except Exception:
        pass

    if ok_redis:
        console.print("[bold green][OK] Guida TV sincronizzata istantaneamente su Upstash Redis Cloud![/bold green]")
    else:
        try:
            import requests
            from dazn_navigator2.settings import get_setting
            api_url = get_setting("site_api_url") or "http://localhost:3000/api"
            api_key = get_setting("site_api_key") or "zadonkais_secret_2026"
            requests.post(f"{api_url}/sky", json={"source": "guida", "data": nuova}, headers={"x-api-key": api_key}, timeout=4)
        except Exception:
            pass
        console.print("[green][OK] Guida TV salvata in locale.[/green]")