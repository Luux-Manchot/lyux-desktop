import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
ENROLL_DIR = ROOT / "lyux-desktop" / "applications" / "enrollment"


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


discovery = _load("discovery", ENROLL_DIR / "src" / "discovery.py")
enrollment_client = _load("enrollment_client", ENROLL_DIR / "src" / "enrollment_client.py")
api_main = _load("lyux_server_api_main", ROOT / "lyux-server" / "lyux-server-api" / "src" / "main.py")


class _TestClientAdapter:
    """Adapte starlette.testclient.TestClient à l'interface requests.* pour les tests hors réseau."""

    def __init__(self, tc: TestClient):
        self.tc = tc

    def get(self, url: str, timeout=None, **kwargs):
        path = "/" + url.split("://", 1)[-1].split("/", 1)[1] if "://" in url else url
        return self.tc.get(path)

    def post(self, url: str, json=None, timeout=None, **kwargs):
        path = "/" + url.split("://", 1)[-1].split("/", 1)[1] if "://" in url else url
        return self.tc.post(path, json=json)


@pytest.fixture
def isolated_client_env(tmp_path, monkeypatch):
    state_file = tmp_path / "enrollment-state.json"
    enrolled_file = tmp_path / "enrolled.json"
    fb_flag = tmp_path / "first-boot.flag"
    cid_file = tmp_path / "client-id"
    log_file = tmp_path / "lyux-oobe.log"
    fb_flag.write_text("", encoding="utf-8")

    monkeypatch.setattr(enrollment_client, "STATE_FILE", state_file)
    monkeypatch.setattr(enrollment_client, "ENROLLED_FILE", enrolled_file)
    monkeypatch.setattr(enrollment_client, "FIRST_BOOT_FLAG", fb_flag)
    monkeypatch.setattr(enrollment_client, "CLIENT_ID_FILE", cid_file)
    monkeypatch.setattr(enrollment_client, "OOBE_LOG_FILE", log_file)
    monkeypatch.setenv("LYUX_STATIC_CONF", str(tmp_path / "network-static.conf"))

    # Sauvegarder et restaurer l'état en mémoire de l'API
    orig_machines = dict(api_main.ENROLLED_MACHINES)
    orig_enabled = api_main.SYSTEM_SETTINGS.get("enrollment_enabled", True)
    api_main.SYSTEM_SETTINGS["enrollment_enabled"] = True

    yield {
        "state_file": state_file,
        "enrolled_file": enrolled_file,
        "fb_flag": fb_flag,
        "cid_file": cid_file,
        "log_file": log_file,
        "tmp_path": tmp_path,
    }

    api_main.ENROLLED_MACHINES.clear()
    api_main.ENROLLED_MACHINES.update(orig_machines)
    api_main.SYSTEM_SETTINGS["enrollment_enabled"] = orig_enabled


class TestSystemdAndNetworkScripts:
    def test_systemd_unit_waits_network_and_launches_xinit_before_sddm(self):
        unit = (ENROLL_DIR / "systemd" / "lyux-enrollment.service").read_text(encoding="utf-8")
        assert "After=network-online.target" in unit
        assert "Wants=network-online.target" in unit
        assert "Before=display-manager.service sddm.service" in unit
        assert "ConditionPathExists=/etc/lyux/first-boot.flag" in unit
        assert "/usr/bin/xinit" in unit
        assert "lyux-oobe-session.sh" in unit
        assert "src/oobe_gui.py" in unit

    def test_x11_session_wrapper_sets_xcb_and_exit_on_enroll(self):
        sh = (ENROLL_DIR / "scripts" / "lyux-oobe-session.sh").read_text(encoding="utf-8")
        assert "QT_QPA_PLATFORM=xcb" in sh
        assert "LYUX_OOBE_EXIT_ON_ENROLL=1" in sh
        assert "oobe_gui.py" in sh

    def test_net_setup_has_no_hardcoded_school_ip(self):
        sh = (ENROLL_DIR / "scripts" / "lyux-net-setup.sh").read_text(encoding="utf-8")
        assert "192.168.10." not in sh
        assert "192.168.100." not in sh
        assert "dhclient" in sh
        assert "first-boot.flag" not in sh


class TestDiscoveryAndValidation:
    def test_no_hardcoded_school_ips_in_discovery(self):
        urls = discovery.get_candidate_server_urls()
        for u in urls:
            assert "192.168.10.1" not in u
            assert "192.168.100.10" not in u
            assert "serveur.lyux.lan" not in u

    def test_validate_server_url_rejects_arbitrary_paths_and_schemes(self):
        assert discovery.validate_server_url("http://10.0.2.2:8000")[0] is True
        assert discovery.validate_server_url("https://lyux.example.local:8443")[0] is True
        assert discovery.validate_server_url("ftp://lyux.local")[0] is False
        assert discovery.validate_server_url("http://lyux.local/evil.sh")[0] is False
        assert discovery.validate_server_url("http://lyux.local?cmd=rm")[0] is False
        assert discovery.validate_server_url("")[0] is False

    def test_probe_distinguishes_unreachable_corrupt_and_unknown_version(self):
        with patch.object(discovery.requests, "get", side_effect=discovery.requests.ConnectionError("refused")):
            st, _ = discovery.probe_server_health("http://10.0.2.2:8000")
            assert st == "server-unreachable"

        bad_json_resp = MagicMock(status_code=200)
        bad_json_resp.json.side_effect = ValueError("corrupt")
        with patch.object(discovery.requests, "get", return_value=bad_json_resp):
            st, _ = discovery.probe_server_health("http://10.0.2.2:8000")
            assert st == "api-error"

        bad_ver_resp = MagicMock(status_code=200)
        bad_ver_resp.json.return_value = {"status": "ok", "api_version": "99"}
        with patch.object(discovery.requests, "get", return_value=bad_ver_resp):
            st, _ = discovery.probe_server_health("http://10.0.2.2:8000")
            assert st == "api-error"


class TestEnrollmentStateAndIdempotency:
    def test_network_error_state_keeps_first_boot_and_writes_no_enrolled_file(self, isolated_client_env):
        with patch.object(enrollment_client, "check_network_ready", return_value=(False, [])):
            res = enrollment_client.inspect_server("http://10.0.2.2:8000")
            assert res["state"] == "network-error"
        assert isolated_client_env["fb_flag"].exists()
        assert not isolated_client_env["enrolled_file"].exists()

    def test_locked_server_returns_awaiting_authorization_and_blocks_enroll(self, isolated_client_env):
        adapter = _TestClientAdapter(TestClient(api_main.app))
        api_main.SYSTEM_SETTINGS["enrollment_enabled"] = False
        with patch.object(enrollment_client, "check_network_ready", return_value=(True, ["eth0"])), \
             patch.object(discovery, "requests", adapter), \
             patch.object(enrollment_client, "requests", adapter):
            insp = enrollment_client.inspect_server("http://testserver:8000")
            assert insp["state"] == "awaiting-authorization"

            res = enrollment_client.perform_enrollment(
                "http://testserver:8000", "BAT-C", "C14", "C14-PC99", "eleve",
                apply_system_changes=False,
            )
            assert res["ok"] is False
            assert res["state"] == "awaiting-authorization"
        assert isolated_client_env["fb_flag"].exists()
        assert not isolated_client_env["enrolled_file"].exists()

    def test_invalid_building_room_role_rejected_without_enrolled_file(self, isolated_client_env):
        adapter = _TestClientAdapter(TestClient(api_main.app))
        with patch.object(enrollment_client, "check_network_ready", return_value=(True, ["eth0"])), \
             patch.object(enrollment_client, "requests", adapter):
            for b, r, role in [("BAT-NOPE", "C14", "eleve"), ("BAT-C", "NOPE", "eleve"), ("BAT-C", "C14", "hacker")]:
                res = enrollment_client.perform_enrollment(
                    "http://testserver:8000", b, r, "C14-PC88", role,
                    apply_system_changes=False,
                )
                assert res["ok"] is False
        assert not isolated_client_env["enrolled_file"].exists()
        assert isolated_client_env["fb_flag"].exists()

    def test_idempotent_replay_and_resume_creates_single_machine(self, isolated_client_env):
        adapter = _TestClientAdapter(TestClient(api_main.app))
        initial_count = len(api_main.ENROLLED_MACHINES)
        with patch.object(enrollment_client, "check_network_ready", return_value=(True, ["eth0"])), \
             patch.object(discovery, "requests", adapter), \
             patch.object(enrollment_client, "requests", adapter):
            res1 = enrollment_client.perform_enrollment(
                "http://testserver:8000", "BAT-C", "C14", "C14-PC77", "eleve",
                apply_system_changes=False,
            )
            assert res1["ok"] is True
            assert res1["idempotent"] is False
            assert res1["signature"]
            assert len(api_main.ENROLLED_MACHINES) == initial_count + 1
            assert isolated_client_env["enrolled_file"].exists()
            assert not isolated_client_env["fb_flag"].exists()

            # Rejeu de la même demande : aucun doublon créé
            res2 = enrollment_client.perform_enrollment(
                "http://testserver:8000", "BAT-C", "C14", "C14-PC77", "eleve",
                apply_system_changes=False,
            )
            assert res2["ok"] is True
            assert res2["idempotent"] is True
            assert len(api_main.ENROLLED_MACHINES) == initial_count + 1

            # Reprise après reboot via inspect_server
            insp = enrollment_client.inspect_server("http://testserver:8000")
            assert insp["state"] == "enrolled"
            assert insp["machine"]["hostname"] == "C14-PC77"

    def test_static_network_validation(self, isolated_client_env):
        ok, _ = enrollment_client.configure_static_network("eth0", "10.0.2.15/24", "10.0.2.2", "10.0.2.3")
        assert ok is True
        bad, _ = enrollment_client.configure_static_network("eth0;rm", "not-an-ip", "10.0.2.2")
        assert bad is False
        assert isolated_client_env["fb_flag"].exists()

    def test_keyboard_layout_validation_and_ui_light_theme(self):
        ok, msg = enrollment_client.apply_keyboard_layout("fr")
        assert ok is True
        assert "FR" in msg
        bad, _ = enrollment_client.apply_keyboard_layout("invalid-kbd")
        assert bad is False

        gui = (ENROLL_DIR / "src" / "oobe_gui.py").read_text(encoding="utf-8")
        assert "LogoPlaceholder" in gui
        assert '"LOGO"' in gui
        assert "lang_combo" not in gui
        assert "role_combo" not in gui
        assert "apply_keyboard_layout" in gui
        assert "hostname_input.setReadOnly(True)" not in gui
        assert "/api/v1/enroll/check-hostname" in gui
        assert "#F1F5F9" in gui
        for emoji in ("🐧", "🌐", "🔍", "🟢", "🔴", "🚀"):
            assert emoji not in gui
