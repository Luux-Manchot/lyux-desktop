"""
Tier 1: Feature Coverage (>=5 test cases per feature across all 24 inventoried features).
Chaque test vérifie de manière autoritative les spécifications définies dans PROJECT.md
et ORIGINAL_REQUEST.md sur les fichiers réels, schémas, scripts, configurations et endpoints.
"""

import os

import re

import csv

import xml.etree.ElementTree as ET

from pathlib import Path

import pytest

import yaml


class TestFeature12_CalamaresOEMInstaller:
    def test_systemd_enrollment_service_exists(self, paths):
        """12.1 Vérifie la présence du service systemd lyux-enrollment.service"""
        srv = paths["enrollment"] / "systemd" / "lyux-enrollment.service"
        assert srv.exists()
        content = srv.read_text(encoding="utf-8")
        assert "[Unit]" in content
        assert "ExecStart" in content

    def test_enrollment_service_enabled_in_preseed(self, preseed_iso_path):
        """12.2 Vérifie l'activation du service lyux-enrollment au premier boot dans preseed.cfg"""
        content = preseed_iso_path.read_text(encoding="utf-8")
        assert "systemctl enable lyux-enrollment.service" in content

    def test_hardware_fingerprint_module(self, paths):
        """12.3 Vérifie le module hardware.py pour l'inventaire matériel au premier boot"""
        hw_file = paths["enrollment"] / "src" / "hardware.py"
        assert hw_file.exists()
        content = hw_file.read_text(encoding="utf-8")
        assert "def get_hardware_fingerprint" in content

    def test_enroll_python_script_cli(self, paths):
        """12.4 Vérifie le script enroll.py de synchronisation avec l'API centrale"""
        enroll_file = paths["enrollment"] / "src" / "enroll.py"
        assert enroll_file.exists()
        content = enroll_file.read_text(encoding="utf-8")
        assert "api" in content.lower() or "requests" in content

    def test_oobe_gui_interface_exists(self, paths):
        """12.5 Vérifie la présence de l'interface graphique First-Boot (oobe_gui.py)"""
        oobe_file = paths["enrollment"] / "src" / "oobe_gui.py"
        assert oobe_file.exists()

    def test_oobe_service_launches_graphical_interface(self, paths):
        """Le premier démarrage lance la GUI au lieu du prompt CLI."""
        srv = paths["enrollment"] / "systemd" / "lyux-enrollment.service"
        content = srv.read_text(encoding="utf-8")
        assert "src/oobe_gui.py" in content
        assert "src/enroll.py" not in content

    def test_oobe_cannot_continue_when_server_is_unreachable(self, paths):
        """Bâtiment, salle et configuration locale restent bloqués hors ligne."""
        gui = (paths["enrollment"] / "src" / "oobe_gui.py").read_text(encoding="utf-8")
        cli = (paths["enrollment"] / "src" / "enroll.py").read_text(encoding="utf-8")
        assert "Mode simulation local" not in gui
        assert "vous pouvez quand même choisir" not in cli.lower()
        assert "    save_pending_config(" not in cli
