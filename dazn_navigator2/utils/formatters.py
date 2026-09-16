import json
import csv
from typing import List
from rich.console import Console
from rich.table import Table
from dazn_navigator2.models.event import Event

console = Console()

def print_events_table(title: str, events: List[Event], start_index: int = 1):
    if not events:
        console.print(f"[yellow]Nessun evento trovato per: {title}[/yellow]")
        return

    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("#", style="bold cyan", justify="right", width=4)
    table.add_column("ID", style="dim", width=15)
    table.add_column("Titolo", max_width=35, overflow="ellipsis")
    table.add_column("Sport", max_width=15, overflow="ellipsis", justify="center")
    table.add_column("Competizione", max_width=20, overflow="ellipsis", justify="center")
    table.add_column("Inizio", justify="center", width=12, no_wrap=True)

    for i, event in enumerate(events, start_index):
        sport_name = event.sport.name if event.sport else "N/A"
        comp_name = event.competition.name if event.competition else "N/A"
        start = event.start_time.strftime("%d/%m %H:%M") if event.start_time else "N/A"

        table.add_row(
            str(i),
            str(event.id)[:15] + "...",
            str(event.title),
            sport_name,
            comp_name,
            start
        )

    console.print(table)

def export_to_json(data: List[Event], filename: str):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump([e.model_dump(mode='json') for e in data], f, indent=4, ensure_ascii=False)
    console.print(f"[bold green]Dati esportati in JSON ({filename})[/bold green]")

def export_to_csv(data: List[Event], filename: str):
    if not data:
        return

    with open(filename, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Titolo", "Descrizione", "Inizio", "Fine", "Durata", "Sport", "Competizione", "Immagine Copertina"])
        for e in data:
            sport = e.sport.name if e.sport else ""
            comp = e.competition.name if e.competition else ""
            writer.writerow([
                e.id,
                e.title,
                e.description,
                e.start_time.isoformat() if e.start_time else "",
                e.end_time.isoformat() if e.end_time else "",
                e.duration,
                sport,
                comp,
                e.cover_image
            ])
    console.print(f"[bold green]Dati esportati in CSV ({filename})[/bold green]")
