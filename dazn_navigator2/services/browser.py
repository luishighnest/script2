import asyncio, json, os, subprocess, sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CDP_PORT = 9222

_current_profile_dir = BASE_DIR / "chrome_profile"

def set_active_profile_dir(p: Path):
    global _current_profile_dir
    _current_profile_dir = Path(p)

def get_active_profile_dir() -> Path:
    return _current_profile_dir

class BrowserManager:
    def __init__(self):
        self._context = None
        self._page = None
        self._playwright = None

    async def start(self, user_data_dir: Path = None):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        
        p_dir = user_data_dir or get_active_profile_dir()
        p_dir.mkdir(parents=True, exist_ok=True)

        launch_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--no-first-run'
        ]

        try:
            # Avvio context persistente con Edge (msedge): i profili sono creati da Edge,
            # solo Edge sa decifrare i cookie di sessione DAZN del profilo.
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(p_dir),
                channel="msedge",
                headless=True,
                args=launch_args,
                viewport={"width": 1280, "height": 720}
            )
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            return
        except Exception as e:
            print(f"[BrowserManager] msedge fallito ({e}), fallback su Chromium Playwright")

        try:
            # Fallback: Chromium nativo di Playwright
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(p_dir),
                headless=True,
                args=launch_args,
                viewport={"width": 1280, "height": 720}
            )
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            return
        except Exception as e:
            print(f"[BrowserManager] launch_persistent_context fallito: {e}, fallback su subprocess")

        # Fallback secondario: subprocess + CDP
        browser = await self._try_connect_cdp()
        if browser is None:
            browser = await self._launch_chrome(p_dir)
            if browser is None:
                raise RuntimeError("Impossibile avviare o connettersi a Chrome.")
        self._context = browser.contexts[0]
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

    async def _try_connect_cdp(self):
        try:
            browser = await self._playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
            return browser
        except Exception:
            return None

    async def _launch_chrome(self, profile_dir: Path):
        chrome_bin = "chromium"
        if sys.platform == "win32":
            chrome_bin = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            if not os.path.exists(chrome_bin):
                chrome_bin = "msedge"
        try:
            subprocess.Popen(
                [chrome_bin, '--headless=new', f'--remote-debugging-port={CDP_PORT}',
                 f'--user-data-dir={profile_dir}', '--no-first-run', '--no-sandbox',
                 '--log-level=3', '--disable-logging',
                 '--disable-blink-features=AutomationControlled', 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            for _ in range(20):
                await asyncio.sleep(1)
                browser = await self._try_connect_cdp()
                if browser:
                    return browser
            return None
        except Exception:
            return None

    async def ensure_session(self):
        if self._page is None:
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
        try:
            cur = self._page.url
        except Exception:
            self._page = await self._context.new_page()
            cur = "about:blank"

        js_check = """
        (() => {
            try {
                const tok = window.localStorage ? window.localStorage.getItem('MISL.authToken') : null;
                if (!tok) return false;
                let p = tok.split('.')[1];
                p = p.replace(/-/g, '+').replace(/_/g, '/');
                while (p.length % 4) p += '=';
                const dec = JSON.parse(atob(p));
                return (dec.exp && dec.exp > Math.floor(Date.now() / 1000) + 300);
            } catch(e) { return false; }
        })()
        """

        # Se gia' su DAZN con token valido, ritorna subito
        if "dazn.com" in cur:
            try:
                if await self._page.evaluate(js_check):
                    return
            except Exception:
                pass

        # Naviga su DAZN per ottenere cookies e token in localStorage
        try:
            await self._page.goto("https://www.dazn.com/it-IT/home", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"[BrowserManager] Errore navigazione su DAZN: {e}")
            return

        # Verifica token dopo navigazione
        try:
            is_valid = await self._page.evaluate(js_check)
        except Exception:
            is_valid = False

        if not is_valid:
            try:
                await self._page.goto("https://www.dazn.com/it-IT/home", wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
            except Exception:
                pass

    async def evaluate(self, js: str):
        await self.ensure_session()
        if self._page is None:
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
        # Wrapper sicuro per evitare SecurityError se evaluate accede a localStorage
        safe_js = f"""
        (() => {{
            try {{
                return (eval({json.dumps(js)}));
            }} catch(e) {{
                return null;
            }}
        }})()
        """
        return await self._page.evaluate(safe_js)

    async def fetch_json(self, url: str, method: str = "GET", body: dict = None, headers: dict = None) -> dict:
        h = dict(headers or {})
        h.setdefault("Accept", "application/json")
        if body:
            h.setdefault("Content-Type", "application/json")
        hdrs = json.dumps(h)
        body_js = json.dumps(body) if body else "null"
        method_js = json.dumps(method)
        js = f"""
        (async () => {{
            const tok = localStorage.getItem('MISL.authToken');
            const h = {hdrs};
            if (tok) h['Authorization'] = 'Bearer ' + tok;
            const opts = {{method: {method_js}, headers: h}};
            if ({body_js}) opts.body = JSON.stringify({body_js});
            try {{
                const r = await fetch('{url}', opts);
                const txt = await r.text();
                try {{ return {{ok: r.ok, status: r.status, data: JSON.parse(txt)}}; }}
                catch(e) {{ return {{ok: r.ok, status: r.status, data: txt}}; }}
            }} catch(e) {{
                return {{ok: false, error: e.message}};
            }}
        }})()
        """
        return await self._page.evaluate(js)

    @property
    def page(self):
        return self._page

    @property
    def context(self):
        return self._context

    async def close(self):
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._context = None
        self._page = None
        self._playwright = None

_browser = None
_browser_user_data_dir = None

async def get_browser(user_data_dir: Path = None) -> BrowserManager:
    global _browser, _browser_user_data_dir
    target_dir = Path(user_data_dir) if user_data_dir else get_active_profile_dir()
    if _browser is not None:
        try:
            # Se la directory profilo richiesta è cambiata, chiudi il browser precedente
            if _browser_user_data_dir != target_dir:
                await _browser.close()
                _browser = None
            elif _browser._page is not None:
                await _browser._page.evaluate('1')
                return _browser
        except Exception:
            try:
                await _browser.close()
            except Exception:
                pass
            _browser = None
    _browser = BrowserManager()
    _browser_user_data_dir = target_dir
    await _browser.start(user_data_dir=target_dir)
    return _browser

async def close_browser():
    global _browser
    if _browser:
        await _browser.close()
        _browser = None
