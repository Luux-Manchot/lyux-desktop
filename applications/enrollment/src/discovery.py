import os
from typing import Tuple, Dict
import requests

DEFAULT_TARGETS = [
    os.getenv("LYUX_SERVER_URL"),
    "http://server.lyux.lan:8000",
    "http://serveur.lyux.lan:8000",
    "http://192.168.100.10:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]

def discover_lyux_server(timeout_sec: float = 1.5, custom_target: str = None) -> Tuple[bool, str, Dict]:
    """Détecte dynamiquement la présence du serveur LyuX et récupère la liste des salles."""
    targets = [custom_target] if custom_target else DEFAULT_TARGETS
    for target in filter(None, targets):
        try:
            res = requests.get(f"{target}/health", timeout=timeout_sec)
            if res.status_code == 200:
                rooms_res = requests.get(f"{target}/api/v1/rooms", timeout=timeout_sec)
                rooms = rooms_res.json() if rooms_res.status_code == 200 else {}
                return True, target, rooms
        except Exception:
            continue
    return False, "", {}
