"""Windows local companion endpoint; AnkiConnect exclusively owns port 8765."""
from urllib.parse import urlsplit

LOCAL_PORT = 8766
LEGACY_LOCAL_PORT = 8765
LOCAL_URL = f"http://127.0.0.1:{LOCAL_PORT}"


def migrate_local_url(url):
    """Upgrade *only* old loopback companion URLs; never rewrite hosted/LAN URLs."""
    if not isinstance(url, str):
        return url
    try:
        parts = urlsplit(url.rstrip('/'))
        if (parts.scheme == 'http' and parts.hostname in ('127.0.0.1', 'localhost', '::1')
                and parts.port == LEGACY_LOCAL_PORT and not (parts.username or parts.password or parts.path or parts.query or parts.fragment)):
            return LOCAL_URL
    except ValueError:
        pass
    return url
