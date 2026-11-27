import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "applications" / "enrollment" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def test_pam_auth_rejects_cleartext_http_and_pin_mismatch(tmp_path, monkeypatch):
    import pam_auth_hook

    # 1. HTTP non-loopback refusé
    state_http = tmp_path / "state-http.json"
    state_http.write_text(json.dumps({"server_url": "http://192.168.10.1:8000"}), encoding="utf-8")

    called = False

    def _fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("urlopen ne doit pas être appelé en HTTP clair")

    monkeypatch.setattr(pam_auth_hook, "urlopen", _fail_if_called)
    ok, reason = pam_auth_hook.authenticate_desktop_user(
        "camille.dupont", "Secret123!", state_path=state_http
    )
    assert ok is False
    assert reason == "insecure-transport"
    assert called is False

    # 2. HTTP loopback autorisé uniquement pour dev
    assert pam_auth_hook._is_secure_auth_url("http://127.0.0.1:8000") is True
    assert pam_auth_hook._is_secure_auth_url("https://api.lyux.lan") is True

    # 3. Empreinte TLS divergente doit échouer fermé
    state_pin = tmp_path / "state-pin.json"
    state_pin.write_text(
        json.dumps({"server_url": "https://api.lyux.lan", "tls_cert_sha256": "a" * 64}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pam_auth_hook, "_verify_pinned_cert", lambda *args, **kwargs: False)
    ok_pin, reason_pin = pam_auth_hook.authenticate_desktop_user(
        "camille.dupont", "Secret123!", state_path=state_pin
    )
    assert ok_pin is False
    assert reason_pin == "tls-pin-mismatch"


def test_pam_hook_excludes_admin_validates_user_uid_and_avoids_sufficient(tmp_path, monkeypatch):
    import enrollment_client
    import pam_auth_hook

    # 1. common-auth ne doit jamais utiliser 'sufficient' et doit créer une sauvegarde
    pam_auth = tmp_path / "common-auth"
    pam_auth.write_text("auth\t[success=1 default=ignore]\tpam_unix.so nullok\n", encoding="utf-8")
    changed = enrollment_client._install_pam_auth_hook(pam_auth, "/opt/lyux/apps/enrollment/scripts/lyux-pam-auth.sh")
    assert changed is True
    updated = pam_auth.read_text(encoding="utf-8")
    assert "sufficient" not in updated
    assert "[success=ok default=ignore]" in updated
    assert (tmp_path / "common-auth.lyux.bak").exists()

    # 2. lyux-admin et noms hostiles refusés avant tout appel réseau
    state_https = tmp_path / "state-https.json"
    state_https.write_text(json.dumps({"server_url": "https://api.lyux.lan"}), encoding="utf-8")
    for bad_user in ("lyux-admin", "root"):
        ok, reason = pam_auth_hook.authenticate_desktop_user(bad_user, "Secret123!", state_path=state_https)
        assert ok is False
        assert reason == "local-fallback"

    for hostile_user in ("../evil", "user:0", "user\nbad", "ADMIN"):
        ok, reason = pam_auth_hook.authenticate_desktop_user(hostile_user, "Secret123!", state_path=state_https)
        assert ok is False
        assert reason == "invalid-username"

    # 3. UID hors [1000, 60000] refusé
    class _FakeUidResp:
        def __init__(self, uid_val):
            self.uid_val = uid_val

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"authenticated": True, "uid": self.uid_val}).encode("utf-8")

    monkeypatch.setattr(pam_auth_hook, "sync_nss_users", lambda **kwargs: 1)
    for bad_uid in (0, 500, 60001):
        monkeypatch.setattr(pam_auth_hook, "urlopen", lambda req, timeout=5.0, u=bad_uid: _FakeUidResp(u))
        ok_u, reason_u = pam_auth_hook.authenticate_desktop_user(
            "camille.dupont", "Secret123!", state_path=state_https
        )
        assert ok_u is False
        assert reason_u == "invalid-uid"


def test_manifest_fails_closed_without_local_trusted_keys_and_rejects_unknown_key(tmp_path):
    import datetime
    import profile_applier
    import profile_manifest

    # 1. Sans trousseau local, sync_and_apply_profile échoue fermé sans interroger l'API
    missing_keys = tmp_path / "missing-keys.json"
    res = profile_applier.sync_and_apply_profile(
        server_url="https://api.lyux.lan",
        client_id="c1",
        hostname="PC1",
        building_id="BAT-C",
        room_id="C14",
        role="eleve",
        trusted_keys_file=missing_keys,
    )
    assert res["ok"] is False
    assert "absent" in res["detail"].lower()

    # 2. Manifeste signé avec une clé inconnue doit être refusé
    now = datetime.datetime.now(datetime.timezone.utc)
    manifest = {
        "schema": "lyux-profile-manifest",
        "schema_version": 1,
        "profile_id": "standard",
        "profile_version": "1.0.0",
        "issued_at": now.isoformat(),
        "expires_at": (now + datetime.timedelta(hours=1)).isoformat(),
        "scope": {"building_id": "BAT-C", "room_id": "C14", "role": "eleve"},
        "compatibility": {"debian": "13", "desktop": "plasma6-x11"},
        "artifacts": [
            {
                "name": "lyux-profile-standard.deb",
                "type": "deb",
                "package": "lyux-profile-standard",
                "url": "https://lyux-server/pkg.deb",
                "sha256": "a" * 64,
                "size": 123,
            }
        ],
        "signature": "invalid-sig",
    }
    ok, msg = profile_manifest.validate_manifest(
        manifest,
        {"known-key-1": "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----"},
        key_id="unknown-key-999",
        now=now,
    )
    assert ok is False
    assert "inconnue" in msg.lower()


def test_nss_extrausers_rejects_line_injection_uid0_and_bad_shells(tmp_path):
    import nss_user_sync

    extra_dir = tmp_path / "extrausers"
    hostile_users = [
        {"username": "evil\nroot2:x:0:0::/root:/bin/bash", "uid": 1001, "shell": "/bin/bash"},
        {"username": "backdoor", "uid": 0, "gid": 0, "shell": "/bin/bash"},
        {"username": "lyux-admin", "uid": 1002, "shell": "/bin/bash"},
        {"username": "bad.shell", "uid": 1003, "shell": "/tmp/evil.sh"},
        {"username": "bad.disp", "uid": 1004, "display_name": "Evil\nroot3:x:0:0::/:/bin/sh", "shell": "/bin/bash"},
        {
            "username": "alice.prof",
            "uid": 1050,
            "gid": 1050,
            "display_name": "Alice Prof",
            "home": "/etc/shadow",
            "shell": "/bin/bash",
        },
    ]
    count = nss_user_sync.write_extrausers_files(hostile_users, extrausers_dir=extra_dir)
    assert count == 1
    passwd_text = (extra_dir / "passwd").read_text(encoding="utf-8")
    assert passwd_text.strip() == "alice.prof:x:1050:1050:Alice Prof:/home/alice.prof:/bin/bash"
    assert "root2" not in passwd_text
    assert "backdoor" not in passwd_text
    assert "lyux-admin" not in passwd_text
    assert "/tmp/evil.sh" not in passwd_text


def test_deb_and_flatpak_allowlist_cannot_be_bypassed_when_package_missing():
    import datetime
    import profile_manifest

    now = datetime.datetime.now(datetime.timezone.utc)
    base_manifest = {
        "schema": "lyux-profile-manifest",
        "schema_version": 1,
        "profile_id": "standard",
        "profile_version": "1.0.0",
        "issued_at": now.isoformat(),
        "expires_at": (now + datetime.timedelta(hours=1)).isoformat(),
        "scope": {"building_id": "BAT-C", "room_id": "C14", "role": "eleve"},
        "compatibility": {"debian": "13", "desktop": "plasma6-x11"},
        "artifacts": [
            {
                "name": "evil.deb",
                "type": "deb",
                "url": "https://lyux-server/evil.deb",
                "sha256": "a" * 64,
                "size": 123,
            }
        ],
        "signature": "dummy",
    }
    keys = {"k1": "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----"}
    ok, msg = profile_manifest.validate_manifest(base_manifest, keys, key_id="k1", now=now)
    assert ok is False
    assert "catalogue" in msg.lower() or "manquant" in msg.lower()

    base_manifest["artifacts"] = [
        {
            "name": "evil.flatpakref",
            "type": "flatpak",
            "url": "https://lyux-server/evil.flatpakref",
            "sha256": "b" * 64,
            "size": 123,
        }
    ]
    ok_fp, msg_fp = profile_manifest.validate_manifest(base_manifest, keys, key_id="k1", now=now)
    assert ok_fp is False
    assert "catalogue" in msg_fp.lower() or "manquant" in msg_fp.lower()
