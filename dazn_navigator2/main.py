import asyncio
import sys
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

import signal
import os

def _sigint_handler(sig, frame):
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
        menu = f"""[bold yellow]── Navigazione contenuti ──[/bold yellow]
[bold cyan]1.[/bold cyan]  🔴 Eventi Live (In Diretta)
[bold cyan]2.[/bold cyan]  ⏰ Eventi In Programma (Prossimi Eventi & Live)
[bold cyan]3.[/bold cyan]  ⏮️ Contenuti VOD (On-Demand & Replay)
[bold cyan]4.[/bold cyan]  📺 Canali Lineari (DAZN TV, Eurosport, ecc.)
[bold cyan]5.[/bold cyan]  🏆 Esplora per Sport & Categorie (Serie A, LaLiga, Basket, NFL, Boxe...)
[bold cyan]6.[/bold cyan]  📅 Guida TV & Palinsesto
[bold cyan]7.[/bold cyan]  🔍 Cerca un Evento

[bold yellow]── Eventi sito ──[/bold yellow]
[bold cyan]8.[/bold cyan]  Eventi (test.json)
[bold cyan]9.[/bold cyan]  Aggiungi evento manuale a test.json (EVENTI)
[bold cyan]10.[/bold cyan] Importa eventi Live da Heroku a test.json (EVENTI)
[bold cyan]11.[/bold cyan] Sky sito
[bold cyan]12.[/bold cyan] Sky2 sito

[bold yellow]── Account & Test ──[/bold yellow]
[bold cyan]13.[/bold cyan] Impostazioni
[bold cyan]14.[/bold cyan] {status}
[bold cyan]15.[/bold cyan] Logout
[bold cyan]16.[/bold cyan] Estrai e pubblica da kodi.log
[bold cyan]17.[/bold cyan] 🌐 Repository GitHub

[bold yellow]── Amazon ──[/bold yellow]
[bold cyan]18.[/bold cyan] 🎬 Amazon Prime Video (Login & Estrazione)"""

        console.print("\n")
        console.print(Panel(menu, title="[bold magenta]DAZN[/bold magenta]", expand=False))
        try:
            scelta = Prompt.ask("Scegli un'opzione", default="")
        except (KeyboardInterrupt, Exception):
            import os
            os._exit(0)

        if scelta == "1":
            run_async(events_cmds.quick_navigate("Live", "Eventi Live"))
        elif scelta == "2":
            run_async(events_cmds.quick_navigate("upcoming", "Eventi In Programma"))
        elif scelta == "3":
            run_async(events_cmds.quick_navigate("Catchup", "Contenuti VOD (On-Demand)"))
        elif scelta == "4":
            run_async(events_cmds.quick_navigate("epg", "Canali Lineari (DAZN TV)"))
        elif scelta == "5":
            run_async(events_cmds.navigate())
        elif scelta == "6":
            run_async(events_cmds.quick_navigate("Livetvschedule", "Guida TV & Palinsesto"))
        elif scelta == "7":
            run_async(events_cmds.quick_search())
        elif scelta == "8":
            from dazn_navigator2.cli.eventi_cmds import manage_events
            manage_events()
        elif scelta == "9":
            from dazn_navigator2.cli.aggiungi_cmds import aggiungi_da_link
            aggiungi_da_link()
        elif scelta == "10":
            try:
                from dazn_navigator2.cli.heroku_eventi_cmds import importa_eventi_da_heroku
                importa_eventi_da_heroku()
            except Exception as e:
                console.print(f"[red]Errore durante l'importazione da Heroku: {e}[/red]")
        elif scelta == "11":
            try:
                from dazn_navigator2.cli.sky_cmds import sync_sky_site
                sync_sky_site()
            except Exception as e:
                console.print(f"[red]Errore durante la sincronizzazione: {e}[/red]")
        elif scelta == "12":
            try:
                from dazn_navigator2.cli.sky2_cmds import sync_sky2_site
                sync_sky2_site()
            except Exception as e:
                console.print(f"[red]Errore durante la sincronizzazione: {e}[/red]")
        elif scelta == "13":
            from dazn_navigator2.cli.settings_cmds import settings_menu
            settings_menu()
        elif scelta == "14":
            console.print(f"Stato sessione: {status}")
        elif scelta == "15":
            from dazn_navigator2.auth.auth import logout
            logout()
        elif scelta == "16":
            from dazn_navigator2.cli.kodi_log_cmds import estrai_da_kodi_log
            estrai_da_kodi_log()
        elif scelta == "17":
            import webbrowser
            sub_menu = f"""[bold cyan]1.[/bold cyan] 📦 luishighnest/kodi
[bold cyan]2.[/bold cyan] 🌐 luishighnest/zadonkais
[bold cyan]3.[/bold cyan] 🤖 luishighnest/telegram-calcio-bot
[bold cyan]4.[/bold cyan] ⚡ luishighnest/next

[bold cyan]0.[/bold cyan] ⬅️ Torna al menu principale"""
            console.print("\n")
            console.print(Panel(sub_menu, title="[bold magenta]Repository GitHub[/bold magenta]", expand=False))
            sub_scelta = Prompt.ask("Scegli un repository da aprire nel browser", default="0").strip()
            if sub_scelta == "1":
                webbrowser.open("https://github.com/luishighnest/kodi")
                console.print("[green]Apertura nel browser di luishighnest/kodi in corso...[/green]")
            elif sub_scelta == "2":
                webbrowser.open("https://github.com/luishighnest/zadonkais")
                console.print("[green]Apertura nel browser di luishighnest/zadonkais in corso...[/green]")
            elif sub_scelta == "3":
                webbrowser.open("https://github.com/luishighnest/telegram-calcio-bot")
                console.print("[green]Apertura nel browser di luishighnest/telegram-calcio-bot in corso...[/green]")
            elif sub_scelta == "4":
                webbrowser.open("https://github.com/luishighnest/next")
                console.print("[green]Apertura nel browser di luishighnest/next in corso...[/green]")
        elif scelta == "18":
            try:
                from dazn_navigator2.cli.amazon_cmds import amazon_menu
                amazon_menu()
            except Exception as e:
                console.print(f"[red]Errore Amazon: {e}[/red]")

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

