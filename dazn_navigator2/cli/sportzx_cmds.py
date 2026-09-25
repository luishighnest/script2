"""Sincronizzazione Eventi Sportzx: scarica da dudetvapi (come scrape_sportzx.py),
filtra gli eventi di oggi, salva sportzx.json (locale + fallback sito) e pubblica
sull'API via Upstash Redis Cloud (stream:sportzx_cached)."""

import json
import os
import subprocess
import time
import webbrowser

import requests
from pathlib import Path
from rich.console import Console

console = Console()

BASE = "https://raw.githubusercontent.com/mdjamsad9/dudetvapi/main/public_decrypted"
SPORTZX_SOURCE_DIR = Path(r"C:\Users\alecl\Desktop\Sportzx - Htsport")
NEXT_REPO = Path(r"C:\Users\alecl\Desktop\next")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
sess = requests.Session()
sess.headers.update(HEADERS)

SITO_URL = "https://luishighnest.github.io/next"
SCRIPT2_URL = "https://luishighnest.github.io/script2/"
AVVIA_SCRIPT2_VBS = r"C:\Users\alecl\Desktop\Avvia Script2.vbs"


def fetch(path, base=BASE):
    for attempt in range(3):
        try:
            r = sess.get(f"{base}/{path}", timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            console.print(f"  [dim yellow]retry {attempt + 1}/3 su {path}: {exc}[/dim yellow]")
            time.sleep(3)
    raise RuntimeError(f"fallimento su {path}")


def sync_sportzx_site():
    console.print("\n[bold cyan]=== Sincronizzazione Eventi Sportzx (dudetvapi) ===[/bold cyan]")
    data = fetch("events_with_channels.json")
    data.sort(key=lambda e: e.get("eventInfo", {}).get("startTime", ""))
    if not data:
        console.print("[red]Nessun evento trovato nel remoto.[/red]")
        return
    console.print(f"[cyan]Trovati {len(data)} eventi (oggi e prossimi)...[/cyan]")

    text = json.dumps(data, ensure_ascii=False, indent=2)

    SPORTZX_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    out_src = SPORTZX_SOURCE_DIR / "sportzx.json"
    out_src.write_text(text, encoding="utf-8")
    console.print(f"[green]File salvato in: {out_src}[/green]")

    next_json = NEXT_REPO / "public" / "sportzx.json"
    if next_json.parent.exists():
        try:
            next_json.write_text(text, encoding="utf-8")
            console.print(f"[green]File salvato in: {next_json}[/green]")
        except Exception:
            pass

    console.print("[cyan]Pubblicazione eventi sportzx su Upstash Redis Cloud (Zero Git)...[/cyan]")
    ok_redis = False
    try:
        from dazn_navigator2.services.redis_sync import sync_to_upstash
        ok_redis = sync_to_upstash("sportzx_cached", data)
    except Exception:
        pass

    if ok_redis:
        console.print("[bold green][OK] Eventi Sportzx pubblicati istantaneamente sull'API![/bold green]")
    else:
        console.print("[yellow]Upstash non disponibile: resto i dati nel file locale (fallback del sito).[/yellow]")


def avvia_script2():
    console.print("\n[bold cyan]=== Avvio Script2 ===[/bold cyan]")
    if not os.path.exists(AVVIA_SCRIPT2_VBS):
        console.print(f"[red]VBS non trovato: {AVVIA_SCRIPT2_VBS}[/red]")
        return
    subprocess.Popen(["wscript.exe", AVVIA_SCRIPT2_VBS])
    console.print(f"[green]Lanciato in background: {AVVIA_SCRIPT2_VBS}[/green]")
    webbrowser.open(SCRIPT2_URL)
    console.print(f"[cyan]Apertura nel browser: {SCRIPT2_URL}[/cyan]")


def apri_sito():
    console.print("\n[bold cyan]=== Apri sito ===[/bold cyan]")
    webbrowser.open(SITO_URL)
    console.print(f"[green]Apertura nel browser: {SITO_URL}[/green]")


if __name__ == "__main__":
    sync_sportzx_site()