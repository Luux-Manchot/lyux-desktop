"""
Applicateur technique de profil post-enrôlement (Étape 4) :
- Vérifie le manifeste Ed25519 et chaque artefact SHA-256 avant toute action
- Installe les paquets Debian approuvés (dpkg -i / contrôle dpkg-query)
- Applique la configuration KDE/Kiosk/X11 de manière atomique sans activer Wayland
- Rapporte l'état et les versions installées au serveur LyuX
- Effectue un rollback automatique vers le profil précédent en cas d'échec
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

try:
    from profile_manifest import (
        ACTIVE_PROFILE_DIR,
        BACKUP_PROFILE_DIR,
        PROFILE_STATE_FILE,
        TRUSTED_KEYS_FILE,
        apply_verified_manifest,
        load_profile_state,
        load_trusted_public_keys,
        rollback_profile,
        save_profile_state,
    )
except ImportError:
    from .profile_manifest import (
        ACTIVE_PROFILE_DIR,
        BACKUP_PROFILE_DIR,
        PROFILE_STATE_FILE,
        TRUSTED_KEYS_FILE,
        apply_verified_manifest,
        load_profile_state,
        load_trusted_public_keys,
        rollback_profile,
        save_profile_state,
    )


def get_installed_package_versions(packages: List[str]) -> Dict[str, str]:
    versions: Dict[str, str] = {}
    for pkg in packages:
        try:
            res = subprocess.run(
                ["dpkg-query", "-W", "-f=${Status}|${Version}", pkg],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and "install ok installed|" in res.stdout:
                versions[pkg] = res.stdout.split("|", 1)[1].strip()
        except Exception:
            pass
    return versions


def apply_kde_x11_baseline(config_dir: Path, sddm_conf_dir: Optional[Path] = None) -> None:
    """Garantit X11 actif et dépose la configuration KDE/Kiosk sans jamais activer Wayland."""
    sddm_dir = sddm_conf_dir or Path("/etc/sddm.conf.d")
    sddm_dir.mkdir(parents=True, exist_ok=True)
    conf_file = sddm_dir / "99-lyux-theme.conf"
    tmp = conf_file.with_suffix(".conf.tmp")
    tmp.write_text(
        "[Theme]\nCurrent=lyux-sddm\n\n[General]\nDisplayServer=x11\n\n[X11]\nDefaultSession=plasmax11.desktop\n",
        encoding="utf-8",
    )
    os.replace(tmp, conf_file)

    config_dir.mkdir(parents=True, exist_ok=True)
    marker = config_dir / "x11-kiosk-applied.json"
    marker.write_text(json.dumps({"display_server": "x11", "wayland_disabled": True}, indent=2), encoding="utf-8")


def report_profile_status(
    server_url: str,
    *,
    client_id: str,
    hostname: str,
    profile_id: str,
    profile_version: str,
    state: str,
    installed_packages: Optional[Dict[str, str]] = None,
    error: str = "",
) -> bool:
    try:
        res = requests.post(
            f"{server_url.rstrip('/')}/api/v1/client/profile-report",
            json={
                "client_id": client_id,
                "hostname": hostname,
                "profile_id": profile_id,
                "profile_version": profile_version,
                "state": state,
                "installed_packages": installed_packages or {},
                "error": error,
            },
            timeout=5,
        )
        return res.status_code == 200
    except Exception:
        return False


def sync_and_apply_profile(
    *,
    server_url: str,
    client_id: str,
    hostname: str,
    building_id: str,
    room_id: str,
    role: str = "eleve",
    public_keys: Optional[Dict[str, str]] = None,
    downloader: Optional[Callable[[str, Path], None]] = None,
    deb_installer: Optional[Callable[[Path], Tuple[bool, str]]] = None,
    state_file: Optional[Path] = None,
    active_dir: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    sddm_conf_dir: Optional[Path] = None,
    trusted_keys_file: Optional[Path] = None,
) -> Dict[str, Any]:
    st_file = state_file or PROFILE_STATE_FILE
    act_dir = active_dir or ACTIVE_PROFILE_DIR
    bak_dir = backup_dir or BACKUP_PROFILE_DIR

    keys = dict(public_keys) if public_keys else load_trusted_public_keys(trusted_keys_file or TRUSTED_KEYS_FILE)
    if not keys:
        return {"ok": False, "state": "failed", "detail": "Trousseau local de clés publiques absent ou vide."}

    try:
        mr = requests.get(
            f"{server_url.rstrip('/')}/api/v1/client/profile-manifest",
            params={
                "client_id": client_id,
                "hostname": hostname,
                "building_id": building_id,
                "room_id": room_id,
                "role": role,
                "schema_version": 1,
            },
            timeout=5,
        )
        if mr.status_code != 200:
            return {"ok": False, "state": "failed", "detail": f"Manifeste refusé ({mr.status_code})"}
        payload = mr.json()
    except Exception as exc:
        return {"ok": False, "state": "failed", "detail": f"Serveur injoignable : {exc}"}

    manifest = payload.get("manifest", {})
    kid = payload.get("public_key_id")
    scope = {"building_id": building_id, "room_id": room_id, "role": role}

    # Idempotence : si ce profil et cette version sont déjà appliqués, ne rien réappliquer
    cur_state = load_profile_state(st_file)
    prev_good_profile = cur_state.get("last_good_profile")
    prev_good_manifest = cur_state.get("last_good_manifest")
    cur_man = prev_good_manifest or {}
    if (
        cur_state.get("state") == "applied"
        and cur_state.get("current_profile") == manifest.get("profile_id")
        and cur_man.get("profile_version") == manifest.get("profile_version")
        and act_dir.exists()
    ):
        return {"ok": True, "state": "applied", "idempotent": True, "profile_id": manifest.get("profile_id")}

    apply_res = apply_verified_manifest(
        manifest,
        keys,
        expected_scope=scope,
        key_id=kid,
        downloader=downloader,
        state_file=st_file,
        active_dir=act_dir,
        backup_dir=bak_dir,
    )
    if not apply_res.get("ok"):
        report_profile_status(
            server_url,
            client_id=client_id,
            hostname=hostname,
            profile_id=manifest.get("profile_id", "unknown"),
            profile_version=manifest.get("profile_version", ""),
            state=apply_res.get("state", "failed"),
            error=apply_res.get("detail", ""),
        )
        return apply_res

    installed_pkgs: Dict[str, str] = {}
    for art in manifest.get("artifacts", []):
        if art.get("type") == "deb":
            deb_path = act_dir / os.path.basename(art["name"])
            if deb_installer is not None:
                ok_deb, msg_deb = deb_installer(deb_path)
            else:
                meta = subprocess.run(["dpkg-deb", "-f", str(deb_path), "Package"], capture_output=True, text=True, timeout=15)
                if meta.returncode != 0 or meta.stdout.strip() != art.get("package"):
                    ok_deb, msg_deb = False, f"Métadonnée Package incohérente ({meta.stdout.strip()})"
                else:
                    r = subprocess.run(["dpkg", "-i", str(deb_path)], capture_output=True, text=True, timeout=60)
                    ok_deb, msg_deb = (r.returncode == 0), r.stderr or r.stdout
            if not ok_deb:
                if prev_good_profile:
                    save_profile_state(
                        "rolling_back",
                        state_file=st_file,
                        last_good_profile=prev_good_profile,
                        last_good_manifest=prev_good_manifest,
                    )
                rollback_profile(state_file=st_file, active_dir=act_dir, backup_dir=bak_dir)
                report_profile_status(
                    server_url,
                    client_id=client_id,
                    hostname=hostname,
                    profile_id=manifest["profile_id"],
                    profile_version=manifest["profile_version"],
                    state="rolling_back",
                    error=f"Échec installation paquet {art['name']}: {msg_deb}",
                )
                return {"ok": False, "state": "rolling_back", "detail": msg_deb, "rolled_back": True}
            pkg_name = art.get("package") or art["name"].split("_")[0]
            installed_pkgs[pkg_name] = art.get("version", "1.0.0")

    apply_kde_x11_baseline(act_dir, sddm_conf_dir=sddm_conf_dir)
    report_profile_status(
        server_url,
        client_id=client_id,
        hostname=hostname,
        profile_id=manifest["profile_id"],
        profile_version=manifest["profile_version"],
        state="applied",
        installed_packages=installed_pkgs,
    )
    return {
        "ok": True,
        "state": "applied",
        "idempotent": False,
        "profile_id": manifest["profile_id"],
        "installed_packages": installed_pkgs,
    }
