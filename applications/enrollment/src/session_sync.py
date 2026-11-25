"""
Client de contrôle de session (mono/multi-session selon le rôle)
et synchronisation différentielle du dossier personnel depuis/vers le NAS.
"""

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests


def check_session_allowed(
    server_url: str,
    username: str,
    hostname: str,
    ip: str = "",
    *,
    timeout: float = 4.0,
) -> Tuple[bool, Dict[str, Any]]:
    url = f"{server_url.rstrip('/')}/api/v1/sessions/login-check"
    try:
        res = requests.post(
            url,
            json={"username": username, "hostname": hostname, "ip": ip},
            timeout=timeout,
        )
        if res.status_code == 200:
            return True, res.json()
        detail = ""
        try:
            detail = res.json().get("detail", "")
        except Exception:
            detail = res.text
        return False, {
            "status_code": res.status_code,
            "already_logged_in": res.status_code == 409,
            "detail": detail or f"Connexion refusée ({res.status_code}).",
        }
    except Exception as exc:
        return False, {
            "status_code": 0,
            "already_logged_in": False,
            "detail": f"Serveur injoignable : {exc}",
        }


def sync_delta_directory(src_dir: Path, dst_dir: Path) -> List[str]:
    """
    Synchronise de manière différentielle `src_dir` -> `dst_dir` :
    ne copie que les fichiers absents dans `dst_dir` ou plus récents dans `src_dir`.
    Retourne la liste des chemins relatifs mis à jour.
    """
    src = Path(src_dir)
    dst = Path(dst_dir)
    if not src.exists():
        return []
    dst.mkdir(parents=True, exist_ok=True)
    updated: List[str] = []

    for root, _, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        target_root = dst / rel_root
        target_root.mkdir(parents=True, exist_ok=True)
        for fname in files:
            src_file = Path(root) / fname
            dst_file = target_root / fname
            should_copy = False
            if not dst_file.exists():
                should_copy = True
            else:
                s_stat = src_file.stat()
                d_stat = dst_file.stat()
                if s_stat.st_mtime > d_stat.st_mtime + 1e-3 or s_stat.st_size != d_stat.st_size:
                    should_copy = True
            if should_copy:
                shutil.copy2(src_file, dst_file)
                updated.append(str(rel_root / fname))
    return updated


def notify_session_logout(
    server_url: str,
    username: str,
    hostname: str,
    files_synced: int = 0,
    *,
    timeout: float = 4.0,
) -> bool:
    url = f"{server_url.rstrip('/')}/api/v1/sessions/logout"
    try:
        res = requests.post(
            url,
            json={"username": username, "hostname": hostname, "files_synced": files_synced},
            timeout=timeout,
        )
        return res.status_code == 200
    except Exception:
        return False
