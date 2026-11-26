"""Hook PAM d'authentification desktop contre lyux-api (/api/v1/auth/desktop-login)."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nss_user_sync import DEFAULT_EXTRAUSERS_DIR, DEFAULT_STATE_PATH, load_server_url, sync_nss_users


def _local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def authenticate_desktop_user(
    username: str,
    password: str,
    state_path: Path = DEFAULT_STATE_PATH,
    extrausers_dir: Path = DEFAULT_EXTRAUSERS_DIR,
    home_root: Path = Path("/home"),
    timeout: float = 5.0,
) -> tuple[bool, str]:
    """Vérifie les identifiants auprès de lyux-api et prépare /home/<username>."""
    if not username or username == "root" or not password:
        return False, "local-fallback"

    # Synchroniser NSS AVANT l'auth pour que le compte soit déjà connu de SDDM
    sync_nss_users(state_path=state_path, extrausers_dir=extrausers_dir)

    server_url = load_server_url(state_path)
    if not server_url:
        return False, "unconfigured"

    payload = json.dumps({
        "username": username,
        "password": password,
        "hostname": socket.gethostname(),
        "ip": _local_ip(),
    }).encode("utf-8")
    req = Request(
        f"{server_url}/api/v1/auth/desktop-login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=timeout) as resp:
            data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail", exc.reason)
        except Exception:
            detail = str(exc.reason)
        return False, str(detail)
    except (OSError, URLError, ValueError) as exc:
        return False, str(exc)

    if not data.get("authenticated"):
        return False, "rejected"

    sync_nss_users(state_path=state_path, extrausers_dir=extrausers_dir)

    uid = int(data.get("uid", 0) or 0)
    home_dir = home_root / username
    home_dir.mkdir(parents=True, exist_ok=True)
    if uid > 0 and hasattr(os, "chown"):
        try:
            os.chown(home_dir, uid, uid)
        except OSError:
            pass
    return True, "ok"


def main() -> int:
    username = os.environ.get("PAM_USER", "").strip()
    password = sys.stdin.read().rstrip("\x00\r\n")
    ok, message = authenticate_desktop_user(username, password)
    if not ok:
        if message not in ("local-fallback", "unconfigured"):
            print(f"LyuX auth refusée: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
