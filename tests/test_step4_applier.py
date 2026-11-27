import datetime
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
ENROLL_SRC = ROOT / "lyux-desktop" / "applications" / "enrollment" / "src"
API_DIR = ROOT / "lyux-server" / "lyux-server-api" / "src"


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


class _Adapter:
    def __init__(self, tc: TestClient):
        self.tc = tc

    def get(self, url: str, params=None, timeout=None, stream=False):
        path = "/" + url.split("://", 1)[-1].split("/", 1)[1] if "://" in url else url
        return self.tc.get(path, params=params)

    def post(self, url: str, json=None, timeout=None):
        path = "/" + url.split("://", 1)[-1].split("/", 1)[1] if "://" in url else url
        return self.tc.post(path, json=json)


@pytest.fixture
def step4_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LYUX_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LYUX_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("LYUX_APT_REPO_DIR", str(tmp_path / "apt-repo"))
    monkeypatch.setenv("LYUX_APPROVED_SOURCES", "http://lyux-server,https://github.com/Luux-Manchot/")

    for m in ("main", "admin_routes", "release_registry", "profile_trust", "apt_repo"):
        sys.modules.pop(m, None)
    sys.path.insert(0, str(API_DIR))
    main_mod = _load("main", API_DIR / "main.py")
    pm = _load("profile_manifest", ENROLL_SRC / "profile_manifest.py")
    pa = _load("profile_applier", ENROLL_SRC / "profile_applier.py")
    return main_mod, pm, pa, TestClient(main_mod.app), tmp_path


def test_sync_and_apply_pilot_deb_profile_idempotent_and_rollback(step4_env):
    main_mod, pm, pa, tc, tmp_path = step4_env
    adapter = _Adapter(tc)

    # 1. Enrôler un poste dans BAT-C / C14
    r_enr = tc.post("/api/v1/enroll/client-enroll", json={
        "client_id": "lyux-step4-01",
        "hostname": "C14-PC40",
        "building_id": "BAT-C",
        "room_id": "C14",
        "role": "eleve",
    })
    assert r_enr.status_code == 200

    # 2. Publier un manifeste contenant le paquet .deb pilote réel du dépôt APT
    deb_bytes = (main_mod.APT_REPOSITORY.repo_dir / "pool" / "main" / "lyux-profile-standard_1.0.0_all.deb").read_bytes()
    km = main_mod.RELEASE_REGISTRY.key_manager
    ok_d, rel = main_mod.RELEASE_REGISTRY.create_draft(
        version="1.0.1",
        profile_id="nsi",
        artifacts=[{
            "id": "lyux-profile-standard",
            "type": "deb",
            "package": "lyux-profile-standard",
            "name": "lyux-profile-standard_1.0.0_all.deb",
            "url": "http://lyux-server:8000/api/v1/apt-repo/pool/main/lyux-profile-standard_1.0.0_all.deb",
            "sha256": hashlib.sha256(deb_bytes).hexdigest(),
            "size": len(deb_bytes),
            "version": "1.0.0",
        }],
    )
    assert ok_d is True
    main_mod.RELEASE_REGISTRY.get_release(rel["id"])["artifacts"][0]["package"] = "lyux-profile-standard"
    assert main_mod.RELEASE_REGISTRY.sign_release(rel["id"])[0] is True
    assert main_mod.RELEASE_REGISTRY.publish_release(rel["id"])[0] is True

    state_file = tmp_path / "profile-state.json"
    active_dir = tmp_path / "active"
    backup_dir = tmp_path / "backup"
    sddm_dir = tmp_path / "sddm.conf.d"

    def dl_from_api(url, dest):
        path = "/" + url.split("://", 1)[-1].split("/", 1)[1]
        resp = tc.get(path)
        assert resp.status_code == 200
        dest.write_bytes(resp.content)

    trusted_keys_file = tmp_path / "trusted-public-keys.json"
    trusted_keys_file.write_text(json.dumps(tc.get("/api/v1/client/public-keys").json()), encoding="utf-8")

    with patch.object(pa, "requests", adapter):
        res1 = pa.sync_and_apply_profile(
            server_url="http://lyux-server:8000",
            client_id="lyux-step4-01",
            hostname="C14-PC40",
            building_id="BAT-C",
            room_id="C14",
            role="eleve",
            downloader=dl_from_api,
            deb_installer=lambda p: (True, "installed"),
            state_file=state_file,
            active_dir=active_dir,
            backup_dir=backup_dir,
            sddm_conf_dir=sddm_dir,
            trusted_keys_file=trusted_keys_file,
        )
        assert res1["ok"] is True
        assert res1["idempotent"] is False
        assert res1["installed_packages"]["lyux-profile-standard"] == "1.0.0"
        assert "DisplayServer=x11" in (sddm_dir / "99-lyux-theme.conf").read_text(encoding="utf-8")

        # Rejeu idempotent : ne réinstalle pas
        res2 = pa.sync_and_apply_profile(
            server_url="http://lyux-server:8000",
            client_id="lyux-step4-01",
            hostname="C14-PC40",
            building_id="BAT-C",
            room_id="C14",
            role="eleve",
            downloader=dl_from_api,
            deb_installer=lambda p: (True, "installed"),
            state_file=state_file,
            active_dir=active_dir,
            backup_dir=backup_dir,
            sddm_conf_dir=sddm_dir,
            trusted_keys_file=trusted_keys_file,
        )
        assert res2["ok"] is True
        assert res2["idempotent"] is True

        # Rapport enregistré sur le serveur
        reports = tc.get("/api/v1/client/profile-report").json()
        assert any(r["hostname"] == "C14-PC40" and r["state"] == "applied" for r in reports)

        # 3. Échec dpkg lors d'une nouvelle version -> rollback automatique vers nsi + rapport rolling_back
        ok_d2, rel2 = main_mod.RELEASE_REGISTRY.create_draft(
            version="1.0.2",
            profile_id="sciences",
            artifacts=[{
                "id": "lyux-profile-standard",
                "type": "deb",
                "package": "lyux-profile-standard",
                "name": "lyux-profile-standard_1.0.0_all.deb",
                "url": "http://lyux-server:8000/api/v1/apt-repo/pool/main/lyux-profile-standard_1.0.0_all.deb",
                "sha256": hashlib.sha256(deb_bytes).hexdigest(),
                "size": len(deb_bytes),
                "version": "1.0.0",
            }],
        )
        assert ok_d2 is True
        main_mod.RELEASE_REGISTRY.get_release(rel2["id"])["artifacts"][0]["package"] = "lyux-profile-standard"
        assert main_mod.RELEASE_REGISTRY.sign_release(rel2["id"])[0] is True
        assert main_mod.RELEASE_REGISTRY.publish_release(rel2["id"])[0] is True

        # Changer la salle du poste vers S102 (sciences) ou garder la portée cohérente
        main_mod.ENROLLED_MACHINES["C14-PC40"]["room"] = "S102"
        main_mod.ENROLLED_MACHINES["C14-PC40"]["room_id"] = "S102"
        main_mod.ENROLLED_MACHINES["C14-PC40"]["building_id"] = "BAT-B"
        main_mod.ROOM_CATALOG["S102"]["profile"] = "sciences"

        res3 = pa.sync_and_apply_profile(
            server_url="http://lyux-server:8000",
            client_id="lyux-step4-01",
            hostname="C14-PC40",
            building_id="BAT-B",
            room_id="S102",
            role="eleve",
            downloader=dl_from_api,
            deb_installer=lambda p: (False, "dpkg dependency error"),
            state_file=state_file,
            active_dir=active_dir,
            backup_dir=backup_dir,
            sddm_conf_dir=sddm_dir,
            trusted_keys_file=trusted_keys_file,
        )
        assert res3["ok"] is False
        assert res3["rolled_back"] is True
        assert pm.load_profile_state(state_file)["current_profile"] == "nsi"
        reports_after = tc.get("/api/v1/client/profile-report").json()
        assert any(r["hostname"] == "C14-PC40" and r["state"] == "rolling_back" for r in reports_after)
