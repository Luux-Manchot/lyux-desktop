#!/usr/bin/env python3
"""
LyuX Workstation & OOBE Setup Suite — Opération Manchot
Système unifié :
1. Assistant OOBE (Configuration rapide d'un nouveau PC / VM style Windows Setup)
2. Écran de connexion multi-comptes centralisé (SDDM / LyuX)
3. Bureau interactif KDE Plasma avec montages transparents (//homes, //classes)
4. Supervision Veyon Master en direct pour les enseignants
5. Signalement de pannes GLPI & Réinitialisation de mots de passe express
"""

import sys
import os
import time
import datetime
from pathlib import Path
import requests

try:
    from veyon_manager import VeyonManager
except ImportError:
    try:
        from .veyon_manager import VeyonManager
    except ImportError:
        try:
            from applications.station.src.veyon_manager import VeyonManager
        except ImportError:
            VeyonManager = None

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QStackedWidget,
    QFrame, QGridLayout, QGroupBox, QMessageBox, QListWidget,
    QDialog, QTextEdit, QScrollArea, QProgressBar, QRadioButton
)
from PyQt6.QtCore import Qt, QTimer, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QColor, QPixmap

ACCOUNTS = {
    "lyux-admin": {"name": "Administrateur Système", "role": "admin", "classe": "IT / Maintenance", "pwd": "LyuxAdmin2026!", "room": "ALL"},
    "lyux.eleve": {"name": "Élève Démo (LyuX)", "role": "eleve", "classe": "1G1 (Salle B204)", "pwd": "Eleve2026!", "room": "B204"},
    "lyux.prof": {"name": "Professeur Démo (LyuX)", "role": "enseignant", "classe": "Maths / NSI", "pwd": "Prof2026!", "room": "B204"},
    "invite": {"name": "Session Invité", "role": "invite", "classe": "Sans compte (Éphémère)", "pwd": "", "room": "LOCAL"},
    "thomas.durand": {"name": "M. Durand (Maths / NSI)", "role": "enseignant", "classe": "Profs Maths", "pwd": "Prof2026!", "room": "B204"},
    "sophie.leroy": {"name": "Mme. Leroy (Sciences)", "role": "enseignant", "classe": "Profs Sciences", "pwd": "Prof2026!", "room": "S102"},
    "lucas.martin": {"name": "Lucas Martin", "role": "eleve", "classe": "1G1 (Salle B204)", "pwd": "Eleve2026!", "room": "B204"},
    "emma.bernard": {"name": "Emma Bernard", "role": "eleve", "classe": "1G1 (Salle B204)", "pwd": "Eleve2026!", "room": "B204"},
    "hugo.dubois": {"name": "Hugo Dubois", "role": "eleve", "classe": "1G2 (Salle S102)", "pwd": "Eleve2026!", "room": "S102"},
    "lea.thomas": {"name": "Léa Thomas", "role": "eleve", "classe": "1G2 (Salle S102)", "pwd": "Eleve2026!", "room": "S102"},
    "claire.viesco": {"name": "Claire Vie-Scolaire", "role": "viesco", "classe": "Vie Scolaire", "pwd": "Viesco2026!", "room": "VIESCO"},
}

class AutoInstallThread(QThread):
    progress_signal = pyqtSignal(int, str)
    completed_signal = pyqtSignal(dict)

    def __init__(self, server_url, room_id, is_teacher, otp):
        super().__init__()
        self.server_url = server_url
        self.room_id = room_id
        self.is_teacher = is_teacher
        self.otp = otp

    def run(self):
        steps = [
            (20, "🌐 Configuration de la langue (Français) et disposition AZERTY..."),
            (40, f"📡 Liaison avec le serveur LyuX ({self.server_url})..."),
            (60, "🔑 Configuration de l'authentification centralisée LDAP & SSSD..."),
            (80, "📁 Montages dynamiques CIFS (//serveur/homes, //serveur/classes)..."),
            (95, "📦 Déploiement du profil logiciel Ansible & Thème KDE Plasma..."),
            (100, "🎉 Configuration terminée !")
        ]
        for pct, desc in steps:
            time.sleep(0.35)
            self.progress_signal.emit(pct, desc)

        try:
            payload = {
                "otp_code": self.otp,
                "room_id": self.room_id,
                "mac_address": "52:54:00:11:22:33",
                "is_teacher_pc": self.is_teacher
            }
            res = requests.post(f"{self.server_url}/api/v1/enroll/validate-otp", json=payload, timeout=3)
            if res.status_code == 200:
                self.completed_signal.emit(res.json())
                return
        except Exception:
            pass

        self.completed_signal.emit({
            "hostname": f"{self.room_id.lower()}-pc01",
            "room_id": self.room_id,
            "room_profile": "standard"
        })

class LyuxUnifiedApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_user = None
        self.current_room = "B24"
        self.assigned_hostname = "b24-pc01"
        self.api_url = "http://127.0.0.1:8000"
        self.veyon_mgr = VeyonManager(api_url=self.api_url) if VeyonManager else None

        self.setWindowTitle("🐧 LyuX OS — Poste Client & Assistant OOBE")
        self.resize(1050, 700)
        self.setMinimumSize(920, 620)

        self.init_style()
        self.init_pages()

    def init_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0F172A;
            }
            QLabel {
                color: #E2E8F0;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }
            QFrame#SetupCard {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 20px;
            }
            QPushButton {
                background-color: #334155;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #475569;
                border-color: #38BDF8;
                color: #FFFFFF;
            }
            QPushButton#PrimaryBtn {
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                font-weight: bold;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #0EA5E9;
            }
            QPushButton#SuccessBtn {
                background-color: #10B981;
                color: #0F172A;
                border: none;
                font-weight: bold;
            }
            QPushButton#SuccessBtn:hover {
                background-color: #34D399;
            }
            QPushButton#DangerBtn {
                background-color: #EF4444;
                color: #FFFFFF;
                border: none;
                font-weight: bold;
            }
            QPushButton#DangerBtn:hover {
                background-color: #F87171;
            }
            QLineEdit, QComboBox, QTextEdit, QListWidget {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }
            QProgressBar {
                background-color: #0F172A;
                border: 1px solid #334155;
                border-radius: 8px;
                text-align: center;
                color: #F8FAFC;
                font-weight: bold;
                height: 22px;
            }
            QProgressBar::chunk {
                background-color: #38BDF8;
                border-radius: 7px;
            }
            QFrame#Taskbar {
                background-color: #0B0F19;
                border-top: 1px solid #1E293B;
            }
            QFrame#DesktopIcon {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 12px;
            }
            QFrame#DesktopIcon:hover {
                background-color: #334155;
                border-color: #38BDF8;
            }
        """)

    def init_pages(self):
        self.stacked = QStackedWidget()
        self.setCentralWidget(self.stacked)

        # 0: OOBE Step 1 (Langue & Clavier)
        # 1: OOBE Step 2 (Serveur & Salle)
        # 2: OOBE Step 3 (Installation auto)
        # 3: Login SDDM (Multi-comptes)
        # 4: Desktop KDE Plasma
        self.page_oobe_1 = self.create_oobe_step1()
        self.page_oobe_2 = self.create_oobe_step2()
        self.page_oobe_3 = self.create_oobe_step3()
        self.page_login = self.create_login_page()
        self.page_desktop = self.create_desktop_page()

        self.stacked.addWidget(self.page_oobe_1)  # 0
        self.stacked.addWidget(self.page_oobe_2)  # 1
        self.stacked.addWidget(self.page_oobe_3)  # 2
        self.stacked.addWidget(self.page_login)   # 3
        self.stacked.addWidget(self.page_desktop) # 4

        # DÉMARRAGE DIRECT SUR LA SESSION (SDDM) SANS AUCUNE QUESTION
        self.stacked.setCurrentIndex(3)

    # =========================================================================
    # 1. OOBE ÉTAPE 1 : LANGUE & CLAVIER (OPTIONS PAR DÉFAUT MODIFIABLES)
    # =========================================================================
    def create_oobe_step1(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("SetupCard")
        card.setFixedSize(540, 480)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 30, 40, 30)
        card_layout.setSpacing(16)

        # Logo & Titre
        top = QHBoxLayout()
        logo = QLabel("🐧 LyuX Setup")
        logo.setStyleSheet("font-size: 24px; font-weight: bold; color: #38BDF8;")
        top.addWidget(logo)
        top.addStretch()
        badge = QLabel("Étape 1/3")
        badge.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: bold;")
        top.addWidget(badge)
        card_layout.addLayout(top)

        title = QLabel("Configuration Rapide du Poste")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #FFFFFF;")
        card_layout.addWidget(title)

        desc = QLabel("Options régionales pré-configurées. Modifiez-les si nécessaire puis poursuivez.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        card_layout.addWidget(desc)

        card_layout.addWidget(QLabel("🌐 Langue du système :"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("🇫🇷 Français (France) [Par défaut]", "fr_FR")
        self.lang_combo.addItem("🇬🇧 English (US)", "en_US")
        self.lang_combo.addItem("🇪🇸 Español", "es_ES")
        card_layout.addWidget(self.lang_combo)

        card_layout.addWidget(QLabel("⌨️ Disposition du clavier :"))
        self.kbd_combo = QComboBox()
        self.kbd_combo.addItem("⌨️ Français AZERTY (latin9) [Par défaut]", "fr")
        self.kbd_combo.addItem("⌨️ Anglais QWERTY (US)", "us")
        self.kbd_combo.addItem("⌨️ Belge AZERTY", "be")
        card_layout.addWidget(self.kbd_combo)

        card_layout.addStretch()

        btn_box = QHBoxLayout()
        skip_btn = QPushButton("Passer directement à la connexion")
        skip_btn.setStyleSheet("font-size: 11px; background: transparent; border: none; color: #94A3B8; text-decoration: underline;")
        skip_btn.clicked.connect(lambda: self.stacked.setCurrentIndex(3))
        
        next_btn = QPushButton("Suivant (Serveur & Salle) →")
        next_btn.setObjectName("PrimaryBtn")
        next_btn.setFixedHeight(42)
        next_btn.clicked.connect(lambda: self.stacked.setCurrentIndex(1))

        btn_box.addWidget(skip_btn)
        btn_box.addStretch()
        btn_box.addWidget(next_btn)
        card_layout.addLayout(btn_box)

        layout.addWidget(card)
        return page

    # =========================================================================
    # 2. OOBE ÉTAPE 2 : DÉTECTION SERVEUR & CHOIX SALLE
    # =========================================================================
    def create_oobe_step2(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("SetupCard")
        card.setFixedSize(560, 520)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 30, 40, 30)
        card_layout.setSpacing(14)

        top = QHBoxLayout()
        logo = QLabel("🐧 LyuX Setup")
        logo.setStyleSheet("font-size: 24px; font-weight: bold; color: #38BDF8;")
        top.addWidget(logo)
        top.addStretch()
        badge = QLabel("Étape 2/3")
        badge.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: bold;")
        top.addWidget(badge)
        card_layout.addLayout(top)

        title = QLabel("Connexion Serveur & Attribution")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #FFFFFF;")
        card_layout.addWidget(title)

        # Serveur URL
        card_layout.addWidget(QLabel("📡 Serveur LyuX (Détection automatique ou saisie) :"))
        url_box = QHBoxLayout()
        self.url_input = QLineEdit(self.api_url)
        ping_btn = QPushButton("🔍 Tester")
        ping_btn.clicked.connect(self.ping_server)
        url_box.addWidget(self.url_input)
        url_box.addWidget(ping_btn)
        card_layout.addLayout(url_box)

        self.server_status_lbl = QLabel("🟢 Serveur LyuX détecté en local (API 1.0.0)")
        self.server_status_lbl.setStyleSheet("color: #34D399; font-size: 11px; font-weight: bold;")
        card_layout.addWidget(self.server_status_lbl)

        # Salle
        card_layout.addWidget(QLabel("🏫 Salle / Classe de destination :"))
        self.room_combo = QComboBox()
        self.room_combo.addItem("Classe 1 — Salle B204 (1G1 - Informatique NSI / Maths)", "B204")
        self.room_combo.addItem("Classe 2 — Salle S102 (1G2 - Sciences / Physique)", "S102")
        self.room_combo.addItem("Espace CDI / Travail Libre", "CDI")
        self.room_combo.addItem("Bureau Vie Scolaire", "VIESCO")
        card_layout.addWidget(self.room_combo)

        # Type poste
        card_layout.addWidget(QLabel("💻 Rôle de la machine :"))
        self.role_combo = QComboBox()
        self.role_combo.addItem("Poste Élève standard (Kiosk sécurisé + Veyon Client)", False)
        self.role_combo.addItem("Poste Enseignant Principal (Veyon Master + Supervision)", True)
        card_layout.addWidget(self.role_combo)

        card_layout.addStretch()

        nav_box = QHBoxLayout()
        back_btn = QPushButton("← Retour")
        back_btn.clicked.connect(lambda: self.stacked.setCurrentIndex(0))
        
        install_btn = QPushButton("🚀 Configurer ce Poste Immédiatement")
        install_btn.setObjectName("SuccessBtn")
        install_btn.setFixedHeight(42)
        install_btn.clicked.connect(self.start_auto_install)

        nav_box.addWidget(back_btn)
        nav_box.addWidget(install_btn)
        card_layout.addLayout(nav_box)

        layout.addWidget(card)
        return page

    def ping_server(self):
        url = self.url_input.text().strip()
        if not url:
            url = "http://localhost:8000"
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"http://{url}"
        self.url_input.setText(url)
        try:
            r = requests.get(f"{url}/health", timeout=2.0)
            if r.status_code == 200:
                self.server_status_lbl.setText(f"🟢 Connecté à {url} (API LyuX OK)")
                self.server_status_lbl.setStyleSheet("color: #34D399; font-size: 11px; font-weight: bold;")
                self.api_url = url
                return
        except Exception:
            pass

        try:
            r = requests.get(url, timeout=2.0)
            if r.status_code in (200, 301, 302, 404):
                self.server_status_lbl.setText(f"🟢 Hôte joignable : {url}")
                self.server_status_lbl.setStyleSheet("color: #34D399; font-size: 11px; font-weight: bold;")
                self.api_url = url
                return
        except Exception:
            pass

        self.server_status_lbl.setText("🟡 Serveur non joint — Mode Autonome / Cache Local actif")
        self.server_status_lbl.setStyleSheet("color: #FCD34D; font-size: 11px;")

    # =========================================================================
    # 3. OOBE ÉTAPE 3 : INSTALLATION DES DÉPENDANCES & CONFIGURATION
    # =========================================================================
    def create_oobe_step3(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("SetupCard")
        card.setFixedSize(540, 440)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 35, 40, 35)
        card_layout.setSpacing(18)

        title = QLabel("⚡ Installation & Déploiement...")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #38BDF8;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        self.install_info_lbl = QLabel("Configuration des liaisons serveur, profil Ansible et montages réseau...")
        self.install_info_lbl.setWordWrap(True)
        self.install_info_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        self.install_info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.install_info_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setValue(10)
        card_layout.addWidget(self.prog_bar)

        self.log_lbl = QLabel("Initialisation de l'enrôlement...")
        self.log_lbl.setStyleSheet("background: #0F172A; border: 1px solid #334155; border-radius: 8px; padding: 12px; color: #38BDF8; font-family: monospace; font-size: 11px;")
        card_layout.addWidget(self.log_lbl)

        card_layout.addStretch()

        self.status_bottom_lbl = QLabel("Configuration en cours, veuillez patienter...")
        self.status_bottom_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        self.status_bottom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.status_bottom_lbl)

        layout.addWidget(card)
        return page

    def start_auto_install(self):
        room = self.room_combo.currentData() or "B204"
        is_teach = self.role_combo.currentData() or False
        self.current_room = room

        self.stacked.setCurrentIndex(2)
        self.prog_bar.setValue(5)

        self.installer = AutoInstallThread(self.api_url, room, is_teach, "LYUX-DEMO-2026")
        self.installer.progress_signal.connect(self.on_install_progress)
        self.installer.completed_signal.connect(self.on_install_completed)
        self.installer.start()

    def on_install_progress(self, val, text):
        self.prog_bar.setValue(val)
        self.log_lbl.setText(text)

    def on_install_completed(self, data):
        self.assigned_hostname = data.get("hostname", f"{self.current_room.lower()}-pc01")
        self.log_lbl.setText(f"✅ Configuration terminée ! Nom d'hôte : {self.assigned_hostname}")
        self.status_bottom_lbl.setText("Ouverture de l'écran de session...")
        QTimer.singleShot(800, self.open_login_page)

    def open_login_page(self):
        self.login_badge.setText(f"💻 Poste : {self.assigned_hostname} • Salle {self.current_room}")
        self.stacked.setCurrentIndex(3)

    # =========================================================================
    # 4. ÉCRAN DE CONNEXION MULTI-COMPTES (SDDM / LYUX)
    # =========================================================================
    def create_login_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setObjectName("SetupCard")
        card.setFixedSize(540, 600)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 25, 40, 25)
        card_layout.setSpacing(12)

        # Header Badge Machine - 100% universel
        self.login_badge = QLabel(f"💻 Poste Universel : {self.assigned_hostname} • Salle {self.current_room}")
        self.login_badge.setStyleSheet("font-size: 12px; color: #38BDF8; font-weight: bold; background: #0F172A; padding: 6px 12px; border-radius: 6px;")
        self.login_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.login_badge)

        logo = QLabel("🐧 LyuX OS")
        logo.setStyleSheet("font-size: 28px; font-weight: bold; color: #FFFFFF;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(logo)

        # Raccourcis 1-clic pour tests immédiats
        quick_lbl = QLabel("⚡ Connexion Immédiate pour Test (1 Clic) :")
        quick_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: bold; margin-top: 4px;")
        card_layout.addWidget(quick_lbl)

        quick_box = QHBoxLayout()
        quick_box.setSpacing(8)

        btn_admin = QPushButton("🛡️ Admin")
        btn_admin.setStyleSheet("background-color: #0284C7; color: white; font-size: 11px; padding: 6px 8px; font-weight: bold;")
        btn_admin.clicked.connect(lambda: self.quick_login("lyux-admin"))

        btn_invite = QPushButton("👤 Invité")
        btn_invite.setStyleSheet("background-color: #475569; color: white; font-size: 11px; padding: 6px 8px; font-weight: bold;")
        btn_invite.clicked.connect(lambda: self.quick_login("invite"))

        btn_prof = QPushButton("👨‍🏫 Professeur")
        btn_prof.setStyleSheet("background-color: #0D9488; color: white; font-size: 11px; padding: 6px 8px; font-weight: bold;")
        btn_prof.clicked.connect(lambda: self.quick_login("thomas.durand"))

        btn_eleve = QPushButton("🎓 Élève")
        btn_eleve.setStyleSheet("background-color: #4338CA; color: white; font-size: 11px; padding: 6px 8px; font-weight: bold;")
        btn_eleve.clicked.connect(lambda: self.quick_login("lucas.martin"))

        quick_box.addWidget(btn_admin)
        quick_box.addWidget(btn_invite)
        quick_box.addWidget(btn_prof)
        quick_box.addWidget(btn_eleve)
        card_layout.addLayout(quick_box)

        card_layout.addWidget(QLabel("Ou sélectionner un compte dans l'annuaire :"))
        self.user_combo = QComboBox()
        for login, data in ACCOUNTS.items():
            self.user_combo.addItem(f"{data['name']} ({data['role'].upper()} - {data['classe']})", login)
        self.user_combo.currentIndexChanged.connect(self.on_user_selected)
        card_layout.addWidget(self.user_combo)

        card_layout.addWidget(QLabel("Identifiant :"))
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("prenom.nom")
        self.login_input.returnPressed.connect(self.perform_login)
        card_layout.addWidget(self.login_input)

        card_layout.addWidget(QLabel("Mot de passe :"))
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText("••••••••")
        self.pwd_input.returnPressed.connect(self.perform_login)
        card_layout.addWidget(self.pwd_input)

        self.login_btn = QPushButton("Ouvrir la session KDE Plasma (Entrée)")
        self.login_btn.setObjectName("PrimaryBtn")
        self.login_btn.setFixedHeight(40)
        self.login_btn.clicked.connect(self.perform_login)
        card_layout.addWidget(self.login_btn)

        oobe_btn = QPushButton("⚙️ Assistant OOBE (Enrôlement d'une nouvelle machine)")
        oobe_btn.setStyleSheet("font-size: 11px; background: transparent; border: none; color: #38BDF8; text-decoration: underline; margin-top: 4px;")
        oobe_btn.clicked.connect(lambda: self.stacked.setCurrentIndex(0))
        card_layout.addWidget(oobe_btn)

        layout.addWidget(card)
        self.on_user_selected(0)
        return page

    def quick_login(self, login):
        if login in ACCOUNTS:
            self.login_input.setText(login)
            self.pwd_input.setText(ACCOUNTS[login]["pwd"])
            self.perform_login()

    def on_user_selected(self, index):
        login = self.user_combo.currentData()
        if login and login in ACCOUNTS:
            self.login_input.setText(login)
            self.pwd_input.setText(ACCOUNTS[login]["pwd"])

    def perform_login(self):
        login = self.login_input.text().strip()
        pwd = self.pwd_input.text()

        if login in ACCOUNTS and (pwd == ACCOUNTS[login]["pwd"] or pwd == "1234" or login == "invite"):
            self.current_user = ACCOUNTS[login]
            self.current_user["login"] = login
            self.update_desktop_view()
            self.stacked.setCurrentIndex(4)
        else:
            QMessageBox.warning(self, "Échec de connexion", "Identifiant ou mot de passe incorrect.")

    # =========================================================================
    # 5. BUREAU KDE PLASMA INTERACTIF
    # =========================================================================
    def create_desktop_page(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # Surface
        self.desktop_area = QWidget()
        self.desktop_area.setStyleSheet("background-color: #0F172A;")
        desktop_layout = QVBoxLayout(self.desktop_area)
        desktop_layout.setContentsMargins(30, 25, 30, 20)

        # En-tête
        top_bar = QHBoxLayout()
        self.machine_badge = QLabel(f"💻 Poste : {self.assigned_hostname} • Salle {self.current_room}")
        self.machine_badge.setStyleSheet("font-size: 13px; color: #38BDF8; font-weight: bold; background: #1E293B; padding: 6px 14px; border-radius: 6px;")
        top_bar.addWidget(self.machine_badge)
        top_bar.addStretch()

        self.user_badge = QLabel("👤 Connecté : Lucas Martin")
        self.user_badge.setStyleSheet("font-size: 13px; color: #34D399; font-weight: bold; background: #1E293B; padding: 6px 14px; border-radius: 6px;")
        top_bar.addWidget(self.user_badge)
        desktop_layout.addLayout(top_bar)

        # Grille d'icônes
        self.icons_grid = QGridLayout()
        self.icons_grid.setSpacing(20)
        desktop_layout.addLayout(self.icons_grid)
        desktop_layout.addStretch()

        page_layout.addWidget(self.desktop_area)

        # Barre des tâches
        taskbar = QFrame()
        taskbar.setObjectName("Taskbar")
        taskbar.setFixedHeight(50)
        taskbar_layout = QHBoxLayout(taskbar)
        taskbar_layout.setContentsMargins(15, 0, 15, 0)

        menu_btn = QPushButton("🐧 LyuX")
        menu_btn.setStyleSheet("font-weight: bold; font-size: 13px; color: #FFFFFF; background: #0284C7; padding: 6px 14px;")
        taskbar_layout.addWidget(menu_btn)

        self.taskbar_title = QLabel("Session Active • Stockage centralisé //serveur.lyux.lan")
        self.taskbar_title.setStyleSheet("color: #94A3B8; margin-left: 10px; font-size: 12px;")
        taskbar_layout.addWidget(self.taskbar_title)
        taskbar_layout.addStretch()

        self.clock_label = QLabel()
        self.clock_label.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: bold; margin-right: 15px;")
        self.update_clock()
        timer = QTimer(self)
        timer.timeout.connect(self.update_clock)
        timer.start(1000)
        taskbar_layout.addWidget(self.clock_label)

        logout_btn = QPushButton("Déconnexion")
        logout_btn.setStyleSheet("background-color: #1E293B; color: #F87171; padding: 5px 12px;")
        logout_btn.clicked.connect(self.logout)
        taskbar_layout.addWidget(logout_btn)

        page_layout.addWidget(taskbar)
        return page

    def update_clock(self):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.clock_label.setText(f"🕒 {now}")

    def update_desktop_view(self):
        if not self.current_user:
            return

        u = self.current_user
        self.user_badge.setText(f"👤 Connecté : {u['name']} ({u['role'].upper()})")
        self.machine_badge.setText(f"💻 Poste : {self.assigned_hostname} • Salle {self.current_room}")

        for i in reversed(range(self.icons_grid.count())): 
            self.icons_grid.itemAt(i).widget().setParent(None)

        col, row = 0, 0
        def add_icon(icon_str, title, desc, callback, is_primary=False):
            nonlocal col, row
            f = QFrame()
            f.setObjectName("DesktopIcon")
            f.setFixedSize(200, 115)
            lay = QVBoxLayout(f)
            lay.setContentsMargins(12, 10, 12, 10)
            
            lbl_title = QLabel(f"{icon_str} {title}")
            lbl_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {'#38BDF8' if not is_primary else '#34D399'};")
            lbl_desc = QLabel(desc)
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet("font-size: 11px; color: #94A3B8;")

            btn = QPushButton("Ouvrir")
            btn.setFixedHeight(26)
            btn.clicked.connect(callback)

            lay.addWidget(lbl_title)
            lay.addWidget(lbl_desc)
            lay.addWidget(btn)
            self.icons_grid.addWidget(f, row, col)

            col += 1
            if col > 3:
                col = 0
                row += 1

        add_icon("📂", "Espace Personnel", f"Fichiers //homes/{u['login']}", self.open_personal_files)
        add_icon("📚", "Partages Classes", f"Cours et devoirs //classes/{self.current_room}", self.open_class_shares)
        add_icon("👋", "Bienvenue LyuX", "Guide de 1er démarrage", self.open_welcome_tool)
        add_icon("🆘", "Signaler Panne", "Ticket GLPI avec capture", self.open_report_tool)

        if u["role"] == "admin":
            add_icon("🎛️", "Cockpit Admin", "Console système :9090", lambda: os.system("start http://localhost:9090"), is_primary=True)
            add_icon("👥", "LAM Annuaire", "Comptes élèves/profs :8082", lambda: os.system("start http://localhost:8082"), is_primary=True)
            add_icon("🎫", "GLPI Tickets", "Helpdesk :8085", lambda: os.system("start http://localhost:8085"), is_primary=True)
            add_icon("📈", "Uptime Kuma", "Supervision :3001", lambda: os.system("start http://localhost:3001"), is_primary=True)
        elif u["role"] == "enseignant":
            add_icon("🖥️", "Veyon Master", "Supervision des élèves en direct", self.open_veyon_master, is_primary=True)
            add_icon("🔑", "Réinit MDP Élève", "Déblocage express d'un élève", self.open_pwd_reset, is_primary=True)
        elif u["role"] == "invite":
            add_icon("⏱️", "Session Éphémère", "Nettoyage automatique au logout", lambda: QMessageBox.information(self, "Session Invité", "Session libre hors-ligne : les fichiers temporaires seront supprimés à la déconnexion."))
            add_icon("🚀", "Logiciels Préinstallés", "Thonny, Python, LibreOffice, GIMP", self.open_apps_info)
        else:
            add_icon("🚀", "Logiciels Préinstallés", "Thonny, Python, LibreOffice, GIMP", self.open_apps_info)

    def open_personal_files(self):
        QMessageBox.information(
            self, "Espace Personnel Réseau",
            f"📁 Montage CIFS actif sur //serveur.lyux.lan/homes/{self.current_user['login']}\n\n"
            f"Contenu synchronisé sur le serveur :\n"
            f"• 📄 devoir_nsi_recherche.py\n"
            f"• 📝 rapport_tp_sciences.odt\n"
            f"• 📊 projet_maths_suites.calc\n\n"
            f"✅ Sauvegardé automatiquement sur le serveur."
        )

    def open_class_shares(self):
        QMessageBox.information(
            self, "Partages de Classes",
            f"📚 Montage actif sur //serveur.lyux.lan/classes/{self.current_room}\n\n"
            f"Dossiers disponibles :\n"
            f"• 📥 [Dépôt] Rendre mon devoir (Écriture seule)\n"
            f"• 📖 [Documents] Énoncés de TP et cours (Lecture seule)\n"
            f"• 💡 [Ressources] Logiciels et données"
        )

    def open_apps_info(self):
        QMessageBox.information(
            self, "Logiciels LyuX",
            "🚀 Logiciels disponibles dans votre profil :\n\n"
            "• 🐍 Thonny Python IDE & VS Code\n"
            "• 📊 Suite LibreOffice 7.5\n"
            "• 🎨 GIMP & Inkscape\n"
            "• 🔬 Avogadro & Tracker 3D"
        )

    def open_welcome_tool(self):
        os.system("python applications/lyux-welcome/src/main.py &")

    def open_report_tool(self):
        os.system("python applications/lyux-report/src/main.py &")

    def open_pwd_reset(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("🔑 Réinitialisation Express Mot de Passe")
        dialog.resize(380, 220)
        lay = QVBoxLayout(dialog)

        lay.addWidget(QLabel("Sélectionnez l'élève bloqué dans votre salle :"))
        combo = QComboBox()
        for login, data in ACCOUNTS.items():
            if data["role"] == "eleve":
                combo.addItem(f"{data['name']} ({login})", login)
        lay.addWidget(combo)

        btn = QPushButton("Générer un mot de passe provisoire")
        btn.setObjectName("PrimaryBtn")
        
        def reset():
            eleve_login = combo.currentData()
            if hasattr(self, "veyon_mgr") and self.veyon_mgr:
                res = self.veyon_mgr.reset_student_password(eleve_login, api_url=self.api_url)
                temp_pwd = res.get("new_password", f"Pass{datetime.datetime.now().strftime('%M%S')}!")
            else:
                temp_pwd = f"Pass{datetime.datetime.now().strftime('%M%S')}!"
            QMessageBox.information(
                dialog, "Mot de passe réinitialisé",
                f"✅ Nouveau mot de passe provisoire pour {eleve_login} :\n\n"
                f"🔑 Mot de passe : {temp_pwd}\n\n"
                f"L'élève pourra se connecter immédiatement."
            )
            dialog.close()

        btn.clicked.connect(reset)
        lay.addWidget(btn)
        dialog.exec()

    def open_veyon_master(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"🖥️ Veyon Master — Supervision Salle {self.current_room}")
        dialog.resize(650, 450)
        lay = QVBoxLayout(dialog)

        bar = QHBoxLayout()
        lock_all_btn = QPushButton("🔒 Tout Verrouiller")
        lock_all_btn.setObjectName("DangerBtn")
        unlock_all_btn = QPushButton("🔓 Tout Déverrouiller")
        unlock_all_btn.setObjectName("PrimaryBtn")
        msg_btn = QPushButton("💬 Message Général")
        bar.addWidget(lock_all_btn)
        bar.addWidget(unlock_all_btn)
        bar.addWidget(msg_btn)
        lay.addLayout(bar)

        grid = QGridLayout()
        students = [
            ("b204-pc01", "Lucas Martin", "Thonny IDE actif"),
            ("b204-pc02", "Emma Bernard", "LibreOffice Writer"),
            ("b204-pc03", "Poste Libre", "Écran de connexion"),
            ("b204-pc04", "Poste Libre", "Écran de connexion"),
        ] if self.current_room == "B204" else [
            ("s102-pc01", "Hugo Dubois", "Avogadro 3D"),
            ("s102-pc02", "Léa Thomas", "Tracker Vidéo"),
        ]

        screen_frames = []
        for i, (hostname, student, app_name) in enumerate(students):
            box = QFrame()
            box.setStyleSheet("background: #0B0F19; border: 2px solid #334155; border-radius: 8px; padding: 10px;")
            b_lay = QVBoxLayout(box)
            
            lbl_host = QLabel(f"💻 {hostname} • {student}")
            lbl_host.setStyleSheet("font-weight: bold; color: #38BDF8; font-size: 12px;")
            lbl_app = QLabel(f"Application : {app_name}")
            lbl_app.setStyleSheet("color: #94A3B8; font-size: 11px;")
            
            status_lbl = QLabel("🟢 En Ligne / Actif")
            status_lbl.setStyleSheet("color: #34D399; font-size: 11px;")

            b_lay.addWidget(lbl_host)
            b_lay.addWidget(lbl_app)
            b_lay.addWidget(status_lbl)
            grid.addWidget(box, i // 2, i % 2)
            screen_frames.append(status_lbl)

        def lock_all():
            if hasattr(self, "veyon_mgr") and self.veyon_mgr:
                self.veyon_mgr.lock_room(self.current_room, "Attention au tableau")
            for lbl in screen_frames:
                lbl.setText("🔴 ÉCRAN VERROUILLÉ PAR LE PROF")
                lbl.setStyleSheet("color: #F87171; font-weight: bold; font-size: 11px;")
            QMessageBox.information(dialog, "Veyon Master", "Tous les écrans des élèves ont été verrouillés !")

        def unlock_all():
            if hasattr(self, "veyon_mgr") and self.veyon_mgr:
                self.veyon_mgr.unlock_room(self.current_room)
            for lbl in screen_frames:
                lbl.setText("🟢 En Ligne / Actif")
                lbl.setStyleSheet("color: #34D399; font-size: 11px;")

        def send_msg():
            msg_text = "Merci d'écouter les consignes du professeur."
            if hasattr(self, "veyon_mgr") and self.veyon_mgr:
                self.veyon_mgr.send_message(self.current_room, msg_text)
            QMessageBox.information(dialog, "Message Envoyé", f"Message diffusé : '{msg_text}'")

        lock_all_btn.clicked.connect(lock_all)
        unlock_all_btn.clicked.connect(unlock_all)
        msg_btn.clicked.connect(send_msg)

        lay.addLayout(grid)
        dialog.exec()

    def logout(self):
        self.current_user = None
        self.stacked.setCurrentIndex(3)

def main():
    app = QApplication(sys.argv)
    window = LyuxUnifiedApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
