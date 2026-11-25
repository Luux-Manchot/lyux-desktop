import base64
import datetime
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[2]
ENROLL_SRC = ROOT / "lyux-desktop" / "applications" / "enrollment" / "src"
PT_PATH = ROOT / "lyux-server" / "lyux-server-api" / "src" / "profile_trust.py"


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


pt = _load("profile_trust", PT_PATH)
maint = _load("maintenance", ENROLL_SRC / "maintenance.py")


def _sign_usb_token(km, *, token_id="usb-admin-1", usb_serial="SERIAL-001", days_delta=7):
    now = datetime.datetime.now(datetime.timezone.utc)
    tok = {
        "token_id": token_id,
        "usb_serial": usb_serial,
        "issued_at": (now - datetime.timedelta(minutes=5)).isoformat(timespec="seconds"),
        "expires_at": (now + datetime.timedelta(days=days_delta)).isoformat(timespec="seconds"),
    }
    kr = km._load_keyring()
    priv = serialization.load_pem_private_key(km._priv_path(kr["active_key_id"]).read_bytes(), password=None)
    canonical = json.dumps(tok, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    tok["signature"] = base64.urlsafe_b64encode(priv.sign(canonical)).decode("ascii").rstrip("=")
    return tok


def test_maintenance_usb_valid_duplicated_expired_revoked_and_actions(tmp_path):
    km = pt.Ed25519KeyManager(keys_dir=tmp_path / "keys")
    pub_pem = km.get_public_bundle()["keys"][0]["public_key_pem"]
    other_km = pt.Ed25519KeyManager(keys_dir=tmp_path / "other_keys")
    other_tok = _sign_usb_token(other_km, usb_serial="SERIAL-001")

    session = maint.MaintenanceSession(public_key_pem=pub_pem, revoked_ids=["usb-revoked"])

    # Hors maintenance : toute action privilégiée est refusée
    with pytest.raises(PermissionError):
        session.repair_server_url("http://10.0.2.2:8000")

    # Mauvaise clé (signée par autre autorité)
    ok, _ = session.authenticate_usb(other_tok, "SERIAL-001")
    assert ok is False
    assert session.active is False

    # Clé dupliquée sur une autre clé USB (numéro de série différent)
    valid_tok = _sign_usb_token(km, token_id="usb-admin-1", usb_serial="SERIAL-001")
    ok, _ = session.authenticate_usb(valid_tok, "CLONED-SERIAL-999")
    assert ok is False

    # Jeton expiré
    exp_tok = _sign_usb_token(km, token_id="usb-exp", usb_serial="SERIAL-001", days_delta=-1)
    ok, _ = session.authenticate_usb(exp_tok, "SERIAL-001")
    assert ok is False

    # Jeton révoqué
    rev_tok = _sign_usb_token(km, token_id="usb-revoked", usb_serial="SERIAL-001")
    ok, _ = session.authenticate_usb(rev_tok, "SERIAL-001")
    assert ok is False

    # Clé valide -> déverrouillage, réparation IP et ré-enrôlement
    ok, _ = session.authenticate_usb(valid_tok, "SERIAL-001")
    assert ok is True
    state_file = tmp_path / "state.json"
    fb_flag = tmp_path / "first-boot.flag"
    ok_ip, norm_ip = session.repair_server_url("http://192.168.1.30:8000", state_file=state_file)
    assert ok_ip is True
    assert norm_ip == "http://192.168.1.30:8000"
    assert session.trigger_reenroll(first_boot_flag=fb_flag, state_file=state_file) is True
    assert fb_flag.exists()

    # Fermeture -> plus d'escalade possible
    session.deactivate()
    with pytest.raises(PermissionError):
        session.trigger_reenroll(first_boot_flag=fb_flag, state_file=state_file)


def test_maintenance_fido2_and_admin_pin(tmp_path):
    pin_rec = maint.hash_admin_pin("AdminSecours2026!")
    session = maint.MaintenanceSession(admin_pin_record=pin_rec, fido2_verifier=lambda h: h == "yubikey-1")
    assert session.authenticate_pin("wrong")[0] is False
    assert session.authenticate_pin("AdminSecours2026!")[0] is True
    session.deactivate()
    assert session.authenticate_fido2("wrong-key", False)[0] is False
    assert session.authenticate_fido2("yubikey-1", True)[0] is True
