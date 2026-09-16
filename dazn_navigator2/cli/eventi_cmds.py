"""Gestione eventi in dazn_event.json locale (nessun deploy su GitHub)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt

EVENTS_FILE = Path(__file__).resolve().parent.parent.parent / "dazn_event.json"
console = Console()


def get_events_file():
    return EVENTS_FILE


def _load():
    if EVENTS_FILE.exists():
        try:
            data = json.loads(EVENTS_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return data
        except Exception as e:
            console.print(f"[red]dazn_event.json corrotto ({e}) - backup in dazn_event.json.bak[/red]")
            try:
                bak = EVENTS_FILE.with_suffix(".json.bak")
                bak.write_text(EVENTS_FILE.read_text(encoding="utf-8-sig"), encoding="utf-8")
            except Exception:
                pass
    return {}


def _save(data):
    """Scrive il file locale dazn_event.json."""
    EVENTS_FILE.write_text(json.dumps(data, indent=3, ensure_ascii=False) + "\n", encoding="utf-8")


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


def add_event(comp_title, entry):
    """Aggiunge/sostituisce un evento (dedup per titolo) e salva in locale."""
    data = _load()
    comp_title = comp_title or "Eventi"
    grp = data.setdefault(comp_title, [])
    grp[:] = [e for e in grp if e.get("name") != entry.get("name")]
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
