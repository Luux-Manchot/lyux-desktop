"""
Logique métier OOBE / Enrôlement client LyuX :
- Machine à états persistée atomiquement
- Identité stable (client_id) pour l'idempotence
- Validation stricte des catalogues serveur (bâtiments, salles, rôles)
- Aucun faux fichier d'enrôlement écrit avant confirmation serveur
"""

import datetime
import hashlib
import ipaddress
import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from discovery import probe_server_health, validate_server_url, get_candidate_server_urls
    from hardware import get_hardware_fingerprint
except ImportError:
    from .discovery import probe_server_health, validate_server_url, get_candidate_server_urls
    from .hardware import get_hardware_fingerprint

VALID_STATES = (
    "pending",
    "network-error",
    "server-unreachable",
    "awaiting-authorization",
    "authorized",
    "enrolled",
    "retry",
)

FIRST_BOOT_FLAG = Path(os.getenv("LYUX_FIRST_BOOT_FLAG", "/etc/lyux/first-boot.flag"))
ENROLLED_FILE = Path(os.getenv("LYUX_ENROLLED_FILE", "/etc/lyux/enrolled.json"))
STATE_FILE = Path(os.getenv("LYUX_STATE_FILE", "/var/lib/lyux/enrollment-state.json"))
CLIENT_ID_FILE = Path(os.getenv("LYUX_CLIENT_ID_FILE", "/var/lib/lyux/client-id"))
OOBE_LOG_FILE = Path(os.getenv("LYUX_OOBE_LOG", "/var/log/lyux-oobe.log"))


def get_oobe_logger() -> logging.Logger:
    logger = logging.getLogger("lyux.oobe")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        try:
            OOBE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(OOBE_LOG_FILE, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            pass
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def get_or_create_client_id(client_id_file: Optional[Path] = None) -> str:
    """Retourne une clé d'idempotence stable entre reboots et tentatives."""
    target = client_id_file or CLIENT_ID_FILE
    if target.exists():
        existing = target.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    machine_id = ""
    mid_path = Path("/etc/machine-id")
    if mid_path.exists():
        machine_id = mid_path.read_text(encoding="utf-8").strip()

    try:
        mac = get_hardware_fingerprint().get("mac_address", "")
    except Exception:
        mac = ""

    seed = f"{machine_id}|{mac}" if (machine_id or mac) else str(uuid.uuid4())
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    client_id = f"lyux-{digest}"
    try:
        _atomic_write_text(target, client_id + "\n")
    except Exception:
        pass
    return client_id


def load_state(state_file: Optional[Path] = None) -> Dict[str, Any]:
    target = state_file or STATE_FILE
    if target.exists():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "state": "pending",
        "client_id": get_or_create_client_id(),
        "server_url": "",
        "building_id": "",
        "room_id": "",
        "role": "",
        "hostname": "",
        "last_error": "",
        "attempts": 0,
        "updated_at": "",
    }


def save_state(
    state: str,
    *,
    state_file: Optional[Path] = None,
    server_url: Optional[str] = None,
    building_id: Optional[str] = None,
    room_id: Optional[str] = None,
    role: Optional[str] = None,
    hostname: Optional[str] = None,
    last_error: Optional[str] = None,
    increment_attempt: bool = False,
) -> Dict[str, Any]:
    if state not in VALID_STATES:
        raise ValueError(f"État OOBE invalide : {state}")
    target = state_file or STATE_FILE
    current = load_state(target)
    current["state"] = state
    current["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if server_url is not None:
        current["server_url"] = server_url
    if building_id is not None:
        current["building_id"] = building_id
    if room_id is not None:
        current["room_id"] = room_id
    if role is not None:
        current["role"] = role
    if hostname is not None:
        current["hostname"] = hostname
    if last_error is not None:
        current["last_error"] = last_error
    if increment_attempt:
        current["attempts"] = int(current.get("attempts", 0)) + 1
    _atomic_write_json(target, current)
    return current


def check_network_ready() -> Tuple[bool, List[str]]:
    """Vérifie si au moins une interface non-loopback possède une IPv4."""
    try:
        res = subprocess.run(
            ["ip", "-4", "-brief", "addr"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            active = []
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0] != "lo" and not parts[0].startswith(("docker", "veth", "br-")):
                    active.append(f"{parts[0]} ({parts[2]})")
            return bool(active), active
    except Exception:
        pass
    # Fallback sans commande `ip` (ex. environnement Windows de test)
    return True, ["default"]


ALLOWED_KEYMAPS = {
    "fr": ("fr", "latin9"),
    "us": ("us", ""),
    "be": ("be", ""),
    "ch": ("ch", "fr"),
}


def apply_keyboard_layout(layout_code: str) -> Tuple[bool, str]:
    """Applique réellement la disposition clavier (X11 immédiat + persistance localectl)."""
    code = (layout_code or "").strip().lower()
    if code not in ALLOWED_KEYMAPS:
        return False, f"Disposition clavier non prise en charge : {layout_code}"
    layout, variant = ALLOWED_KEYMAPS[code]
    logger = get_oobe_logger()
    try:
        if os.name != "nt":
            xkb_cmd = ["setxkbmap", layout] + ([variant] if variant else [])
            subprocess.run(xkb_cmd, check=False, timeout=3)
            loc_cmd = ["localectl", "set-x11-keymap", layout, "pc105"] + ([variant] if variant else [])
            subprocess.run(loc_cmd, check=False, timeout=3)
            subprocess.run(["localectl", "set-keymap", layout], check=False, timeout=3)
        logger.info("Disposition clavier appliquée : %s (%s)", layout, variant or "standard")
        return True, f"Clavier {layout.upper()} appliqué"
    except Exception as exc:
        logger.warning("Impossible d'appliquer le clavier %s : %s", code, exc)
        return False, str(exc)


def configure_static_network(iface: str, ip_cidr: str, gateway: str, dns: str = "") -> Tuple[bool, str]:
    """Valide et écrit une configuration IPv4 statique sans toucher à first-boot.flag."""
    iface = (iface or "").strip()
    if not iface or any(ch in iface for ch in (" ", "/", ";", "&")):
        return False, "Nom d'interface invalide."
    try:
        ipaddress.ip_interface(ip_cidr.strip())
    except ValueError:
        return False, "Adresse IP/masque CIDR invalide (ex: 192.168.1.50/24)."
    if gateway.strip():
        try:
            ipaddress.ip_address(gateway.strip())
        except ValueError:
            return False, "Passerelle IPv4 invalide."
    if dns.strip():
        try:
            ipaddress.ip_address(dns.strip())
        except ValueError:
            return False, "Serveur DNS IPv4 invalide."

    conf_path = Path(os.getenv("LYUX_STATIC_CONF", "/etc/lyux/network-static.conf"))
    content = (
        f"IFACE={iface}\n"
        f"IP_CIDR={ip_cidr.strip()}\n"
        f"GATEWAY={gateway.strip()}\n"
        f"DNS={dns.strip()}\n"
    )
    try:
        _atomic_write_text(conf_path, content)
        script = Path(__file__).resolve().parent.parent / "scripts" / "lyux-net-setup.sh"
        if script.exists() and os.name != "nt":
            subprocess.run(["/bin/bash", str(script)], check=False, timeout=10)
        return True, "Configuration statique appliquée."
    except Exception as exc:
        return False, f"Erreur application réseau : {exc}"


def inspect_server(target_url: Optional[str] = None, timeout_sec: float = 2.5) -> Dict[str, Any]:
    """
    Teste le réseau, la joignabilité serveur, l'API et le verrou d'enrôlement.
    Retourne un dict avec state in:
      'network-error' | 'server-unreachable' | 'awaiting-authorization' | 'authorized' | 'enrolled'
    """
    logger = get_oobe_logger()
    net_ok, ifaces = check_network_ready()
    if not net_ok:
        logger.warning("Réseau indisponible : aucune interface IPv4 active.")
        return {"state": "network-error", "detail": "Aucune interface réseau IPv4 active.", "ifaces": []}

    if target_url:
        valid, norm, err = validate_server_url(target_url)
        if not valid:
            return {"state": "server-unreachable", "detail": err, "ifaces": ifaces}
        candidates = [norm]
    else:
        candidates = get_candidate_server_urls()

    last_status = "server-unreachable"
    last_detail = "Aucun serveur LyuX détecté sur le réseau."
    for url in candidates:
        h_status, h_data = probe_server_health(url, timeout_sec=timeout_sec)
        if h_status == "api-error":
            last_status = "server-unreachable"
            last_detail = f"API inaccessible ou invalide sur {url} ({h_data.get('detail', '')})"
            continue
        if h_status != "ok":
            last_detail = f"Serveur injoignable sur {url}"
            continue

        # Vérifier si ce poste est déjà enrôlé côté serveur (reprise idempotente)
        client_id = get_or_create_client_id()
        try:
            st_res = requests.get(f"{url}/api/v1/enroll/status/{client_id}", timeout=timeout_sec)
            if st_res.status_code == 200:
                st_json = st_res.json()
                if st_json.get("enrolled") is True:
                    return {
                        "state": "enrolled",
                        "server_url": url,
                        "machine": st_json.get("machine", {}),
                        "profile": st_json.get("profile", {}),
                        "signature": st_json.get("signature", ""),
                        "ifaces": ifaces,
                    }
        except Exception:
            pass

        try:
            settings_res = requests.get(f"{url}/api/v1/settings", timeout=timeout_sec)
            if settings_res.status_code != 200:
                return {"state": "server-unreachable", "detail": f"Erreur API /settings ({settings_res.status_code})", "ifaces": ifaces}
            settings = settings_res.json()
            buildings = requests.get(f"{url}/api/v1/buildings", timeout=timeout_sec).json()
            rooms = requests.get(f"{url}/api/v1/rooms", timeout=timeout_sec).json()
            roles_res = requests.get(f"{url}/api/v1/enroll/roles", timeout=timeout_sec)
            roles = roles_res.json() if roles_res.status_code == 200 else [
                {"id": "eleve", "name": "Poste Élève"},
                {"id": "prof", "name": "Poste Enseignant"},
            ]
        except Exception as exc:
            logger.error("Erreur lecture catalogue sur %s : %s", url, exc)
            return {"state": "server-unreachable", "detail": f"API inaccessible : {exc}", "ifaces": ifaces}

        if not isinstance(buildings, list) or not isinstance(rooms, list):
            return {"state": "server-unreachable", "detail": "Catalogue serveur invalide.", "ifaces": ifaces}

        if not settings.get("enrollment_enabled", False):
            logger.warning("Enrôlement verrouillé sur %s", url)
            return {
                "state": "awaiting-authorization",
                "server_url": url,
                "settings": settings,
                "buildings": buildings,
                "rooms": rooms,
                "roles": roles,
                "detail": "Enrôlement verrouillé par l'administrateur sur le serveur.",
                "ifaces": ifaces,
            }

        return {
            "state": "authorized",
            "server_url": url,
            "settings": settings,
            "buildings": buildings,
            "rooms": rooms,
            "roles": roles,
            "detail": "Serveur joignable et enrôlement autorisé.",
            "ifaces": ifaces,
        }

    logger.warning("Échec détection serveur : %s", last_detail)
    return {"state": last_status, "detail": last_detail, "ifaces": ifaces}


def _configure_pam_nss_after_enrollment(server_url: str) -> None:
    """
    Configure PAM (common-auth + common-session), NSS (nsswitch.conf + extrausers)
    et active le timer de synchronisation NSS après enrôlement réussi.
    Idempotent : ne modifie que ce qui manque.
    """
    logger = get_oobe_logger()

    PAM_AUTH = Path("/etc/pam.d/common-auth")
    PAM_SESSION = Path("/etc/pam.d/common-session")
    NSSWITCH = Path("/etc/nsswitch.conf")
    EXTRA_DIR = Path("/var/lib/extrausers")
    PAM_AUTH_HOOK = "/opt/lyux/apps/enrollment/scripts/lyux-pam-auth.sh"
    PAM_SESSION_HOOK = "/opt/lyux/apps/enrollment/scripts/lyux-pam-session.sh"
    NSS_SYNC = "/opt/lyux/apps/enrollment/src/nss_user_sync.py"

    # 1. PAM auth : ajouter notre hook si absent
    if PAM_AUTH.exists() and Path(PAM_AUTH_HOOK).exists():
        content = PAM_AUTH.read_text(encoding="utf-8")
        if PAM_AUTH_HOOK not in content:
            PAM_AUTH.write_text(
                f"auth sufficient pam_exec.so expose_authtok quiet {PAM_AUTH_HOOK}\n" + content,
                encoding="utf-8",
            )
            logger.info("PAM common-auth : hook lyux-pam-auth.sh ajouté.")

    # 2. PAM session : ajouter notre hook si absent
    if PAM_SESSION.exists() and Path(PAM_SESSION_HOOK).exists():
        content = PAM_SESSION.read_text(encoding="utf-8")
        if PAM_SESSION_HOOK not in content:
            with PAM_SESSION.open("a", encoding="utf-8") as f:
                f.write(f"session requisite pam_exec.so {PAM_SESSION_HOOK}\n")
            logger.info("PAM common-session : hook lyux-pam-session.sh ajouté.")

    # 3. NSS : ajouter extrausers à passwd/group/shadow si absent
    if NSSWITCH.exists():
        lines = NSSWITCH.read_text(encoding="utf-8").splitlines()
        changed = False
        updated = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("passwd:", "group:", "shadow:")) and "extrausers" not in stripped.split():
                updated.append(f"{line.rstrip()} extrausers")
                changed = True
            else:
                updated.append(line)
        if changed:
            NSSWITCH.write_text("\n".join(updated) + "\n", encoding="utf-8")
            logger.info("nsswitch.conf : extrausers ajouté.")

    # 4. Répertoire extrausers
    EXTRA_DIR.mkdir(parents=True, exist_ok=True)
    for fname in ("passwd", "group", "shadow"):
        p = EXTRA_DIR / fname
        if not p.exists():
            p.write_text("", encoding="utf-8")
    try:
        import os as _os
        _os.chmod(EXTRA_DIR / "shadow", 0o600)
    except OSError:
        pass

    # 5. Timer systemd lyux-nss-sync
    for unit in ("lyux-nss-sync.service", "lyux-nss-sync.timer"):
        src = Path(f"/opt/lyux/apps/enrollment/systemd/{unit}")
        dst = Path(f"/lib/systemd/system/{unit}")
        if src.exists() and not dst.exists():
            import shutil as _shutil
            _shutil.copy2(src, dst)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "--now", "lyux-nss-sync.timer"], check=False)
    logger.info("Timer lyux-nss-sync activé.")

    # 6. Première synchronisation NSS immédiate
    if Path(NSS_SYNC).exists():
        try:
            subprocess.run(["python3", NSS_SYNC], check=False, timeout=10)
            logger.info("Première synchronisation NSS effectuée.")
        except Exception as exc:
            logger.warning("Sync NSS initiale échouée : %s", exc)

    # 7. Montage NAS (/mnt/lyux-nas/homes) si activé côté serveur
    try:
        nas_enabled = True
        share_path = "/srv/samba/homes"
        try:
            import requests as _req
            r = _req.get(f"{server_url.rstrip('/')}/api/v1/system/settings", timeout=3)
            if r.status_code == 200:
                sdata = r.json()
                nas_enabled = bool(sdata.get("nas_sync_enabled", True))
                share_path = str(sdata.get("nas_share_path") or "/srv/samba/homes").strip()
        except Exception:
            pass
        if nas_enabled:
            from urllib.parse import urlparse as _urlparse
            host = (_urlparse(server_url).hostname or "").strip()
            nas_mount = Path("/mnt/lyux-nas/homes")
            nas_mount.mkdir(parents=True, exist_ok=True)
            fstab = Path("/etc/fstab")
            if host and fstab.exists():
                entry = f"{host}:{share_path} /mnt/lyux-nas/homes nfs rw,sync,nosuid,nodev,_netdev,nofail 0 0 # lyux-nas"
                lines = [ln for ln in fstab.read_text(encoding="utf-8").splitlines() if "# lyux-nas" not in ln and "/mnt/lyux-nas/homes" not in ln]
                lines.append(entry)
                fstab.write_text("\n".join(lines) + "\n", encoding="utf-8")
                subprocess.run(["mount", str(nas_mount)], check=False)
                logger.info("Montage NAS configuré dans /etc/fstab: %s:%s", host, share_path)
    except Exception as exc:
        logger.warning("Configuration montage NAS non bloquante échouée: %s", exc)


def perform_enrollment(
    server_url: str,
    building_id: str,
    room_id: str,
    hostname: str,
    role: str = "eleve",
    *,
    state_file: Optional[Path] = None,
    enrolled_file: Optional[Path] = None,
    first_boot_flag: Optional[Path] = None,
    client_id_file: Optional[Path] = None,
    apply_system_changes: bool = True,
) -> Dict[str, Any]:
    """
    Exécute l'enrôlement idempotent auprès du serveur.
    Ne écrit `enrolled.json` et ne retire `first-boot.flag` QU'APRÈS confirmation serveur.
    """
    logger = get_oobe_logger()
    st_file = state_file or STATE_FILE
    enr_file = enrolled_file or ENROLLED_FILE
    fb_flag = first_boot_flag or FIRST_BOOT_FLAG
    cid_file = client_id_file or CLIENT_ID_FILE

    valid, norm_url, err = validate_server_url(server_url)
    if not valid:
        save_state("server-unreachable", state_file=st_file, last_error=err, increment_attempt=True)
        return {"ok": False, "state": "server-unreachable", "detail": err}

    client_id = get_or_create_client_id(cid_file)
    try:
        hw = get_hardware_fingerprint()
        mac = hw.get("mac_address", "")
    except Exception:
        mac = ""

    save_state(
        "retry",
        state_file=st_file,
        server_url=norm_url,
        building_id=building_id,
        room_id=room_id,
        role=role,
        hostname=hostname,
        increment_attempt=True,
    )

    payload = {
        "client_id": client_id,
        "hostname": hostname.strip(),
        "building_id": building_id.strip(),
        "room_id": room_id.strip(),
        "mac_address": mac,
        "ip_address": "",
        "role": role,
    }

    try:
        resp = requests.post(f"{norm_url}/api/v1/enroll/client-enroll", json=payload, timeout=5)
    except requests.RequestException as exc:
        msg = f"Serveur injoignable : {exc}"
        logger.error(msg)
        save_state("server-unreachable", state_file=st_file, last_error=msg)
        return {"ok": False, "state": "server-unreachable", "detail": msg}

    if resp.status_code == 403:
        msg = "Enrôlement verrouillé par l'administrateur."
        logger.warning(msg)
        save_state("awaiting-authorization", state_file=st_file, last_error=msg)
        return {"ok": False, "state": "awaiting-authorization", "detail": msg}

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        msg = f"Refus serveur ({resp.status_code}) : {detail}"
        logger.error(msg)
        save_state("retry", state_file=st_file, last_error=msg)
        return {"ok": False, "state": "retry", "detail": msg}

    try:
        data = resp.json()
    except ValueError:
        msg = "Réponse serveur corrompue (JSON invalide)."
        logger.error(msg)
        save_state("retry", state_file=st_file, last_error=msg)
        return {"ok": False, "state": "retry", "detail": msg}

    if not data.get("success") or not isinstance(data.get("machine"), dict):
        msg = "Réponse d'enrôlement incomplète ou non confirmée."
        logger.error(msg)
        save_state("retry", state_file=st_file, last_error=msg)
        return {"ok": False, "state": "retry", "detail": msg}

    machine = data["machine"]
    profile = data.get("profile", {})
    signature = data.get("signature", "")

    enrolled_record = {
        "client_id": client_id,
        "server_url": norm_url,
        "hostname": machine.get("hostname", hostname),
        "building_id": machine.get("building_id", building_id),
        "room_id": machine.get("room_id", room_id),
        "role": machine.get("role", role),
        "profile": profile,
        "signature": signature,
        "enrolled_at": machine.get("enrolled_at", ""),
        "enrollment_pending": False,
    }
    _atomic_write_json(enr_file, enrolled_record)
    save_state(
        "enrolled",
        state_file=st_file,
        server_url=norm_url,
        building_id=enrolled_record["building_id"],
        room_id=enrolled_record["room_id"],
        role=enrolled_record["role"],
        hostname=enrolled_record["hostname"],
        last_error="",
    )

    if apply_system_changes and os.name != "nt":
        try:
            subprocess.run(["hostnamectl", "set-hostname", enrolled_record["hostname"]], check=False)
            subprocess.run(["systemctl", "disable", "lyux-enrollment.service"], check=False)
        except Exception:
            pass
        # Configurer PAM + NSS + timer au moment de l'enrôlement
        _configure_pam_nss_after_enrollment(norm_url)

    if fb_flag.exists():
        try:
            fb_flag.unlink()
        except Exception:
            pass

    logger.info("Enrôlement confirmé : %s (%s/%s)", enrolled_record["hostname"], enrolled_record["building_id"], enrolled_record["room_id"])
    return {
        "ok": True,
        "state": "enrolled",
        "idempotent": bool(data.get("idempotent", False)),
        "machine": machine,
        "profile": profile,
        "signature": signature,
    }
