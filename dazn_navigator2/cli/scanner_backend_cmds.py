"""Modulo per la scansione automatica di canali MPD nascosti, feed POP e canali di test nel backend DAZN."""

import asyncio
import json
import re
from typing import List, Dict
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from dazn_navigator2.services.extractor import HeadlessExtractor
from dazn_navigator2.auth.token_refresh import PROFILE_DIR
from dazn_navigator2.api.client import DaznClient
from dazn_navigator2.cli.eventi_cmds import add_event, pubblica
from dazn_navigator2.cli.aggiungi_cmds import parse_evento_da_link, DEFAULT_UA, CATEGORIA_EVENTI

console = Console()

# Pattern di ID noti e storici usati nel backend DAZN per canali lineari / test / backup / feed POP
CANDIDATE_ASSET_IDS = [
    # Canali lineari classici / numerati
    "dazn1", "dazn2", "dazn3", "dazn4", "dazn5", "dazn6",
    "dazn_1", "dazn_2", "dazn_3", "dazn_4", "dazn_5", "dazn_6",
    "dazn_it_1", "dazn_it_2", "dazn_it_3", "dazn_it_4", "dazn_it_5", "dazn_it_6",
    "dazn_channel_1", "dazn_channel_2", "dazn_channel_3", "dazn_channel_4", "dazn_channel_5", "dazn_channel_6",
    "dazn_linear_1", "dazn_linear_2", "dazn_linear_3", "dazn_linear_4", "dazn_linear_5", "dazn_linear_6",
    "channel_01", "channel_02", "channel_03", "channel_04", "channel_05", "channel_06",
    "channel_1", "channel_2", "channel_3", "channel_4", "channel_5", "channel_6",
    
    # Zona DAZN e varianti
    "zonadazn", "zonadazn1", "zonadazn2", "zonadazn3", "zonadazn4", "zonadazn5",
    "zona_dazn", "zona_dazn_1", "zona_dazn_2", "zona_dazn_3", "zona_dazn_4", "zona_dazn_5",
    "zona_dazn_dtt", "zona_dazn_sat", "zona_dazn_backup",

    # Pop-up channels & feed di contribuzione
    "pop1", "pop2", "pop3", "pop4", "pop5", "pop6",
    "pop_1", "pop_2", "pop_3", "pop_4", "pop_5", "pop_6",
    "pop_channel_1", "pop_channel_2", "pop_channel_3", "pop_channel_4", "pop_channel_5", "pop_channel_6",
    "feed_1", "feed_2", "feed_3", "feed_4", "feed_5", "feed_6",
    "live_linear_1", "live_linear_2", "live_linear_3", "live_linear_4", "live_linear_5", "live_linear_6",

    # Test / Backup / Staging
    "test_channel_1", "test_channel_2", "test_channel_3",
    "backup_1", "backup_2", "backup_3",
    "euro_linear_1", "euro_linear_2", "event_linear_1", "event_linear_2"
]

# Query speciali su Rail API per stanare sezioni interne non presenti sul sito web
HIDDEN_RAIL_QUERIES = [
    {"groupId": "HiddenLinear", "params": "PageType:TvChannels"},
    {"groupId": "TvGuide", "params": "PageType:LinearSchedule"},
    {"groupId": "Home", "params": "PageType:TvGuide"},
    {"groupId": "Admin", "params": "PageType:LiveTest"},
    {"groupId": "Epg", "params": "PageType:Linear"},
    {"groupId": "Home", "params": "Platform:androidtv"},
    {"groupId": "Home", "params": "Platform:smarttv"},
]


async def scan_hidden_rails(client: DaznClient) -> List[Dict]:
    """Cerca canali o asset ID nascosti nelle Rails di backend."""
    discovered = []
    seen_ids = set()

    for q in HIDDEN_RAIL_QUERIES:
        try:
            params = {
                "platform": "web",
                "country": "it",
                "brand": "dazn",
                "languageCode": "it",
                **q
            }
            res = await client.get("/Rails", params=params)
            rails = res.get("Rails", [])
            for r in rails:
                for t in r.get("Tiles", []):
                    aid = t.get("AssetId") or t.get("Id")
                    title = t.get("Title") or t.get("Label") or "Canale Nascosto"
                    if aid and aid not in seen_ids:
                        seen_ids.add(aid)
                        discovered.append({"id": aid, "title": title, "source": f"Rail ({q.get('groupId')})"})
        except Exception:
            continue

    return discovered


async def probe_asset(extractor: HeadlessExtractor, asset_id: str, title: str = "") -> Dict:
    """Tenta l'estrazione Playback API e DRM per un assetId."""
    try:
        res = await extractor.estrai(PROFILE_DIR, asset_id, titolo=title)
        if res.get("ok") and res.get("mpd_url"):
            return {
                "id": asset_id,
                "title": title or f"Feed Backend ({asset_id})",
                "mpd": res["mpd_url"],
                "key": res.get("keys") or "",
                "status": "Attivo (200 OK)",
                "success": True
            }
        else:
            return {
                "id": asset_id,
                "title": title or asset_id,
                "status": res.get("error") or "Non attivo / Non trovato",
                "success": False
            }
    except Exception as e:
        return {
            "id": asset_id,
            "title": title or asset_id,
            "status": str(e),
            "success": False
        }


def run_backend_scanner():
    """Menu interattivo per la scansione canali nascosti DAZN."""
    console.print("\n[bold magenta]═══ SCANNER CANALI MPD NASCOSTI & BACKEND DAZN ═══[/bold magenta]")
    console.print("[dim]Scansiona i servizi di Playback e le Rails interne alla ricerca di feed continui non visibili.[/dim]\n")

    console.print("[bold cyan]1.[/bold cyan] Scansione Completa (Pattern ID noti + Rails Nascoste)")
    console.print("[bold cyan]2.[/bold cyan] Scansione Rapida Feed POP / DAZN 1-6 Storici")
    console.print("[bold cyan]3.[/bold cyan] Scansione ID Personalizzato / Range Manuale")
    console.print("[bold cyan]0.[/bold cyan] Indietro")

    scelta = Prompt.ask("\nScegli un'opzione", default="1").strip()
    if scelta == "0" or not scelta:
        return

    async def _execute_scan():
        extractor = HeadlessExtractor()
        client = DaznClient()
        to_scan = []
        seen = set()

        def _add(aid, name=""):
            if aid not in seen:
                seen.add(aid)
                to_scan.append({"id": aid, "title": name})

        if scelta == "1":
            console.print("[cyan]1/2 Ricerca nelle Rail nascoste del backend...[/cyan]")
            rail_items = await scan_hidden_rails(client)
            for it in rail_items:
                _add(it["id"], it["title"])

            for aid in CANDIDATE_ASSET_IDS:
                _add(aid, f"Feed ID: {aid}")

        elif scelta == "2":
            pop_ids = [
                "dazn1", "dazn2", "dazn3", "dazn4", "dazn5", "dazn6",
                "zonadazn", "zonadazn1", "zonadazn2", "zonadazn3", "zonadazn4", "zonadazn5",
                "pop1", "pop2", "pop3", "pop4", "pop5", "pop6",
                "channel_01", "channel_02", "channel_03", "channel_04", "channel_05", "channel_06"
            ]
            for aid in pop_ids:
                _add(aid, f"Feed POP: {aid}")

        elif scelta == "3":
            prefix = Prompt.ask("Inserisci prefisso ID (es. 'channel_' o 'dazn_')", default="channel_").strip()
            start_n = int(Prompt.ask("Numero iniziale", default="1"))
            end_n = int(Prompt.ask("Numero finale", default="10"))
            for i in range(start_n, end_n + 1):
                aid = f"{prefix}{i:02d}" if "0" in prefix else f"{prefix}{i}"
                _add(aid, f"Manuale: {aid}")
                _add(f"{prefix}{i}", f"Manuale: {prefix}{i}")

        if not to_scan:
            console.print("[yellow]Nessun ID da scansionare.[/yellow]")
            return

        console.print(f"\n[cyan]Avvio scansione di [bold]{len(to_scan)}[/bold] canali/feed con Playback API e CDM...[/cyan]\n")

        active_channels = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[yellow]Scansione backend in corso...", total=len(to_scan))

            for item in to_scan:
                progress.update(task, description=f"[cyan]Testando: [bold]{item['id']}[/bold]")
                res = await probe_asset(extractor, item["id"], item["title"])
                if res["success"]:
                    active_channels.append(res)
                    console.print(f"[bold green]✔ TROVATO CANALE ATTIVO:[/bold green] {item['id']} -> {res['mpd'][:60]}...")
                progress.advance(task)

        # Risultati
        console.print("\n")
        if not active_channels:
            console.print("[bold yellow]Nessun canale nascosto ha risposto con uno stream attivo al momento.[/bold yellow]")
            console.print("[dim]Nota: Molti feed vengono accesi dal backend solo a ridosso degli eventi live.[/dim]")
            return

        console.print(f"[bold green]═══ RISULTATO: {len(active_channels)} CANALI MPD TROVATI ATTIVI! ═══[/bold green]\n")

        table = Table(title="Canali Nascosti Rilevati", show_header=True, header_style="bold magenta")
        table.add_column("#", style="bold cyan", width=4)
        table.add_column("Asset ID", style="bold")
        table.add_column("Titolo / Descrizione", style="white")
        table.add_column("MPD URL", style="blue")
        table.add_column("ClearKey", style="green")

        for idx, ch in enumerate(active_channels, 1):
            table.add_row(
                str(idx),
                ch["id"],
                ch["title"],
                ch["mpd"][:45] + "..." if len(ch["mpd"]) > 45 else ch["mpd"],
                ch["key"] or "[dim]In chiaro / Senza DRM[/dim]"
            )

        console.print(table)

        # Esportazione
        scelta_exp = Prompt.ask("\nVuoi salvare i canali trovati su test.json (EVENTI)? (s/n)", default="s").strip().lower()
        if scelta_exp in ("s", "si", "y", "yes"):
            for ch in active_channels:
                full_raw = f"{ch['mpd']}|{ch['key']}" if ch['key'] else ch['mpd']
                entry = parse_evento_da_link(full_raw, ch['title'])
                if not entry:
                    entry = {
                        'name': ch['title'],
                        'image': '',
                        'start': '',
                        'end': '',
                        'mpd': ch['mpd'],
                        'key': ch['key'],
                        'ua': DEFAULT_UA,
                        'type': 'canale'
                    }
                add_event(CATEGORIA_EVENTI, entry)
                console.print(f"[green]✔ Aggiunto: {entry['name']}[/green]")

            pubblica(f"dazn2: aggiunti {len(active_channels)} canali MPD nascosti da backend scanner")
            console.print("[bold green]✔ Pubblicazione su GitHub & Sito completata con successo![/bold green]")

    from dazn_navigator2.main import run_async
    run_async(_execute_scan())
