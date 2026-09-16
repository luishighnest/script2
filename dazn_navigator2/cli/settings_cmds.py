from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from dazn_navigator2.settings import load_config, toggle_setting

console = Console()

def on_off(val):
    return "[green]ON[/green]" if val else "[red]OFF[/red]"

def settings_menu():
    while True:
        config = load_config()
        engine = config.get('extraction_engine', 'curl_cffi')
        github_deploy = config.get('github_deploy', True)

        if engine == "curl_cffi":
            engine_str = "[bold green]1. Veloce / HTTP (curl_cffi)[/bold green]\n   [dim]→ Richieste API istantanee ad alte prestazioni[/dim]"
        else:
            engine_str = "[bold yellow]2. Browser Headless (Playwright - Metodo dazn2)[/bold yellow]\n   [dim]→ Esegue le richieste direttamente nel browser[/dim]"

        if github_deploy:
            save_str = "[bold green]1. GitHub[/bold green]\n   [dim]→ Pubblica su luishighnest/kodi (test.json)[/dim]"
        else:
            save_str = "[bold yellow]2. Locale[/bold yellow]\n   [dim]→ Salva solo in dazn_event.json nella cartella DAZN1[/dim]"

        menu = f"""[bold cyan]1.[/bold cyan] Mostra Link Estensione in Output: {on_off(config.get('print_extension_link'))}
[bold cyan]2.[/bold cyan] Modalità Salvataggio:
   {save_str}

[bold cyan]3.[/bold cyan] Modalità Debug (Mostra errori grezzi): {on_off(config.get('debug_mode'))}
[bold cyan]4.[/bold cyan] Motore Estrazione:
   {engine_str}

[bold cyan]5.[/bold cyan] User-Agent nel JSON:
   [dim]Veloce (curl_cffi):[/dim]   {on_off(config.get('include_ua_curl', True))}
   [dim]Headless (Playwright):[/dim] {on_off(config.get('include_ua_headless', True))}

[bold cyan]6.[/bold cyan] Download VOD in MP4 automatico: {on_off(config.get('download_vod_mp4'))}

[bold yellow]7.[/bold yellow] 🛠️ [bold yellow]Fix problemi (Auto-Riparazione & Calibrazione)[/bold yellow]

[bold cyan]0.[/bold cyan] ⬅ Torna al menu principale"""

        console.print("\n")
        console.print(Panel(menu, title="[bold magenta]Impostazioni[/bold magenta]", expand=False))
        scelta = Prompt.ask("Scegli un'opzione da modificare", default="0").strip()

        if scelta == "0":
            break
        elif scelta == "1":
            toggle_setting("print_extension_link")
        elif scelta == "2":
            from dazn_navigator2.settings import save_config
            console.print("\n[bold cyan]Scegli dove salvare gli eventi estratti:[/bold cyan]")
            console.print("  [bold green]1[/bold green] → GitHub  (pubblica su luishighnest/kodi → test.json)")
            console.print("  [bold yellow]2[/bold yellow] → Locale  (salva in dazn_event.json nella cartella DAZN1)")
            sub = Prompt.ask("Modalità", choices=["1", "2"], default="1" if github_deploy else "2")
            config['github_deploy'] = (sub == "1")
            save_config(config)
            name_display = "GitHub" if sub == "1" else "Locale (dazn_event.json)"
            console.print(f"\n[bold green]✓ Modalità salvataggio impostata su:[/bold green] [bold cyan]{name_display}[/bold cyan]")
        elif scelta == "3":
            toggle_setting("debug_mode")
        elif scelta == "4":
            from dazn_navigator2.settings import save_config
            console.print("\n[bold cyan]Scegli il metodo predefinito:[/bold cyan]")
            console.print("  [bold green]1[/bold green] → Veloce / HTTP (curl_cffi)")
            console.print("  [bold yellow]2[/bold yellow] → Browser Headless (Playwright - Metodo dazn2)")
            sub = Prompt.ask("Metodo", choices=["1", "2"], default="1" if engine == "curl_cffi" else "2")
            new_engine = "curl_cffi" if sub == "1" else "headless"
            config['extraction_engine'] = new_engine
            save_config(config)
            name_display = "Browser Headless (Playwright - dazn2)" if new_engine == "headless" else "Veloce / HTTP (curl_cffi)"
            console.print(f"\n[bold green]✓ Metodo predefinito impostato su:[/bold green] [bold cyan]{name_display}[/bold cyan]")
        elif scelta == "5":
            console.print("\n[bold cyan]Per quale metodo vuoi cambiare il User-Agent nel JSON?[/bold cyan]")
            console.print(f"  [bold green]1[/bold green] → Veloce (curl_cffi):   {on_off(config.get('include_ua_curl', True))}")
            console.print(f"  [bold yellow]2[/bold yellow] → Headless (Playwright): {on_off(config.get('include_ua_headless', True))}")
            console.print(f"  [bold white]3[/bold white] → Tutti e due")
            sub = Prompt.ask("Metodo", choices=["1", "2", "3"])
            if sub == "1":
                toggle_setting("include_ua_curl")
            elif sub == "2":
                toggle_setting("include_ua_headless")
            else:
                toggle_setting("include_ua_curl")
                toggle_setting("include_ua_headless")
        elif scelta == "6":
            toggle_setting("download_vod_mp4")
        elif scelta == "7":
            import asyncio
            from dazn_navigator2.services.self_healing import run_doctor
            asyncio.run(run_doctor())
        else:
            console.print("[red]Opzione non valida.[/red]")

