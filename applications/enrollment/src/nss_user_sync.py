"""Synchronise les utilisateurs actifs de LyuX-Server vers libnss-extrausers.

Écrit /var/lib/extrausers/{passwd,group,shadow} avec un mot de passe verrouillé (*)
pour forcer l'authentification via pam_exec (lyux-pam-auth.sh) tout en permettant
à NSS (getpwnam / getpwuid / SDDM) de résoudre les comptes prenom.nom.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

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


def write_extrausers_files(
    users: list[dict[str, Any]],
    extrausers_dir: Path = DEFAULT_EXTRAUSERS_DIR,
) -> int:
    """Écrit passwd, group et shadow dans extrausers_dir et retourne le nombre d'utilisateurs."""
    extrausers_dir.mkdir(parents=True, exist_ok=True)
    passwd_lines: list[str] = []
    group_lines: list[str] = []
    shadow_lines: list[str] = []

    for user in users:
        username = str(user.get("username") or "").strip()
        if not username or ":" in username:
            continue
        uid = int(user["uid"])
        gid = int(user.get("gid", uid))
        display_name = str(user.get("display_name") or username).replace(":", " ")
        home = str(user.get("home") or f"/home/{username}")
        shell = str(user.get("shell") or "/bin/bash")

        passwd_lines.append(f"{username}:x:{uid}:{gid}:{display_name}:{home}:{shell}")
        group_lines.append(f"{username}:x:{gid}:")
        shadow_lines.append(f"{username}:*:19000:0:99999:7:::")

    (extrausers_dir / "passwd").write_text(
        "\n".join(passwd_lines) + ("\n" if passwd_lines else ""),
        encoding="utf-8",
    )
    (extrausers_dir / "group").write_text(
        "\n".join(group_lines) + ("\n" if group_lines else ""),
        encoding="utf-8",
    )
    shadow_path = extrausers_dir / "shadow"
    shadow_path.write_text(
        "\n".join(shadow_lines) + ("\n" if shadow_lines else ""),
        encoding="utf-8",
    )
    try:
        os.chmod(shadow_path, 0o600)
    except OSError:
        pass
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
    return write_extrausers_files(users, extrausers_dir)


if __name__ == "__main__":
    count = sync_nss_users()
    raise SystemExit(0 if count >= 0 else 1)
