from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "applications" / "enrollment" / "src"
sys.path.insert(0, str(SRC_DIR))

import update_policy_sync as ups  # noqa: E402


def test_get_local_debian_version(tmp_path: Path):
    deb_ver = tmp_path / "debian_version"
    deb_ver.write_text("13.1\n", encoding="utf-8")
    assert ups.get_local_debian_version(debian_version_path=deb_ver) == "13.1"


def test_write_and_remove_apt_pinning(tmp_path: Path):
    prefs = tmp_path / "lyux-policy.pref"
    written = ups.write_apt_pinning(
        {
            "auto_enforce": True,
            "apt_preferences": "Package: lyux-desktop-core\nPin: version 0.6.2*\nPin-Priority: 1001",
        },
        prefs_path=prefs,
    )
    assert written is True
    assert "Pin-Priority: 1001" in prefs.read_text(encoding="utf-8")

    removed = ups.write_apt_pinning({"auto_enforce": False}, prefs_path=prefs)
    assert removed is False
    assert not prefs.exists()
