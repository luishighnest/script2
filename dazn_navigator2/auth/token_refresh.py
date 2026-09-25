import json, base64, time
from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parent.parent.parent / "dazn_bearer.json"
PROFILE_DIR = Path(__file__).resolve().parent.parent.parent / "saved_profiles" / "profile_mpd" / "chrome_profile"


def decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    padding = 4 - len(payload) % 4
    if padding != 4:
        payload += "=" * padding
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def get_time_remaining(exp: int) -> str:
    if not exp:
        return "sconosciuta"
    rem = exp - int(time.time())
    if rem < 0:
        return "scaduto"
    return f"{rem//60}m {rem%60}s"