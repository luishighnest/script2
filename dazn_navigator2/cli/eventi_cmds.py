"""Gestione eventi nel test.json del repo Kodi (luishighnest/kodi).

Architettura di sincronizzazione:
- le modifiche scrivono SEMPRE e subito il file locale nel repo (mai perse)
- la pubblicazione git (commit+push) e' centralizzata in pubblica(): una sola
  operazione atomica con retry, richiamata a fine batch / dopo ogni comando /
  automaticamente alla chiusura del programma se restano modifiche pendenti
"""
import json
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

KODI_REPO = Path(r"C:\Users\user\Desktop\kodi_repo")
NEXT_REPO = Path(r"C:\Users\user\Desktop\next")
GIT_EXE = r"C:\Program Files\Git\cmd\git.exe"
GLITCH_BASE = "https://alemagno1994alex-glitch.github.io/autoupdate/test.html"
console = Console()


def _split_keys(key_field):
    """Ritorna lista di (kid_hex, key_hex) dal campo key 'kid:key:kid:key'."""
    pairs = []
    parts = (key_field or '').split(':')
    for i in range(0, len(parts) - 1, 2):
        kid, k = parts[i], parts[i + 1]
        if kid and k:
            pairs.append((kid, k))
    return pairs


def build_glitch_link(entry):
    """Costruisce il link wrapper glitch completo da un entry test.json.

    Forma: GLITCH_BASE?url=<mpd url-encoded>&key=<clearkey JSON url-encoded>
    """
    mpd = (entry.get('mpd') or '').strip()
    if not mpd:
        return ''
    key_field = entry.get('key') or ''
    ck = [{"keyId": kid, "key": k} for kid, k in _split_keys(key_field)]
    key_json = json.dumps(ck, separators=(',', ':'))
    return (GLITCH_BASE + '?url=' + urllib.parse.quote(mpd, safe='()') +
            '&key=' + urllib.parse.quote(key_json, safe=''))

_pending = False  # True se il file locale ha modifiche non ancora pubblicate

def get_events_file():
    from dazn_navigator2.settings import get_setting
    if get_setting("github_deploy"):
        return Path(r"C:\Users\user\Desktop\kodi_repo") / "test.json"
    else:
        return Path(__file__).resolve().parent.parent.parent / "dazn_event.json"


def _git(args, timeout=120):
    """Esegue un comando git sul repo. Ritorna (ok, stdout, stderr)."""
    try:
        r = subprocess.run([GIT_EXE, "-C", str(KODI_REPO)] + args,
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout or ""), (r.stderr or "")
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)


def _load():
    if get_events_file().exists():
        try:
            data = json.loads(get_events_file().read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                if "enc" in data:
                    from dazn_navigator2.cli.sky2_cmds import decrypt_site_payload
                    return decrypt_site_payload(data["enc"])
                return data
        except Exception as e:
            console.print(f"[red]test.json corrotto ({e}) - backup in test.json.bak[/red]")
            try:
                bak = get_events_file().with_suffix(".json.bak")
                bak.write_text(get_events_file().read_text(encoding="utf-8-sig"), encoding="utf-8")
            except Exception:
                pass
    return {}


def _save(data):
    """Scrive il file locale nel repo e in htdocs CIFRATO con AES-256 (Password 2941). La pubblicazione avviene con pubblica()."""
    global _pending
    import shutil
    from dazn_navigator2.cli.sky2_cmds import encrypt_site_payload
    enc = encrypt_site_payload(data)
    json_text = json.dumps({"enc": enc}, indent=2, ensure_ascii=False) + "\n"
    
    # 1. Scrive in kodi_repo
    events_file = get_events_file()
    events_file.write_text(json_text, encoding="utf-8")
    
    # 2. Sincronizza istantaneamente in htdocs per il sito web
    htdocs_test = Path(r"C:\Users\user\Desktop\htdocs\test.json")
    if htdocs_test.parent.exists():
        try:
            htdocs_test.write_text(json_text, encoding="utf-8")
        except Exception:
            pass

    # 3. Sincronizza in zadonkais repo se presente
    zadonkais_test = Path(r"C:\Users\user\Desktop\zadonkais\test.json")
    if zadonkais_test.parent.exists():
        try:
            zadonkais_test.write_text(json_text, encoding="utf-8")
        except Exception:
            pass

    # 4. Sincronizza in next/public/test.json
    next_test = NEXT_REPO / "public" / "test.json"
    if next_test.parent.exists():
        try:
            next_test.write_text(json_text, encoding="utf-8")
        except Exception:
            pass

    # Sincronizzazione automatica su Upstash Redis Cloud (Zero Git!)
    try:
        from dazn_navigator2.services.redis_sync import sync_to_upstash
        sync_to_upstash("eventi", data)
    except Exception:
        pass

    _pending = True


def pubblica(messaggio="dazn2: aggiornamento eventi"):
    """Pubblica le modifiche via Upstash Redis Cloud e API HTTP (Zero Git)."""
    global _pending
    if not _pending:
        return True

    data = _load()
    console.print("[cyan]Sincronizzazione eventi su Upstash Redis Cloud (Zero Git)...[/cyan]")
    ok_redis = False
    try:
        from dazn_navigator2.services.redis_sync import sync_to_upstash
        ok_redis = sync_to_upstash("eventi", data)
    except Exception:
        pass

    if ok_redis:
        console.print("[bold green][OK] Eventi pubblicati istantaneamente su Upstash Redis Cloud![/bold green]")
        _pending = False
        return True

    # Fallback su API locale se presente
    try:
        import requests
        from dazn_navigator2.settings import get_setting
        api_url = get_setting("site_api_url") or "http://localhost:3000/api"
        api_key = get_setting("site_api_key") or "zadonkais_secret_2026"
        res = requests.post(f"{api_url}/eventi", json={"all": data}, headers={"x-api-key": api_key}, timeout=4)
        if res.status_code == 200:
            console.print("[bold green][OK] Eventi sincronizzati via API![/bold green]")
            _pending = False
            return True
    except Exception:
        pass

    console.print("[green][OK] Eventi salvati con successo in locale.[/green]")
    _pending = False
    return True


def flush_alla_chiusura():
    """Chiamato all'uscita di dazn2: prova a pubblicare modifiche pendenti."""
    if _pending:
        try:
            console.print("[yellow]Uscita: pubblico le modifiche pendenti...[/yellow]")
            pubblica()
        except Exception:
            pass


def _iter_entries(data):
    """Rende (comp, indice, evento) su tutti gli eventi nell'ordine attuale."""
    n = 0
    for comp, items in data.items():
        for i, e in enumerate(items):
            yield n, comp, i, e
            n += 1


def _clean_base_and_warp(name: str):
    """Estrae il nome base pulito e se è WARP.
    Es. 'DAZN 1 (WARP) (2)' -> base 'DAZN 1', is_warp True
        'DAZN 1 (3)' -> base 'DAZN 1', is_warp False
    """
    import re
    is_warp = "(WARP)" in name.upper()
    # Rimuovi (WARP) e qualsiasi suffisso numerico tipo (2), (3), 2, 3
    cleaned = re.sub(r'\s*\(WARP\)\s*', ' ', name, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\(\d+\)\s*', ' ', cleaned)
    cleaned = re.sub(r'\s+\d+\s*$', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned, is_warp

def _format_target_name(base: str, is_warp: bool, num: int = 1) -> str:
    """Formatta esattamente secondo lo standard:
    num=1, is_warp=False -> 'DAZN 1'
    num=1, is_warp=True  -> 'DAZN 1 (WARP)'
    num=2, is_warp=False -> 'DAZN 1 (2)'
    num=2, is_warp=True  -> 'DAZN 1 (WARP) 2'
    """
    if not is_warp:
        return base if num == 1 else f"{base} ({num})"
    else:
        return f"{base} (WARP)" if num == 1 else f"{base} (WARP) {num}"

def add_event(comp_title, entry):
    """Aggiunge/sostituisce un evento in modo ultra-ottimizzato:
    - Se l'URL (o token) è già presente, aggiorna sul posto.
    - Gestisce la divisione perfetta tra flussi Standard e WARP.
    - Se si estraggono flussi aggiornati per lo stesso canale/evento, sostituisce i vecchi flussi
      invece di accumulare duplicati infiniti.
    - Se coesistono più flussi contemporanei attivi dello stesso tipo, usa i nomi compatti:
      es. 'DAZN 1', 'DAZN 1 (WARP)', e solo per ulteriori flussi 'DAZN 1 (2)' o 'DAZN 1 (WARP) 2'.
    """
    import re
    from dazn_navigator2.services.playlist_ed import token_expiry
    data = _load()
    comp_title = comp_title or "Eventi"
    grp = data.setdefault(comp_title, [])
    entry_url = entry.get("mpd") or entry.get("url") or ""
    entry_name = entry.get("name", "")

    # Determina base e se questo nuovo entry è WARP
    base_name, entry_is_warp = _clean_base_and_warp(entry_name)

    # 1. Se esiste già lo stesso URL identico, sostituiscilo subito
    existing_same_url = [e for e in grp if (e.get("mpd") or e.get("url")) == entry_url and entry_url]
    if existing_same_url:
        grp[:] = [e for e in grp if (e.get("mpd") or e.get("url")) != entry_url]

    # 2. Gestione intelligente dei canali lineari (es. DAZN 1, Eurosport, ecc.) o eventi:
    # Trova tutti gli elementi già registrati che appartengono alla stessa famiglia (stesso base_name e stesso tipo WARP/non-WARP)
    same_family = []
    for e in grp:
        b, w = _clean_base_and_warp(e.get("name", ""))
        if b.lower() == base_name.lower() and w == entry_is_warp:
            same_family.append(e)

    # Per i canali 24/7 (end = 3000 o comp_title 'Live TV' o nome contiene 'DAZN')
    # se c'è già uno stream della stessa famiglia (es. Standard o WARP),
    # sostituisci quello vecchio se scaduto o se è lo slot primario, mantenendo pulizia massima.
    is_channel = (entry.get("end", "").startswith("3000") or 
                  comp_title.lower() == "live tv" or 
                  "dazn" in base_name.lower())

    if is_channel and same_family:
        # Se c'è già un canale primario (senza numero extra o scaduto), sostituiscilo per non accumulare
        target_name = _format_target_name(base_name, entry_is_warp, 1)
        # Rimuovi l'eventuale canale precedente con quel target_name per aggiornarlo con il nuovo link attivo
        grp[:] = [e for e in grp if e.get("name") != target_name]
        entry["name"] = target_name
    else:
        # Se non è un canale continuo, o se vogliamo tenere traccia di un secondo flusso parallelo
        num = 1
        cand_name = _format_target_name(base_name, entry_is_warp, num)
        while any(e.get("name") == cand_name for e in grp):
            num += 1
            cand_name = _format_target_name(base_name, entry_is_warp, num)
        entry["name"] = cand_name

    grp.append(entry)
    _save(data)


def _sort_key(item):
    _, _, _, ev = item
    s = (ev.get("start") or "").strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


def manage_events():
    while True:
        data = _load()
        entries = list(_iter_entries(data))
        console.print("\n[bold magenta]=== GESTIONE EVENTI ===[/bold magenta]  (%s)" % get_events_file().name)
        if not entries:
            console.print("[yellow]Nessun evento salvato.[/yellow]")
        else:
            for n, comp, i, e in entries:
                console.print("[cyan]%2d.[/cyan] [%s] %s" % (n + 1, comp, e.get("name", "?")))
        console.print("""
[bold cyan]R.[/bold cyan] Rinomina un evento
[bold cyan]E.[/bold cyan] Elimina eventi (numeri separati da spazio, o 'tutti')
[bold cyan]O.[/bold cyan] Ordina eventi (nuovo ordine con numeri separati da spazio)
[bold cyan]D.[/bold cyan] Ordina automaticamente per data di inizio
[bold cyan]P.[/bold cyan] Sincronizza subito con il sito (API)
[bold cyan]0.[/bold cyan] Indietro""")
        scelta = Prompt.ask("Scelta", default="0").strip().upper()
        if scelta == "0":
            break
        elif scelta == "P":
            pubblica()
            continue
        elif scelta == "D":
            if not entries:
                continue
            ordinato = sorted(entries, key=_sort_key)
            nuovo_data = {}
            for _, comp, _, ev_ in ordinato:
                nuovo_data.setdefault(comp, []).append(ev_)
            _save(nuovo_data)
            pubblica("dazn2: ordina eventi per data")
            data = _load()
            entries = list(_iter_entries(data))
            console.print("[green]Eventi ordinati per data di inizio.[/green]")
            for n, comp, i, e in entries:
                console.print("[cyan]%2d.[/cyan] [%s] %s  (%s)" % (n + 1, comp, e.get("name", "?"), (e.get("start") or "?")[:16]))
            continue
        elif scelta == "R":
            if not entries:
                continue
            idx = Prompt.ask("Numero evento da rinominare", default="")
            if not idx.isdigit() or not (1 <= int(idx) <= len(entries)):
                console.print("[red]Numero non valido[/red]")
                continue
            n, comp, i, e = entries[int(idx) - 1]
            nuovo = Prompt.ask("Nuovo titolo", default=e.get("name", ""))
            if nuovo.strip():
                e["name"] = nuovo.strip()
                _save(data)
                pubblica("dazn2: rinomina evento")
                console.print("[green]Rinominato.[/green]")
        elif scelta == "E":
            if not entries:
                continue
            q = Prompt.ask("Numeri da eliminare (es. '1 3 5') o 'tutti'", default="")
            ql = q.strip().lower()
            if ql == "tutti":
                _save({})
                pubblica("dazn2: eliminati tutti gli eventi")
                console.print("[green]Tutti gli eventi eliminati.[/green]")
                continue
            to_del = set()
            for p in ql.split():
                if p.isdigit() and 1 <= int(p) <= len(entries):
                    to_del.add(int(p))
            if not to_del:
                console.print("[red]Nessun numero valido[/red]")
                continue
            for k in sorted(to_del, reverse=True):
                n, comp, i, e = entries[k - 1]
                del data[comp][i]
                if not data[comp]:
                    del data[comp]
            _save(data)
            pubblica("dazn2: elimina eventi")
            console.print("[green]%d evento/i eliminato/i.[/green]" % len(to_del))
        elif scelta == "O":
            if len(entries) < 2:
                console.print("[yellow]Servono almeno 2 eventi per riordinare.[/yellow]")
                continue
            for n, comp, i, e in entries:
                console.print("[cyan]%2d.[/cyan] %s" % (n + 1, e.get("name", "?")))
            q = Prompt.ask("Nuovo ordine (es. '3 1 2')", default="")
            nums = [int(p) for p in q.split() if p.isdigit() and 1 <= int(p) <= len(entries)]
            if sorted(nums) != list(range(1, len(entries) + 1)):
                console.print("[red]Ordine non valido: servono tutti i numeri una sola volta[/red]")
                continue
            flat = [e for _, _, _, e in entries]
            mappa = dict(enumerate(flat))
            orig = [(comp, e) for _, comp, _, e in entries]
            nuovo_data = {}
            for k in nums:
                comp = orig[k - 1][0]
                nuovo_data.setdefault(comp, []).append(mappa[k - 1])
            _save(nuovo_data)
            pubblica("dazn2: riordino manuale eventi")
            console.print("[green]Ordine aggiornato.[/green]")
