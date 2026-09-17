"""Aggiorna la pagina GitHub Pages che reindirizza al link tunnel corrente."""
import subprocess
import sys
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
<meta http-equiv="refresh" content="0; url={link}">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<style>
body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; background: #0b0f14; color: #fff; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
a {{ color: #00e59b; }}
</style>
</head>
<body>
<p>Connessione al sito Script2...<br>Se non vieni reindirizzato automaticamente: <a href="{link}">clicca qui</a></p>
<script>window.location.replace("{link}");</script>
</body>
</html>
"""


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

    INDEX.write_text(TEMPLATE.format(link=link), encoding="utf-8")

    repo_url = f"https://x-access-token:{token}@github.com/luishighnest/script2.git"
    try:
        subprocess.run(["git", "config", "user.name", "Render Auto-Sync"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "config", "user.email", "render-sync@users.noreply.github.com"], cwd=str(BASE_DIR), check=True)
        subprocess.run(["git", "add", "index.html"], cwd=str(BASE_DIR), check=True)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(BASE_DIR))
        if diff.returncode != 0:
            subprocess.run(["git", "commit", "-m", "redirect: aggiorna link tunnel"], cwd=str(BASE_DIR), check=True)
            subprocess.run(["git", "push", repo_url, "HEAD:main"], cwd=str(BASE_DIR), check=True)
            print(f"[redirect] Link aggiornato: {link}")
        else:
            print(f"[redirect] Link invariato: {link}")
        return 0
    except Exception as e:
        print(f"[redirect] Errore push: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())