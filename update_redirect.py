"""Aggiorna la pagina GitHub Pages che reindirizza al link tunnel corrente in tempo reale."""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INDEX = BASE_DIR / "index.html"
TOKEN_FILE = BASE_DIR / "github_token.txt"

TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Script2</title>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b0f14;
    color: #e2e8f0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    margin: 0;
    text-align: center;
}}
.spinner {{
    width: 44px;
    height: 44px;
    border: 4px solid rgba(0, 229, 155, 0.15);
    border-top: 4px solid #00e59b;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-bottom: 20px;
}}
@keyframes spin {{
    0% {{ transform: rotate(0deg); }}
    100% {{ transform: rotate(360deg); }}
}}
h2 {{ margin: 0 0 8px 0; font-size: 1.25rem; font-weight: 600; }}
p {{ margin: 0; font-size: 0.95rem; color: #94a3b8; }}
a {{ color: #00e59b; text-decoration: none; font-weight: 500; }}
a:hover {{ text-decoration: underline; }}
.manual-link {{ margin-top: 20px; display: none; }}
</style>
</head>
<body>

<div class="spinner" id="spinner"></div>
<h2 id="statusTitle">Connessione a Script2...</h2>
<p id="statusDesc">Caricamento in corso...</p>

<div class="manual-link" id="manualBox">
    <p>Se non vieni reindirizzato automaticamente: <a id="manualLink" href="{link}">clicca qui per accedere</a></p>
</div>

<script>
const FALLBACK_URL = "{link}";
let redirected = false;

function doRedirect(targetUrl) {{
    if (redirected || !targetUrl || !targetUrl.startsWith("http")) return;
    redirected = true;
    const manualBox = document.getElementById("manualBox");
    const manualLink = document.getElementById("manualLink");
    if (manualBox && manualLink) {{
        manualLink.href = targetUrl;
        manualBox.style.display = "block";
    }}
    window.location.replace(targetUrl);
}}

// 1. Chiamata in tempo reale alle API GitHub: istantanea, senza ritardi di build e immune a cache browser
fetch("https://api.github.com/repos/luishighnest/script2?t=" + Date.now(), {{
    headers: {{ "Accept": "application/vnd.github.v3+json" }},
    cache: "no-store"
}})
.then(r => r.json())
.then(data => {{
    if (data && data.homepage && data.homepage.startsWith("https://")) {{
        doRedirect(data.homepage);
    }} else {{
        doRedirect(FALLBACK_URL);
    }}
}})
.catch(err => {{
    console.warn("API Error:", err);
    doRedirect(FALLBACK_URL);
}});

// 2. Timeout di sicurezza nel caso in cui le API esterne impieghino piu di 1.5s
setTimeout(() => {{
    if (!redirected) {{
        doRedirect(FALLBACK_URL);
    }}
}}, 1500);
</script>

</body>
</html>
"""


def update_github_repo_homepage(token: str, link: str) -> bool:
    """Aggiorna la homepage del repo GitHub tramite API (immediata, zero secondi di attesa)."""
    try:
        url = "https://api.github.com/repos/luishighnest/script2"
        data = json.dumps({"homepage": link}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "Script2-Sync",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
            },
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 204):
                print(f"[redirect] API GitHub Homepage aggiornata istantaneamente a: {link}")
                return True
    except Exception as e:
        print(f"[redirect] Attenzione: errore aggiornamento API GitHub homepage: {e}")
    return False


def main():
    if len(sys.argv) < 2:
        print("[redirect] Errore: manca il link come argomento")
        return 1
    link = sys.argv[1].strip()
    token = ""
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        print("[redirect] Errore: github_token.txt non trovato")
        return 1

    # 1. Aggiorna subito l'API repo homepage (ha effetto in 0 secondi)
    update_github_repo_homepage(token, link)

    # 2. Aggiorna index.html per la copia statica di riserva
    INDEX.write_text(TEMPLATE.format(link=link), encoding="utf-8")

    repo_url = f"https://x-access-token:{token}@github.com/luishighnest/script2.git"
    no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        subprocess.run(["git", "config", "user.name", "Render Auto-Sync"], cwd=str(BASE_DIR), check=True, creationflags=no_win, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "render-sync@users.noreply.github.com"], cwd=str(BASE_DIR), check=True, creationflags=no_win, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", "index.html", "update_redirect.py"], cwd=str(BASE_DIR), check=True, creationflags=no_win, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(BASE_DIR), creationflags=no_win, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if diff.returncode != 0:
            subprocess.run(["git", "commit", "-m", "redirect: supporto dynamic real-time zero-cache redirect"], cwd=str(BASE_DIR), check=True, creationflags=no_win, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "push", repo_url, "HEAD:main"], cwd=str(BASE_DIR), check=True, creationflags=no_win, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[redirect] File index.html salvato e pushato con successo.")
        else:
            print(f"[redirect] Nessuna modifica da pushare su git.")
        return 0
    except Exception as e:
        print(f"[redirect] Errore push: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())