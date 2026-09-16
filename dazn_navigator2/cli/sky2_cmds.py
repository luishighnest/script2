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

HTDOCS_REPO = Path(r"C:\Users\user\Desktop\htdocs")
NEXT_REPO = Path(r"C:\Users\user\Desktop\next")
M3U_FILE = Path(r"C:\Users\user\Desktop\SKY_DEFINITIVO_COMPLETO.m3u")
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

    # 1. Carica le categorie esistenti da sky2.json per preservare Sky Cinema e Sky Bambini
    sky2_path = HTDOCS_REPO / "sky2.json"
    existing_data = {}
    if sky2_path.exists():
        try:
            with open(sky2_path, "r", encoding="utf-8") as f:
                enc_obj = json.load(f)
            if "enc" in enc_obj:
                existing_data = decrypt_site_payload(enc_obj["enc"])
        except Exception:
            pass

    # Backup fallback di Sky Cinema e Sky Bambini se non ancora presenti
    CINEMA_FALLBACK = [
        {"key": "111863abbad4cce241ca8598c84c40fe:6231a62b51c78812fbfda7203a951000", "logo": "https://pixel.disco.nowtv.it/logo/skychb_202_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155525_f~0_g~1_s~4d88e078-43da-470b-9df0-94e8a760b9ea_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~60_x~d0d216503c94833246eb0498eb79e0a0/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycinemauno)/master_2hr-all.mpd?t=v1&c3.ri=6a264c67_Q1ZYMDc_0_Q0xPVURGUk9OVA_95679c0966a3:0&c3.ri=6a264c67_Q1ZYMDc_0_Q0xPVURGUk9OVA_95679c0966a3:0", "name": "Sky Cinema Uno"},
        {"key": "111842d004b5526b6d8d42dcb192a7b2:2ffb5115eeee17ae656610d4ed0a8991", "logo": "https://pixel.disco.nowtv.it/logo/skychb_204_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155526_f~0_g~1_s~596a2d98-1e43-4f96-bd76-9c445ca1c0fe_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~67_x~fa7110dd0aeb29a24446b38c23f46f04/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycinemacollection)/master_2hr-all.mpd?t=v1&c3.ri=6a264c68_Q1ZYMDc_0_Q0xPVURGUk9OVA_8c1b9794cbdb:0&c3.ri=6a264c68_Q1ZYMDc_0_Q0xPVURGUk9OVA_8c1b9794cbdb:0", "name": "Sky Cinema Collection"},
        {"key": "11182a43b0144b044c62720e33725818:cd78f626ac5d5ccca52edb813f2ee1c1", "logo": "https://pixel.disco.nowtv.it/logo/skychb_255_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155527_f~0_g~1_s~be11075f-293e-4e4b-84a1-dbbb746f31ef_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~62_x~7d61189d28db44a307044dfef03d5272/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycinemafamily)/master_2hr-all.mpd?t=v1&c3.ri=6a264c69_Q1ZYMDc_0_Q0xPVURGUk9OVA_183d29a1b023:0&c3.ri=6a264c69_Q1ZYMDc_0_Q0xPVURGUk9OVA_183d29a1b023:0", "name": "Sky Cinema Family"},
        {"key": "1118af1480d8765f680a3eeffe1ae932:a8d8d9dc82b3e3f56e28f863df626fdb", "logo": "https://pixel.disco.nowtv.it/logo/skychb_206_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155529_f~0_g~1_s~d262bf6f-2115-46eb-8e2b-fceeebeee4e8_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~62_x~a357fbb400dd881d7f662908f512781b/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycinemaaction)/master_2hr-all.mpd?t=v1&c3.ri=6a264c6b_Q1ZYMDc_0_Q0xPVURGUk9OVA_22b27ba9e34e:0&c3.ri=6a264c6b_Q1ZYMDc_0_Q0xPVURGUk9OVA_22b27ba9e34e:0", "name": "Sky Cinema Action"},
        {"key": "11188caa4b6ced49f01f390c8b9c3d8b:b86fe4d85aa99b9a2420d59e5e96a6ad", "logo": "https://pixel.disco.nowtv.it/logo/skychb_47_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155530_f~0_g~1_s~ec5f7959-ffef-468e-9080-45aa53e9a7e6_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~64_x~f6cf1a8bc5bf99ca55b41042797e88fb/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycinemasuspense)/master_2hr-all.mpd?t=v1&c3.ri=6a264c6c_Q1ZYMDc_0_Q0xPVURGUk9OVA_c68c221a711a:0&c3.ri=6a264c6c_Q1ZYMDc_0_Q0xPVURGUk9OVA_c68c221a711a:0", "name": "Sky Cinema Suspense"},
        {"key": "1118b308d7860b5a2cfc1353e087aa9b:2ed82203afcaa7c0b6f1a7d7810abf57", "logo": "https://pixel.disco.nowtv.it/logo/skychb_231_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155531_f~0_g~1_s~8bfb8df3-bfda-4467-96bf-bcda873f1d8f_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~63_x~4755fa61f3640ce9760773d1ae9fc9f1/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycinemaromance)/master_2hr-all.mpd?t=v1&c3.ri=6a264c6d_Q1ZYMDc_0_Q0xPVURGUk9OVA_4917fa9eaef3:0&c3.ri=6a264c6d_Q1ZYMDc_0_Q0xPVURGUk9OVA_4917fa9eaef3:0", "name": "Sky Cinema Romance"},
        {"key": "11187f0771eface703670c2e03f25c60:f1a4f55221438edfad33f71ce8d11e53", "logo": "https://pixel.disco.nowtv.it/logo/skychb_769_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155533_f~0_g~1_s~d891fc5a-d9df-41dc-ab5b-dd1855a8fb48_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~61_x~65aa667ee837265be7ce0976ba7d108d/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycinemadrama)/master_2hr-all.mpd?t=v1&c3.ri=6a264c6f_Q1ZYMDc_0_Q0xPVURGUk9OVA_3959bb4254bb:0&c3.ri=6a264c6f_Q1ZYMDc_0_Q0xPVURGUk9OVA_3959bb4254bb:0", "name": "Sky Cinema Drama"},
        {"key": "111836971e38304c36c93efbf3fce921:9dcd57529ba3bce36cb46c384905a989", "logo": "https://pixel.disco.nowtv.it/logo/skychb_30_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155534_f~0_g~1_s~4d8a5563-7182-4148-8df0-9430c6a5839c_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~62_x~7f41fc86a51d2797e88703a11b61cff9/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycinemacomedy)/master_2hr-all.mpd?t=v1&c3.ri=6a264c70_Q1ZYMDc_0_Q0xPVURGUk9OVA_cf03c7e7aa23:0&c3.ri=6a264c70_Q1ZYMDc_0_Q0xPVURGUk9OVA_cf03c7e7aa23:0", "name": "Sky Cinema Comedy"},
        {"key": "11182667efb06ba840c6a8ecf1b8e4d8:6dbcb41305431e6507fab46c25f08e9f", "logo": "https://pixel.disco.nowtv.it/logo/skychb_564_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155536_f~0_g~1_s~fe403063-7901-447a-8f5b-11ee05b9b940_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~63_x~ebfd41458e0a16b9b3e0c0fe8569550e/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycinemastories)/master_2hr-all.mpd?t=v1&c3.ri=6a264c72_Q1ZYMDc_0_Q0xPVURGUk9OVA_9533ad037e5e:0&c3.ri=6a264c72_Q1ZYMDc_0_Q0xPVURGUk9OVA_9533ad037e5e:0", "name": "Sky Cinema Stories"},
        {"key": "111846ad1b8bb11b3f11bf7f0f170701:2cffd969c3e289c667474fdacb23bc17", "logo": "https://pixel.disco.nowtv.it/logo/skychb_431_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155489_f~0_g~1_s~2207b7b1-2182-4166-a67b-1cb81ec4562c_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~59_x~8f4604b126d4052306d860d5b4104085/nowitlin2/Content/CMAF_CTR_H1/Live/channel(skycollection)/master_2hr-all.mpd?t=v1&c3.ri=6a264c43_Q1ZYMDc_0_Q0xPVURGUk9OVA_9706eb782631:0&c3.ri=6a264c43_Q1ZYMDc_0_Q0xPVURGUk9OVA_9706eb782631:0", "name": "Sky Collection"}
    ]

    BAMBINI_FALLBACK = [
        {"key": "11186c855368b14808a44caa148954db:779ac5495ac22c6458b6f705c46b9aef", "logo": "https://pixel.disco.nowtv.it/logo/skychb_249_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155546_f~0_g~1_s~d89d44c9-c127-4a0b-801b-5fae6cba307a_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~53_x~9434863e46c7ba0ef2f2050965d1d604/nowitlin2/Content/CMAF_CTR_H1/Live/channel(deakids)/master_2hr-all.mpd?t=v1&c3.ri=6a264c7c_Q1ZYMDc_0_Q0xPVURGUk9OVA_380aeef50849:0&c3.ri=6a264c7c_Q1ZYMDc_0_Q0xPVURGUk9OVA_380aeef50849:0", "name": "Deakids"},
        {"key": "111857755be339a7e050fb2804479fde:9268ae2adb60f6648d1f49ec1c2f07ae", "logo": "https://pixel.disco.nowtv.it/logo/skychb_513_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155548_f~0_g~1_s~da24cb52-fae0-47fa-8086-53ffb25e1fc5_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~53_x~cb347ec28362629b3528b99c75ae47ff/nowitlin2/Content/CMAF_CTR_H1/Live/channel(nickjr)/master_2hr-all.mpd?t=v1&c3.ri=6a264c7e_Q1ZYMDc_0_Q0xPVURGUk9OVA_3ec7307ecaa0:0&c3.ri=6a264c7e_Q1ZYMDc_0_Q0xPVURGUk9OVA_3ec7307ecaa0:0", "name": "Nick Jr"},
        {"key": "11184d4970ee622e9acdc10016b4112e:d4e99a107ba1c7ab10e0494285bbacf7", "logo": "https://pixel.disco.nowtv.it/logo/skychb_258_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155549_f~0_g~1_s~e0d86927-4a0c-4396-857e-6ae53ffeb2ea_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~57_x~0e83b8b171694f4c2dc9e93ae47dfb21/nowitlin2/Content/CMAF_CTR_H1/Live/channel(nickelodeon)/master_2hr-all.mpd?t=v1&c3.ri=6a264c7f_Q1ZYMDc_0_Q0xPVURGUk9OVA_f68a55b68239:0&c3.ri=6a264c7f_Q1ZYMDc_0_Q0xPVURGUk9OVA_f68a55b68239:0", "name": "Nickelodeon"},
        {"key": "11189c4f64af73ffdc1a8c6bbb6e2f8a:eb3517c592b7774693a2b30e4b39e461", "logo": "https://pixel.disco.nowtv.it/logo/skychb_234_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155550_f~0_g~1_s~d9ba943a-da9b-449e-af54-43ff9e3ee760_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~61_x~d08d9753c162eb04be36bfbb71d7aee7/nowitlin2/Content/CMAF_CTR_H1/Live/channel(cartoonnetwork)/master_2hr-all.mpd?t=v1&c3.ri=6a264c80_Q1ZYMDc_0_Q0xPVURGUk9OVA_49b575ae5e93:0&c3.ri=6a264c80_Q1ZYMDc_0_Q0xPVURGUk9OVA_49b575ae5e93:0", "name": "Cartoon Network"},
        {"key": "1118ba94e4aef8a14f6a0a8427eb25dc:a7d17a614e2ac297c248d9435c99d6e3", "logo": "https://pixel.disco.nowtv.it/logo/skychb_233_darknow/LOGO_CHANNEL_LIGHT/4000?language=it-IT&proposition=NOWOTT", "mpd": "https://g006-lin-it-cmaf-prd-cf.pcdn07.cssott02.com/v~1-0-0_e~1788155552_f~0_g~1_s~eaee0038-f1c2-491d-b8d9-3e3bf9b1fa85_u~c0712fe81439b039492d5b58a626d540e0f19c1da6e63a813cb8c4d6f65e95b309ba4ab0223c0a47120cc0d2625c6b24_k~A_l~55_x~4014f3b14a2b97bfb2d46e9196b0dc1a/nowitlin2/Content/CMAF_CTR_H1/Live/channel(boomerang)/master_2hr-all.mpd?t=v1&c3.ri=6a264c82_Q1ZYMDc_0_Q0xPVURGUk9OVA_df398544dcfb:0&c3.ri=6a264c82_Q1ZYMDc_0_Q0xPVURGUk9OVA_df398544dcfb:0", "name": "Boomerang"}
    ]

    saved_cinema = existing_data.get("Sky Cinema") or CINEMA_FALLBACK
    saved_bambini = existing_data.get("Sky Bambini") or BAMBINI_FALLBACK

    lines = [l.strip() for l in m3u_text.splitlines() if l.strip()]

    output_data = {
        "Sky Sport": [],
        "Sky Cinema": saved_cinema,
        "Sky Intrattenimento": [],
        "Sky Bambini": saved_bambini,
        "RAI": [],
        "MEDIASET": [],
        "DISCOVERY": [],
        "ALTRI": []
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
                    output_data[group] = []
                output_data[group].append(entry)
                m3u_parsed_counts += 1

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
    kodi_repo_path = Path(r"C:\Users\user\Desktop\kodi_repo")
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
