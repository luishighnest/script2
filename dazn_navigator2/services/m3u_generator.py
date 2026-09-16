"""
Modulo per generare la Playlist M3U unificata (Sky1, Sky2, DAZN, Eventi)
nel formato standard ClearKey + Kodi/TiviMate compatibile al 100% con TiviMate.
Salvata in kodi_repo/playlist.m3u e inviata su GitHub luishighnest/kodi.
"""
import json
import urllib.parse
from pathlib import Path

KODI_REPO = Path(r"C:\Users\user\Desktop\kodi_repo")
HTDOCS_REPO = Path(r"C:\Users\user\Desktop\htdocs")

def generate_unified_m3u() -> str:
    from dazn_navigator2.cli.sky2_cmds import decrypt_site_payload

    lines = [
        "#EXTM3U name=\"DAZN & SKY TV LIVE (TiviMate)\"",
        ""
    ]

    added_channels = set()

    # ─── 1. CARICA CANALI DAZN ED EVENTI DA test.json ───
    test_json_path = KODI_REPO / "test.json"
    if not test_json_path.exists():
        test_json_path = HTDOCS_REPO / "test.json"

    if test_json_path.exists():
        try:
            raw_t = json.loads(test_json_path.read_text(encoding="utf-8-sig"))
            data_test = decrypt_site_payload(raw_t["enc"]) if "enc" in raw_t else raw_t
            if isinstance(data_test, dict):
                for group_name, items in data_test.items():
                    for item in items:
                        name = item.get("name", "").strip()
                        mpd_raw = item.get("mpd", "").strip()
                        key = item.get("key", "").strip()
                        logo = item.get("logo") or item.get("image") or ""
                        ua = item.get("ua", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

                        # Formato vecchio: "https://...stream.mpd?...|KID:KEY" → separa
                        if "|" in mpd_raw and mpd_raw.startswith("http"):
                            parts = mpd_raw.split("|", 1)
                            mpd = parts[0].strip()
                            if not key:
                                key = parts[1].strip()
                        else:
                            mpd = mpd_raw

                        if not mpd or not key:
                            continue
                        
                        unique_id = f"dazn_{name}".lower()
                        added_channels.add(unique_id)

                        clean_keys = key.replace("|", ",")
                        grp = group_name or "DAZN"

                        lines.append(f'#EXTINF:-1 tvg-id="{unique_id}" tvg-name="{name}" tvg-logo="{logo}" group-title="{grp}",{name}')
                        lines.append('#KODIPROP:inputstream=inputstream.adaptive')
                        lines.append('#KODIPROP:inputstream.adaptive.manifest_type=mpd')
                        lines.append(f'#KODIPROP:inputstream.adaptive.license_type=org.w3.clearkey')
                        lines.append(f'#KODIPROP:inputstream.adaptive.license_key={clean_keys}')
                        lines.append(f'#KODIPROP:inputstream.adaptive.drm_legacy=org.w3.clearkey|{clean_keys}')
                        lines.append(f'#EXTVLCOPT:http-user-agent={ua}')
                        lines.append(f'#EXTVLCOPT:http-referrer=https://www.dazn.com/')
                        lines.append(f'#EXTVLCOPT:http-origin=https://www.dazn.com')
                        lines.append(mpd)
                        lines.append("")
        except Exception:
            pass

    # ─── 2. CARICA CANALI SKY2 DA sky2.json ───
    sky2_path = HTDOCS_REPO / "sky2.json"
    if sky2_path.exists():
        try:
            raw_s2 = json.loads(sky2_path.read_text(encoding="utf-8-sig"))
            data_sky2 = decrypt_site_payload(raw_s2["enc"]) if "enc" in raw_s2 else raw_s2
            if isinstance(data_sky2, dict):
                for group_name, items in data_sky2.items():
                    for item in items:
                        name = item.get("name", "").strip()
                        mpd = item.get("mpd", "").strip()
                        key = item.get("key", "").strip()
                        logo = item.get("logo", "")
                        
                        if not mpd or not key:
                            continue

                        unique_id = f"sky2_{name}".lower()
                        if unique_id in added_channels:
                            continue
                        added_channels.add(unique_id)

                        clean_keys = key.replace("|", ",")
                        grp = group_name or "Sky"

                        lines.append(f'#EXTINF:-1 tvg-id="{unique_id}" tvg-name="{name}" tvg-logo="{logo}" group-title="{grp}",{name}')
                        lines.append('#KODIPROP:inputstream=inputstream.adaptive')
                        lines.append('#KODIPROP:inputstream.adaptive.manifest_type=mpd')
                        lines.append(f'#KODIPROP:inputstream.adaptive.license_type=org.w3.clearkey')
                        lines.append(f'#KODIPROP:inputstream.adaptive.license_key={clean_keys}')
                        lines.append(f'#KODIPROP:inputstream.adaptive.drm_legacy=org.w3.clearkey|{clean_keys}')
                        lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                        lines.append(mpd)
                        lines.append("")
        except Exception:
            pass

    # ─── 3. CARICA CANALI SKY1 DA sky.json ───
    sky_path = HTDOCS_REPO / "sky.json"
    if sky_path.exists():
        try:
            raw_s = json.loads(sky_path.read_text(encoding="utf-8-sig"))
            data_sky = decrypt_site_payload(raw_s["enc"]) if "enc" in raw_s else raw_s
            if isinstance(data_sky, dict):
                for group_name, items in data_sky.items():
                    for item in items:
                        name = item.get("name", "").strip()
                        mpd = item.get("mpd", "").strip()
                        key = item.get("key", "").strip()
                        logo = item.get("logo", "")
                        
                        if not mpd or not key:
                            continue

                        unique_id = f"sky1_{name}".lower()
                        if unique_id in added_channels:
                            continue
                        added_channels.add(unique_id)

                        clean_keys = key.replace("|", ",")
                        grp = group_name or "Sky Sport"

                        lines.append(f'#EXTINF:-1 tvg-id="{unique_id}" tvg-name="{name}" tvg-logo="{logo}" group-title="{grp}",{name}')
                        lines.append('#KODIPROP:inputstream=inputstream.adaptive')
                        lines.append('#KODIPROP:inputstream.adaptive.manifest_type=mpd')
                        lines.append(f'#KODIPROP:inputstream.adaptive.license_type=org.w3.clearkey')
                        lines.append(f'#KODIPROP:inputstream.adaptive.license_key={clean_keys}')
                        lines.append(f'#KODIPROP:inputstream.adaptive.drm_legacy=org.w3.clearkey|{clean_keys}')
                        lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                        lines.append(mpd)
                        lines.append("")
        except Exception:
            pass

    m3u_content = "\n".join(lines)

    # Scrittura in kodi_repo/playlist.m3u
    target_kodi = KODI_REPO / "playlist.m3u"
    target_kodi.write_text(m3u_content, encoding="utf-8")

    # Scrittura anche in htdocs/playlist.m3u (se presente)
    target_htdocs = HTDOCS_REPO / "playlist.m3u"
    if HTDOCS_REPO.exists():
        target_htdocs.write_text(m3u_content, encoding="utf-8")

    return m3u_content
