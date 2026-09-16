import asyncio, json, os, subprocess
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parent.parent.parent / "chrome_profile"
CDP_PORT = 9222


class BrowserManager:
    def __init__(self):
        self._context = None
        self._page = None
        self._playwright = None

    async def start(self):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        browser = await self._try_connect_cdp()
        if browser is None:
            browser = await self._launch_chrome()
            if browser is None:
                raise RuntimeError("Impossibile avviare o connettersi a Chrome.")
        self._context = browser.contexts[0]
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        await self._page.wait_for_load_state("domcontentloaded")

    async def _try_connect_cdp(self):
        try:
            browser = await self._playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
            return browser
        except Exception:
            return None

    async def _launch_chrome(self):
        chrome_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if not os.path.exists(chrome_path):
            chrome_path = "msedge"
        try:
            subprocess.Popen(
                [chrome_path, '--headless=new', f'--remote-debugging-port={CDP_PORT}',
                 f'--user-data-dir={PROFILE_DIR}', '--no-first-run',
                 '--log-level=3', '--disable-logging',
                 '--disable-blink-features=AutomationControlled', 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            for _ in range(30):
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
        if "dazn" not in cur:
            await self._page.goto("https://www.dazn.com/it-it", wait_until="load", timeout=0)
        js_check = """
        (() => {
            const tok = localStorage.getItem('MISL.authToken');
            if (!tok) return false;
            try {
                let p = tok.split('.')[1];
                p = p.replace(/-/g, '+').replace(/_/g, '/');
                while (p.length % 4) p += '=';
                const dec = JSON.parse(atob(p));
                return (dec.exp && dec.exp > Math.floor(Date.now() / 1000) + 300);
            } catch(e) { return false; }
        })()
        """
        try:
            is_valid = await self._page.evaluate(js_check)
        except Exception:
            is_valid = False
        if not is_valid:
            await self._page.goto("https://www.dazn.com/it-it", wait_until="networkidle", timeout=0)
            await asyncio.sleep(2)

    async def evaluate(self, js: str):
        return await self._page.evaluate(js)

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
        if self._playwright:
            await self._playwright.stop()
        self._context = None
        self._page = None
        self._playwright = None


_browser = None


async def get_browser() -> BrowserManager:
    global _browser
    if _browser is not None:
        try:
            if _browser._page is not None:
                await _browser._page.evaluate('1')
                return _browser
        except Exception:
            pass
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
    _browser = BrowserManager()
    await _browser.start()
    return _browser


async def close_browser():
    global _browser
    if _browser:
        await _browser.close()
        _browser = None
