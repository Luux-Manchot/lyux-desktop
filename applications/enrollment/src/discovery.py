import ipaddress
import os
import re
import socket
import struct
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

_HOST_PORT_RE = re.compile(r"^[a-zA-Z0-9.-]{1,253}(:\d{1,5})?$")


def _default_gateway_ip() -> Optional[str]:
    """Lit la passerelle par défaut IPv4 depuis /proc/net/route sans IP figée."""
    try:
        with open("/proc/net/route", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    gw_hex = int(fields[2], 16)
                    return socket.inet_ntoa(struct.pack("<L", gw_hex))
    except Exception:
        pass
    return None


def get_candidate_server_urls() -> List[str]:
    """Construit dynamiquement la liste des cibles possibles sans IP d'établissement."""
    candidates: List[str] = []
    env_url = os.getenv("LYUX_SERVER_URL", "").strip()
    if env_url:
        candidates.append(env_url)
    gw = _default_gateway_ip()
    if gw:
        candidates.append(f"https://{gw}")
        candidates.append(f"https://{gw}:8443")
    candidates.extend([
        "https://lyux-server",
        "https://api.lyux.lan",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ])
    seen = set()
    unique: List[str] = []
    for c in candidates:
        norm = c.rstrip("/")
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(norm)
    return unique


def validate_server_url(raw_url: str) -> Tuple[bool, str, str]:
    """Valide strictement une adresse serveur (schéma http/https + hôte[:port], sans chemin libre)."""
    cleaned = (raw_url or "").strip().rstrip("/")
    if not cleaned:
        return False, "", "Adresse serveur vide."
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        return False, "", "Schéma non autorisé (http ou https uniquement)."
    if not parsed.netloc or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return False, "", "Format attendu : http(s)://hote[:port] sans chemin ni paramètre."
    if not _HOST_PORT_RE.match(parsed.netloc):
        return False, "", "Nom d'hôte ou port invalide."
    host = parsed.hostname or ""
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        return False, "", "Port TCP hors plage (1-65535)."
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if any(ch in host for ch in (" ", "/", "\\", "@")):
            return False, "", "Nom d'hôte invalide."
    return True, f"{parsed.scheme}://{parsed.netloc}", ""


def probe_server_health(server_url: str, timeout_sec: float = 2.0) -> Tuple[str, Dict]:
    """
    Teste /health et distingue :
    - 'ok' : API joignable et version compatible
    - 'api-error' : serveur joignable mais réponse HTTP invalide / corrompue / version inconnue
    - 'server-unreachable' : hôte injoignable ou timeout
    """
    try:
        res = requests.get(f"{server_url.rstrip('/')}/health", timeout=timeout_sec)
        if res.status_code != 200:
            return "api-error", {"detail": f"HTTP {res.status_code}"}
        data = res.json()
        if not isinstance(data, dict) or data.get("status") != "ok":
            return "api-error", {"detail": "Réponse /health invalide"}
        api_ver = str(data.get("api_version", "1"))
        if api_ver not in ("1", "1.0", "1.0.0"):
            return "api-error", {"detail": f"Version API non supportée : {api_ver}"}
        return "ok", data
    except ValueError:
        return "api-error", {"detail": "Réponse JSON corrompue"}
    except requests.RequestException as exc:
        return "server-unreachable", {"detail": str(exc)}


def discover_lyux_server(timeout_sec: float = 1.5, custom_target: Optional[str] = None) -> Tuple[bool, str, Dict]:
    """Détecte dynamiquement la présence du serveur LyuX et récupère la liste des salles."""
    if custom_target:
        valid, normalized, _ = validate_server_url(custom_target)
        if not valid:
            return False, "", {}
        targets = [normalized]
    else:
        targets = get_candidate_server_urls()

    for target in targets:
        status, _ = probe_server_health(target, timeout_sec=timeout_sec)
        if status == "ok":
            try:
                rooms_res = requests.get(f"{target}/api/v1/rooms", timeout=timeout_sec)
                rooms = rooms_res.json() if rooms_res.status_code == 200 else []
            except Exception:
                rooms = []
            return True, target, rooms
    return False, "", {}
