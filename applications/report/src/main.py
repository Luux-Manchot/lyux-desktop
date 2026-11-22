#!/usr/bin/env python3
import sys
import base64
from io import BytesIO

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QComboBox, QCheckBox, QMessageBox,
    QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QScreen

from system_info import collect_machine_diagnostics
from glpi_client import GlpiTicketClient

class LyuxReportWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.diagnostics = collect_machine_diagnostics()
        self.glpi_client = GlpiTicketClient()

        self.setWindowTitle("Signaler un problème — LyuX")
        self.resize(550, 580)
        self.setMinimumSize(500, 520)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #1E1E2E;
            }
            QLabel {
                color: #CDD6F4;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                color: #89B4FA;
                font-weight: bold;
                border: 1px solid #45475A;
                border-radius: 8px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QComboBox, QTextEdit {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 6px;
                padding: 10px 18px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475A;
                border-color: #89B4FA;
            }
            QPushButton#SubmitBtn {
                background-color: #F38BA8;
                color: #11111B;
                border: none;
            }
            QPushButton#SubmitBtn:hover {
                background-color: #EBA0AC;
            }
            QCheckBox {
                color: #BAC2DE;
            }
        """)

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        # En-tête
        header = QLabel("🚨 Signaler un dysfonctionnement")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #F38BA8;")
        layout.addWidget(header)

        # Cadre Informations Techniques
        info_box = QGroupBox("💻 Informations du poste (automatiques)")
        info_layout = QFormLayout(info_box)
        info_layout.addRow("Poste / Salle :", QLabel(f"{self.diagnostics['hostname']} ({self.diagnostics['room']})"))
        info_layout.addRow("Utilisateur :", QLabel(self.diagnostics['username']))
        info_layout.addRow("Adresse IP :", QLabel(self.diagnostics['ip_address']))
        layout.addWidget(info_box)

        # Formulaire
        form_box = QGroupBox("📝 Description du problème")
        form_layout = QVBoxLayout(form_box)

        form_layout.addWidget(QLabel("Type de problème :"))
        self.category_combo = QComboBox()
        self.category_combo.addItems([
            "Écran / Affichage / TNI",
            "Logiciel / Application manquante",
            "Clavier / Souris / Périphérique",
            "Impression",
            "Compte / Mot de passe",
            "Autre"
        ])
        form_layout.addWidget(self.category_combo)

        form_layout.addWidget(QLabel("Expliquez ce qui ne fonctionne pas :"))
        self.desc_text = QTextEdit()
        self.desc_text.setPlaceholderText("Exemple : L'écran clignote en ouvrant LibreOffice, ou l'imprimante ne répond pas...")
        form_layout.addWidget(self.desc_text)

        self.screenshot_check = QCheckBox("📸 Joindre une capture d'écran actuelle")
        self.screenshot_check.setChecked(True)
        form_layout.addWidget(self.screenshot_check)

        layout.addWidget(form_box)

        # Boutons
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()

        self.submit_btn = QPushButton("Envoyer le signalement")
        self.submit_btn.setObjectName("SubmitBtn")
        self.submit_btn.clicked.connect(self.send_report)
        btn_layout.addWidget(self.submit_btn)

        layout.addLayout(btn_layout)

    def capture_screenshot_base64(self):
        screen = QApplication.primaryScreen()
        if screen:
            pixmap = screen.grabWindow(0)
            buffer = BytesIO()
            # Enregistrement en mémoire
            img = pixmap.toImage()
            img.save(buffer, "PNG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        return None

    def send_report(self):
        description = self.desc_text.toPlainText().strip()
        if not description:
            QMessageBox.warning(self, "Attention", "Veuillez saisir une brève description du problème.")
            return

        category = self.category_combo.currentText()
        screenshot_data = self.capture_screenshot_base64() if self.screenshot_check.isChecked() else None

        self.submit_btn.setEnabled(False)
        self.submit_btn.setText("Envoi en cours...")

        result = self.glpi_client.submit_ticket(
            title=f"Incident {category}",
            category=category,
            description=description,
            system_info=self.diagnostics,
            screenshot_b64=screenshot_data
        )

        if result.get("success"):
            ticket_id = result.get("ticket_id", "T-1000")
            msg = f"Votre signalement a bien été enregistré !\n\nNuméro de ticket : {ticket_id}\nL'équipe technique a été prévenue."
            if result.get("simulated"):
                msg += "\n\n(Enregistré en mode local)"
            QMessageBox.information(self, "Signalement envoyé", msg)
            self.close()
        else:
            QMessageBox.critical(self, "Erreur", f"Échec lors de l'envoi du ticket : {result.get('error')}")
            self.submit_btn.setEnabled(True)
            self.submit_btn.setText("Envoyer le signalement")

def main():
    app = QApplication(sys.argv)
    window = LyuxReportWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
