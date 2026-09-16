"""Menu Amazon Prime Video: login, navigazione eventi, estrazione DRM."""

import asyncio
import json
import re
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()


def run_async(coro):
    from dazn_navigator2.main import run_async as _main_run_async
    return _main_run_async(coro)


def amazon_status() -> str:
    from dazn_navigator2.auth.amazon_login import is_amazon_logged_in
    if is_amazon_logged_in():
        return "[green]Connesso[/green]"
    return "[red]Non connesso[/red]"


def _fmt_date(d: str) -> str:
    if not d:
        return ""
    from datetime import datetime
    try:
        clean = d[:19].replace("T", " ")
        dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m %H:%M")
    except Exception:
        return d[:10]


def _build_amazon_entry(titolo: str, result: dict, image: str = "") -> dict:
    """Costruisce l'entry evento Amazon nel formato test.json."""
    mpd_url = result.get("mpd_url", "")
    keys = result.get("keys", [])
    ua = result.get("ua", "")
    keys_str = ",".join(keys)

    entry = {
        "name": f"[Amazon] {titolo}",
        "image": image or "",
        "start": "",
        "end": "",
        "mpd": mpd_url,
        "key": keys_str,
    }
    if ua:
        entry["ua"] = ua

    return entry


def _print_amazon_result(titolo: str, result: dict):
    """Stampa il risultato dell'estrazione Amazon."""
    if not result.get("ok"):
        console.print(f"[bold red]Fallito: {titolo} — {result.get('error', 'Errore sconosciuto')}[/bold red]")
        return

    keys = result.get("keys", [])
    mpd = result.get("mpd_url", "")
    ext = result.get("ext_url", "")

    console.print(f"\n[bold green]✓ Estrazione Amazon riuscita![/bold green]")
    console.print(f"  [bold]Titolo:[/bold] {titolo}")
    console.print(f"  [bold]MPD:[/bold] [dim]{mpd[:80]}...[/dim]" if len(mpd) > 80 else f"  [bold]MPD:[/bold] {mpd}")
    console.print(f"  [bold]Chiavi:[/bold]")
    for k in keys:
        console.print(f"    [cyan]{k}[/cyan]")

    if ext:
        console.print(f"\n[bold cyan]Link Estensione:[/bold cyan]")
        console.print(f"[green]{ext}[/green]")

    # Stampa JSON
    entry = _build_amazon_entry(titolo, result)
    console.print(f"\n[bold yellow]JSON per test.json:[/bold yellow]")
    console.print(json.dumps({"AMAZON": [entry]}, indent=3))


async def _amazon_inserisci_manuale():
    """Inserimento manuale di URL MPD Amazon con chiavi."""
    console.print("\n[bold cyan]── Inserimento Manuale Evento Amazon ──[/bold cyan]")
    console.print("[dim]Incolla l'URL del MPD Amazon (con aws.sessionId nell'URL se presente)[/dim]")

    mpd_url = Prompt.ask("URL MPD (.mpd)").strip()
    if not mpd_url:
        console.print("[yellow]Annullato.[/yellow]")
        return

    titolo = Prompt.ask("Titolo dell'evento").strip() or "Evento Amazon"

    # Estrai aws.sessionId dall'URL se presente
    aws_session = None
    m = re.search(r'aws\.sessionId=([^&]+)', mpd_url)
    if m:
        aws_session = m.group(1)
        console.print(f"[dim]aws.sessionId rilevato: {aws_session[:20]}...[/dim]")

    console.print(f"\n[cyan]Avvio estrazione chiavi per: {titolo}...[/cyan]")

    from dazn_navigator2.services.amazon_extractor import AmazonExtractor
    ext = AmazonExtractor()

    # Usa direttamente l'URL MPD fornito
    result = {"ok": False, "error": "Modalità manuale: inserisci le chiavi manualmente."}

    # Opzione: inserimento manuale chiavi
    console.print("\n[yellow]Non ho un URL dell'evento per intercettare la licenza automaticamente.[/yellow]")
    console.print("Hai 2 opzioni:")
    console.print("[bold cyan]1.[/bold cyan] Inserisci le chiavi manualmente (kid:key)")
    console.print("[bold cyan]2.[/bold cyan] Inserisci l'URL della pagina evento Prime Video per estrazione automatica")

    scelta = Prompt.ask("Scelta", default="1").strip()

    if scelta == "2":
        event_url = Prompt.ask("URL pagina evento Prime Video").strip()
        if event_url:
            result = await ext.estrai(event_url=event_url, titolo=titolo)
    else:
        # Inserimento manuale chiavi
        console.print("[dim]Formato: kid_hex:key_hex (una per riga, vuota per terminare)[/dim]")
        keys = []
        while True:
            k = Prompt.ask(f"Chiave {len(keys)+1}").strip()
            if not k:
                break
            if ":" in k:
                keys.append(k)
        if keys:
            result = {
                "ok": True,
                "mpd_url": mpd_url,
                "keys": keys,
                "ua": "",
                "ext_url": "",
                "titolo": titolo,
            }

    _print_amazon_result(titolo, result)

    if result.get("ok"):
        entry = _build_amazon_entry(titolo, result)
        from dazn_navigator2.cli.eventi_cmds import add_event, pubblica
        add_event("AMAZON", entry)
        pubblica(f"amazon: estrazione {titolo}")
        console.print("[green]Evento Amazon salvato in test.json categoria AMAZON![/green]")


async def _amazon_sfoglia_eventi():
    """Sfoglia eventi disponibili su Prime Video ed estrae quello scelto."""
    console.print("\n[bold cyan]── Sfoglia Eventi Amazon Prime Video ──[/bold cyan]")
    console.print("[dim]Caricamento eventi da primevideo.com...[/dim]")

    from dazn_navigator2.services.amazon_extractor import AmazonExtractor
    ext = AmazonExtractor()

    events = await ext.get_amazon_events()

    if not events:
        console.print("[yellow]Nessun evento trovato automaticamente.[/yellow]")
        console.print("[dim]Prova l'opzione 'Inserimento Manuale' con l'URL della pagina evento.[/dim]")
        return

    # Mostra tabella eventi
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="cyan", width=4)
    table.add_column("Titolo", style="white")
    table.add_column("ID", style="dim", width=12)

    for i, ev in enumerate(events, 1):
        table.add_row(str(i), ev.get("title", "?"), ev.get("asset_id", "")[:12])

    console.print(table)
    console.print(f"[dim]Trovati {len(events)} eventi. Invio per tornare.[/dim]")

    scelta = Prompt.ask("Numero evento da estrarre", default="").strip()
    if not scelta or not scelta.isdigit():
        return

    idx = int(scelta) - 1
    if not (0 <= idx < len(events)):
        console.print("[red]Numero non valido.[/red]")
        return

    event = events[idx]
    titolo = event.get("title", "Evento Amazon")
    event_url = event.get("url", "")
    image = event.get("image", "")

    console.print(f"\n[cyan]Estrazione: {titolo}...[/cyan]")
    result = await ext.estrai(event_url=event_url, titolo=titolo, asset_id=event.get("asset_id", ""))

    _print_amazon_result(titolo, result)

    if result.get("ok"):
        entry = _build_amazon_entry(titolo, result, image)
        from dazn_navigator2.cli.eventi_cmds import add_event, pubblica
        add_event("AMAZON", entry)
        pubblica(f"amazon: estrazione {titolo}")
        console.print("[green]Evento Amazon salvato in test.json categoria AMAZON![/green]")


async def _amazon_estrai_da_url():
    """Estrai da URL diretto della pagina evento Prime Video."""
    console.print("\n[bold cyan]── Estrai da URL Pagina Evento ──[/bold cyan]")
    console.print("[dim]Incolla l'URL della pagina dell'evento su primevideo.com[/dim]")
    console.print("[dim]Esempio: https://www.primevideo.com/detail/0RTRDHDM7M2M79...[/dim]")

    event_url = Prompt.ask("URL pagina evento").strip()
    if not event_url:
        console.print("[yellow]Annullato.[/yellow]")
        return

    titolo = Prompt.ask("Titolo (lascia vuoto per rilevamento automatico)").strip()
    if not titolo:
        # Prova a estrarre dal URL
        m = re.search(r'/detail/([A-Z0-9]+)', event_url, re.IGNORECASE)
        titolo = m.group(1) if m else "Evento Amazon"

    console.print(f"\n[cyan]Estrazione: {titolo}...[/cyan]")
    console.print("[dim]Apertura browser headless Amazon in corso...[/dim]")

    from dazn_navigator2.services.amazon_extractor import AmazonExtractor
    ext = AmazonExtractor()
    result = await ext.estrai(event_url=event_url, titolo=titolo)

    _print_amazon_result(titolo, result)

    if result.get("ok"):
        entry = _build_amazon_entry(titolo, result)
        from dazn_navigator2.cli.eventi_cmds import add_event, pubblica
        add_event("AMAZON", entry)
        pubblica(f"amazon: estrazione {titolo}")
        console.print("[green]Evento Amazon salvato in test.json categoria AMAZON![/green]")


def amazon_menu():
    """Menu principale Amazon Prime Video."""
    from dazn_navigator2.auth.amazon_login import (
        is_amazon_logged_in, do_amazon_login, do_amazon_logout
    )

    # Se non loggato, proponi il login
    if not is_amazon_logged_in():
        console.print("\n[bold yellow]Nessun profilo Amazon trovato![/bold yellow]")
        ok_login = Prompt.ask("Vuoi fare il login Amazon Prime Video ora? (s/N)", default="n").strip().lower()
        if ok_login == "s":
            if not do_amazon_login():
                console.print("[red]Login Amazon fallito. Riprova.[/red]")
                return
        else:
            return

    while True:
        stato = amazon_status()
        menu = f"""[bold cyan]1.[/bold cyan]  🔍 Sfoglia eventi Amazon Prime Video
[bold cyan]2.[/bold cyan]  🔗 Estrai da URL pagina evento
[bold cyan]3.[/bold cyan]  ✏️  Inserimento manuale (MPD + chiavi)

[bold yellow]── Account ──[/bold yellow]
[bold cyan]4.[/bold cyan]  {stato} (stato sessione)
[bold cyan]5.[/bold cyan]  🔑 Login Amazon (nuovo profilo)
[bold cyan]6.[/bold cyan]  🚪 Logout Amazon

[bold cyan]0.[/bold cyan]  ⬅️ Torna al menu principale"""

        console.print("\n")
        console.print(Panel(menu, title="[bold magenta]Amazon Prime Video[/bold magenta]", expand=False))

        try:
            scelta = Prompt.ask("Scegli un'opzione", default="0").strip()
        except (KeyboardInterrupt, Exception):
            break

        if scelta == "0":
            break
        elif scelta == "1":
            run_async(_amazon_sfoglia_eventi())
        elif scelta == "2":
            run_async(_amazon_estrai_da_url())
        elif scelta == "3":
            run_async(_amazon_inserisci_manuale())
        elif scelta == "4":
            console.print(f"\nStato sessione Amazon: {stato}")
        elif scelta == "5":
            do_amazon_login()
        elif scelta == "6":
            conferma = Prompt.ask("Sei sicuro di voler fare il logout Amazon? (s/N)", default="n").strip().lower()
            if conferma == "s":
                do_amazon_logout()
        else:
            console.print("[red]Scelta non valida.[/red]")
