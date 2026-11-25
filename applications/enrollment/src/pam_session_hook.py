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
import sys
from pathlib import Path

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
        if n_home.exists():
            for sub in SYNC_SUBDIRS:
                if (n_home / sub).exists():
                    sync_delta_directory(n_home / sub, l_home / sub)
        return 0

    if pam_type == "close_session":
        total_synced = 0
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
