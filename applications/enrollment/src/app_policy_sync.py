"""Synchronisation et filtrage par rôle des logiciels autorisés depuis le serveur LyuX."""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

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


def _pick_fastest_cache_proxy(candidates: List[str], timeout: float = 0.8) -> Optional[str]:
    """Teste le cache serveur et les pairs LAN par latence TCP, retourne le meilleur joignable."""
    best_url: Optional[str] = None
    best_rtt = float("inf")
    import time as _time

    for url in candidates:
        u = (url or "").strip()
        if not u:
            continue
        parsed = urlparse(u)
        host = parsed.hostname
        port = parsed.port or 3142
        if not host:
            continue
        t0 = _time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                rtt = _time.monotonic() - t0
            if rtt < best_rtt:
                best_rtt = rtt
                best_url = u
        except OSError:
            continue
    return best_url


def sync_client_packages(server_url: str, timeout: float = 120.0) -> List[str]:
    """
    Installe les paquets Debian (.deb) et Flatpak marqués deployed=True absents du poste.
    Stratégie :
      1. Cache LAN serveur (apt-cacher-ng:3142) ou pair LAN le plus rapide.
      2. Fallback automatique vers Internet direct si aucun cache LAN ne répond ou échoue.
    """
    data = fetch_client_apps(server_url)
    apps = data.get("apps") or []
    proxy_candidates = [data.get("cache_proxy") or ""] + list(data.get("peer_caches") or [])
    fallback_direct = bool(data.get("fallback_direct", True))

    apt_to_install: List[str] = []
    flatpak_to_install: List[str] = []

    for entry in apps:
        if not entry.get("deployed"):
            continue
        pkg = (entry.get("package") or "").strip()
        if not pkg:
            continue
        is_flatpak = (
            str(entry.get("format") or "").lower() == "flatpak"
            or str(entry.get("source") or "").lower() == "flathub"
            or (pkg.count(".") >= 2 and " " not in pkg)
        )
        if is_flatpak:
            chk = subprocess.run(["flatpak", "info", pkg], capture_output=True, text=True, check=False)
            if chk.returncode != 0:
                flatpak_to_install.append(pkg)
        else:
            chk = subprocess.run(["dpkg-query", "-W", "-f=${Status}", pkg], capture_output=True, text=True, check=False)
            if "install ok installed" not in (chk.stdout or ""):
                apt_to_install.append(pkg)

    installed: List[str] = []

    if apt_to_install:
        best_proxy = _pick_fastest_cache_proxy(proxy_candidates)
        success = False
        if best_proxy:
            subprocess.run(["apt-get", "-o", f"Acquire::http::Proxy={best_proxy}", "update", "-qq"], check=False, timeout=60)
            res = subprocess.run(
                ["apt-get", "install", "-y", "--no-install-recommends", "-o", f"Acquire::http::Proxy={best_proxy}", *apt_to_install],
                check=False,
                timeout=timeout,
            )
            success = res.returncode == 0
        if not success and fallback_direct:
            subprocess.run(["apt-get", "-o", "Acquire::http::Proxy=false", "update", "-qq"], check=False, timeout=60)
            res = subprocess.run(
                ["apt-get", "install", "-y", "--no-install-recommends", "-o", "Acquire::http::Proxy=false", *apt_to_install],
                check=False,
                timeout=timeout,
            )
            success = res.returncode == 0
        if success:
            installed.extend(apt_to_install)

    if flatpak_to_install:
        subprocess.run(
            ["flatpak", "remote-add", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"],
            check=False,
            timeout=30,
        )
        for fp_id in flatpak_to_install:
            res = subprocess.run(["flatpak", "install", "-y", "--noninteractive", "flathub", fp_id], check=False, timeout=timeout)
            if res.returncode == 0:
                installed.append(fp_id)

    return installed


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
