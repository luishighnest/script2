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
        
        if engine == "curl_cffi":
            engine_str = "[bold green]1. Veloce / HTTP (curl_cffi)[/bold green]\n   [dim]→ Richieste API istantanee ad alte prestazioni[/dim]"
        else:
            engine_str = "[bold yellow]2. Browser Headless (Playwright - Metodo dazn2)[/bold yellow]\n   [dim]→ Esegue le richieste direttamente nel browser[/dim]"
        
        menu = f"""[bold cyan]1.[/bold cyan] Mostra Link Estensione in Output: {on_off(config.get('print_extension_link'))}
[bold cyan]2.[/bold cyan] Modalità Debug (Mostra errori grezzi): {on_off(config.get('debug_mode'))}
[bold cyan]3.[/bold cyan] Motore Estrazione:
   {engine_str}

[bold cyan]4.[/bold cyan] User-Agent nel JSON:
   [dim]Veloce (curl_cffi):[/dim]   {on_off(config.get('include_ua_curl', True))}
   [dim]Headless (Playwright):[/dim] {on_off(config.get('include_ua_headless', True))}

[bold cyan]0.[/bold cyan] Torna indietro"""

        console.print("\n")
        console.print(Panel(menu, title="[bold magenta]Impostazioni[/bold magenta]", expand=False))
        scelta = Prompt.ask("Scegli un'opzione da modificare", default="0").strip()

        if scelta == "0":
            break
        elif scelta == "1":
            toggle_setting("print_extension_link")
        elif scelta == "2":
            toggle_setting("debug_mode")
        elif scelta == "3":
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
        elif scelta == "4":
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
        else:
            console.print("[red]Opzione non valida.[/red]")
