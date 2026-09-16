import asyncio
import base64
import json
import re
import urllib.parse
from rich.console import Console
from rich.prompt import Prompt

from dazn_navigator2.cli.aggiungi_cmds import parse_evento_da_link, CATEGORIA_EVENTI
from dazn_navigator2.cli.eventi_cmds import add_event, pubblica
from dazn_navigator2.services.extractor import WIDEVINE_SID

console = Console()

TEST_DEFAULT_URL = "https://swisslau1-3-dash-pvr.zahs.tv/HD_dazn_event_7_ch/1788011856000/1788029100800/m_drm_widevine.mpd?z32=MF2WI2LPL5RW6ZDFMNZT2YLBMMTGG43JMQ6TCOCEGA2EENKEIEZUCMBVIRCEELJSIJCEGM2CGQ2UCNZYIVBTCQSBEZSHE3J5MV4HA2LSMF2GS33OHIYTOOBYGYYTMNZRG4TGK5TFNZ2D2MJGNFXGS5DJMFWHEYLUMU6TQMBQGATG2YLYOJQXIZJ5HAYDAMBGNVUW44TBORST2MJQGAYCM4DSMVTGK4TSMVSF63DBNZTXKYLHMU6WS5BGONUWOPJUHBPWMZTEMRRWENDCGQYGMOLCGI2GGOJXGBTGKMJUMFRWCYLCMRTGENJGON2WE5DJORWGK4Z5NBUWIZDFNYWXGZDIEZ2HIPJREZ2XGZLSL5UWIPLTNN4V6Y3IHI5DKMBTGA4DKJTWHUYA"


async def _fetch_mpd_and_pssh(mpd_url: str):
    """Scarica il file MPD ed estrae l'eventuale PSSH Widevine."""
    from curl_cffi.requests import AsyncSession
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Referer": "https://zattoo.com/",
        "Origin": "https://zattoo.com"
    }
    async with AsyncSession(impersonate="chrome110") as s:
        resp = await s.get(mpd_url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return None, "HTTP Error %d" % resp.status_code
        
        body = resp.text
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(body)
            for el in root.iter():
                if el.tag.endswith("}pssh"):
                    b64 = (el.text or "").strip()
                    if b64:
                        return b64, None
            return None, "Nessun PSSH trovato nell'MPD"
        except Exception as e:
            return None, "Errore parsing XML MPD: %s" % e


def run_test_swiss_extraction():
    """Menu tasto 12: testa l'estrazione evento da link zahs.tv."""
    console.print("\n[bold magenta]=== TEST ESTRAZIONE DAZN SVIZZERA (zahs.tv) ===[/bold magenta]")
    console.print("[dim]Link predefinito di test:[/dim]\n[cyan]%s...[/cyan]\n" % TEST_DEFAULT_URL[:95])

    titolo = Prompt.ask("Titolo evento", default="DAZN 7 CH (Test Svizzera)").strip()
    link = Prompt.ask("Link MPD (premi Invio per usare il link predefinito)", default=TEST_DEFAULT_URL).strip()
    if not link:
        link = TEST_DEFAULT_URL

    console.print("\n[cyan]1. Analisi link ed estrazione parametri...[/cyan]")
    
    # Prova a scaricare MPD per estrarre PSSH
    console.print("[cyan]2. Connessione all'endpoint MPD zahs.tv...[/cyan]")
    try:
        pssh, err = asyncio.run(_fetch_mpd_and_pssh(link))
        if pssh:
            console.print("[green]✓ PSSH Widevine individuato:[/green] [dim]%s[/dim]" % pssh)
        else:
            console.print("[yellow]PSSH non recuperato direttamente: %s[/yellow]" % err)
    except Exception as e:
        console.print("[yellow]Nota download MPD: %s[/yellow]" % e)

    entry = parse_evento_da_link(link, titolo)
    if not entry or not entry.get('mpd'):
        console.print("[red]Impossibile estrarre un MPD valido dal link fornito.[/red]")
        return

    entry['type'] = 'evento'

    # Stampa dettagli
    console.print("\n[bold green]=== RISULTATO ESTRAZIONE TEST ===[/bold green]")
    console.print("[bold]Nome:[/bold] %s" % entry['name'])
    console.print("[bold]MPD:[/bold] %s" % entry['mpd'])
    console.print("[bold]Key (ClearKey/KID:KEY):[/bold] %s" % (entry.get('key') or '(Nessuna - Widevine Zahs)'))
    console.print("[bold]Tipo:[/bold] %s" % entry['type'])
    console.print("[bold]User-Agent:[/bold] %s" % entry.get('ua'))

    salva = Prompt.ask("\nVuoi aggiungere questo evento a test.json (EVENTI)?", choices=["s", "n"], default="n").strip().lower()
    if salva == "s":
        add_event(CATEGORIA_EVENTI, entry)
        console.print("[green]Aggiunto con successo a '%s'![/green]" % CATEGORIA_EVENTI)
        pubblica("test_cmds: aggiunto test '%s' a EVENTI" % entry['name'])
