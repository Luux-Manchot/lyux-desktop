import sys

import os

import importlib.util

from pathlib import Path

import pytest

from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parents[2]

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    # Ajouter le dossier parent au sys.path temporairement pour les imports relatifs
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module

def _resolve(rel: str) -> Path:
    p = BASE_DIR / rel
    if p.exists():
        return p
    p_leg = BASE_DIR / "projects" / rel.split("/", 1)[-1]
    return p if p.exists() else p_leg

api_main = load_module("server_api_main", _resolve("lyux-server/lyux-server-api/src/main.py"))

role_detector = load_module("role_detector", _resolve("lyux-desktop/applications/welcome/src/role_detector.py"))

system_info = load_module("system_info", _resolve("lyux-desktop/applications/report/src/system_info.py"))

hardware = load_module("hardware", _resolve("lyux-desktop/applications/enrollment/src/hardware.py"))

client = TestClient(api_main.app)


class TestLyuXClientModules:
    def test_role_detector(self):
        info = role_detector.get_current_user_info()
        assert "username" in info
        assert "role" in info
        assert info["role"] in ["eleve", "enseignant", "viesco", "technicien"]

    def test_system_diagnostics(self):
        diag = system_info.collect_machine_diagnostics()
        assert "hostname" in diag
        assert "ram_usage" in diag
        assert "ip_address" in diag

    def test_hardware_fingerprint(self):
        hw = hardware.get_hardware_fingerprint()
        assert "mac_address" in hw
        assert "serial_number" in hw
        assert hw["ram_mb"] > 0
