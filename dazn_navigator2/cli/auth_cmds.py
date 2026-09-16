import typer
from dazn_navigator2.auth.login import do_login, do_logout

app = typer.Typer(help="Comandi per l'autenticazione.")

@app.command("login")
def login_cmd():
    do_login()

@app.command("logout")
def logout_cmd():
    do_logout()
