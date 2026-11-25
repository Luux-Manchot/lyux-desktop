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
