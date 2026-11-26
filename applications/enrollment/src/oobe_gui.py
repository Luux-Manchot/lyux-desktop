#!/usr/bin/env python3
"""
LyuX OOBE (Out-Of-Box Experience) — Assistant de Premier Démarrage
Thème clair moderne, sans emojis, avec placeholder texte "LOGO" (voir issue #27).
Écrans :
  1. Connexion & autorisation Serveur LyuX
  2. Affectation Bâtiment / Salle / Rôle / Nom attribué par le serveur
  3. Enrôlement idempotent & passage à SDDM
"""

import os
import sys
import time
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QThread, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from discovery import validate_server_url
except ImportError:
    from .discovery import validate_server_url

try:
    from enrollment_client import (
        OOBE_LOG_FILE,
        apply_keyboard_layout,
        check_network_ready,
        configure_static_network,
        get_oobe_logger,
        inspect_server,
        perform_enrollment,
        save_state,
    )
except ImportError:
    from .enrollment_client import (
        OOBE_LOG_FILE,
        apply_keyboard_layout,
        check_network_ready,
        configure_static_network,
        get_oobe_logger,
        inspect_server,
        perform_enrollment,
        save_state,
    )


class ServerScanWorker(QThread):
    finished_signal = pyqtSignal(dict)

    def __init__(self, target_url=None):
        super().__init__()
        self.target_url = target_url

    def run(self):
        self.finished_signal.emit(inspect_server(self.target_url))


class InstallWorker(QThread):
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, dict)

    def __init__(self, server_url, building_id, room_id, hostname, is_teacher):
        super().__init__()
        self.server_url = server_url
        self.building_id = building_id
        self.room_id = room_id
        self.hostname = hostname
        self.is_teacher = is_teacher

    def run(self):
        steps = [
            (25, "Vérification de l'état réseau et de l'identité matérielle..."),
            (55, f"Demande d'enrôlement auprès de {self.server_url}..."),
            (80, "Validation du catalogue et de la signature serveur..."),
        ]
        for pct, msg in steps:
            time.sleep(0.15)
            self.progress_signal.emit(pct, msg)

        role = "prof" if self.is_teacher else "eleve"
        result = perform_enrollment(
            self.server_url,
            self.building_id,
            self.room_id,
            self.hostname,
            role=role,
        )
        if result.get("ok"):
            self.progress_signal.emit(100, "Enrôlement confirmé par le serveur.")
            self.finished_signal.emit(True, result)
        else:
            self.progress_signal.emit(100, f"Échec : {result.get('detail', 'Erreur inconnue')}")
            self.finished_signal.emit(False, result)


class LyuxOOBEWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LyuX Setup — Enrôlement du poste")
        self.resize(1024, 680)
        self.setMinimumSize(860, 580)

        self.server_url = ""
        self.selected_building = ""
        self.selected_room = ""
        self.assigned_hostname = ""
        self.is_teacher = False
        self.server_rooms = []
        self.server_buildings = []
        self.server_roles = []
        self.oobe_logger = get_oobe_logger()

        self._apply_light_theme()
        self._build_ui()
        self._refresh_network_badge()
        self.auto_scan_server()

    def _apply_light_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#RootCanvas {
                background-color: #F1F5F9;
                color: #0F172A;
                font-family: 'Inter', 'Noto Sans', 'Segoe UI', sans-serif;
            }
            QFrame#ShellCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 14px;
            }
            QFrame#Sidebar {
                background-color: #F8FAFC;
                border-right: 1px solid #E2E8F0;
                border-top-left-radius: 14px;
                border-bottom-left-radius: 14px;
            }
            QFrame#BottomBar {
                background-color: #F8FAFC;
                border-top: 1px solid #E2E8F0;
                border-bottom-right-radius: 14px;
            }
            QLabel#LogoPlaceholder {
                background-color: #EFF6FF;
                color: #1D4ED8;
                border: 1px dashed #93C5FD;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 800;
                letter-spacing: 2px;
                padding: 10px 14px;
            }
            QLabel#PageTitle {
                font-size: 20px;
                font-weight: 700;
                color: #0F172A;
            }
            QLabel#PageSubtitle {
                font-size: 13px;
                color: #475569;
            }
            QLabel#FieldLabel {
                font-size: 12px;
                font-weight: 600;
                color: #334155;
            }
            QLineEdit, QComboBox {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #2563EB;
            }
            QLineEdit:read-only {
                background-color: #F8FAFC;
                color: #334155;
            }
            QPushButton {
                background-color: #FFFFFF;
                color: #1E293B;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #F8FAFC;
                border-color: #94A3B8;
            }
            QPushButton:disabled {
                background-color: #E2E8F0;
                color: #94A3B8;
                border-color: #CBD5E1;
            }
            QPushButton#PrimaryBtn {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #1D4ED8;
            }
            QPushButton#PrimaryBtn:disabled {
                background-color: #CBD5E1;
                color: #64748B;
            }
            QPushButton#SuccessBtn {
                background-color: #059669;
                color: #FFFFFF;
                border: none;
            }
            QPushButton#SuccessBtn:hover {
                background-color: #047857;
            }
            QProgressBar {
                background-color: #E2E8F0;
                border: none;
                border-radius: 6px;
                height: 12px;
                text-align: center;
                font-size: 11px;
                color: #0F172A;
            }
            QProgressBar::chunk {
                background-color: #2563EB;
                border-radius: 6px;
            }
        """)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("RootCanvas")
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(36, 28, 36, 28)
        root_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        shell = QFrame()
        shell.setObjectName("ShellCard")
        shell.setFixedSize(920, 590)
        shell_lay = QHBoxLayout(shell)
        shell_lay.setContentsMargins(0, 0, 0, 0)
        shell_lay.setSpacing(0)

        # Colonne gauche : LOGO texte + étapes
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(22, 26, 22, 22)
        sb_lay.setSpacing(14)

        logo_lbl = QLabel("LOGO")
        logo_lbl.setObjectName("LogoPlaceholder")
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_lay.addWidget(logo_lbl)

        brand_sub = QLabel("LyuX Client Setup")
        brand_sub.setStyleSheet("font-size: 13px; font-weight: 700; color: #334155;")
        brand_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_lay.addWidget(brand_sub)

        sb_lay.addSpacing(12)

        self.step_labels = []
        for idx, title in enumerate(["1. Serveur LyuX", "2. Affectation", "3. Enrôlement"], start=0):
            lbl = QLabel(title)
            lbl.setStyleSheet(self._step_style(idx == 0, False))
            sb_lay.addWidget(lbl)
            self.step_labels.append(lbl)

        sb_lay.addStretch()

        info_lbl = QLabel("Système : Debian 13 (FR)\nX11 / OOBE sécurisé")
        info_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        sb_lay.addWidget(info_lbl)

        shell_lay.addWidget(sidebar)

        # Zone droite : contenu + barre utilitaire basse
        right_col = QWidget()
        right_lay = QVBoxLayout(right_col)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self.stacked = QStackedWidget()
        self.page_server = self._create_page_server()     # 0
        self.page_room = self._create_page_room()         # 1
        self.page_install = self._create_page_install()   # 2
        self.stacked.addWidget(self.page_server)
        self.stacked.addWidget(self.page_room)
        self.stacked.addWidget(self.page_install)
        self.stacked.currentChanged.connect(self._update_sidebar_steps)
        right_lay.addWidget(self.stacked, 1)

        # Barre utilitaire basse (clavier réel, réseau, journal)
        bottom_bar = QFrame()
        bottom_bar.setObjectName("BottomBar")
        bottom_bar.setFixedHeight(52)
        bb_lay = QHBoxLayout(bottom_bar)
        bb_lay.setContentsMargins(20, 6, 20, 6)
        bb_lay.setSpacing(10)

        kbd_lbl = QLabel("Clavier :")
        kbd_lbl.setStyleSheet("font-size: 12px; color: #475569; font-weight: 600;")
        bb_lay.addWidget(kbd_lbl)

        self.kbd_combo = QComboBox()
        self.kbd_combo.addItem("FR (AZERTY)", "fr")
        self.kbd_combo.addItem("US (QWERTY)", "us")
        self.kbd_combo.addItem("BE (AZERTY)", "be")
        self.kbd_combo.addItem("CH (Romand)", "ch")
        self.kbd_combo.setFixedWidth(135)
        self.kbd_combo.currentIndexChanged.connect(self._on_keyboard_changed)
        bb_lay.addWidget(self.kbd_combo)

        self.net_status_lbl = QLabel("Réseau : vérification...")
        self.net_status_lbl.setStyleSheet("font-size: 12px; color: #475569;")
        bb_lay.addWidget(self.net_status_lbl)

        bb_lay.addStretch()

        self.static_net_btn = QPushButton("IP statique")
        self.static_net_btn.clicked.connect(self.open_static_network_dialog)
        bb_lay.addWidget(self.static_net_btn)

        self.logs_btn = QPushButton("Journal")
        self.logs_btn.clicked.connect(self._open_logs_dialog)
        bb_lay.addWidget(self.logs_btn)

        right_lay.addWidget(bottom_bar)
        shell_lay.addWidget(right_col, 1)

        root_lay.addWidget(shell)
        self.setCentralWidget(root)

    def _step_style(self, active: bool, done: bool) -> str:
        if active:
            return (
                "background-color: #EFF6FF; color: #1D4ED8; font-weight: 700;"
                "border-left: 3px solid #2563EB; border-radius: 6px; padding: 9px 12px; font-size: 13px;"
            )
        if done:
            return (
                "background-color: #ECFDF5; color: #047857; font-weight: 600;"
                "border-radius: 6px; padding: 9px 12px; font-size: 13px;"
            )
        return "color: #64748B; padding: 9px 12px; font-size: 13px;"

    def _update_sidebar_steps(self, current_idx: int):
        for i, lbl in enumerate(self.step_labels):
            lbl.setStyleSheet(self._step_style(i == current_idx, i < current_idx))

    def _on_keyboard_changed(self):
        code = self.kbd_combo.currentData()
        ok, msg = apply_keyboard_layout(code)
        if not ok:
            QMessageBox.warning(self, "Clavier", msg)

    def _refresh_network_badge(self):
        ok, ifaces = check_network_ready()
        if ok:
            self.net_status_lbl.setText(f"Réseau : {', '.join(ifaces[:2])}")
            self.net_status_lbl.setStyleSheet("font-size: 12px; color: #047857; font-weight: 600;")
        else:
            self.net_status_lbl.setText("Réseau : aucune IPv4")
            self.net_status_lbl.setStyleSheet("font-size: 12px; color: #B91C1C; font-weight: 600;")

    def _open_logs_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Journal OOBE")
        dlg.resize(660, 420)
        lay = QVBoxLayout(dlg)
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        if OOBE_LOG_FILE.exists():
            txt.setPlainText(OOBE_LOG_FILE.read_text(encoding="utf-8", errors="replace"))
        else:
            txt.setPlainText("Aucun journal OOBE enregistré pour le moment.")
        lay.addWidget(txt)
        btn = QPushButton("Fermer")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    # -------------------------------------------------------------------------
    # ÉCRAN 1 : CONNEXION AU SERVEUR LYUX
    # -------------------------------------------------------------------------
    def _create_page_server(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(14)

        title = QLabel("Connexion au serveur LyuX")
        title.setObjectName("PageTitle")
        lay.addWidget(title)

        sub = QLabel("Le poste recherche le serveur d'enrôlement sur le réseau local ou via l'adresse saisie ci-dessous.")
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        self.server_status_frame = QFrame()
        self.server_status_frame.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 10px; padding: 12px;"
        )
        st_lay = QVBoxLayout(self.server_status_frame)
        st_lay.setSpacing(4)
        self.server_status_lbl = QLabel("Recherche du serveur en cours...")
        self.server_status_lbl.setStyleSheet("color: #B45309; font-weight: 700; font-size: 13px;")
        self.server_details_lbl = QLabel("Vérification du réseau et de l'API...")
        self.server_details_lbl.setStyleSheet("color: #475569; font-size: 12px;")
        self.server_details_lbl.setWordWrap(True)
        st_lay.addWidget(self.server_status_lbl)
        st_lay.addWidget(self.server_details_lbl)
        lay.addWidget(self.server_status_frame)

        url_lbl = QLabel("Adresse du serveur (format http(s)://hote:port)")
        url_lbl.setObjectName("FieldLabel")
        lay.addWidget(url_lbl)

        url_row = QHBoxLayout()
        self.server_url_input = QLineEdit()
        self.server_url_input.setPlaceholderText("http://lyux-server:8000")
        self.rescan_btn = QPushButton("Tester / Réessayer")
        self.rescan_btn.clicked.connect(self.manual_scan_server)
        url_row.addWidget(self.server_url_input, 1)
        url_row.addWidget(self.rescan_btn)
        lay.addLayout(url_row)

        lay.addStretch()

        nav = QHBoxLayout()
        nav.addStretch()
        self.server_next_btn = QPushButton("Suivant : Affectation")
        self.server_next_btn.setObjectName("PrimaryBtn")
        self.server_next_btn.setFixedHeight(40)
        self.server_next_btn.setEnabled(False)
        self.server_next_btn.clicked.connect(lambda: self.stacked.setCurrentIndex(1))
        nav.addWidget(self.server_next_btn)
        lay.addLayout(nav)
        return page

    def auto_scan_server(self):
        self.worker = ServerScanWorker()
        self.worker.finished_signal.connect(self.on_server_scanned)
        self.worker.start()

    def manual_scan_server(self):
        self._refresh_network_badge()
        url = self.server_url_input.text().strip()
        if url:
            valid, norm, err = validate_server_url(url)
            if not valid:
                self._set_status_box("#FEF2F2", "#FECACA", "#B91C1C", "Adresse serveur invalide", err)
                self.server_next_btn.setEnabled(False)
                return
            url = norm
        self._set_status_box("#EFF6FF", "#BFDBFE", "#1D4ED8", "Test de connexion...", "Vérification de la santé de l'API...")
        self.worker = ServerScanWorker(target_url=url or None)
        self.worker.finished_signal.connect(self.on_server_scanned)
        self.worker.start()

    def _set_status_box(self, bg: str, border: str, fg: str, title: str, detail: str):
        self.server_status_frame.setStyleSheet(
            f"background-color: {bg}; border: 1px solid {border}; border-radius: 10px; padding: 12px;"
        )
        self.server_status_lbl.setStyleSheet(f"color: {fg}; font-weight: 700; font-size: 13px; border: none;")
        self.server_details_lbl.setStyleSheet("color: #334155; font-size: 12px; border: none;")
        self.server_status_lbl.setText(title)
        self.server_details_lbl.setText(detail)

    def open_static_network_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Configuration réseau statique (IPv4)")
        form = QFormLayout(dlg)
        iface_in = QLineEdit("eth0")
        ip_in = QLineEdit()
        ip_in.setPlaceholderText("192.168.1.50/24")
        gw_in = QLineEdit()
        gw_in.setPlaceholderText("192.168.1.1")
        dns_in = QLineEdit()
        dns_in.setPlaceholderText("192.168.1.1")
        form.addRow("Interface :", iface_in)
        form.addRow("IP / Masque (CIDR) :", ip_in)
        form.addRow("Passerelle :", gw_in)
        form.addRow("DNS :", dns_in)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ok, msg = configure_static_network(iface_in.text(), ip_in.text(), gw_in.text(), dns_in.text())
            if ok:
                self._refresh_network_badge()
                self.manual_scan_server()
            else:
                QMessageBox.warning(self, "Erreur réseau", msg)

    def on_server_scanned(self, result):
        self._refresh_network_badge()
        state = result.get("state", "server-unreachable")
        detail = result.get("detail", "")
        url = result.get("server_url", "")

        if state == "enrolled":
            machine = result.get("machine", {})
            self.server_url = url
            self.assigned_hostname = machine.get("hostname", "")
            self.selected_building = machine.get("building_id", "")
            self.selected_room = machine.get("room_id", "")
            self._set_status_box(
                "#ECFDF5", "#A7F3D0", "#047857",
                "Poste déjà enrôlé (reprise confirmée)",
                f"Identité : {self.assigned_hostname} ({self.selected_building}/{self.selected_room})",
            )
            save_state("enrolled", server_url=url, hostname=self.assigned_hostname, building_id=self.selected_building, room_id=self.selected_room)
            if os.getenv("LYUX_OOBE_EXIT_ON_ENROLL", "0") == "1":
                QTimer.singleShot(900, QApplication.instance().quit)
            return

        if state == "authorized":
            self.server_url = url
            self.server_rooms = result.get("rooms", [])
            self.server_buildings = result.get("buildings", [])
            self.server_roles = result.get("roles", [])
            self.server_url_input.setText(url)
            self._set_status_box(
                "#ECFDF5", "#A7F3D0", "#047857",
                "Connecté au serveur LyuX — Enrôlement ouvert",
                f"API v1 joignable sur {url}",
            )
            self.server_next_btn.setEnabled(True)
            self.server_next_btn.setText("Suivant : Affectation")
            save_state("authorized", server_url=url, last_error="")
            self.update_buildings_and_rooms()
        elif state == "awaiting-authorization":
            self.server_url = url
            self.server_url_input.setText(url)
            self._set_status_box(
                "#FFFBEB", "#FDE68A", "#B45309",
                "Serveur joignable — Enrôlement verrouillé",
                detail or "Activez l'enrôlement dans l'Admin Panel puis cliquez sur Tester / Réessayer.",
            )
            self.server_next_btn.setEnabled(False)
            self.server_next_btn.setText("Enrôlement verrouillé")
            save_state("awaiting-authorization", server_url=url, last_error=detail)
        elif state == "network-error":
            self._set_status_box(
                "#FEF2F2", "#FECACA", "#B91C1C",
                "Erreur réseau : aucune IPv4 active",
                detail or "Vérifiez le câble ou configurez une IP statique ci-dessous.",
            )
            self.server_next_btn.setEnabled(False)
            self.server_next_btn.setText("Réseau requis")
            save_state("network-error", last_error=detail)
        else:
            self._set_status_box(
                "#FEF2F2", "#FECACA", "#B91C1C",
                "Serveur absent ou API inaccessible",
                detail or "Vérifiez le réseau ou l'adresse du serveur.",
            )
            self.server_next_btn.setEnabled(False)
            self.server_next_btn.setText("Serveur requis")
            save_state("server-unreachable", server_url=self.server_url_input.text().strip(), last_error=detail)

    # -------------------------------------------------------------------------
    # ÉCRAN 2 : AFFECTATION (CATALOGUE SERVEUR UNIQUEMENT)
    # -------------------------------------------------------------------------
    def _create_page_room(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(12)

        title = QLabel("Affectation et identité du poste")
        title.setObjectName("PageTitle")
        lay.addWidget(title)

        sub = QLabel("Les bâtiments, salles, rôles et noms d'ordinateur proviennent exclusivement du serveur LyuX.")
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        b_lbl = QLabel("Bâtiment")
        b_lbl.setObjectName("FieldLabel")
        lay.addWidget(b_lbl)
        self.building_combo = QComboBox()
        self.building_combo.currentIndexChanged.connect(self.on_building_changed)
        lay.addWidget(self.building_combo)

        r_lbl = QLabel("Salle / Classe")
        r_lbl.setObjectName("FieldLabel")
        lay.addWidget(r_lbl)
        self.room_combo = QComboBox()
        self.room_combo.currentIndexChanged.connect(self.on_room_changed)
        lay.addWidget(self.room_combo)

        h_lbl = QLabel("Nom d'ordinateur (modifiable, vérifié par le serveur)")
        h_lbl.setObjectName("FieldLabel")
        lay.addWidget(h_lbl)
        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText("Ex : C14-PC01")
        lay.addWidget(self.hostname_input)

        root_lbl = QLabel("Mot de passe root local (seul compte local de secours)")
        root_lbl.setObjectName("FieldLabel")
        lay.addWidget(root_lbl)
        self.root_pwd_input = QLineEdit()
        self.root_pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.root_pwd_input.setPlaceholderText("Définir le mot de passe root (min. 8 caractères)")
        lay.addWidget(self.root_pwd_input)

        self.root_pwd_confirm_input = QLineEdit()
        self.root_pwd_confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.root_pwd_confirm_input.setPlaceholderText("Confirmer le mot de passe root")
        lay.addWidget(self.root_pwd_confirm_input)

        key_notice = QLabel(
            "Note : les autres comptes locaux seront verrouillés après l'enrôlement. "
            "La prise en charge des clés de sécurité matérielles (FIDO2 / USB) arrive prochainement."
        )
        key_notice.setWordWrap(True)
        key_notice.setStyleSheet(
            "background-color: #EFF6FF; color: #1E40AF; border: 1px solid #BFDBFE; "
            "border-radius: 8px; padding: 8px 10px; font-size: 11px;"
        )
        lay.addWidget(key_notice)

        self.disable_ssh_checkbox = QCheckBox("Désactiver l'accès SSH après l'enrôlement (recommandé en salle élèves)")
        self.disable_ssh_checkbox.setChecked(False)
        lay.addWidget(self.disable_ssh_checkbox)

        lay.addStretch()

        nav = QHBoxLayout()
        back_btn = QPushButton("Retour")
        back_btn.clicked.connect(lambda: self.stacked.setCurrentIndex(0))
        launch_btn = QPushButton("Lancer l'enrôlement")
        launch_btn.setObjectName("SuccessBtn")
        launch_btn.setFixedHeight(40)
        launch_btn.clicked.connect(self.start_installation)
        nav.addWidget(back_btn)
        nav.addStretch()
        nav.addWidget(launch_btn)
        lay.addLayout(nav)
        return page

    def update_buildings_and_rooms(self):
        self.building_combo.blockSignals(True)
        self.building_combo.clear()
        room_buildings = {r.get("building_id") for r in self.server_rooms if r.get("building_id")}
        first_valid_idx = 0
        for idx, b in enumerate(self.server_buildings):
            self.building_combo.addItem(f"{b['name']} ({b['id']})", b["id"])
            if first_valid_idx == 0 and b["id"] in room_buildings:
                first_valid_idx = idx
        if self.building_combo.count() > 0:
            self.building_combo.setCurrentIndex(first_valid_idx)
        self.building_combo.blockSignals(False)
        self.on_building_changed()

    def on_building_changed(self):
        b_id = self.building_combo.currentData()
        self.room_combo.blockSignals(True)
        self.room_combo.clear()
        for r in [rm for rm in self.server_rooms if rm.get("building_id") == b_id]:
            self.room_combo.addItem(f"{r['name']} ({r['id']})", r["id"])
        self.room_combo.blockSignals(False)
        self.on_room_changed()

    def on_room_changed(self):
        r_id = self.room_combo.currentData()
        b_id = self.building_combo.currentData()
        if not r_id or not b_id or not self.server_url:
            self.hostname_input.setText("")
            return
        try:
            res = requests.get(
                f"{self.server_url}/api/v1/enroll/suggest-hostname?room_id={r_id}&building_id={b_id}",
                timeout=2,
            )
            if res.status_code == 200:
                self.hostname_input.setText(res.json().get("suggested_hostname", ""))
                return
        except Exception:
            pass
        self.hostname_input.setText("")

    # -------------------------------------------------------------------------
    # ÉCRAN 3 : ENRÔLEMENT & FINALISATION
    # -------------------------------------------------------------------------
    def _create_page_install(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(14)

        self.install_title = QLabel("Enrôlement du poste en cours...")
        self.install_title.setObjectName("PageTitle")
        lay.addWidget(self.install_title)

        self.install_desc = QLabel("Communication sécurisée avec le serveur LyuX...")
        self.install_desc.setObjectName("PageSubtitle")
        self.install_desc.setWordWrap(True)
        lay.addWidget(self.install_desc)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        lay.addWidget(self.progress_bar)

        self.log_box = QLabel("Initialisation...")
        self.log_box.setWordWrap(True)
        self.log_box.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px;"
            "padding: 12px; color: #1E293B; font-family: monospace; font-size: 12px;"
        )
        lay.addWidget(self.log_box)

        lay.addStretch()

        nav = QHBoxLayout()
        self.install_back_btn = QPushButton("Retour")
        self.install_back_btn.clicked.connect(lambda: self.stacked.setCurrentIndex(0))
        self.install_back_btn.setVisible(False)
        self.install_retry_btn = QPushButton("Réessayer l'enrôlement")
        self.install_retry_btn.setObjectName("PrimaryBtn")
        self.install_retry_btn.clicked.connect(self.start_installation)
        self.install_retry_btn.setVisible(False)
        nav.addWidget(self.install_back_btn)
        nav.addStretch()
        nav.addWidget(self.install_retry_btn)
        lay.addLayout(nav)
        return page

    def start_installation(self):
        self.selected_building = self.building_combo.currentData() or ""
        self.selected_room = self.room_combo.currentData() or ""
        self.assigned_hostname = self.hostname_input.text().strip()
        self.is_teacher = False

        if not self.selected_building or not self.selected_room or not self.assigned_hostname:
            QMessageBox.warning(self, "Champs requis", "Sélectionnez un bâtiment, une salle et saisissez un nom d'ordinateur.")
            return

        import re
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$", self.assigned_hostname):
            QMessageBox.warning(self, "Nom invalide", "Le nom d'ordinateur doit contenir uniquement lettres, chiffres et tirets.")
            return

        root_pwd = self.root_pwd_input.text().strip()
        root_pwd_confirm = self.root_pwd_confirm_input.text().strip()
        if root_pwd or root_pwd_confirm or os.getenv("LYUX_REQUIRE_ROOT_PASSWORD", "0") == "1":
            if len(root_pwd) < 8:
                QMessageBox.warning(self, "Mot de passe root", "Le mot de passe root doit contenir au moins 8 caractères.")
                return
            if root_pwd != root_pwd_confirm:
                QMessageBox.warning(self, "Mot de passe root", "Les deux mots de passe root ne correspondent pas.")
                return
            try:
                from maintenance import configure_root_only_access
            except ImportError:
                from .maintenance import configure_root_only_access
            apply_sys = hasattr(os, "geteuid") and os.geteuid() == 0
            ok_root, msg_root = configure_root_only_access(root_pwd, apply_system=apply_sys)
            if not ok_root:
                QMessageBox.warning(self, "Mot de passe root", msg_root)
                return

        if getattr(self, "disable_ssh_checkbox", None) and self.disable_ssh_checkbox.isChecked():
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                import subprocess
                subprocess.run(["systemctl", "disable", "--now", "ssh"], check=False)

        try:
            chk = requests.post(
                f"{self.server_url}/api/v1/enroll/check-hostname",
                json={"hostname": self.assigned_hostname},
                timeout=3,
            )
            if chk.status_code == 200 and chk.json().get("available") is False:
                QMessageBox.warning(self, "Nom déjà utilisé", f"Le nom '{self.assigned_hostname}' est déjà attribué sur le serveur.")
                return
        except Exception:
            pass

        self.install_back_btn.setVisible(False)
        self.install_retry_btn.setVisible(False)
        self.stacked.setCurrentIndex(2)
        self.progress_bar.setValue(5)
        self.log_box.setText(f"Démarrage de l'enrôlement pour {self.assigned_hostname}...")

        self.install_worker = InstallWorker(
            self.server_url,
            self.selected_building,
            self.selected_room,
            self.assigned_hostname,
            self.is_teacher,
        )
        self.install_worker.progress_signal.connect(self.on_install_progress)
        self.install_worker.finished_signal.connect(self.on_install_finished)
        self.install_worker.start()

    def on_install_progress(self, percent, text):
        self.progress_bar.setValue(percent)
        self.log_box.setText(text)

    def on_install_finished(self, success, data):
        if success:
            self.install_title.setText("Poste enrôlé avec succès")
            self.install_desc.setText(f"{self.assigned_hostname} enregistré sur {self.selected_building}/{self.selected_room}.")
            self.log_box.setText(f"Enrôlement confirmé pour {self.assigned_hostname}. Ouverture de l'écran de connexion...")
            if os.getenv("LYUX_OOBE_EXIT_ON_ENROLL", "0") == "1":
                QTimer.singleShot(900, QApplication.instance().quit)
        else:
            detail = data.get("detail", "Erreur d'enrôlement.")
            self.install_title.setText("Enrôlement non confirmé")
            self.install_desc.setText("Aucun fichier d'enrôlement n'a été écrit. Corrigez puis réessayez.")
            self.log_box.setText(detail)
            self.install_back_btn.setVisible(True)
            self.install_retry_btn.setVisible(True)


def main():
    app = QApplication(sys.argv)
    win = LyuxOOBEWindow()
    if os.getenv("LYUX_OOBE_EXIT_ON_ENROLL", "0") == "1":
        win.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        screen = app.primaryScreen()
        if screen is not None:
            win.setGeometry(screen.geometry())
        win.showFullScreen()
    else:
        win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
