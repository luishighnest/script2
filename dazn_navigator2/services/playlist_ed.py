"""Costruisce il blocco Kodi (stesso identico formato della playlist GitHub di dazn1) da mostrare a schermo."""
import urllib.parse


def build_block(titolo, logo, keys_str, dazn_token, mpd_url, ua, cdn_name="dazn-token"):
    """Ritorna le 5 righe dell'entry: drm_legacy, manifest_headers, stream_headers, EXTINF, url."""
    group = "DAZN" if titolo == "DAZN 1" else "Eventi"
    keys = keys_str.replace("|", ",")
    hdrs_dict = {"User-Agent": ua,
                 "Referer": "https://www.dazn.com/",
                 "Origin": "https://www.dazn.com",
                 "dazn-token": dazn_token}
    hdrs = urllib.parse.urlencode(hdrs_dict, quote_via=urllib.parse.quote, safe='')
    sep = "&" if "?" in mpd_url else "?"
    mpd_auth = f"{mpd_url}{sep}{cdn_name}={urllib.parse.quote(dazn_token)}"
    return [
        f"#KODIPROP:inputstream.adaptive.drm_legacy=org.w3.clearkey|{keys}",
        f"#KODIPROP:inputstream.adaptive.manifest_headers={hdrs}",
        f"#KODIPROP:inputstream.adaptive.stream_headers={hdrs}",
        f'#EXTINF:-1 tvg-logo="{logo}" tvg-provider="DAZN" group-title="{group}", {titolo}',
        mpd_auth,
    ]


def token_expiry(dazn_token):
    """Estrae la data di scadenza dal token.

    - JWT (eyJ...): decodifica il payload e legge 'exp'.
    - Formato evento (tend:<epoch>~...): il primo campo è l'epoch di scadenza.
    Ritorna datetime locale o None se non riconosciuto.
    """
    from datetime import datetime
    import base64, json
    try:
        if dazn_token.startswith("eyJ"):
            payload = dazn_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
            if exp:
                return datetime.fromtimestamp(int(exp))
        elif "~" in dazn_token:
            first = dazn_token.split("~")[0]
            for part in first.split(":"):
                if part.isdigit() and len(part) == 10:
                    return datetime.fromtimestamp(int(part))
    except Exception:
        pass
    return None
