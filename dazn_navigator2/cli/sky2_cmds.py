"""Modulo per sincronizzare i canali Sky2 in TEMPO REALE da skycript worker (AES-256) e pubblicarli su sky2.json CIFRATO (Password: 2941) nel repo zadonkais."""

import os
import re
import json
import base64
import hashlib
import subprocess
import requests
from pathlib import Path
from rich.console import Console
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

console = Console()

HTDOCS_REPO = Path(r"C:\Users\alecl\Desktop\htdocs")
NEXT_REPO = Path(r"C:\Users\alecl\Desktop\next")
M3U_FILE = Path(r"C:\Users\alecl\Desktop\SKY_DEFINITIVO_COMPLETO.m3u")
GIT_EXE = r"C:\Program Files\Git\cmd\git.exe"
if not os.path.exists(GIT_EXE):
    GIT_EXE = "git"

SKY_WORKER_URL = "https://skycript.oren-enoz.workers.dev/"
DECRYPT_PASSWORD = "IPXfJrt68qLZ3J9T4UCU78mS2RzuSvUrt3FKCzyqkDOaw3gF93oeduLByciL"

# MASTER PASSWORD PER LA CIFRATURA DEL SITO
SITE_MASTER_PASSWORD = "2941"
SITE_SALT = b"zadonkais_secure_salt_2026"
_CACHED_SITE_KEY = None

def derive_site_key(password: str = SITE_MASTER_PASSWORD) -> bytes:
    global _CACHED_SITE_KEY
    if _CACHED_SITE_KEY is not None and password == SITE_MASTER_PASSWORD:
        return _CACHED_SITE_KEY
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SITE_SALT,
        iterations=100000,
        backend=default_backend()
    )
    key = kdf.derive(password.encode('utf-8'))
    if password == SITE_MASTER_PASSWORD:
        _CACHED_SITE_KEY = key
    return key


def decrypt_site_payload(b64payload: str, password: str = SITE_MASTER_PASSWORD) -> dict:
    key = derive_site_key(password)
    aesgcm = AESGCM(key)
    raw = base64.b64decode(b64payload)
    iv = raw[:12]
    ct = raw[12:]
    pt = aesgcm.decrypt(iv, ct, None)
    return json.loads(pt.decode('utf-8'))

def encrypt_site_payload(data: dict, password: str = SITE_MASTER_PASSWORD) -> str:
    key = derive_site_key(password)
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    plaintext = json.dumps(data, ensure_ascii=False).encode('utf-8')
    ciphertext = aesgcm.encrypt(iv, plaintext, None)
    payload = iv + ciphertext
    return base64.b64encode(payload).decode('ascii')

LOGO_MAP = {
    "sky uno": "https://pixel.disco.nowtv.it/logo/skychb_477_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky uno +": "https://pixel.disco.nowtv.it/logo/skychb_477_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky atlantic": "https://pixel.disco.nowtv.it/logo/skychb_226_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky serie": "https://pixel.disco.nowtv.it/logo/skychb_684_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky investigation": "https://pixel.disco.nowtv.it/logo/skychb_686_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky collection": "https://pixel.disco.nowtv.it/logo/skychb_431_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "comedy central": "https://pixel.disco.nowtv.it/logo/skychb_404_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "mtv": "https://pixel.disco.nowtv.it/logo/skychb_763_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky tg24": "https://pixel.disco.nowtv.it/logo/skychb_519_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport 24": "https://pixel.disco.nowtv.it/logo/skychb_35_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport uno": "https://pixel.disco.nowtv.it/logo/skychb_23_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport calcio": "https://pixel.disco.nowtv.it/logo/skychb_209_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport tennis": "https://pixel.disco.nowtv.it/logo/skychb_559_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport arena": "https://pixel.disco.nowtv.it/logo/skychb_24_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport max": "https://pixel.disco.nowtv.it/logo/skychb_248_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport golf": "https://pixel.disco.nowtv.it/logo/skychb_768_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport f1": "https://pixel.disco.nowtv.it/logo/skychb_478_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport motogp": "https://pixel.disco.nowtv.it/logo/skychb_483_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport basket": "https://pixel.disco.nowtv.it/logo/skychb_764_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport legend": "https://pixel.disco.nowtv.it/logo/skychb_951_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky sport mix": "https://pixel.disco.nowtv.it/logo/skychb_961_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema uno": "https://pixel.disco.nowtv.it/logo/skychb_202_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema due": "https://pixel.disco.nowtv.it/logo/skychb_564_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema collection": "https://pixel.disco.nowtv.it/logo/skychb_204_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema family": "https://pixel.disco.nowtv.it/logo/skychb_255_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema action": "https://pixel.disco.nowtv.it/logo/skychb_206_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema suspense": "https://pixel.disco.nowtv.it/logo/skychb_47_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema romance": "https://pixel.disco.nowtv.it/logo/skychb_231_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema drama": "https://pixel.disco.nowtv.it/logo/skychb_769_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema comedy": "https://pixel.disco.nowtv.it/logo/skychb_30_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky cinema stories": "https://pixel.disco.nowtv.it/logo/skychb_564_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky arte": "https://pixel.disco.nowtv.it/logo/skychb_74_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky documentaries": "https://pixel.disco.nowtv.it/logo/skychb_697_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky nature": "https://pixel.disco.nowtv.it/logo/skychb_772_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky adventure": "https://pixel.disco.nowtv.it/logo/skychb_775_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "history": "https://pixel.disco.nowtv.it/logo/skychb_320_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "sky crime": "https://pixel.disco.nowtv.it/logo/skychb_367_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "cartoon network": "https://pixel.disco.nowtv.it/logo/skychb_234_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "boomerang": "https://pixel.disco.nowtv.it/logo/skychb_233_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "deakids": "https://pixel.disco.nowtv.it/logo/skychb_249_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "nickelodeon": "https://pixel.disco.nowtv.it/logo/skychb_258_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
    "nick jr": "https://pixel.disco.nowtv.it/logo/skychb_513_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT",
}

def clean_channel_name(raw_name: str) -> str:
    n = re.sub(r'\s+FHD\b', '', raw_name, flags=re.I).strip()
    
    # Normalizza SPORT X -> Sky Sport X
    m_sport = re.match(r'^SPORT\s+(.+)$', n, flags=re.I)
    if m_sport:
        sub = m_sport.group(1).strip()
        specials = {
            "24": "24", "uno": "Uno", "calcio": "Calcio", "tennis": "Tennis",
            "arena": "Arena", "basket": "Basket", "max": "Max", "f1": "F1",
            "motogp": "MotoGP", "golf": "Golf", "legend": "Legend", "mix": "Mix"
        }
        sub_clean = specials.get(sub.lower(), sub.title())
        return f"Sky Sport {sub_clean}"

    # Normalizza SKY X -> Sky X
    m_sky = re.match(r'^SKY\s+(.+)$', n, flags=re.I)
    if m_sky:
        sub = m_sky.group(1).strip()
        if sub.lower() in ["uno plus", "uno+"]:
            return "Sky Uno +"
        return f"Sky {sub.title()}"
    
    if n.upper() == "TG 24" or n.upper() == "TG24":
        return "Sky Tg24"
    if n.upper() == "HISTORY":
        return "History"
    if n.upper() == "COMEDY CENTRAL":
        return "Comedy Central"
    if n.upper() == "MTV":
        return "MTV"
        
    return n

def determine_group(name: str, m3u_group: str) -> str:
    n = name.lower().strip()
    g = m3u_group.upper().strip()
    
    # 1. Sky Sport
    if g == "SPORT" or "sky sport" in n or "skysport" in n or re.match(r'^(sky\s+)?sport\b', n):
        return "Sky Sport"
        
    # 2. Sky Bambini
    if any(k in n for k in ["deakids", "nick jr", "nickelodeon", "cartoon network", "boomerang", "baby tv", "babytv"]):
        return "Sky Bambini"
        
    # 3. Sky Cinema
    if "cinema" in n:
        return "Sky Cinema"
        
    # 4. Sky Intrattenimento
    if g == "INTRATTENIMENTO" or any(k in n for k in ["sky uno", "atlantic", "serie", "investigation", "collection", "adventure", "crime", "documentaries", "nature", "history", "comedy central", "arte", "mtv", "tg24", "tg 24"]):
        return "Sky Intrattenimento"
        
    # 5. Gruppi M3U Standard
    if g == "RAI":
        return "RAI"
    if g == "MEDIASET":
        return "MEDIASET"
    if g == "DISCOVERY":
        return "DISCOVERY"
    if g == "ALTRI":
        return "ALTRI"
        
    return g if g else "ALTRI"

def get_logo(name: str, default_logo: str) -> str:
    n = name.lower().strip()
    if n in LOGO_MAP:
        return LOGO_MAP[n]
    for k, v in LOGO_MAP.items():
        if k in n:
            return v
    if "25" in n and "sky sport" in n:
        num = re.search(r'25\d', n)
        if num:
            return f"https://ui-avatars.com/api/?name=Sky+Sport+{num.group(0)}&background=0D8ABC&color=fff&size=256&font-size=0.3"
    if default_logo:
        return default_logo
    safe_name = name.replace(' ', '+')
    return f"https://ui-avatars.com/api/?name={safe_name}&background=0D8ABC&color=fff&size=256&font-size=0.3&v=3"

def _extract_exp(mpd: str) -> int:
    """Estrae il timestamp di scadenza dal token e~ nell'URL MPD. Restituisce 0 se assente."""
    m = re.search(r'e~(\d+)', mpd)
    return int(m.group(1)) if m else 0

def fetch_and_decrypt_m3u():
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(SKY_WORKER_URL, headers=headers, timeout=12)
        if resp.status_code == 200 and len(resp.text) > 1000:
            encrypted_str = resp.text.strip()
            key = hashlib.sha256(DECRYPT_PASSWORD.encode('utf-8')).digest()
            raw_bytes = base64.b64decode(encrypted_str)
            iv = raw_bytes[:16]
            ciphertext = raw_bytes[16:]

            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            dec = decryptor.update(ciphertext) + decryptor.finalize()
            m3u_text = dec.decode('utf-8', errors='ignore').rstrip('\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10')
            
            with open(M3U_FILE, "w", encoding="utf-8") as f:
                f.write(m3u_text)
            console.print("[green][OK] Scaricato e decifrato payload live dal Worker Cloudflare![/green]")
            return m3u_text
    except Exception as e:
        console.print(f"[yellow]Attenzione: download dal Worker fallito ({e}), uso fallback locale...[/yellow]")
    
    if M3U_FILE.exists():
        return M3U_FILE.read_text(encoding="utf-8")
    return None

def sync_sky2_site():
    console.print("\n[bold cyan]=== Sincronizzazione Canali Sky 2 (Cifratura AES-256 Impenetrabile) ===[/bold cyan]")
    console.print(f"[cyan]Interrogazione worker {SKY_WORKER_URL}...[/cyan]")
    
    m3u_text = fetch_and_decrypt_m3u()
    if not m3u_text:
        console.print("[red]Errore: Impossibile ottenere la lista canali M3U.[/red]")
        return

    lines = [l.strip() for l in m3u_text.splitlines() if l.strip()]

    # Usa dict keyed by name.lower() per deduplicare: mantiene entry con scadenza più lontana
    output_data = {
        "Sky Sport": {},
        "Sky Cinema": {},
        "Sky Intrattenimento": {},
        "Sky Bambini": {},
        "RAI": {},
        "MEDIASET": {},
        "DISCOVERY": {},
        "ALTRI": {}
    }

    m3u_parsed_counts = 0
    for i in range(len(lines)):
        if lines[i].startswith("#EXTINF"):
            inf_line = lines[i]
            
            raw_name = inf_line.split(",")[-1].strip()
            name = clean_channel_name(raw_name) if raw_name else "Canale"

            group_match = re.search(r'group-title="([^"]*)"', inf_line)
            m3u_group = group_match.group(1) if group_match else ""

            logo_match = re.search(r'tvg-logo="([^"]*)"', inf_line)
            raw_logo = logo_match.group(1) if logo_match else ""

            key_val = ""
            mpd_val = ""
            for j in range(i+1, min(i+5, len(lines))):
                if "license_key=" in lines[j]:
                    key_val = lines[j].split("license_key=")[-1].strip()
                elif lines[j].startswith("http"):
                    mpd_val = lines[j].strip()
                    break

            if mpd_val:
                group = determine_group(name, m3u_group)
                logo = get_logo(name, raw_logo)
                
                entry = {
                    "key": key_val,
                    "name": name,
                    "logo": logo,
                    "mpd": mpd_val
                }
                
                if group not in output_data:
                    output_data[group] = {}
                
                name_key = name.lower().strip()
                existing_entry = output_data[group].get(name_key)
                if existing_entry is None:
                    output_data[group][name_key] = entry
                else:
                    # Mantieni l'entry con scadenza più lontana
                    if _extract_exp(mpd_val) > _extract_exp(existing_entry["mpd"]):
                        output_data[group][name_key] = entry
                m3u_parsed_counts += 1

    # Converti i dict di dedup in liste
    output_data = {cat: list(entries.values()) for cat, entries in output_data.items()}

    # Ordine canonico definitivo del sito
    canonical_order = [
        "Sky Sport",
        "Sky Cinema",
        "Sky Intrattenimento",
        "Sky Bambini",
        "RAI",
        "MEDIASET",
        "DISCOVERY",
        "ALTRI"
    ]
    ordered_output = {}
    for cat in canonical_order:
        if cat in output_data and len(output_data[cat]) > 0:
            ordered_output[cat] = output_data[cat]
    for cat, items in output_data.items():
        if cat not in ordered_output and len(items) > 0:
            ordered_output[cat] = items

    total_parsed = sum(len(v) for v in ordered_output.values())

    # Cifra l'intero JSON con AES-256-GCM Master Password "2941"
    console.print(f"[cyan]Cifratura AES-256-GCM con Master Password univoca...[/cyan]")
    encrypted_base64 = encrypt_site_payload(output_data, SITE_MASTER_PASSWORD)
    encrypted_file_content = {
        "enc": encrypted_base64
    }

    sky2_path = HTDOCS_REPO / "sky2.json"
    sky2_text = json.dumps(encrypted_file_content, indent=2) + "\n"
    with open(sky2_path, "w", encoding="utf-8") as f:
        f.write(sky2_text)

    # Scrittura anche su next/public/sky2.json
    next_sky2_path = NEXT_REPO / "public" / "sky2.json"
    if next_sky2_path.parent.exists():
        try:
            next_sky2_path.write_text(sky2_text, encoding="utf-8")
            console.print(f"[green]File salvato in: {next_sky2_path}[/green]")
        except Exception:
            pass

    # Sincronizza sky2.json e guida_tv_sky.json anche in kodi_repo per l'addon Kodi (luishighnest/kodi)
    kodi_repo_path = Path(r"C:\Users\alecl\Desktop\kodi_repo")
    if kodi_repo_path.exists():
        try:
            (kodi_repo_path / "sky2.json").write_text(json.dumps(encrypted_file_content, indent=2) + "\n", encoding="utf-8")
            guida_src = HTDOCS_REPO / "guida_tv_sky.json"
            if guida_src.exists():
                import shutil
                shutil.copy2(guida_src, kodi_repo_path / "guida_tv_sky.json")
        except Exception:
            pass

    console.print(f"[bold green][OK] Convertiti e CIFRATI con successo {total_parsed} canali in {sky2_path.name}[/bold green]")
    for g, chs in output_data.items():
        console.print(f"  [dim]- {g}: {len(chs)} canali[/dim]")

    # Sincronizzazione automatica su Upstash Redis Cloud (Zero Git!)
    console.print("\n[cyan]Sincronizzazione canali Sky 2 su Upstash Redis Cloud (Zero Git)...[/cyan]")
    ok_redis = False
    try:
        from dazn_navigator2.services.redis_sync import sync_to_upstash
        ok_redis = sync_to_upstash("sky2", output_data)
    except Exception:
        pass

    if ok_redis:
        console.print("[bold green][OK] Canali Sky 2 sincronizzati istantaneamente su Upstash Redis Cloud![/bold green]")
    else:
        try:
            import requests
            from dazn_navigator2.settings import get_setting
            api_url = get_setting("site_api_url") or "http://localhost:3000/api"
            api_key = get_setting("site_api_key") or "zadonkais_secret_2026"
            requests.post(f"{api_url}/sky", json={"source": "sky2", "data": output_data}, headers={"x-api-key": api_key}, timeout=4)
        except Exception:
            pass
        console.print("[green][OK] Canali Sky 2 salvati in locale.[/green]")

if __name__ == "__main__":
    sync_sky2_site()
