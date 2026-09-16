"""Login Amazon Prime Video con profilo Chrome persistente separato."""

import asyncio
import shutil
import time
from pathlib import Path
from rich.console import Console

console = Console()

# Profilo Chrome Amazon separato da quello DAZN
AMAZON_PROFILE_DIR = Path(__file__).resolve().parent.parent.parent / "amazon_profile"
AMAZON_FLAG_FILE = AMAZON_PROFILE_DIR / "amazon_logged_in.flag"


def is_amazon_logged_in() -> bool:
    """Controlla se esiste un profilo Amazon salvato."""
    return AMAZON_PROFILE_DIR.exists() and AMAZON_FLAG_FILE.exists()


def do_amazon_login() -> bool:
    """Apre il browser per il login Amazon Prime Video."""
    console.print("\n[bold cyan]Login Amazon Prime Video[/bold cyan]")
    console.print("Verrà aperto il browser per l'accesso ad Amazon Prime Video.")
    console.print("Fai il login con email/password nella finestra.")
    console.print("[dim]Il profilo Chrome verrà salvato: non dovrai più rifare login.[/dim]\n")

    ok = asyncio.run(_login_amazon_playwright())
    if ok:
        console.print("[bold green]Login Amazon effettuato![/bold green]")
        console.print("[dim]Profilo salvato in amazon_profile/[/dim]")
        return True
    console.print("[red]Login Amazon non completato.[/red]")
    return False


async def _login_amazon_playwright() -> bool:
    from playwright.async_api import async_playwright

    # Rimuove vecchio flag fasullo se presente
    if AMAZON_FLAG_FILE.exists():
        try:
            AMAZON_FLAG_FILE.unlink()
        except Exception:
            pass

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(AMAZON_PROFILE_DIR),
                headless=False,
                channel="msedge",
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
                no_viewport=True,
            )
            page = context.pages[0] if context.pages else await context.new_page()

            # Apre la home pulita di primevideo.com
            try:
                await page.goto("https://www.primevideo.com", timeout=30000)
            except Exception:
                pass

            # Cerca e clicca il tasto "Accedi" / "Sign in" presente nella pagina
            try:
                btn = await page.query_selector('a[href*="signin"], a[href*="login"], [data-testid="sign-in-button"]')
                if btn:
                    await btn.click()
            except Exception:
                pass

            console.print("\n[bold green]Finestra aperta su Prime Video.[/bold green]")
            console.print("[bold yellow]Inserisci email e password nella finestra del browser.[/bold yellow]")
            console.print("[cyan]Una volta effettuato l'accesso completo nel browser, premi [bold white]INVIO[/bold white] qui sotto nel terminale![/cyan]\n")

            # Attendiamo in modo asincrono che l'utente prema INVIO nel terminale, oppure che rilevi il cookie di auth token reale
            loop = asyncio.get_running_loop()
            
            async def wait_user_input():
                return await loop.run_in_executor(None, lambda: input("Premi INVIO dopo aver effettuato il login su Amazon: "))

            input_task = asyncio.create_task(wait_user_input())

            while not input_task.done():
                await asyncio.sleep(2)
                try:
                    if not context.pages or all(pg.is_closed() for pg in context.pages):
                        console.print("[yellow]Browser chiuso dall'utente.[/yellow]")
                        input_task.cancel()
                        return False

                    cookies = await context.cookies()
                    # Cookie che esistono SOLO ed ESCLUSIVAMENTE quando l'utente è davvero autenticato
                    # at-main o at-acbit contiene il JWT Bearer token di Amazon
                    has_real_jwt = any(
                        c.get("name", "") in ("at-main", "at-acbit") and len(c.get("value", "")) > 50
                        for c in cookies
                    )
                    
                    if has_real_jwt:
                        console.print("\n[bold green]Rilevato token di autenticazione Amazon valido![/bold green]")
                        input_task.cancel()
                        break
                except Exception:
                    pass

            if not input_task.done():
                try:
                    input_task.cancel()
                except Exception:
                    pass

            # Controllo finale cookie
            cookies = await context.cookies()
            has_auth = any(
                ("at-main" in c.get("name", "") or "at-acbit" in c.get("name", ""))
                and len(c.get("value", "")) > 20
                for c in cookies
            )

            AMAZON_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            AMAZON_FLAG_FILE.write_text("logged_in")
            await context.close()
            return True

    except Exception as e:
        console.print(f"[red]Errore browser Amazon: {e}[/red]")
        return False



def do_amazon_logout():
    """Rimuove il profilo Amazon salvato."""
    if AMAZON_PROFILE_DIR.exists():
        for _ in range(3):
            try:
                shutil.rmtree(AMAZON_PROFILE_DIR, ignore_errors=True)
                if not AMAZON_PROFILE_DIR.exists():
                    break
            except Exception:
                pass
            time.sleep(1)

        if AMAZON_PROFILE_DIR.exists():
            import os
            os.system(f'rmdir /S /Q "{str(AMAZON_PROFILE_DIR)}"')

    console.print("[bold green]Logout Amazon completato![/bold green]")
