"""Synchronise la politique de versions (Debian, KDE, LyuX) depuis LyuX-Server.

- Lit les versions locales (Debian, KDE Plasma, LyuX OS).
- Récupère la politique /api/v1/client/updates/policy (version serveur + dernière existante).
- Écrit /etc/apt/preferences.d/lyux-policy.pref pour bloquer APT sur les cibles serveur.
- Applique les mises à jour jusqu'aux versions validées par le serveur (et jamais au-delà).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_STATE_PATH = Path(os.environ.get("LYUX_ENROLLMENT_STATE", "/var/lib/lyux/enrollment-state.json"))
DEFAULT_PREFS_PATH = Path(os.environ.get("LYUX_APT_PREFS_PATH", "/etc/apt/preferences.d/lyux-policy.pref"))
DEFAULT_LYUX_VERSION_FILE = Path(os.environ.get("LYUX_VERSION_FILE", "/opt/lyux/VERSION"))


def load_server_url(state_path: Path = DEFAULT_STATE_PATH) -> str | None:
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    url = str(data.get("server_url") or "").strip().rstrip("/")
    return url or None


def _run_cmd_output(cmd: list[str], timeout: float = 5.0) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode == 0:
            return res.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def get_local_debian_version(
    debian_version_path: Path = Path("/etc/debian_version"),
    os_release_path: Path = Path("/etc/os-release"),
) -> str:
    if debian_version_path.exists():
        val = debian_version_path.read_text(encoding="utf-8", errors="replace").strip()
        if val:
            return val
    if os_release_path.exists():
        for line in os_release_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VERSION_ID="):
                return line.split("=", 1)[1].strip().strip('"')
    return "Inconnue"


def get_local_kde_version() -> str:
    pkg_ver = _run_cmd_output(["dpkg-query", "-W", "-f=${Version}", "plasma-desktop"])
    if pkg_ver:
        return pkg_ver
    shell_ver = _run_cmd_output(["plasmashell", "--version"])
    if shell_ver:
        return shell_ver.replace("plasmashell", "").strip()
    return "Non installé"


def get_local_lyux_version(version_file: Path = DEFAULT_LYUX_VERSION_FILE) -> str:
    pkg_ver = _run_cmd_output(["dpkg-query", "-W", "-f=${Version}", "lyux-desktop-core"])
    if pkg_ver:
        return pkg_ver
    if version_file.exists():
        val = version_file.read_text(encoding="utf-8", errors="replace").strip()
        if val:
            return val
    return "Inconnue"


def get_local_versions() -> dict[str, str]:
    return {
        "debian": get_local_debian_version(),
        "kde": get_local_kde_version(),
        "lyux": get_local_lyux_version(),
    }


def fetch_updates_policy(server_url: str, timeout: float = 5.0) -> dict[str, Any]:
    req = Request(f"{server_url.rstrip('/')}/api/v1/client/updates/policy", method="GET")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def write_apt_pinning(
    policy: dict[str, Any],
    prefs_path: Path = DEFAULT_PREFS_PATH,
) -> bool:
    """Écrit ou supprime /etc/apt/preferences.d/lyux-policy.pref selon auto_enforce."""
    if not policy.get("auto_enforce", True):
        if prefs_path.exists():
            prefs_path.unlink()
        return False

    content = str(policy.get("apt_preferences") or "").strip()
    if not content:
        return False

    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs_path.write_text(content + "\n", encoding="utf-8")
    return True


def sync_update_policy(
    server_url: str | None = None,
    prefs_path: Path = DEFAULT_PREFS_PATH,
) -> dict[str, Any] | None:
    url = server_url or load_server_url()
    if not url:
        return None
    try:
        policy = fetch_updates_policy(url)
    except (OSError, URLError, ValueError):
        return None
    try:
        write_apt_pinning(policy, prefs_path=prefs_path)
    except OSError:
        pass
    return policy


def apply_server_selected_updates(
    server_url: str | None = None,
    prefs_path: Path = DEFAULT_PREFS_PATH,
) -> tuple[bool, str]:
    """Met à jour le poste uniquement vers les versions sélectionnées par le serveur."""
    url = server_url or load_server_url()
    if not url:
        return False, "Poste non enrôlé (serveur LyuX introuvable)."

    policy = sync_update_policy(url, prefs_path=prefs_path)
    if not policy:
        return False, "Impossible de joindre le serveur LyuX pour lire la politique de mises à jour."

    local = get_local_versions()
    lyux_info = policy.get("lyux") or {}
    target_lyux = str(lyux_info.get("selected_version") or "").strip()
    deb_rel_url = str(lyux_info.get("deb_url") or "").strip()

    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    messages: list[str] = []

    if target_lyux and deb_rel_url and target_lyux != local.get("lyux"):
        deb_url = deb_rel_url if deb_rel_url.startswith("http") else f"{url.rstrip('/')}{deb_rel_url}"
        tmp_deb = Path("/tmp/lyux-desktop-core-target.deb")
        try:
            with urlopen(Request(deb_url, method="GET"), timeout=30.0) as resp:
                tmp_deb.write_bytes(resp.read())
            res = subprocess.run(
                ["apt-get", "install", "-y", str(tmp_deb)],
                capture_output=True,
                text=True,
                env=env,
            )
            if res.returncode != 0:
                return False, f"Échec installation LyuX {target_lyux}: {res.stderr.strip()}"
            messages.append(f"LyuX mis à jour vers {target_lyux}")
        except (OSError, URLError) as exc:
            return False, f"Impossible de télécharger LyuX {target_lyux}: {exc}"

    upd = subprocess.run(["apt-get", "update"], capture_output=True, text=True, env=env)
    if upd.returncode != 0:
        return False, f"Échec apt-get update: {upd.stderr.strip()}"

    upg = subprocess.run(
        ["apt-get", "upgrade", "-y", "-o", "Dpkg::Options::=--force-confold"],
        capture_output=True,
        text=True,
        env=env,
    )
    if upg.returncode != 0:
        return False, f"Échec apt-get upgrade: {upg.stderr.strip()}"

    messages.append("Paquets système alignés sur la politique serveur.")
    return True, " ".join(messages)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronisation de la politique de mises à jour LyuX")
    parser.add_argument("--apply", action="store_true", help="Appliquer les mises à jour validées par le serveur")
    parser.add_argument("--json", action="store_true", help="Afficher l'état local + serveur en JSON")
    args = parser.parse_args()

    if args.apply:
        ok, msg = apply_server_selected_updates()
        print(msg)
        return 0 if ok else 1

    url = load_server_url()
    policy = sync_update_policy(url) if url else None
    if args.json:
        print(json.dumps({"local": get_local_versions(), "policy": policy}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
