import datetime
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PM_PATH = ROOT / "lyux-desktop" / "applications" / "enrollment" / "src" / "profile_manifest.py"
PT_PATH = ROOT / "lyux-server" / "lyux-server-api" / "src" / "profile_trust.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pm = _load("profile_manifest", PM_PATH)
pt = _load("profile_trust", PT_PATH)


def _make_signed_manifest(km, *, profile_id="nsi", content=b'{"theme":"orchis"}', url=None, debian="13"):
    now = datetime.datetime.now(datetime.timezone.utc)
    m = {
        "schema": "lyux-profile-manifest",
        "schema_version": 1,
        "profile_id": profile_id,
        "profile_version": "2026.11.1",
        "issued_at": (now - datetime.timedelta(minutes=2)).isoformat(timespec="seconds"),
        "expires_at": (now + datetime.timedelta(days=5)).isoformat(timespec="seconds"),
        "scope": {"building_id": "BAT-C", "room_id": "C14", "role": "eleve"},
        "artifacts": [{
            "id": "art-cfg",
            "type": "config",
            "name": f"{profile_id}.json",
            "url": url or f"https://github.com/Luux-Manchot/lyux-desktop/releases/download/v1.0.0/{profile_id}.json",
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }],
        "compatibility": {"debian": debian, "desktop": "plasma6-x11", "lyux_client_min": "1.0.0"},
    }
    sig, kid = km.sign_manifest(m)
    m["signature"] = sig
    return m, kid


def test_client_apply_valid_manifest_and_rollback_on_corrupt_download(tmp_path):
    km = pt.Ed25519KeyManager(keys_dir=tmp_path / "keys")
    pub_keys = {k["key_id"]: k["public_key_pem"] for k in km.get_public_bundle()["keys"]}

    state_file = tmp_path / "profile-state.json"
    active_dir = tmp_path / "active"
    backup_dir = tmp_path / "backup"
    scope = {"building_id": "BAT-C", "room_id": "C14", "role": "eleve"}

    payload_v1 = b'{"profile":"standard","kiosk":true}'
    m1, kid1 = _make_signed_manifest(km, profile_id="standard", content=payload_v1)

    res1 = pm.apply_verified_manifest(
        m1, pub_keys, expected_scope=scope, key_id=kid1,
        downloader=lambda url, dest: dest.write_bytes(payload_v1),
        state_file=state_file, active_dir=active_dir, backup_dir=backup_dir,
    )
    assert res1["ok"] is True
    assert (active_dir / "standard.json").read_bytes() == payload_v1

    # Deuxième déploiement avec téléchargement corrompu (SHA-256 incorrect) -> rollback automatique vers standard
    payload_v2 = b'{"profile":"nsi","kiosk":true}'
    m2, kid2 = _make_signed_manifest(km, profile_id="nsi", content=payload_v2)

    res2 = pm.apply_verified_manifest(
        m2, pub_keys, expected_scope=scope, key_id=kid2,
        downloader=lambda url, dest: dest.write_bytes(b"CORRUPTED_BYTES"),
        state_file=state_file, active_dir=active_dir, backup_dir=backup_dir,
    )
    assert res2["ok"] is False
    assert res2["rolled_back"] is True
    assert pm.load_profile_state(state_file)["current_profile"] == "standard"
    assert (active_dir / "standard.json").read_bytes() == payload_v1


def test_client_rejects_bad_signature_compat_unapproved_url_and_interrupted_dl(tmp_path):
    km = pt.Ed25519KeyManager(keys_dir=tmp_path / "keys")
    pub_keys = {k["key_id"]: k["public_key_pem"] for k in km.get_public_bundle()["keys"]}
    state_file = tmp_path / "profile-state.json"
    active_dir = tmp_path / "active"
    backup_dir = tmp_path / "backup"

    # 1. Mauvaise signature
    m_bad_sig, _ = _make_signed_manifest(km)
    m_bad_sig["signature"] = "invalid"
    r = pm.apply_verified_manifest(m_bad_sig, pub_keys, state_file=state_file, active_dir=active_dir, backup_dir=backup_dir)
    assert r["ok"] is False

    # 2. Compatibilité refusée (Debian 12)
    m_bad_deb, kid = _make_signed_manifest(km, debian="12")
    r = pm.apply_verified_manifest(m_bad_deb, pub_keys, key_id=kid, state_file=state_file, active_dir=active_dir, backup_dir=backup_dir)
    assert r["ok"] is False

    # 3. URL non approuvée
    m_bad_url, kid = _make_signed_manifest(km, url="http://untrusted.local/evil.sh")
    r = pm.apply_verified_manifest(m_bad_url, pub_keys, key_id=kid, state_file=state_file, active_dir=active_dir, backup_dir=backup_dir)
    assert r["ok"] is False

    # 4. Téléchargement interrompu (serveur coupé)
    m_ok, kid = _make_signed_manifest(km)
    def fail_dl(url, dest):
        raise ConnectionError("network cut")
    r = pm.apply_verified_manifest(m_ok, pub_keys, key_id=kid, downloader=fail_dl, state_file=state_file, active_dir=active_dir, backup_dir=backup_dir)
    assert r["ok"] is False
    assert not (active_dir / "nsi.json").exists()
