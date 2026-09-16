import json
import requests
from rich.console import Console

console = Console()

UPSTASH_URL = "https://ace-seal-162556.upstash.io"
UPSTASH_TOKEN = "gQAAAAAAAnr8AAIgcDEyZjRkYjEwYmUzZDY0M2RhYjZkNjhmMDFjNGVkMjVmYw"

def sync_to_upstash(key: str, data) -> bool:
    """Invia i dati direttamente al cloud Upstash Redis via HTTPS (Zero Git)."""
    try:
        url = f"{UPSTASH_URL}/set/stream:{key}"
        headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
        payload = json.dumps(data, ensure_ascii=False)
        r = requests.post(url, headers=headers, data=payload, timeout=8)
        return r.status_code == 200
    except Exception:
        return False
