import asyncio
import shutil
import time
from pathlib import Path
from rich.console import Console
from dazn_navigator2.auth.token_refresh import TOKEN_FILE, PROFILE_DIR

console = Console()


def do_login():
    console.print("\n[bold cyan]Login DAZN[/bold cyan]")
    console.print("Verrà aperto il browser per l'accesso a DAZN.")
    console.print("Fai il login con email/password nella finestra.")
    console.print("[dim]Il profilo Chrome verrà salvato: non dovrai più rifare login.[/dim]\n")

    ok = asyncio.run(_login_playwright())
    if ok:
        console.print(f"[bold green]Login effettuato![/bold green]")
        console.print(f"[dim]Profilo salvato in chrome_profile/[/dim]")
        return True
    console.print("[red]Login non completato.[/red]")
    return False


async def _login_playwright() -> bool:
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                channel="msedge",
                args=["--no-sandbox"],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://www.dazn.com/it-IT/signin", wait_until="domcontentloaded", timeout=0)
            console.print("[cyan]Attendo il login nella finestra del browser... (puoi prenderti tutto il tempo che vuoi)[/cyan]")

            while True:
                await asyncio.sleep(2)
                try:
                    t = await page.evaluate("localStorage.getItem('MISL.authToken')")
                    if t and t.startswith("eyJ"):
                        await context.close()
                        return True
                except:
                    pass

            await context.close()
            return False
    except Exception as e:
        console.print(f"[red]Errore: {e}[/red]")
        return False


def do_logout():
    base_dir = PROFILE_DIR.parent
    files_to_remove = [
        TOKEN_FILE,
        base_dir / "dazn_session.db",
        base_dir / "dazn_state.json",
        base_dir / "dazn_storage.json",
        base_dir / "dazn_playback_debug.json",
        base_dir / "dazn_raw_response.json",
    ]

    for f in files_to_remove:
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass

    if PROFILE_DIR.exists():
        for _ in range(3):
            try:
                shutil.rmtree(PROFILE_DIR, ignore_errors=True)
                if not PROFILE_DIR.exists():
                    break
            except Exception:
                pass
            time.sleep(1)

        if PROFILE_DIR.exists():
            import os
            os.system(f'rmdir /S /Q "{str(PROFILE_DIR)}"')

    console.print("[bold green]Logout totale completato![/bold green]")
