"""Synchronisation et filtrage par rôle des logiciels autorisés depuis le serveur LyuX."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import requests

try:
    import pwd
except ImportError:
    pwd = None

_ROLE_GROUP_ALIASES = {
    "eleve": {"eleve", "eleves"},
    "eleves": {"eleve", "eleves"},
    "prof": {"prof", "enseignant", "enseignants"},
    "enseignant": {"prof", "enseignant", "enseignants"},
    "enseignants": {"prof", "enseignant", "enseignants"},
    "viesco": {"viesco", "vie_scolaire"},
    "administration": {"administration", "direction"},
    "admin": {"admin", "techniciens"},
}


def is_role_allowed_for_app(app_entry: Dict[str, Any], role: str) -> bool:
    """Vérifie si le rôle effectif est autorisé à utiliser le logiciel."""
    r_low = (role or "").strip().lower()
    if not r_low or r_low == "admin":
        return True
    if "authorized" in app_entry:
        return bool(app_entry["authorized"])
    allowed = [
        str(x).strip().lower()
        for x in (app_entry.get("allowed_roles") or app_entry.get("allowed_groups") or [])
    ]
    if not allowed or "all" in allowed or "tous" in allowed:
        return True
    aliases = _ROLE_GROUP_ALIASES.get(r_low, {r_low})
    return any(a in allowed for a in aliases)


def fetch_client_apps(server_url: str, role: str = "", timeout: float = 4.0) -> Dict[str, Any]:
    """Récupère le catalogue applicatif client depuis /api/v1/apps/client."""
    if not server_url:
        return {"apps": []}
    params = {"role": role} if role else None
    try:
        res = requests.get(f"{server_url.rstrip('/')}/api/v1/apps/client", params=params, timeout=timeout)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"apps": []}


def sync_client_packages(server_url: str, timeout: float = 120.0) -> List[str]:
    """Installe les paquets Debian marqués deployed=True qui sont absents du poste."""
    data = fetch_client_apps(server_url)
    apps = data.get("apps") or []
    proxy = (data.get("cache_proxy") or "").strip()
    to_install: List[str] = []
    for entry in apps:
        if not entry.get("deployed"):
            continue
        pkg = (entry.get("package") or "").strip()
        if not pkg:
            continue
        chk = subprocess.run(["dpkg-query", "-W", "-f=${Status}", pkg], capture_output=True, text=True, check=False)
        if "install ok installed" not in (chk.stdout or ""):
            to_install.append(pkg)

    if not to_install:
        return []

    cmd = ["apt-get", "install", "-y", "--no-install-recommends"]
    if proxy:
        cmd.extend(["-o", f"Acquire::http::Proxy={proxy}"])
    cmd.extend(to_install)
    subprocess.run(["apt-get", "update", "-qq"], check=False, timeout=60)
    res = subprocess.run(cmd, check=False, timeout=timeout)
    return to_install if res.returncode == 0 else []


def apply_role_app_restrictions(
    server_url: str,
    username: str,
    role: str,
    home_dir: Path,
    *,
    system_apps_dir: Path = Path("/usr/share/applications"),
) -> Dict[str, List[str]]:
    """
    Masque dans ~/.local/share/applications les lanceurs .desktop des logiciels
    non autorisés pour le rôle de l'utilisateur, et rétablit ceux qui le sont.
    """
    data = fetch_client_apps(server_url, role=role)
    apps = data.get("apps") or []
    if not apps:
        return {"hidden": [], "unhidden": []}

    user_apps_dir = Path(home_dir) / ".local" / "share" / "applications"
    user_apps_dir.mkdir(parents=True, exist_ok=True)
    hidden: List[str] = []
    unhidden: List[str] = []

    uid = gid = None
    if pwd is not None and hasattr(os, "chown"):
        try:
            pw = pwd.getpwnam(username)
            uid, gid = pw.pw_uid, pw.pw_gid
        except KeyError:
            pass

    for entry in apps:
        pkg = (entry.get("package") or entry.get("id") or "").strip().lower()
        if not pkg:
            continue
        desktop_names = [f"{pkg}.desktop"]
        if system_apps_dir.exists():
            for cand in system_apps_dir.glob(f"*{pkg}*.desktop"):
                if cand.name not in desktop_names:
                    desktop_names.append(cand.name)

        allowed = is_role_allowed_for_app(entry, role)
        for dname in desktop_names:
            override = user_apps_dir / dname
            if not allowed:
                override.write_text(
                    "[Desktop Entry]\n"
                    f"Name={entry.get('name', pkg)}\n"
                    "Type=Application\n"
                    "NoDisplay=true\n"
                    "Hidden=true\n",
                    encoding="utf-8",
                )
                if uid is not None:
                    try:
                        os.chown(override, uid, gid)
                    except OSError:
                        pass
                hidden.append(dname)
            else:
                if override.exists() and "NoDisplay=true" in override.read_text(encoding="utf-8", errors="ignore"):
                    override.unlink(missing_ok=True)
                    unhidden.append(dname)

    if uid is not None:
        for p in (Path(home_dir) / ".local", Path(home_dir) / ".local" / "share", user_apps_dir):
            try:
                os.chown(p, uid, gid)
            except OSError:
                pass

    return {"hidden": hidden, "unhidden": unhidden}
