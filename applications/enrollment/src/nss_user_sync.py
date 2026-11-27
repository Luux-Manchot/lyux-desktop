"""Synchronise les utilisateurs actifs de LyuX-Server vers libnss-extrausers.

Écrit /var/lib/extrausers/{passwd,group,shadow} avec un mot de passe verrouillé (*)
pour forcer l'authentification via pam_exec (lyux-pam-auth.sh) tout en permettant
à NSS (getpwnam / getpwuid / SDDM) de résoudre les comptes prenom.nom.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9._-]{0,31}$")
_DISPLAY_NAME_RE = re.compile(r"^[^\x00-\x1f\x7f:]{1,128}$")
_EXCLUDED_USERS = frozenset({"root", "lyux-admin", "nobody", "daemon", "sync", "sys"})
_ALLOWED_SHELLS = frozenset({"/bin/bash", "/bin/sh", "/usr/sbin/nologin"})
_MIN_UID = 1000
_MAX_UID = 60000

DEFAULT_STATE_PATH = Path(os.environ.get("LYUX_ENROLLMENT_STATE", "/var/lib/lyux/enrollment-state.json"))
DEFAULT_EXTRAUSERS_DIR = Path(os.environ.get("LYUX_EXTRAUSERS_DIR", "/var/lib/extrausers"))
DEFAULT_NSSWITCH_PATH = Path(os.environ.get("LYUX_NSSWITCH_PATH", "/etc/nsswitch.conf"))


def load_server_url(state_path: Path = DEFAULT_STATE_PATH) -> str | None:
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    url = str(data.get("server_url") or "").strip().rstrip("/")
    return url or None


def fetch_nss_users(server_url: str, timeout: float = 5.0) -> list[dict[str, Any]]:
    req = Request(f"{server_url}/api/v1/client/nss-users", method="GET")
    with urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    users = payload.get("users")
    return users if isinstance(users, list) else []


def ensure_nsswitch_extrausers(nsswitch_path: Path = DEFAULT_NSSWITCH_PATH) -> bool:
    """Ajoute 'extrausers' aux lignes passwd, group et shadow de /etc/nsswitch.conf."""
    if not nsswitch_path.exists():
        return False
    lines = nsswitch_path.read_text(encoding="utf-8").splitlines()
    changed = False
    updated: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("passwd:", "group:", "shadow:")) and "extrausers" not in stripped.split():
            updated.append(f"{line.rstrip()} extrausers")
            changed = True
        else:
            updated.append(line)
    if changed:
        nsswitch_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    return changed


def _atomic_write_extrausers_file(path: Path, content: str, mode: int) -> None:
    """Écrit un fichier NSS atomiquement (mkstemp 0600, chmod, fsync, os.replace)."""
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def write_extrausers_files(
    users: list[dict[str, Any]],
    extrausers_dir: Path = DEFAULT_EXTRAUSERS_DIR,
) -> int:
    """Écrit passwd, group et shadow atomiquement dans extrausers_dir après validation stricte."""
    extrausers_dir.mkdir(parents=True, exist_ok=True)
    passwd_lines: list[str] = []
    group_lines: list[str] = []
    shadow_lines: list[str] = []

    for user in users:
        if not isinstance(user, dict):
            continue
        username = str(user.get("username") or "").strip()
        if not _USERNAME_RE.match(username) or username in _EXCLUDED_USERS:
            continue
        try:
            uid = int(user["uid"])
            gid = int(user.get("gid", uid))
        except (KeyError, TypeError, ValueError):
            continue
        if not (_MIN_UID <= uid <= _MAX_UID and _MIN_UID <= gid <= _MAX_UID):
            continue

        raw_display = str(user.get("display_name") or username).strip()
        if not _DISPLAY_NAME_RE.match(raw_display):
            continue

        home = f"/home/{username}"
        shell = str(user.get("shell") or "/bin/bash").strip()
        if shell not in _ALLOWED_SHELLS:
            continue

        passwd_lines.append(f"{username}:x:{uid}:{gid}:{raw_display}:{home}:{shell}")
        group_lines.append(f"{username}:x:{gid}:")
        shadow_lines.append(f"{username}:*:19000:0:99999:7:::")

    _atomic_write_extrausers_file(
        extrausers_dir / "passwd",
        "\n".join(passwd_lines) + ("\n" if passwd_lines else ""),
        0o644,
    )
    _atomic_write_extrausers_file(
        extrausers_dir / "group",
        "\n".join(group_lines) + ("\n" if group_lines else ""),
        0o644,
    )
    _atomic_write_extrausers_file(
        extrausers_dir / "shadow",
        "\n".join(shadow_lines) + ("\n" if shadow_lines else ""),
        0o600,
    )
    return len(passwd_lines)


def sync_nss_users(
    state_path: Path = DEFAULT_STATE_PATH,
    extrausers_dir: Path = DEFAULT_EXTRAUSERS_DIR,
    nsswitch_path: Path = DEFAULT_NSSWITCH_PATH,
) -> int:
    """Synchronise NSS depuis lyux-api. Retourne -1 en cas d'erreur réseau/config."""
    server_url = load_server_url(state_path)
    if not server_url:
        return -1
    try:
        users = fetch_nss_users(server_url)
    except (OSError, URLError, ValueError):
        return -1
    ensure_nsswitch_extrausers(nsswitch_path)
    count = write_extrausers_files(users, extrausers_dir)
    if state_path == DEFAULT_STATE_PATH:
        try:
            from app_policy_sync import sync_client_packages
            sync_client_packages(server_url)
        except Exception:
            pass
        try:
            from update_policy_sync import sync_update_policy
            sync_update_policy(server_url)
        except Exception:
            pass
    return count


if __name__ == "__main__":
    count = sync_nss_users()
    raise SystemExit(0 if count >= 0 else 1)
