"""Aggiunta manuale di un evento a test.json partendo da un link incollato.

Il link puo' arrivare in moltissimi formati (wrapper glitch autoupdate, MPD
grezzo, ClearKey JSON, coppie kid:key, JSON di un intero evento, base64...).
parse_evento_da_link() individua MPD + chiavi + eventuali token e restituisce
un dict con gli STESSI campi usati dai canali in test.json:
    name, image, start, end, mpd, key, ua
piu' il campo 'type' (canale/evento/vod) che l'addon usa per classificare in modo
deterministico la voce. Il dazn-token viene incorporato NEL path dell'URL mpd
(formato @JWT/... degli altri eventi di test.json): addon e sito lo leggono
dall'URL. L'entry viene salvata nella categoria "EVENTI" (imposto dal chiamante).
"""
import base64
import json
import re
import urllib.parse

from rich.console import Console
from rich.prompt import Prompt

from dazn_navigator2.cli.eventi_cmds import add_event, pubblica

console = Console()

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")

CATEGORIA_EVENTI = "EVENTI"

END_CANALE = "3000-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# utilita
# ---------------------------------------------------------------------------

def _normalize_key(key_field):
    """Riduce il campo key a una singola coppia KID:KEY (formato test.json)."""
    parts = [p.strip() for p in (key_field or '').split(':') if p.strip()]
    if len(parts) >= 2:
        return '%s:%s' % (parts[0], parts[1])
    return ''


def _embed_token(mpd, token):
    """Incorpora il dazn-token DENTRO l'URL mpd come '@TOKEN/' nel path,
    esattamente come gli altri contenuti di test.json (Radio TV, LALIGA, Live TV:
    https://host/@eyJ.../path/stream.mpd). Il campo separato dazn_token NON fa
    parte del formato test.json: l'addon e il sito leggono il token dall'URL.
    Ritorna l'URL invariato se un token e' gia' presente (path @... o ?dazn-token=)."""
    token = (token or '').strip()
    if not token:
        return mpd
    if 'dazn-token=' in mpd:
        return mpd
    if '://' in mpd:
        proto, rest = mpd.split('://', 1)
        if '/' in rest:
            host, path = rest.split('/', 1)
            if path.startswith('@'):
                return mpd
            return '%s://%s/@%s/%s' % (proto, host, token, path)
        return mpd
    return mpd


def _guess_type(mpd, name, end=''):
    """Indovina la classificazione per l'addon: vod / canale / evento."""
    m = (mpd or '').lower()
    n = (name or '').lower()
    e = (end or '')
    if any(x in m for x in ('/vod', '-vod', 'dca-ac-vod', 'highlightauto')):
        return 'vod'
    if 'dazn-linear' in m or n in ('dazn 1', 'dazn1', 'dazn 2', 'dazn2'):
        return 'canale'
    if e.startswith('3000') or e.startswith('2999'):
        return 'canale'
    return 'evento'


# ---------------------------------------------------------------------------
# utilita (parsing)
# ---------------------------------------------------------------------------

def _is_hex(s):
    s = (s or '').strip()
    return bool(s) and len(s) % 2 == 0 and re.fullmatch(r'[0-9a-fA-F]+', s) is not None


def _to_hex(val):
    val = (val or '').strip()
    if not val:
        return ''
    if _is_hex(val):
        return val.lower()
    # prova base64 -> hex
    try:
        pad = val + '=' * (-len(val) % 4)
        b = base64.b64decode(pad, validate=False)
        if b and 8 <= len(b) <= 64:
            return b.hex()
    except Exception:
        pass
    return val.lower()


def _b64_maybe_json(text):
    """Se text e' base64 di un JSON, ritorna il JSON decodificato, altrimenti None."""
    try:
        pad = text + '=' * (-len(text) % 4)
        raw = base64.b64decode(pad, validate=False)
        s = raw.decode('utf-8', 'replace')
        if s.strip().startswith(('[', '{')):
            return s
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# estrazione chiavi (ClearKey)
# ---------------------------------------------------------------------------

def _keys_da_json_obj(o):
    """Estrae (kid, key) da un dict ClearKey."""
    kid = o.get('keyId') or o.get('kid') or o.get('KID') or o.get('kId') or ''
    k = o.get('key') or o.get('k') or o.get('Key') or ''
    if kid or k:
        return [(_to_hex(kid), _to_hex(k))]
    return []


def _extract_keys(text):
    """Ritorna lista di (kid_hex, key_hex) trovati in text, in vari formati."""
    keys = []
    t = text or ''

    # 1) array/blob JSON ClearKey: [{"keyId":..,"key":..}, ...] o oggetto singolo
    i = t.find('[')
    if i >= 0:
        depth, end = 0, -1
        for j in range(i, len(t)):
            if t[j] == '[':
                depth += 1
            elif t[j] == ']':
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end > i:
            try:
                arr = json.loads(t[i:end + 1])
                if isinstance(arr, list):
                    for o in arr:
                        if isinstance(o, dict):
                            keys += _keys_da_json_obj(o)
                elif isinstance(arr, dict):
                    keys += _keys_da_json_obj(arr)
            except Exception:
                pass
    j = t.find('{')
    if j >= 0 and not keys:
        depth, end = 0, -1
        for jj in range(j, len(t)):
            if t[jj] == '{':
                depth += 1
            elif t[jj] == '}':
                depth -= 1
                if depth == 0:
                    end = jj
                    break
        if end > j:
            try:
                obj = json.loads(t[j:end + 1])
                if isinstance(obj, dict):
                    keys += _keys_da_json_obj(obj)
            except Exception:
                pass

    # 1b) dict base64 dentro parametri URL es. ?ck=<base64_encoded_json> o ?key=
    for param in re.findall(r'[?&](?:ck|key|keys|clearkey)=([^&\s]+)', t):
        try:
            unquoted = urllib.parse.unquote(param)
            s = _b64_maybe_json(unquoted)
            if s:
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    # formato {"KID_HEX": "KEY_HEX", ...} o {"keys": [...]}
                    for k_id, k_val in parsed.items():
                        if isinstance(k_val, str) and len(k_id) >= 8 and len(k_val) >= 8:
                            keys.append((_to_hex(k_id), _to_hex(k_val)))
                        elif isinstance(k_val, list):
                            for o in k_val:
                                if isinstance(o, dict):
                                    keys += _keys_da_json_obj(o)
                elif isinstance(parsed, list):
                    for o in parsed:
                        if isinstance(o, dict):
                            keys += _keys_da_json_obj(o)
        except Exception:
            pass

    # 2) base64 che nasconde un JSON nel testo
    cand = re.findall(r'[A-Za-z0-9+/=]{16,}', t)
    for c in cand:
        try:
            s = _b64_maybe_json(c)
            if s:
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    for k_id, k_val in parsed.items():
                        if isinstance(k_val, str) and len(k_id) >= 8 and len(k_val) >= 8:
                            keys.append((_to_hex(k_id), _to_hex(k_val)))
                        elif isinstance(k_val, list):
                            for o in k_val:
                                if isinstance(o, dict):
                                    keys += _keys_da_json_obj(o)
                elif isinstance(parsed, list):
                    for o in parsed:
                        if isinstance(o, dict):
                            keys += _keys_da_json_obj(o)
        except Exception:
            pass

    # 3) coppie kid:key / kid|key (hex), anche multiple separate da spazi o virgole
    for mm in re.finditer(r'(?<![0-9a-fA-F])([0-9a-fA-F]{8,})(?::|\|)([0-9a-fA-F]{8,})(?![0-9a-fA-F])', t):
        keys.append((mm.group(1).lower(), mm.group(2).lower()))

    # 3b) resolver style: keyid=<hex>&key=<hex> (es. clearkey-base64.herokuapp.com)
    kids = re.findall(r'(?:^|[?&])(?:keyid|kid)=([0-9a-fA-F]{8,})', t, re.I)
    ks = re.findall(r'(?:^|[?&])(?:key)=([0-9a-fA-F]{8,})', t, re.I)
    for a, b in zip(kids, ks):
        keys.append((_to_hex(a), _to_hex(b)))

    # dedupe mantenendo l'ordine
    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


# ---------------------------------------------------------------------------
# estrazione MPD + token
# ---------------------------------------------------------------------------

def _extract_mpd(text):
    """Trova l'URL MPD tra vari formati possibili."""
    # wrapper con ?url=<enc>
    m = re.search(r'[?&]url=([^&\s]+)', text)
    if m:
        return urllib.parse.unquote(m.group(1))
    # JSON con campo mpd/laurl/manifest
    j = text.find('{')
    if j >= 0:
        try:
            depth, end = 0, -1
            for jj in range(j, len(text)):
                if text[jj] == '{':
                    depth += 1
                elif text[jj] == '}':
                    depth -= 1
                    if depth == 0:
                        end = jj
                        break
            if end > j:
                obj = json.loads(text[j:end + 1])
                for f in ('mpd', 'laurl', 'manifest', 'url', 'playUrl', 'play_url'):
                    if isinstance(obj.get(f), str) and obj[f].startswith('http'):
                        return obj[f]
        except Exception:
            pass
    # URL .mpd grezzo
    m = re.search(r'https?://[^\s"\'<>]+\.mpd(?:\?[^)\]\s"\'<>]*)?', text)
    if m:
        return m.group(0)
    # qualunque URL http
    m = re.search(r'https?://[^\s"\'<>]+', text)
    if m:
        return m.group(0)
    return ''


def _extract_token(text):
    """Estrae un dazn-token / token dagli eventuali parametri del link."""
    for pat in (r'[?&]dazn-token=([^&\s]+)', r'[?&]token=([^&\s]+)'):
        m = re.search(pat, text)
        if m:
            return urllib.parse.unquote(m.group(1))
    return ''


def _extract_image(text):
    m = re.search(r'https?://[^\s"\'<>]+\.(?:png|jpe?g|webp)', text)
    return m.group(0) if m else ''


# ---------------------------------------------------------------------------
# parser principale
# ---------------------------------------------------------------------------

def parse_evento_da_link(raw, title):
    """Converte un link incollato (qualsiasi formato) in un entry test.json.

    Ritorna il dict pronto per add_event(), oppure None se non si trova un MPD.
    """
    # rimuove TUTTI gli spazi/a-capo: gli URL lunghi incollati dal terminale
    # arrivano spesso con ritorni a capo (wrap) che troncherebbero il parsing
    raw = re.sub(r'\s+', '', raw or '')
    if not raw:
        return None

    title = (title or '').strip()

    # se e' gia' un JSON completo di un evento, integra i campi mancanti
    if raw.startswith('{'):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and (obj.get('mpd') or obj.get('url')):
                mpd = obj.get('mpd') or obj.get('url') or ''
                if not mpd and obj.get('laurl'):
                    mpd = obj['laurl']
                # usa la chiave gia' presente nel JSON cosi' com'e' (evita re-processing)
                key = obj.get('key') or ''
                if not key:
                    key = ':'.join('%s:%s' % k for k in _extract_keys(json.dumps(obj)))
                # formato test.json perfettamente leggibile da addon e sito:
                # token nel path URL (campo dazn_token separato NON fa parte del formato),
                # key normalizzata a singola coppia KID:KEY, tipo dichiarato per l'addon.
                mpd = _embed_token(mpd, obj.get('dazn_token') or _extract_token(mpd))
                tipo = (str(obj.get('type') or '')).lower()
                if tipo not in ('canale', 'evento', 'vod'):
                    tipo = _guess_type(mpd, title or obj.get('name') or '', obj.get('end') or '')
                entry = {
                    'name': title or obj.get('name') or 'Evento',
                    'image': obj.get('image') or _extract_image(mpd),
                    'start': obj.get('start') or '',
                    'end': obj.get('end') or '',
                    'mpd': mpd,
                    'key': _normalize_key(key),
                    'ua': obj.get('ua') or DEFAULT_UA,
                    'type': tipo,
                }
                if tipo == 'canale' and not entry['end']:
                    entry['end'] = END_CANALE
                return entry
        except Exception:
            pass

    mpd = _extract_mpd(raw)
    if not mpd:
        return None

    # raccoglie le chiavi da tutto il testo incollato
    keys = _extract_keys(raw)
    # nei wrapper (es. glitch autoupdate) il key e' un parametro ?key=<enc>;
    # decodificalo e cercaci dentro le chiavi (spesso e' un JSON ClearKey encodato)
    mk = re.search(r'[?&]key=([^&\s]+)', raw)
    if mk:
        try:
            keys += _extract_keys(urllib.parse.unquote(mk.group(1)))
        except Exception:
            pass
    # dedupe
    seen, uniq = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    key = _normalize_key(':'.join('%s:%s' % k for k in uniq))

    # formato test.json: token nel path URL, key singola KID:KEY, tipo dichiarato
    mpd = _embed_token(mpd, _extract_token(raw))
    tipo = _guess_type(mpd, title, '')
    entry = {
        'name': title or 'Evento',
        'image': _extract_image(raw),
        'start': '',
        'end': '',
        'mpd': mpd,
        'key': key,
        'ua': DEFAULT_UA,
        'type': tipo,
    }
    if tipo == 'canale' and not entry['end']:
        entry['end'] = END_CANALE
    return entry


# ---------------------------------------------------------------------------
# flusso interattivo (tasto 10)
# ---------------------------------------------------------------------------

def _leggi_link():
    """Legge il link: se incollato usa quello, altrimenti appunti, altrimenti link.txt.

    Gli URL wrapper glitch sono lunghissimi (~1000+ caratteri) e incollati a mano
    nel prompt della console vengono troncati. Meglio copiare il link (Ctrl+C) e
    lasciare il prompt vuoto: viene letto direttamente dagli appunti, integro.
    Alternativa: salvare il link in DAZN1/link.txt e premere Invio al prompt vuoto.
    """
    link = Prompt.ask("Link MPD (incolla, o vuoto=appunti/link.txt)", default="").strip()
    if link:
        return link
    # 1) appunti
    try:
        import pyperclip
        cb = (pyperclip.paste() or "").strip()
        if cb.startswith("http"):
            console.print("[dim]Usato il link dagli appunti.[/dim]")
            return cb
    except Exception:
        pass
    # 2) file link.txt nella root del progetto
    try:
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent.parent / "link.txt"
        if p.exists():
            txt = p.read_text(encoding="utf-8-sig").strip()
            if txt.startswith("http"):
                console.print("[dim]Usato il link da link.txt.[/dim]")
                return txt
    except Exception:
        pass
    return ''


def aggiungi_da_link():
    console.print("\n[bold magenta]=== AGGIUNGI EVENTO A test.json (categoria EVENTI) ===[/bold magenta]")
    console.print("[dim]Formato accettati: wrapper glitch, MPD grezzo, ClearKey JSON, coppie kid:key.[/dim]")
    console.print("[dim]Suggerito: copia il link con Ctrl+C e premi Invio al prompt vuoto (evita troncamenti).[/dim]")
    title = Prompt.ask("Titolo evento", default="").strip()
    if not title:
        console.print("[red]Titolo obbligatorio.[/red]")
        return
    link = _leggi_link()
    if not link:
        console.print("[red]Link obbligatorio.[/red]")
        return

    from dazn_navigator2.cli.events_cmds import detect_warp_from_stream
    if detect_warp_from_stream(url=link, title=title):
        if "(WARP)" not in title:
            title = f"{title} (WARP)"
    else:
        # Assicura che gli stream HLS/Standard non abbiano residui di (WARP)
        title = re.sub(r'\s*\(WARP\)\s*', ' ', title, flags=re.IGNORECASE).strip()

    entry = parse_evento_da_link(link, title)
    if not entry or not entry.get('mpd'):
        console.print("[red]Impossibile estrarre un MPD dal link incollato.[/red]")
        return

    if not entry.get('key'):
        console.print("[yellow]Attenzione: nessuna chiave (key) trovata nel link.[yellow]")
        console.print("[yellow]L'evento sara' salvato senza DRM key (potrebbe non riprodursi).[/yellow]")

    # Conferma/regola il tipo (canale/evento/vod) per la classificazione addon
    types = ['canale', 'evento', 'vod']
    if not entry.get('type'):
        entry['type'] = 'evento'
    cur_type = entry['type'] if entry['type'] in types else 'evento'
    scelta = Prompt.ask("Tipo contenuto", choices=types, default=cur_type)
    entry['type'] = scelta

    # Estrazione e visualizzazione scadenza token / link
    from dazn_navigator2.services.playlist_ed import token_expiry
    from datetime import datetime

    token_str = _extract_token(link)
    if not token_str and '@' in entry.get('mpd', ''):
        try:
            token_str = entry['mpd'].split('@', 1)[1].split('/', 1)[0]
        except Exception:
            pass
    if not token_str:
        # Controlla se c'è un token/epoch nel path dell'URL (es. v~1-0-0_e~1788039920... o tend:...)
        m_path_token = re.search(r'([_~]e~\d{10}[_~a-zA-Z0-9-]*|tend:\d{10}[^\s/?#]*)', entry.get('mpd', ''))
        if m_path_token:
            token_str = m_path_token.group(1)

    scadenza = token_expiry(token_str) if token_str else None
    if scadenza is not None:
        scad_str = scadenza.strftime('%d/%m/%Y %H:%M')
        stato = '[green]✓[/green]' if scadenza > datetime.now() else '[red]SCADUTO[/red]'
    else:
        scad_str = 'non determinabile'
        stato = '[yellow]?[/yellow]'

    console.print("")
    console.print(f"[bold]{entry['name']}[/bold] {stato}")
    console.print(f"[cyan]Scadenza link: [bold]{scad_str}[/bold][/cyan]")
    console.print("")

    add_event(CATEGORIA_EVENTI, entry)
    console.print("[green]Aggiunto a '%s': %s[/green]" % (CATEGORIA_EVENTI, entry['name']))
    console.print("[dim]MPD: %s[/dim]" % entry['mpd'][:120])
    console.print("[dim]KEY: %s[/dim]" % (entry.get('key') or '-'))
    console.print("[dim]TYPE: %s[/dim]" % entry['type'])
    pubblica("dazn2: aggiunto %s '%s' a EVENTI" % (entry['type'], entry['name']))
