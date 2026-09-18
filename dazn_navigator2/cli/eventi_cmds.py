"""Gestione eventi in dazn_event.json locale (nessun deploy su GitHub)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt

BASE_DIR = Path(__file__).resolve().parent.parent.parent
EVENTS_FILE = BASE_DIR / "dazn_event.json"
console = Console()


def get_events_file(profile_id=None):
    if profile_id:
        return BASE_DIR / f"dazn_event_{profile_id}.json"
    return EVENTS_FILE


def _load(profile_id=None):
    target = get_events_file(profile_id)
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return data
        except Exception as e:
            console.print(f"[red]{target.name} corrotto ({e}) - backup in {target.name}.bak[/red]")
            try:
                bak = target.with_suffix(".json.bak")
                bak.write_text(target.read_text(encoding="utf-8-sig"), encoding="utf-8")
            except Exception:
                pass
    return {}


def _save(data, profile_id=None):
    """Scrive il file locale dazn_event.json (per profilo se indicato) e sincronizza istantaneamente su Upstash Redis."""
    target = get_events_file(profile_id)
    target.write_text(json.dumps(data, indent=3, ensure_ascii=False) + "\n", encoding="utf-8")

    # Sincronizzazione istantanea su Upstash Redis (latenza zero)
    try:
        import requests
        upstash_url = "https://ace-seal-162556.upstash.io"
        upstash_token = "gQAAAAAAAnr8AAIgcDEyZjRkYjEwYmUzZDY0M2RhYjZkNjhmMDFjNGVkMjVmYw"
        headers = {"Authorization": f"Bearer {upstash_token}"}
        payload = json.dumps(data, ensure_ascii=False)
        
        # 1. Se il profilo è mpd, sincronizza sulla chiave dedicata stream:eventi_mpd
        if profile_id == "mpd":
            requests.post(f"{upstash_url}/set/stream:eventi_mpd", headers=headers, data=payload, timeout=4)
        
        # 2. Sincronizza anche per profilo stream:eventi_{profile_id}
        if profile_id:
            requests.post(f"{upstash_url}/set/stream:eventi_{profile_id}", headers=headers, data=payload, timeout=4)
    except Exception:
        pass


def pubblica(messaggio=""):
    """Compatibilita': salva in locale. Nessun deploy GitHub."""
    console.print(f"[green]Salvato in locale ({EVENTS_FILE.name}).[/green]")


def flush_alla_chiusura():
    """Nessuna operazione pendente: tutto e' gia' salvato in locale."""
    pass


def _iter_entries(data):
    n = 0
    for comp, items in data.items():
        for i, e in enumerate(items):
            yield n, comp, i, e
            n += 1


def _clean_base_title(name: str) -> str:
    import re
    cleaned = re.sub(r'\s*\(WARP\)\s*', ' ', name, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\(\d+\)\s*', ' ', cleaned)
    # Rimuovi numero finale solo se NON è un canale lineare noto con numerazione ufficiale (es. DAZN, Eurosport, Sky Sport)
    upper_c = cleaned.upper().strip()
    is_numbered_channel = any(upper_c.startswith(k) or upper_c == k for k in ("DAZN", "EUROSPORT", "SKY SPORT"))
    if not is_numbered_channel:
        cleaned = re.sub(r'\s+\d+\s*$', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Normalizzazione nomi lineari
    if cleaned.upper() == "DAZN":
        cleaned = "DAZN 1"
    elif cleaned.upper() == "EUROSPORT":
        cleaned = "Eurosport 1"
    return cleaned


def _normalize_match_key(s: str) -> str:
    import re
    import unicodedata
    if not s:
        return ""
    # 1. Rimuove COMPLETAMENTE qualsiasi cosa tra parentesi (e il loro contenuto)
    s = re.sub(r'[\(\[\{].*?[\)\]\}]', ' ', s)
    s = s.replace('\ufffd', ' ')
    s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
    s = s.lower()
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\b(vs|v|contro|de|di|el|la|los|las|il|lo|le|i|gli|the|fc|cf|ac|as|calcio|club)\b', ' ', s)
    repl = {'barcellona': 'barcelona', 'siviglia': 'sevilla', 'atletico': 'atletico', 'monaco': 'munich', 'bayern': 'bayern'}
    words = re.findall(r'\b[a-z0-9]{3,}\b', s)
    norm_words = sorted(set(repl.get(w, w) for w in words))
    return ' '.join(norm_words)


def _match_event_keys(k1: str, k2: str) -> bool:
    if not k1 or not k2:
        return False
    if k1 == k2:
        return True
    s1 = set(k1.split())
    s2 = set(k2.split())
    inter = s1.intersection(s2)
    return len(inter) >= 2 or (len(inter) >= 1 and (len(s1) <= 2 or len(s2) <= 2))


def add_event(comp_title, entry, profile_id=None):
    """Aggiunge o aggiorna un evento nella lista ignorando totalmente qualsiasi parentesi."""
    data = _load(profile_id)
    entry_url = entry.get("mpd") or entry.get("url") or ""
    entry_name = entry.get("name", "")

    base_name = _clean_base_title(entry_name)
    entry_norm_key = _normalize_match_key(entry_name)

    # 1. Cerca prima se esiste una scheda vuota (nella categoria o ovunque)
    found_cat = None
    found_idx = -1

    if comp_title and comp_title in data:
        for idx, e in enumerate(data[comp_title]):
            if not (e.get("mpd") or e.get("url")):
                b_key = _normalize_match_key(e.get("name", ""))
                if _match_event_keys(entry_norm_key, b_key):
                    found_cat = comp_title
                    found_idx = idx
                    break

    if found_idx == -1:
        for cat, items in data.items():
            for idx, e in enumerate(items):
                if not (e.get("mpd") or e.get("url")):
                    b_key = _normalize_match_key(e.get("name", ""))
                    if _match_event_keys(entry_norm_key, b_key):
                        found_cat = cat
                        found_idx = idx
                        break
            if found_idx != -1:
                break

    if found_idx != -1 and found_cat:
        target_list = data[found_cat]
        old_item = target_list[found_idx]
        if not entry.get("image") and old_item.get("image"):
            entry["image"] = old_item["image"]
        if not entry.get("start") and old_item.get("start"):
            entry["start"] = old_item["start"]
        if not entry.get("end") and old_item.get("end"):
            entry["end"] = old_item["end"]
        entry["name"] = old_item.get("name") or base_name
        target_list[found_idx] = entry
        _save(data, profile_id)
        return

    # 2. Inserimento normale
    comp_title = comp_title or "Eventi"
    grp = data.setdefault(comp_title, [])

    if entry_url:
        grp[:] = [e for e in grp if (e.get("mpd") or e.get("url")) != entry_url]

    is_channel = (entry.get("end", "").startswith("3000") or 
                  comp_title.lower() in ("canali lineari", "live tv") or 
                  any(k in base_name.lower() for k in ("dazn", "eurosport", "milan tv", "inter tv")))

    if is_channel:
        grp[:] = [e for e in grp if _clean_base_title(e.get("name", "")).lower() != base_name.lower()]
        entry["name"] = base_name
        grp.append(entry)
    else:
        num = 1
        cand_name = base_name
        while any(e.get("name") == cand_name for e in grp):
            num += 1
            cand_name = f"{base_name} ({num})"
        entry["name"] = cand_name
        grp.append(entry)

    _save(data, profile_id)


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
        console.print("\n[bold magenta]=== GESTIONE EVENTI ===[/bold magenta]  (%s)" % EVENTS_FILE.name)
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
[bold cyan]0.[/bold cyan] Indietro""")
        scelta = Prompt.ask("Scelta", default="0").strip().upper()
        if scelta == "0":
            break
        elif scelta == "D":
            if not entries:
                continue
            ordinato = sorted(entries, key=_sort_key)
            nuovo_data = {}
            for _, comp, _, ev_ in ordinato:
                nuovo_data.setdefault(comp, []).append(ev_)
            _save(nuovo_data)
            data = _load()
            entries = list(_iter_entries(data))
            console.print("[green]Eventi ordinati per data di inizio.[/green]")
            for n, comp, i, e in entries:
                console.print("[cyan]%2d.[/cyan] [%s] %s  (%s)" % (n + 1, comp, e.get("name", "?"), (e.get("start") or "?")[:16]))
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
                console.print("[green]Rinominato.[/green]")
        elif scelta == "E":
            if not entries:
                continue
            q = Prompt.ask("Numeri da eliminare (es. '1 3 5') o 'tutti'", default="")
            ql = q.strip().lower()
            if ql == "tutti":
                _save({})
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
            console.print("[green]Ordine aggiornato.[/green]")
