#!/usr/bin/env python3
"""
Hook PAM (pam_exec) pour les sessions utilisateur LyuX :
- open_session : vérifie mono/multi-session auprès du serveur (/api/v1/sessions/login-check)
  et rapatrie en différentiel Documents, Bureau, Projets et .config (fond d'écran KDE).
- close_session : pousse les fichiers modifiés vers le NAS et notifie /api/v1/sessions/logout.
"""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import pwd
except ImportError:
    pwd = None

import requests

try:
    from session_sync import check_session_allowed, notify_session_logout, sync_delta_directory
except ImportError:
    from .session_sync import check_session_allowed, notify_session_logout, sync_delta_directory

STATE_FILE = Path(os.getenv("LYUX_ENROLLMENT_STATE", "/var/lib/lyux/enrollment-state.json"))
NAS_MOUNT_BASE = Path(os.getenv("LYUX_NAS_MOUNT", "/mnt/lyux-nas/homes"))
SYNC_SUBDIRS = ("Documents", "Bureau", "Projets", ".config")
IGNORED_USERS = {"root", "lyux-admin", "invite", "sddm", "nobody"}


def _get_server_url() -> str:
    if os.getenv("LYUX_SERVER_URL"):
        return os.environ["LYUX_SERVER_URL"].strip()
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return (data.get("server_url") or "").strip()
        except Exception:
            pass
    return ""


def _fetch_server_nas_settings(server_url: str) -> tuple[bool, str]:
    """Interroge le serveur pour savoir si la synchro NAS est activée et quel partage monter."""
    if not server_url:
        return True, "/srv/samba/homes"
    try:
        res = requests.get(f"{server_url.rstrip('/')}/api/v1/system/settings", timeout=2.0)
        if res.status_code == 200:
            data = res.json()
            enabled = bool(data.get("nas_sync_enabled", True))
            share_path = str(data.get("nas_share_path") or "/srv/samba/homes").strip()
            return enabled, share_path
    except Exception:
        pass
    return True, "/srv/samba/homes"


def _ensure_nas_mounted(server_url: str, share_path: str, mount_base: Path = NAS_MOUNT_BASE) -> bool:
    """Monte le partage NFS /homes du serveur sur /mnt/lyux-nas/homes si nécessaire."""
    if mount_base != NAS_MOUNT_BASE:
        return mount_base.exists()
    if os.path.ismount(mount_base):
        return True
    mount_base.mkdir(parents=True, exist_ok=True)
    host = (urlparse(server_url).hostname or "").strip() if server_url else ""
    if host:
        subprocess.run(
            ["mount", "-t", "nfs", "-o", "rw,sync,nosuid,nodev,_netdev", f"{host}:{share_path}", str(mount_base)],
            check=False,
            capture_output=True,
        )
        if os.path.ismount(mount_base):
            return True
    subprocess.run(["mount", str(mount_base)], check=False, capture_output=True)
    return os.path.ismount(mount_base)


def _chown_user_tree(target_dir: Path, username: str) -> None:
    """Attribue récursivement les fichiers synchronisés à l'utilisateur cible."""
    if pwd is None or not hasattr(os, "chown"):
        return
    try:
        pw = pwd.getpwnam(username)
        uid, gid = pw.pw_uid, pw.pw_gid
    except KeyError:
        return
    for root, dirs, files in os.walk(target_dir):
        try:
            os.chown(root, uid, gid)
        except OSError:
            pass
        for name in dirs + files:
            try:
                os.chown(Path(root) / name, uid, gid)
            except OSError:
                pass


def handle_pam_event(
    pam_type: str,
    username: str,
    *,
    server_url: str = "",
    hostname: str = "",
    local_home: Path = None,
    nas_home: Path = None,
) -> int:
    uname = (username or "").strip().lower()
    if not uname or uname in IGNORED_USERS:
        return 0

    srv = server_url or _get_server_url()
    host = (hostname or socket.gethostname()).strip().upper()
    l_home = local_home or Path(f"/home/{uname}")
    n_home = nas_home or (NAS_MOUNT_BASE / uname)

    if pam_type == "open_session":
        if srv:
            allowed, info = check_session_allowed(srv, uname, host)
            if not allowed and info.get("already_logged_in"):
                print(info.get("detail", "Utilisateur déjà connecté sur un autre poste."), file=sys.stderr)
                return 1
        nas_enabled, share_path = _fetch_server_nas_settings(srv) if nas_home is None else (True, "/srv/samba/homes")
        if nas_enabled:
            if nas_home is None:
                _ensure_nas_mounted(srv, share_path)
            if n_home.exists():
                for sub in SYNC_SUBDIRS:
                    if (n_home / sub).exists():
                        sync_delta_directory(n_home / sub, l_home / sub)
                        _chown_user_tree(l_home / sub, uname)
        return 0

    if pam_type == "close_session":
        total_synced = 0
        nas_enabled, share_path = _fetch_server_nas_settings(srv) if nas_home is None else (True, "/srv/samba/homes")
        if nas_enabled:
            if nas_home is None:
                _ensure_nas_mounted(srv, share_path)
            if n_home.exists():
                for sub in SYNC_SUBDIRS:
                    if (l_home / sub).exists():
                        total_synced += len(sync_delta_directory(l_home / sub, n_home / sub))
        if srv:
            notify_session_logout(srv, uname, host, files_synced=total_synced)
        return 0

    return 0


def main() -> int:
    pam_type = os.getenv("PAM_TYPE", "")
    pam_user = os.getenv("PAM_USER", "")
    return handle_pam_event(pam_type, pam_user)


if __name__ == "__main__":
    sys.exit(main())
