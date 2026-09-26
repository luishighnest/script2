import sys
import json
import time
import shutil
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "dazn_session.json"
AUTH_FILE = BASE_DIR / "auth_token.json"
TEMP_PROFILE_DIR = BASE_DIR / "temp_login_profile"

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[ERRORE] Playwright non trovato. Installalo con: pip install playwright")
    print("Poi esegui: playwright install chromium")
    input("\nPremi Invio per uscire...")
    sys.exit(1)

async def main():
    print("Si sta aprendo il browser per l'accesso a DAZN...")
    print("Effettua il LOGIN con le tue credenziali DAZN.\n")

    TEMP_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=str(TEMP_PROFILE_DIR),
                    headless=False,
                    channel="msedge",
                    viewport={"width": 1280, "height": 900},
                    args=["--no-sandbox", "--force-device-scale-factor=0.8"],
                )
            except Exception:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=str(TEMP_PROFILE_DIR),
                    headless=False,
                    viewport={"width": 1280, "height": 900},
                    args=["--no-sandbox", "--force-device-scale-factor=0.8"],
                )

            page = context.pages[0] if context.pages else await context.new_page()

            await page.add_init_script("""
            (() => {
                const style = document.createElement('style');
                style.innerHTML = `
                    #onetrust-banner-sdk, #onetrust-consent-sdk, .onetrust-pc-dark-filter, 
                    [class*="cookie"], [id*="cookie"], [class*="onetrust"], [id*="onetrust"] {
                        display: none !important;
                        visibility: hidden !important;
                        opacity: 0 !important;
                        pointer-events: none !important;
                    }
                    html, body {
                        overflow: auto !important;
                        position: static !important;
                        height: auto !important;
                    }
                `;
                document.documentElement.appendChild(style);
            })();
            """)

            await page.goto("https://www.dazn.com/it-IT/signin", wait_until="domcontentloaded", timeout=0)

            jwt_token = None
            device_id = None

            print("[*] In attesa del login nella finestra del browser...")

            while True:
                await asyncio.sleep(2)

                try:
                    js_cookie_cleaner = """
                    (() => {
                        const btn = document.querySelector('#onetrust-accept-btn-handler') || 
                                     document.querySelector('button[id*="accept"]') ||
                                     document.querySelector('.onetrust-close-btn-handler');
                        if (btn) btn.click();
                        const banner = document.querySelector('#onetrust-banner-sdk') || document.querySelector('#onetrust-consent-sdk');
                        if (banner) banner.style.display = 'none';
                        document.body.style.overflow = 'auto';
                    })()
                    """
                    await page.evaluate(js_cookie_cleaner)
                except Exception:
                    pass

                try:
                    tok = await page.evaluate("localStorage.getItem('MISL.authToken')")
                    did = await page.evaluate("localStorage.getItem('MISL.deviceId') || localStorage.getItem('dazn.deviceId')")

                    if tok and tok.startswith("eyJ"):
                        jwt_token = tok
                        device_id = did or "extracted_device"
                        print("\n[✓] Login effettuato con successo!")
                        break
                except Exception:
                    pass

            cookies = await context.cookies()

            session_data = {
                "created_at": int(time.time()),
                "jwt": jwt_token,
                "device_id": device_id,
                "cookies": cookies
            }

            OUTPUT_FILE.write_text(json.dumps(session_data, indent=2), encoding="utf-8")
            AUTH_FILE.write_text(json.dumps({"jwt": jwt_token}), encoding="utf-8")

            print(f"\n[SUCCESS] Sessione salvata in: {OUTPUT_FILE.resolve()}")
            print(f"File pronto: auth_token.json ({AUTH_FILE.stat().st_size} bytes)")

            await context.close()

    finally:
        shutil.rmtree(TEMP_PROFILE_DIR, ignore_errors=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperazione annullata dall'utente.")
    except Exception as e:
        print(f"\n[ERRORE]: {e}")
    finally:
        input("\nPremi Invio per uscire...")
