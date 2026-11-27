import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "applications" / "enrollment" / "src"))

from session_sync import sync_delta_directory


def test_sync_delta_directory_copies_only_missing_or_newer_files(tmp_path):
    nas_home = tmp_path / "nas_home"
    local_home = tmp_path / "local_home"
    (nas_home / "Documents").mkdir(parents=True)
    (local_home / "Documents").mkdir(parents=True)

    f_same = nas_home / "Documents" / "cours.txt"
    f_same.write_text("v1", encoding="utf-8")
    l_same = local_home / "Documents" / "cours.txt"
    l_same.write_text("v1", encoding="utf-8")
    now = time.time() - 10
    os.utime(f_same, (now, now))
    os.utime(l_same, (now, now))

    f_new = nas_home / "Documents" / "tp_nouveau.py"
    f_new.write_text("print('ok')", encoding="utf-8")

    updated = sync_delta_directory(nas_home, local_home)
    assert "Documents\\tp_nouveau.py" in updated or "Documents/tp_nouveau.py" in updated
    assert "Documents\\cours.txt" not in updated and "Documents/cours.txt" not in updated
    assert (local_home / "Documents" / "tp_nouveau.py").read_text(encoding="utf-8") == "print('ok')"


def test_pam_session_hook_syncs_documents_and_kde_config_between_pcs(tmp_path):
    from pam_session_hook import handle_pam_event

    nas_home = tmp_path / "nas" / "lucas.martin"
    pc1_home = tmp_path / "pc1" / "lucas.martin"
    pc2_home = tmp_path / "pc2" / "lucas.martin"
    (nas_home / "Documents").mkdir(parents=True)
    (nas_home / ".config").mkdir(parents=True)
    (nas_home / ".config" / "plasma-org.kde.plasma.desktop-appletsrc").write_text("Image=lyux-ocean.png", encoding="utf-8")

    # PC 1 : ouverture de session -> récupère le fond d'écran depuis le NAS
    assert handle_pam_event("open_session", "lucas.martin", local_home=pc1_home, nas_home=nas_home) == 0
    assert (pc1_home / ".config" / "plasma-org.kde.plasma.desktop-appletsrc").read_text(encoding="utf-8") == "Image=lyux-ocean.png"

    # PC 1 : l'utilisateur crée un document et ferme sa session -> poussé sur le NAS
    (pc1_home / "Documents" / "devoir.txt").write_text("mon devoir", encoding="utf-8")
    assert handle_pam_event("close_session", "lucas.martin", local_home=pc1_home, nas_home=nas_home) == 0
    assert (nas_home / "Documents" / "devoir.txt").read_text(encoding="utf-8") == "mon devoir"

    # PC 2 : ouverture de session -> retrouve le document ET le fond d'écran
    assert handle_pam_event("open_session", "lucas.martin", local_home=pc2_home, nas_home=nas_home) == 0
    assert (pc2_home / "Documents" / "devoir.txt").read_text(encoding="utf-8") == "mon devoir"
    assert (pc2_home / ".config" / "plasma-org.kde.plasma.desktop-appletsrc").read_text(encoding="utf-8") == "Image=lyux-ocean.png"


def test_nss_user_sync_writes_extrausers_and_nsswitch(tmp_path, monkeypatch):
    import json
    import nss_user_sync

    state_file = tmp_path / "enrollment-state.json"
    state_file.write_text(json.dumps({"server_url": "https://192.168.10.1:8000"}), encoding="utf-8")

    nsswitch = tmp_path / "nsswitch.conf"
    nsswitch.write_text("passwd: files systemd\ngroup: files systemd\nshadow: files\n", encoding="utf-8")
    extra_dir = tmp_path / "extrausers"

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "users": [
                    {
                        "username": "camille.dupont",
                        "uid": 10421,
                        "gid": 10421,
                        "display_name": "Camille Dupont",
                        "home": "/home/camille.dupont",
                        "shell": "/bin/bash",
                    }
                ]
            }).encode("utf-8")

    monkeypatch.setattr(nss_user_sync, "urlopen", lambda req, timeout=5.0: _FakeResp())
    count = nss_user_sync.sync_nss_users(state_path=state_file, extrausers_dir=extra_dir, nsswitch_path=nsswitch)
    assert count == 1

    assert "camille.dupont:x:10421:10421:Camille Dupont:/home/camille.dupont:/bin/bash" in (extra_dir / "passwd").read_text(encoding="utf-8")
    assert "camille.dupont:x:10421:" in (extra_dir / "group").read_text(encoding="utf-8")
    assert "camille.dupont:*:" in (extra_dir / "shadow").read_text(encoding="utf-8")
    nss_text = nsswitch.read_text(encoding="utf-8")
    assert "passwd: files systemd extrausers" in nss_text
    assert "group: files systemd extrausers" in nss_text
    assert "shadow: files extrausers" in nss_text


def test_pam_auth_hook_authenticates_and_creates_home(tmp_path, monkeypatch):
    import json
    import pam_auth_hook

    state_file = tmp_path / "enrollment-state.json"
    state_file.write_text(json.dumps({"server_url": "https://192.168.10.1:8000"}), encoding="utf-8")
    extra_dir = tmp_path / "extrausers"
    home_root = tmp_path / "home"

    # root doit toujours retomber sur pam_unix local
    ok_root, reason_root = pam_auth_hook.authenticate_desktop_user("root", "secret", state_path=state_file)
    assert ok_root is False
    assert reason_root == "local-fallback"

    class _FakeAuthResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "authenticated": True,
                "username": "camille.dupont",
                "uid": 10421,
                "effective_role": "eleve",
            }).encode("utf-8")

    monkeypatch.setattr(pam_auth_hook, "urlopen", lambda req, timeout=5.0: _FakeAuthResp())
    monkeypatch.setattr(pam_auth_hook, "sync_nss_users", lambda **kwargs: 1)

    ok, msg = pam_auth_hook.authenticate_desktop_user(
        "camille.dupont",
        "TestPassword2026!",
        state_path=state_file,
        extrausers_dir=extra_dir,
        home_root=home_root,
    )
    assert ok is True
    assert msg == "ok"
    assert (home_root / "camille.dupont").is_dir()
