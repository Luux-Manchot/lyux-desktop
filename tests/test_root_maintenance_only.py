import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "applications" / "enrollment" / "src"))

from maintenance import configure_root_only_access, verify_admin_pin


def test_configure_root_only_access_hashes_password_and_marks_keys_coming_soon(tmp_path):
    conf = tmp_path / "maintenance-keys.json"

    ok_short, _ = configure_root_only_access("1234", config_file=conf, apply_system=False)
    assert ok_short is False

    ok, msg = configure_root_only_access("RootSecours2026!", config_file=conf, apply_system=False)
    assert ok is True, msg
    data = json.loads(conf.read_text(encoding="utf-8"))
    assert data["local_account"] == "root"
    assert data["security_keys_status"] == "coming_soon"
    assert "RootSecours2026!" not in conf.read_text(encoding="utf-8")
    assert verify_admin_pin("RootSecours2026!", data["admin_pin"]) is True
    assert verify_admin_pin("mauvais", data["admin_pin"]) is False
