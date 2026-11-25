"""
Vérification, téléchargement sécurisé, application et rollback des manifestes de profils côté client.
États : pending, verifying, downloading, applying, applied, failed, rolling_back.
"""

import base64
import datetime
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

SCHEMA_NAME = "lyux-profile-manifest"
SCHEMA_VERSION = 1

STABLE_PROFILES = frozenset({
    "standard",
    "nsi",
    "sciences",
    "multimedia",
    "atelier",
    "prof",
    "eleve",
})

ALLOWED_ARTIFACT_TYPES = frozenset({
    "deb",
    "apt-repository",
    "flatpak",
    "theme",
    "kde-config",
    "kiosk-config",
    "veyon-config",
    "ansible-playbook-signed",
    "lyux-asset",
    "config",
    "ansible",
})
APPROVED_DEBIAN_PACKAGES = frozenset({
    "lyux-profile-standard",
    "lyux-profile-nsi",
    "lyux-profile-sciences",
    "lyux-profile-multimedia",
    "lyux-profile-atelier",
    "thonny",
    "geogebra",
    "veyon-service",
    "veyon-master",
    "firefox-esr-l10n-fr",
    "libreoffice-l10n-fr",
    "fonts-inter",
})
APPROVED_FLATPAKS = frozenset({
    "org.blender.Blender",
    "org.gimp.GIMP",
    "org.audacityteam.Audacity",
    "org.kde.krita",
})
APPLY_STATES = ("pending", "verifying", "downloading", "applying", "applied", "failed", "rolling_back")

DEFAULT_APPROVED_SOURCES = (
    "https://deb.debian.org/",
    "https://flathub.org/",
    "https://github.com/Luux-Manchot/",
    "http://lyux-server",
    "https://lyux-server",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_CHARS = (";", "|", "&", "`", "$(", "\n", "\r")

PROFILE_STATE_FILE = Path(os.getenv("LYUX_PROFILE_STATE_FILE", "/var/lib/lyux/profile-state.json"))
TRUSTED_KEYS_FILE = Path(os.getenv("LYUX_TRUSTED_KEYS_FILE", "/etc/lyux/trusted-public-keys.json"))
ACTIVE_PROFILE_DIR = Path(os.getenv("LYUX_ACTIVE_PROFILE_DIR", "/var/lib/lyux/active-profile"))
BACKUP_PROFILE_DIR = Path(os.getenv("LYUX_BACKUP_PROFILE_DIR", "/var/lib/lyux/backup-profile"))
PROFILE_LOG_FILE = Path(os.getenv("LYUX_PROFILE_LOG", "/var/log/lyux-profile-apply.log"))


def _get_logger() -> logging.Logger:
    logger = logging.getLogger("lyux.profile")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        try:
            PROFILE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(PROFILE_LOG_FILE, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            pass
    return logger


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def canonical_manifest_bytes(manifest: Dict[str, Any]) -> bytes:
    payload = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _approved_sources() -> Tuple[str, ...]:
    env_val = os.getenv("LYUX_APPROVED_SOURCES", "").strip()
    if env_val:
        return tuple(s.strip() for s in env_val.split(",") if s.strip())
    return DEFAULT_APPROVED_SOURCES


def is_approved_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    if any(c in url for c in _FORBIDDEN_CHARS):
        return False
    return any(url.startswith(prefix) for prefix in _approved_sources())


def verify_ed25519(manifest: Dict[str, Any], signature_b64: str, public_key_pem: str) -> bool:
    if not signature_b64 or not public_key_pem:
        return False
    try:
        padded = signature_b64 + "=" * (-len(signature_b64) % 4)
        sig_bytes = base64.urlsafe_b64decode(padded)
        pub = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        if not isinstance(pub, ed25519.Ed25519PublicKey):
            return False
        pub.verify(sig_bytes, canonical_manifest_bytes(manifest))
        return True
    except (InvalidSignature, ValueError, Exception):
        return False


def validate_manifest(
    manifest: Dict[str, Any],
    public_keys: Dict[str, str],
    *,
    expected_scope: Optional[Dict[str, str]] = None,
    key_id: Optional[str] = None,
    system_debian: str = "13",
    system_desktop: str = "plasma6-x11",
    now: Optional[datetime.datetime] = None,
) -> Tuple[bool, str]:
    if not isinstance(manifest, dict):
        return False, "Manifeste corrompu (objet JSON requis)."
    if manifest.get("schema") != SCHEMA_NAME or manifest.get("schema_version") != SCHEMA_VERSION:
        return False, "Schéma ou version de manifeste incompatible."
    if manifest.get("profile_id") not in STABLE_PROFILES:
        return False, f"Profil inconnu : {manifest.get('profile_id')}"

    current = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        issued = datetime.datetime.fromisoformat(str(manifest["issued_at"]).replace("Z", "+00:00"))
        expires = datetime.datetime.fromisoformat(str(manifest["expires_at"]).replace("Z", "+00:00"))
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=datetime.timezone.utc)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return False, "Dates issued_at/expires_at invalides."

    if issued > current + datetime.timedelta(seconds=60):
        return False, "Manifeste futur refusé."
    if expires <= current:
        return False, "Manifeste expiré refusé."

    scope = manifest.get("scope")
    if not isinstance(scope, dict):
        return False, "Scope manquant."
    if expected_scope:
        for k in ("building_id", "room_id", "role"):
            if expected_scope.get(k) and scope.get(k) != expected_scope[k]:
                return False, f"Portée invalide sur {k}."

    compat = manifest.get("compatibility")
    if not isinstance(compat, dict) or compat.get("debian") != system_debian or compat.get("desktop") != system_desktop:
        return False, "Compatibilité système refusée."

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return False, "Aucun artefact dans le manifeste."
    for art in artifacts:
        if not isinstance(art, dict):
            return False, "Artefact invalide."
        if "command" in art or "script" in art:
            return False, "Champ libre command/script interdit."
        if art.get("type") not in ALLOWED_ARTIFACT_TYPES:
            return False, f"Type d'artefact refusé : {art.get('type')}"
        if art.get("type") == "deb" and art.get("package") and art["package"] not in APPROVED_DEBIAN_PACKAGES:
            return False, f"Paquet Debian hors catalogue approuvé : {art['package']}"
        if art.get("type") == "flatpak" and art.get("flatpak_id") and art["flatpak_id"] not in APPROVED_FLATPAKS:
            return False, f"Flatpak hors catalogue approuvé : {art['flatpak_id']}"
        if not is_approved_url(art.get("url", "")):
            return False, f"Source non approuvée : {art.get('url')}"
        if not _SHA256_RE.match(str(art.get("sha256", ""))):
            return False, f"SHA-256 invalide pour {art.get('name')}"
        if not isinstance(art.get("size"), int) or art["size"] <= 0:
            return False, f"Taille invalide pour {art.get('name')}"

    sig = manifest.get("signature", "")
    candidates = [public_keys[key_id]] if key_id and key_id in public_keys else list(public_keys.values())
    if not sig or not any(verify_ed25519(manifest, sig, pem) for pem in candidates):
        return False, "Signature Ed25519 invalide ou absente."

    return True, "OK"


def load_profile_state(state_file: Optional[Path] = None) -> Dict[str, Any]:
    target = state_file or PROFILE_STATE_FILE
    if target.exists():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "state": "pending",
        "current_profile": None,
        "last_good_profile": None,
        "last_good_manifest": None,
        "last_error": "",
        "history": [],
    }


def save_profile_state(
    state: str,
    *,
    state_file: Optional[Path] = None,
    current_profile: Optional[str] = None,
    last_good_profile: Optional[str] = None,
    last_good_manifest: Optional[Dict[str, Any]] = None,
    last_error: Optional[str] = None,
    history_entry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if state not in APPLY_STATES:
        raise ValueError(f"État invalide : {state}")
    target = state_file or PROFILE_STATE_FILE
    cur = load_profile_state(target)
    cur["state"] = state
    if current_profile is not None:
        cur["current_profile"] = current_profile
    if last_good_profile is not None:
        cur["last_good_profile"] = last_good_profile
    if last_good_manifest is not None:
        cur["last_good_manifest"] = last_good_manifest
    if last_error is not None:
        cur["last_error"] = last_error
    if history_entry is not None:
        cur.setdefault("history", []).insert(0, history_entry)
        cur["history"] = cur["history"][:50]
    _atomic_write_json(target, cur)
    return cur


def _default_downloader(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=10) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)


def download_and_verify_artifacts(
    artifacts: List[Dict[str, Any]],
    staging_dir: Path,
    downloader: Optional[Callable[[str, Path], None]] = None,
) -> Tuple[bool, List[Path], str]:
    dl = downloader or _default_downloader
    downloaded: List[Path] = []
    for art in artifacts:
        safe_name = os.path.basename(art["name"])
        dest = staging_dir / safe_name
        try:
            dl(art["url"], dest)
        except Exception as exc:
            return False, [], f"Téléchargement échoué ({safe_name}) : {exc}"

        if not dest.exists():
            return False, [], f"Artefact manquant après téléchargement : {safe_name}"
        raw = dest.read_bytes()
        if len(raw) != art["size"]:
            return False, [], f"Taille incorrecte pour {safe_name} ({len(raw)} != {art['size']})"
        digest = hashlib.sha256(raw).hexdigest()
        if digest != art["sha256"]:
            return False, [], f"SHA-256 incorrect pour {safe_name}"
        os.chmod(dest, 0o644)
        downloaded.append(dest)
    return True, downloaded, "OK"


def rollback_profile(
    *,
    state_file: Optional[Path] = None,
    active_dir: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    logger = _get_logger()
    st_file = state_file or PROFILE_STATE_FILE
    act_dir = active_dir or ACTIVE_PROFILE_DIR
    bak_dir = backup_dir or BACKUP_PROFILE_DIR

    save_profile_state("rolling_back", state_file=st_file)
    cur = load_profile_state(st_file)
    last_good = cur.get("last_good_profile")
    if bak_dir.exists() and last_good:
        if act_dir.exists():
            shutil.rmtree(act_dir, ignore_errors=True)
        shutil.copytree(bak_dir, act_dir)
        save_profile_state(
            "applied",
            state_file=st_file,
            current_profile=last_good,
            last_error="",
            history_entry={
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "action": "rollback",
                "profile_id": last_good,
                "status": "restored",
            },
        )
        logger.warning("Rollback effectué vers le dernier profil valide : %s", last_good)
        return True, f"Rollback réussi vers {last_good}"

    save_profile_state("failed", state_file=st_file, last_error="Aucun profil de secours disponible.")
    return False, "Aucun profil de secours disponible."


def apply_verified_manifest(
    manifest: Dict[str, Any],
    public_keys: Dict[str, str],
    *,
    expected_scope: Optional[Dict[str, str]] = None,
    key_id: Optional[str] = None,
    downloader: Optional[Callable[[str, Path], None]] = None,
    state_file: Optional[Path] = None,
    active_dir: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    logger = _get_logger()
    st_file = state_file or PROFILE_STATE_FILE
    act_dir = active_dir or ACTIVE_PROFILE_DIR
    bak_dir = backup_dir or BACKUP_PROFILE_DIR

    save_profile_state("verifying", state_file=st_file)
    ok, msg = validate_manifest(manifest, public_keys, expected_scope=expected_scope, key_id=key_id)
    if not ok:
        logger.error("Manifeste rejeté : %s", msg)
        save_profile_state("failed", state_file=st_file, last_error=msg)
        return {"ok": False, "state": "failed", "detail": msg}

    save_profile_state("downloading", state_file=st_file)
    tmp_dir = Path(tempfile.mkdtemp(prefix="lyux-profile-"))
    try:
        dl_ok, files, dl_msg = download_and_verify_artifacts(manifest["artifacts"], tmp_dir, downloader=downloader)
        if not dl_ok:
            logger.error("Échec vérification artefact : %s", dl_msg)
            cur = load_profile_state(st_file)
            if cur.get("last_good_profile"):
                rollback_profile(state_file=st_file, active_dir=act_dir, backup_dir=bak_dir)
                return {"ok": False, "state": "rolling_back", "detail": dl_msg, "rolled_back": True}
            save_profile_state("failed", state_file=st_file, last_error=dl_msg)
            return {"ok": False, "state": "failed", "detail": dl_msg, "rolled_back": False}

        save_profile_state("applying", state_file=st_file)
        if act_dir.exists():
            if bak_dir.exists():
                shutil.rmtree(bak_dir, ignore_errors=True)
            shutil.copytree(act_dir, bak_dir)
            shutil.rmtree(act_dir, ignore_errors=True)

        act_dir.mkdir(parents=True, exist_ok=True)
        for src_file in files:
            shutil.copy2(src_file, act_dir / src_file.name)
        _atomic_write_json(act_dir / "manifest.json", manifest)

        pid = manifest["profile_id"]
        save_profile_state(
            "applied",
            state_file=st_file,
            current_profile=pid,
            last_good_profile=pid,
            last_good_manifest=manifest,
            last_error="",
            history_entry={
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "action": "apply",
                "profile_id": pid,
                "profile_version": manifest["profile_version"],
                "status": "applied",
            },
        )
        logger.info("Profil %s (%s) vérifié et appliqué.", pid, manifest["profile_version"])
        return {"ok": True, "state": "applied", "profile_id": pid}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
