import sys
from pathlib import Path
from unittest.mock import patch

SRC_DIR = Path(__file__).resolve().parents[1] / "applications" / "enrollment" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app_policy_sync import apply_role_app_restrictions, is_role_allowed_for_app, sync_client_packages  # noqa: E402


def test_sync_client_packages_falls_back_to_direct_internet_when_proxy_fails():
    payload = {
        "cache_proxy": "http://192.168.10.1:3142",
        "peer_caches": ["http://192.168.10.50:3142"],
        "fallback_direct": True,
        "apps": [{"package": "inkscape", "deployed": True, "format": "Paquet .deb"}],
    }
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = ""
        if cmd[:2] == ["dpkg-query", "-W"]:
            R.returncode = 1
            return R()
        if any("Proxy=http://" in str(c) for c in cmd):
            R.returncode = 1
            return R()
        return R()

    with patch("app_policy_sync.fetch_client_apps", return_value=payload), \
         patch("app_policy_sync._pick_fastest_cache_proxy", return_value="http://192.168.10.50:3142"), \
         patch("app_policy_sync.subprocess.run", side_effect=fake_run):
        installed = sync_client_packages("http://192.168.10.1:8000")

    assert installed == ["inkscape"]
    assert any("Acquire::http::Proxy=false" in c for c in calls)


def test_is_role_allowed_for_app_aliases_and_admin():
    app_prof_only = {"package": "veyon-master", "allowed_roles": ["prof"]}
    assert is_role_allowed_for_app(app_prof_only, "prof") is True
    assert is_role_allowed_for_app(app_prof_only, "eleve") is False
    assert is_role_allowed_for_app(app_prof_only, "admin") is True

    app_groups_legacy = {"package": "audacity", "allowed_groups": ["eleves", "enseignants"]}
    assert is_role_allowed_for_app(app_groups_legacy, "eleve") is True
    assert is_role_allowed_for_app(app_groups_legacy, "prof") is True


def test_apply_role_app_restrictions_hides_and_unhides(tmp_path):
    sys_apps = tmp_path / "sys_apps"
    sys_apps.mkdir()
    (sys_apps / "veyon-master.desktop").write_text("[Desktop Entry]\nName=Veyon\n", encoding="utf-8")

    home_dir = tmp_path / "home" / "lucas.martin"
    home_dir.mkdir(parents=True)

    payload_eleve = {
        "apps": [
            {"id": "veyon-master", "name": "Veyon Master", "package": "veyon-master", "authorized": False},
            {"id": "inkscape", "name": "Inkscape", "package": "inkscape", "authorized": True},
        ]
    }
    with patch("app_policy_sync.fetch_client_apps", return_value=payload_eleve):
        res = apply_role_app_restrictions(
            "http://127.0.0.1:8000", "lucas.martin", "eleve", home_dir, system_apps_dir=sys_apps
        )
    override = home_dir / ".local" / "share" / "applications" / "veyon-master.desktop"
    assert override.exists()
    assert "NoDisplay=true" in override.read_text(encoding="utf-8")
    assert "veyon-master.desktop" in res["hidden"]

    # Si l'utilisateur passe prof / autorisé, le masquage est retiré
    payload_prof = {
        "apps": [
            {"id": "veyon-master", "name": "Veyon Master", "package": "veyon-master", "authorized": True},
        ]
    }
    with patch("app_policy_sync.fetch_client_apps", return_value=payload_prof):
        res2 = apply_role_app_restrictions(
            "http://127.0.0.1:8000", "lucas.martin", "prof", home_dir, system_apps_dir=sys_apps
        )
    assert not override.exists()
    assert "veyon-master.desktop" in res2["unhidden"]
