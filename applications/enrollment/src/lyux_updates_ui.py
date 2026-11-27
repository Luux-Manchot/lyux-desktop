"""Interface PyQt6 « Mises à jour LyuX » intégrée à Configuration du système KDE.

Affiche la séparation en 3 parties (Debian, KDE Plasma, LyuX OS) avec :
- Dernière version existante (connue du serveur)
- Version sélectionnée par le serveur (cible autorisée)
- Version installée sur la machine
Et lance la mise à jour strictement jusqu'à la version sélectionnée par le serveur.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_policy_sync import (  # noqa: E402
    fetch_updates_policy,
    get_local_versions,
    load_server_url,
)


class UpdateApplyWorker(QThread):
    finished = pyqtSignal(bool, str)

    def run(self) -> None:
        import subprocess
        try:
            res = subprocess.run(
                [
                    "pkexec",
                    "/opt/lyux/apps/enrollment/scripts/lyux-apply-updates.sh",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            msg = (res.stdout or res.stderr or "").strip()
            self.finished.emit(res.returncode == 0, msg or ("Mise à jour terminée." if res.returncode == 0 else "Échec de la mise à jour."))
        except Exception as exc:
            self.finished.emit(False, str(exc))


class ComponentCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "ComponentCard { border: 1px solid palette(mid); border-radius: 8px; padding: 12px; }"
        )
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_lbl = QLabel(title)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.title_lbl.setFont(font)
        self.status_lbl = QLabel("En attente")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.title_lbl)
        header.addWidget(self.status_lbl)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)

        self.latest_val = QLabel("—")
        self.selected_val = QLabel("—")
        self.local_val = QLabel("—")

        for lbl in (self.latest_val, self.selected_val, self.local_val):
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        grid.addWidget(QLabel("Dernière version existante :"), 0, 0)
        grid.addWidget(self.latest_val, 0, 1)
        grid.addWidget(QLabel("Version sélectionnée par le serveur :"), 1, 0)
        grid.addWidget(self.selected_val, 1, 1)
        grid.addWidget(QLabel("Version sur cette machine :"), 2, 0)
        grid.addWidget(self.local_val, 2, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

    def update_data(self, local_ver: str, selected_ver: str, latest_ver: str) -> bool:
        self.local_val.setText(local_ver or "Inconnue")
        self.selected_val.setText(selected_ver or "Non définie par le serveur")
        self.latest_val.setText(latest_ver or "Non vérifiée")

        if not selected_ver:
            self.status_lbl.setText("Cible serveur non définie")
            self.status_lbl.setStyleSheet("color: #d97706; font-weight: bold;")
            return False
        if local_ver == selected_ver or (local_ver and local_ver.startswith(selected_ver)):
            self.status_lbl.setText("À jour (cible serveur)")
            self.status_lbl.setStyleSheet("color: #16a34a; font-weight: bold;")
            return False
        self.status_lbl.setText("Mise à jour validée disponible")
        self.status_lbl.setStyleSheet("color: #2563eb; font-weight: bold;")
        return True


class LyuxUpdatesWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mises à jour du système — LyuX")
        self.setMinimumWidth(640)
        self.worker: UpdateApplyWorker | None = None

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(18, 18, 18, 18)

        title = QLabel("Mises à jour contrôlées par l'établissement")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        root.addWidget(title)

        subtitle = QLabel(
            "Les mises à jour s'alignent strictement sur la version validée par le serveur LyuX "
            "(Debian, KDE Plasma et LyuX OS)."
        )
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.cards = {
            "debian": ComponentCard("Debian"),
            "kde": ComponentCard("KDE Plasma"),
            "lyux": ComponentCard("LyuX OS"),
        }
        for card in self.cards.values():
            root.addWidget(card)

        self.info_lbl = QLabel("")
        self.info_lbl.setWordWrap(True)
        root.addWidget(self.info_lbl)

        actions = QHBoxLayout()
        self.refresh_btn = QPushButton("Actualiser")
        self.refresh_btn.clicked.connect(self.refresh_state)
        self.apply_btn = QPushButton("Mettre à jour vers la version serveur")
        self.apply_btn.clicked.connect(self.apply_updates)
        actions.addWidget(self.refresh_btn)
        actions.addStretch()
        actions.addWidget(self.apply_btn)
        root.addLayout(actions)

        self.refresh_state()

    def refresh_state(self) -> None:
        local = get_local_versions()
        server_url = load_server_url()
        policy: dict = {}
        if not server_url:
            self.info_lbl.setText("Poste non enrôlé : aucune URL de serveur LyuX configurée.")
        else:
            try:
                policy = fetch_updates_policy(server_url)
                self.info_lbl.setText(f"Serveur connecté : {server_url}")
            except Exception as exc:
                self.info_lbl.setText(f"Serveur LyuX inaccessible ({exc}).")

        any_pending = False
        for key, card in self.cards.items():
            comp = policy.get(key) or {}
            pending = card.update_data(
                local.get(key, "Inconnue"),
                str(comp.get("selected_version") or "").strip(),
                str(comp.get("latest_version") or "").strip(),
            )
            if pending:
                any_pending = True

        self.apply_btn.setEnabled(bool(server_url))
        if any_pending:
            self.apply_btn.setText("Mettre à jour vers la version validée par le serveur")
        else:
            self.apply_btn.setText("Vérifier / aligner sur la version serveur")

    def apply_updates(self) -> None:
        self.apply_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.info_lbl.setText("Application des mises à jour validées par le serveur en cours...")
        self.worker = UpdateApplyWorker()
        self.worker.finished.connect(self._on_apply_finished)
        self.worker.start()

    def _on_apply_finished(self, ok: bool, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.refresh_state()
        if ok:
            QMessageBox.information(self, "Mises à jour LyuX", message)
        else:
            QMessageBox.warning(self, "Mises à jour LyuX", message)


def main() -> int:
    app = QApplication(sys.argv)
    win = LyuxUpdatesWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
