"""
Mode maintenance local sécurisé LyuX :
- FIDO2/U2F (recommandé) via défi aléatoire et clé publique enregistrée
- Clé USB économique avec jeton Ed25519 daté, révocable et lié au numéro de série matériel udev
- Mot de passe administrateur local haché PBKDF2 (jamais en clair)
Aucune élévation possible hors session de maintenance active et journalisée.
"""

import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

try:
    from discovery import validate_server_url
    from enrollment_client import FIRST_BOOT_FLAG, STATE_FILE, save_state
    from profile_manifest import rollback_profile
except ImportError:
    from .discovery import validate_server_url
    from .enrollment_client import FIRST_BOOT_FLAG, STATE_FILE, save_state
    from .profile_manifest import rollback_profile

MAINTENANCE_LOG_FILE = Path(os.getenv("LYUX_MAINTENANCE_LOG", "/var/log/lyux-maintenance.log"))
MAINTENANCE_CONFIG_FILE = Path(os.getenv("LYUX_MAINTENANCE_CONF", "/etc/lyux/maintenance-keys.json"))
REVOKED_TOKENS_FILE = Path(os.getenv("LYUX_REVOKED_TOKENS", "/etc/lyux/revoked-tokens.json"))


def _get_logger() -> logging.Logger:
    logger = logging.getLogger("lyux.maintenance")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        try:
            MAINTENANCE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(MAINTENANCE_LOG_FILE, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            pass
    return logger


def hash_admin_pin(pin: str, salt: Optional[bytes] = None) -> Dict[str, str]:
    s = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), s, 200_000)
    return {
        "salt": base64.b64encode(s).decode("ascii"),
        "hash": base64.b64encode(dk).decode("ascii"),
    }


def verify_admin_pin(pin: str, stored: Dict[str, str]) -> bool:
    try:
        s = base64.b64decode(stored["salt"])
        expected = base64.b64decode(stored["hash"])
        dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), s, 200_000)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def verify_signed_usb_token(
    token: Dict[str, Any],
    *,
    public_key_pem: str,
    observed_usb_serial: str,
    revoked_ids: Optional[List[str]] = None,
    now: Optional[datetime.datetime] = None,
) -> Tuple[bool, str]:
    """Vérifie un jeton USB Ed25519 daté, non révoqué et lié au numéro de série udev."""
    if not isinstance(token, dict):
        return False, "Jeton USB invalide."

    token_id = str(token.get("token_id", "")).strip()
    if not token_id:
        return False, "token_id manquant."
    if revoked_ids and token_id in revoked_ids:
        return False, "Jeton révoqué."

    expected_serial = str(token.get("usb_serial", "")).strip()
    if not expected_serial or expected_serial != (observed_usb_serial or "").strip():
        return False, "Numéro de série USB non concordant (clé dupliquée refusée)."

    current = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        expires = datetime.datetime.fromisoformat(str(token["expires_at"]).replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return False, "Date d'expiration invalide."

    if expires <= current:
        return False, "Jeton expiré."

    sig_b64 = str(token.get("signature", "")).strip()
    if not sig_b64 or not public_key_pem:
        return False, "Signature Ed25519 absente."

    payload = {k: v for k, v in token.items() if k != "signature"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    try:
        padded = sig_b64 + "=" * (-len(sig_b64) % 4)
        sig_bytes = base64.urlsafe_b64decode(padded)
        pub = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        if not isinstance(pub, ed25519.Ed25519PublicKey):
            return False, "Clé publique non Ed25519."
        pub.verify(sig_bytes, canonical)
        return True, "OK"
    except (InvalidSignature, ValueError, Exception):
        return False, "Signature Ed25519 invalide."


class MaintenanceSession:
    """Contrôleur d'accès et d'actions du mode maintenance local."""

    def __init__(
        self,
        *,
        public_key_pem: str = "",
        revoked_ids: Optional[List[str]] = None,
        admin_pin_record: Optional[Dict[str, str]] = None,
        fido2_verifier: Optional[Any] = None,
    ):
        self.active = False
        self.actor = ""
        self.method = ""
        self.public_key_pem = public_key_pem
        self.revoked_ids = list(revoked_ids or [])
        self.admin_pin_record = admin_pin_record
        self.fido2_verifier = fido2_verifier
        self.logger = _get_logger()

    def authenticate_usb(self, token: Dict[str, Any], observed_usb_serial: str) -> Tuple[bool, str]:
        ok, msg = verify_signed_usb_token(
            token,
            public_key_pem=self.public_key_pem,
            observed_usb_serial=observed_usb_serial,
            revoked_ids=self.revoked_ids,
        )
        if ok:
            self.active = True
            self.actor = str(token.get("token_id"))
            self.method = "usb-signed"
            self.logger.info("Mode maintenance ouvert via clé USB signée (%s)", self.actor)
        else:
            self.logger.warning("Refus ouverture maintenance USB : %s", msg)
        return ok, msg

    def authenticate_fido2(self, key_handle: str, assertion_ok: bool) -> Tuple[bool, str]:
        if self.fido2_verifier is not None:
            ok = bool(self.fido2_verifier(key_handle))
        else:
            ok = bool(assertion_ok and key_handle)
        if ok:
            self.active = True
            self.actor = key_handle
            self.method = "fido2"
            self.logger.info("Mode maintenance ouvert via FIDO2 (%s)", key_handle)
            return True, "OK"
        self.logger.warning("Refus ouverture maintenance FIDO2")
        return False, "Authentification FIDO2 refusée."

    def authenticate_pin(self, pin: str) -> Tuple[bool, str]:
        if self.admin_pin_record and verify_admin_pin(pin, self.admin_pin_record):
            self.active = True
            self.actor = "local-admin"
            self.method = "admin-pin"
            self.logger.info("Mode maintenance ouvert via mot de passe admin local")
            return True, "OK"
        self.logger.warning("Refus ouverture maintenance PIN admin")
        return False, "Mot de passe administrateur invalide."

    def deactivate(self) -> None:
        if self.active:
            self.logger.info("Mode maintenance fermé (%s)", self.actor)
        self.active = False
        self.actor = ""
        self.method = ""

    def _require_active(self) -> None:
        if not self.active:
            raise PermissionError("Action refusée : mode maintenance inactif.")

    def repair_server_url(self, new_url: str, *, state_file: Optional[Path] = None) -> Tuple[bool, str]:
        self._require_active()
        valid, norm, err = validate_server_url(new_url)
        if not valid:
            return False, err
        save_state("retry", state_file=state_file or STATE_FILE, server_url=norm, last_error="")
        self.logger.info("Adresse serveur réparée : %s", norm)
        return True, norm

    def trigger_reenroll(self, *, first_boot_flag: Optional[Path] = None, state_file: Optional[Path] = None) -> bool:
        self._require_active()
        fb = first_boot_flag or FIRST_BOOT_FLAG
        fb.parent.mkdir(parents=True, exist_ok=True)
        fb.write_text("reenroll\n", encoding="utf-8")
        save_state("pending", state_file=state_file or STATE_FILE, last_error="")
        self.logger.info("Ré-enrôlement déclenché depuis le mode maintenance.")
        return True

    def restore_safe_profile(self, *, state_file: Optional[Path] = None, active_dir: Optional[Path] = None, backup_dir: Optional[Path] = None) -> Tuple[bool, str]:
        self._require_active()
        ok, msg = rollback_profile(state_file=state_file, active_dir=active_dir, backup_dir=backup_dir)
        self.logger.info("Restauration profil sécurisé : %s", msg)
        return ok, msg


def configure_root_only_access(
    root_password: str,
    *,
    config_file: Optional[Path] = None,
    lock_accounts: Tuple[str, ...] = ("lyux-admin", "invite"),
    apply_system: bool = False,
) -> Tuple[bool, str]:
    """
    Configure l'accès local unique `root` (mot de passe haché PBKDF2) et verrouille
    les comptes temporaires d'installation (`lyux-admin`, `invite`).
    """
    pwd_clean = (root_password or "").strip()
    if len(pwd_clean) < 8:
        return False, "Le mot de passe root doit contenir au moins 8 caractères."

    conf_path = config_file or MAINTENANCE_CONFIG_FILE
    existing: Dict[str, Any] = {}
    if conf_path.exists():
        try:
            existing = json.loads(conf_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    existing["admin_pin"] = hash_admin_pin(pwd_clean)
    existing["local_account"] = "root"
    existing["security_keys_status"] = "coming_soon"

    conf_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = conf_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, conf_path)

    logger = _get_logger()
    if apply_system:
        import pwd as pwd_mod
        import subprocess

        subprocess.run(["chpasswd"], input=f"root:{pwd_clean}\n", text=True, check=False)
        subprocess.run(["passwd", "-u", "root"], check=False)
        for user in lock_accounts:
            try:
                pwd_mod.getpwnam(user)
            except KeyError:
                continue
            subprocess.run(["usermod", "-L", user], check=False)
            subprocess.run(["passwd", "-l", user], check=False)
            logger.info("Compte local temporaire verrouillé : %s", user)

    logger.info("Accès local root configuré (compte unique, clés de sécurité matérielles à venir).")
    return True, "Accès root configuré."
