"""
Script Leggero per Export Sessione DAZN (Metodo identico a mpd)
Apre la finestra di login utilizzando Microsoft Edge nativo (channel="msedge").
Una volta completato l'accesso, esporta un file 'dazn_session.json' (pochi KB)
e salva anche 'auth_token.json' pronto per l'uso.
"""

import sys
import json
import time
import shutil
import asyncio
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[ERRORE] Playwright non trovato. Installalo con: pip install playwright")
    print("Poi esegui: playwright install chromium")
    sys.exit(1)


OUTPUT_FILE = Path("dazn_session.json")
TEMP_PROFILE_DIR = Path("./temp_login_profile")


async def main():
    print("==================================================")
    print("      EXPORTATORE LEGGERO SESSIONE DAZN           ")
    print("==================================================")
    print("Si sta aprendo Microsoft Edge per l'accesso a DAZN...")
    print("Effettua il LOGIN con le tue credenziali DAZN.")
    print("Lo script rileverà automaticamente l'accesso completato.")
    print("==================================================\n")

    TEMP_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            # Usa launch_persistent_context con msedge per identità identica a mpd
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(TEMP_PROFILE_DIR),
                headless=False,
                channel="msedge",
                viewport={"width": 1280, "height": 900},
                args=["--no-sandbox", "--force-device-scale-factor=0.8"],
            )

            page = context.pages[0] if context.pages else await context.new_page()

            # Script di soppressione completa del banner prima del caricamento
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

                # Cookie cleaner automatico (pari a mpd)
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

            # Salva il file leggero dazn_session.json (2 KB)
            OUTPUT_FILE.write_text(json.dumps(session_data, indent=2), encoding="utf-8")
            
            # Salva anche direttamente auth_token.json per compatibilità immediata
            Path("auth_token.json").write_text(json.dumps({"jwt": jwt_token}), encoding="utf-8")

            print(f"\n[SUCCESS] Sessione salvata in: {OUTPUT_FILE.resolve()}")
            print(f"File pronto: auth_token.json ({Path('auth_token.json').stat().st_size} bytes)")

            await context.close()

    finally:
        # Pulisce la cartella temporanea del profilo per non lasciare peso su disco
        shutil.rmtree(TEMP_PROFILE_DIR, ignore_errors=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperazione annullata dall'utente.")
        sys.exit(0)
