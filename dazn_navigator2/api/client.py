from dazn_navigator2.config import settings
from dazn_navigator2.services.browser import get_browser
from dazn_navigator2.services.extractor import _get_http_session

class DaznAPIError(Exception):
    pass

class DaznClient:
    """Chiama le API DAZN ad altissima velocità tramite curl_cffi con sessione persistente e token JWT."""

    def __init__(self):
        self.base_url = settings.DAZN_API_BASE_URL
        self._jwt = None

    async def _get_jwt(self, b):
        if not self._jwt:
            try:
                self._jwt = await b.evaluate("localStorage.getItem('MISL.authToken')")
            except Exception:
                self._jwt = None
        return self._jwt

    async def get(self, endpoint: str, params: dict = None) -> dict:
        url = self.base_url + endpoint
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url += "?" + qs
        
        b = await get_browser()
        # Assicura che il browser sia su una pagina DAZN valida prima di accedere a localStorage
        await b.ensure_session()
        jwt = await self._get_jwt(b)

        if jwt:
            try:
                session = await _get_http_session()
                headers = {
                    "authorization": f"Bearer {jwt}",
                    "accept": "application/json",
                    "origin": "https://www.dazn.com",
                    "referer": "https://www.dazn.com/"
                }
                resp = await session.get(url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass

        # Fallback nel browser
        result = await b.fetch_json(url)
        if not result.get("ok"):
            raise DaznAPIError(result.get("error", f"API error: {result.get('status')}"))
        return result["data"]

    async def close(self):
        pass