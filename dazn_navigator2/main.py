import asyncio
import sys
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

import signal
import os

# Gestione immediata e silenziosa di SIGINT (Ctrl+C)
def _sigint_handler(sig, frame):
    try:
        from dazn_navigator2.services.browser import _GLOBAL_BROWSER
        # Chiudi senza stampare trace
    except Exception:
        pass
    os._exit(0)

signal.signal(signal.SIGINT, _sigint_handler)

def _silent_excepthook(exc_type, exc_val, exc_tb):
    if issubclass(exc_type, (KeyboardInterrupt, asyncio.CancelledError)):
        os._exit(0)
    sys.__excepthook__(exc_type, exc_val, exc_tb)

sys.excepthook = _silent_excepthook

if sys.platform == 'win32':
    original_hook = sys.unraisablehook
    def _silent_hook(unraisable):
        if issubclass(unraisable.exc_type, (KeyboardInterrupt, asyncio.CancelledError)):
            return
        if issubclass(unraisable.exc_type, ValueError) and "closed pipe" in str(unraisable.exc_value):
            return
        if original_hook:
            try:
                original_hook(unraisable)
            except Exception:
                pass
        else:
            try:
                sys.__unraisablehook__(unraisable)
            except Exception:
                pass
    sys.unraisablehook = _silent_hook

from dazn_navigator2.auth.login import do_login, do_logout
from dazn_navigator2.auth.token_refresh import PROFILE_DIR
from dazn_navigator2.cli import auth_cmds, events_cmds


_LOOP = None


def run_async(coro):
    """Riusa un unico event loop per tutta la vita del processo: il browser headless
    (singleton di playwright) resta cosi' vivo tra un'estrazione e l'altra invece di
    essere ricreato ad ogni azione del menu."""
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


app = typer.Typer(
    name="dazn-nav",
    help="DAZN Navigator - Login e Navigazione contenuti",
    add_completion=False,
    invoke_without_command=True
)

console = Console()


def profile_status() -> str:
    if PROFILE_DIR.exists():
        return "[green]Connesso[/green]"
    return "[red]Non connesso[/red]"


@app.callback(invoke_without_command=True)
def main_menu(ctx: typer.Context):
    if ctx.invoked_subcommand is not None:
        return

    if not PROFILE_DIR.exists():
        console.print("\n[bold yellow]Nessuna sessione trovata! Avvio login...[/bold yellow]")
        if not do_login():
            console.print("[red]Accesso obbligatorio. Uscita.[/red]")
            return

    while True:
        status = profile_status()
        menu = f"""[bold cyan]1.[/bold cyan]  Eventi Live
[bold cyan]2.[/bold cyan]  Contenuti VOD (On-Demand)
[bold cyan]3.[/bold cyan]  Canali Lineari (DAZN TV)
[bold cyan]4.[/bold cyan]  Cerca un Evento
[bold cyan]5.[/bold cyan]  Eventi
[bold cyan]6.[/bold cyan]  Impostazioni
[bold cyan]7.[/bold cyan]  {status}
[bold cyan]8.[/bold cyan]  Logout"""

        console.print("\n")
        console.print(Panel(menu, title="[bold magenta]DAZN[/bold magenta]", expand=False))
        try:
            scelta = Prompt.ask("Scegli un'opzione", default="")
        except (KeyboardInterrupt, Exception):
            os._exit(0)

        if scelta == "1":
            run_async(events_cmds.quick_navigate("Live", "Eventi Live"))
        elif scelta == "2":
            run_async(events_cmds.quick_navigate("Catchup", "Contenuti VOD (On-Demand)"))
        elif scelta == "3":
            run_async(events_cmds.quick_navigate("epg", "Canali Lineari (DAZN TV)"))
        elif scelta == "4":
            run_async(events_cmds.quick_search())
        elif scelta == "5":
            from dazn_navigator2.cli.eventi_cmds import manage_events
            manage_events()
        elif scelta == "6":
            from dazn_navigator2.cli.settings_cmds import settings_menu
            settings_menu()
        elif scelta == "7":
            console.print("[cyan]Verifico connessione...[/cyan]")
            try:
                ok = run_async(_check_session())
                if ok:
                    console.print("[green]Sessione attiva e funzionante.[/green]")
                else:
                    console.print("[yellow]Nessuna sessione attiva.[/yellow]")
            except Exception as e:
                console.print(f"[red]Errore: {e}[/red]")
        elif scelta == "8":
            do_logout()
            console.print("[green]Logout completato.[/green]")
            break

    # uscita dal menu: pubblica modifiche pendenti e chiude il browser headless
    try:
        from dazn_navigator2.cli.eventi_cmds import flush_alla_chiusura
        flush_alla_chiusura()
    except Exception:
        pass
    try:
        from dazn_navigator2.services.browser import close_browser
        run_async(close_browser())
    except Exception:
        pass

async def _check_session():
    from dazn_navigator2.services.browser import get_browser
    if not PROFILE_DIR.exists():
        return False
    try:
        b = await get_browser()
        await b.ensure_session()
        return True
    except:
        return False


app.add_typer(auth_cmds.app, name="auth", help="Autenticazione e gestione token")
app.add_typer(events_cmds.app, name="nav", help="Navigazione contenuti")


if __name__ == "__main__":
    try:
        app()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except Exception:
        pass
    finally:
        os._exit(0)
