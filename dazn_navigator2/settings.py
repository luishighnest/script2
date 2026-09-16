import json
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"

DEFAULT_CONFIG = {
    "print_extension_link": True,
    "github_deploy": True,
    "browser_timeout": 0,
    "debug_mode": False,
    "extraction_engine": "curl_cffi",  # "curl_cffi" oppure "headless"
    "include_ua_curl": True,       # Includi UA nel JSON con metodo Veloce (curl_cffi)
    "include_ua_headless": True,   # Includi UA nel JSON con metodo Headless (Playwright)
    "download_vod_mp4": False,     # Scarica VOD in formato MP4 automaticamente
    "site_api_url": "http://localhost:3000/api", # URL endpoint API del sito Next.js
    "site_api_key": "zadonkais_secret_2026",    # Chiave segreta x-api-key
}

def load_config():
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # Update with missing defaults
            changed = False
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
                    changed = True
            if changed:
                save_config(data)
            return data
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(data):
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")

def get_setting(key):
    return load_config().get(key, DEFAULT_CONFIG.get(key))

def toggle_setting(key):
    config = load_config()
    if key in config and isinstance(config[key], bool):
        config[key] = not config[key]
        save_config(config)
        return config[key]
    return None
