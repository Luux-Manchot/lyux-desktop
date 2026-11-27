"""Hook PAM d'authentification desktop contre lyux-api (/api/v1/auth/desktop-login)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from nss_user_sync import DEFAULT_EXTRAUSERS_DIR, DEFAULT_STATE_PATH, load_server_url, sync_nss_users


def _local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def _populate_home_from_skel(home_dir: Path, uid: int, skel_dir: Path = Path("/etc/skel")) -> None:
    """Copie le squelette /etc/skel dans un nouveau dossier personnel sans écraser l'existant."""
    if not skel_dir.exists():
        return
    for root, dirs, files in os.walk(skel_dir):
        rel = Path(root).relative_to(skel_dir)
        target_dir = home_dir / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        if uid > 0 and hasattr(os, "chown"):
            try:
                os.chown(target_dir, uid, uid)
            except OSError:
                pass
        for d in dirs:
            sub = target_dir / d
            sub.mkdir(parents=True, exist_ok=True)
            if uid > 0 and hasattr(os, "chown"):
                try:
                    os.chown(sub, uid, uid)
                except OSError:
                    pass
        for fname in files:
            src_file = Path(root) / fname
            dst_file = target_dir / fname
            if not dst_file.exists():
                try:
                    shutil.copy2(src_file, dst_file)
                    if uid > 0 and hasattr(os, "chown"):
                        os.chown(dst_file, uid, uid)
                except OSError:
                    pass


_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9._-]{0,31}$")
_EXCLUDED_LOCAL_USERS = frozenset({"root", "lyux-admin", "nobody", "daemon", "sync", "sys"})
_MIN_UID = 1000
_MAX_UID = 60000


def _is_valid_pam_username(username: str) -> bool:
    return bool(username and username not in _EXCLUDED_LOCAL_USERS and _USERNAME_RE.match(username))


def _is_secure_auth_url(url: str) -> bool:
    """Impose HTTPS pour l'authentification PAM, sauf loopback explicite (dev)."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme == "https":
        return bool(parsed.netloc)
    if parsed.scheme == "http":
        return (parsed.hostname or "").lower() in ("127.0.0.1", "localhost", "::1")
    return False


def _load_tls_pin_config(state_path: Path) -> tuple[str | None, str | None]:
    """Lit ca_cert_path et tls_cert_sha256 depuis l'état d'enrôlement."""
    if not state_path.exists():
        return None, None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    ca_path = str(data.get("ca_cert_path") or "").strip() or None
    pin_sha256 = str(data.get("tls_cert_sha256") or "").strip().lower() or None
    return ca_path, pin_sha256


def _verify_pinned_cert(url: str, expected_sha256: str, ca_path: str | None, timeout: float) -> bool:
    """Vérifie l'empreinte SHA-256 du certificat TLS présenté par le serveur."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or 443
    ctx = ssl.create_default_context(cafile=ca_path) if ca_path else ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            der_cert = ssock.getpeercert(binary_form=True)
    if not der_cert:
        return False
    actual = hashlib.sha256(der_cert).hexdigest().lower()
    return actual == expected_sha256


def authenticate_desktop_user(
    username: str,
    password: str,
    state_path: Path = DEFAULT_STATE_PATH,
    extrausers_dir: Path = DEFAULT_EXTRAUSERS_DIR,
    home_root: Path = Path("/home"),
    timeout: float = 5.0,
) -> tuple[bool, str]:
    """Vérifie les identifiants auprès de lyux-api et prépare /home/<username>."""
    if not password:
        return False, "local-fallback"
    if username in _EXCLUDED_LOCAL_USERS:
        return False, "local-fallback"
    if not _is_valid_pam_username(username):
        return False, "invalid-username"

    server_url = load_server_url(state_path)
    if not server_url:
        return False, "unconfigured"
    if not _is_secure_auth_url(server_url):
        return False, "insecure-transport"

    ca_path, pin_sha256 = _load_tls_pin_config(state_path)
    if server_url.startswith("https://") and pin_sha256:
        try:
            if not _verify_pinned_cert(server_url, pin_sha256, ca_path, timeout):
                return False, "tls-pin-mismatch"
        except (OSError, ssl.SSLError, ValueError) as exc:
            return False, f"tls-error: {exc}"

    # Synchroniser NSS AVANT l'auth pour que le compte soit déjà connu de SDDM
    sync_nss_users(state_path=state_path, extrausers_dir=extrausers_dir)

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
        if ca_path and server_url.startswith("https://"):
            ssl_ctx = ssl.create_default_context(cafile=ca_path)
            resp_ctx = urlopen(req, timeout=timeout, context=ssl_ctx)
        else:
            resp_ctx = urlopen(req, timeout=timeout)
        with resp_ctx as resp:
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

    try:
        uid = int(data.get("uid", 0) or 0)
    except (TypeError, ValueError):
        return False, "invalid-uid"
    if not (_MIN_UID <= uid <= _MAX_UID):
        return False, "invalid-uid"

    sync_nss_users(state_path=state_path, extrausers_dir=extrausers_dir)

    home_dir = home_root / username
    home_dir.mkdir(parents=True, exist_ok=True)
    if uid > 0 and hasattr(os, "chown"):
        try:
            os.chown(home_dir, uid, uid)
        except OSError:
            pass
    _populate_home_from_skel(home_dir, uid)
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
