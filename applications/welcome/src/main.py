#!/usr/bin/env python3
"""
LyuX Welcome — Assistant de premier démarrage et guide utilisateur (KDE Light Theme)
Opération Manchot — Établissements Scolaires
"""
import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame, QCheckBox, QScrollArea
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QPixmap

from role_detector import get_current_user_info


def make_card(icon_name: str, title: str, description: str, badge_text: str = None, accent_color: str = "#2563EB") -> QFrame:
    """Crée une carte visuelle claire et moderne avec une icône Breeze."""
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
        }}
    """)
    layout = QHBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(16)

    # Icône
    icon_label = QLabel()
    icon = QIcon.fromTheme(icon_name)
    if not icon.isNull():
        icon_label.setPixmap(icon.pixmap(QSize(36, 36)))
    else:
        # Fallback icône standard
        icon_label.setPixmap(QIcon.fromTheme("dialog-information").pixmap(QSize(36, 36)))
    icon_label.setFixedSize(40, 40)
    icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(icon_label)

    # Textes
    text_layout = QVBoxLayout()
    text_layout.setSpacing(3)
    text_layout.setContentsMargins(0, 0, 0, 0)

    title_box = QHBoxLayout()
    title_box.setSpacing(8)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: #0F172A; border: none;")
    title_box.addWidget(title_lbl)

    if badge_text:
        badge = QLabel(badge_text)
        badge.setStyleSheet(f"""
            background-color: #EFF6FF;
            color: {accent_color};
            border: 1px solid #BFDBFE;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 11px;
            font-weight: 600;
        """)
        title_box.addWidget(badge)
    title_box.addStretch()

    desc_lbl = QLabel(description)
    desc_lbl.setWordWrap(True)
    desc_lbl.setStyleSheet("font-size: 12px; color: #475569; border: none; line-height: 1.4;")

    text_layout.addLayout(title_box)
    text_layout.addWidget(desc_lbl)
    layout.addLayout(text_layout)

    return card


class LyuxWelcomeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.user_info = get_current_user_info()
        self.setWindowTitle("Bienvenue sur LyuX — Opération Manchot")
        self.resize(820, 560)
        self.setMinimumSize(780, 520)

        # Thème Clair (Light Theme) Moderne & Pro
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F8FAFC;
            }
            QWidget {
                font-family: 'Segoe UI', 'Ubuntu', 'Noto Sans', sans-serif;
            }
            QFrame#Sidebar {
                background-color: #FFFFFF;
                border-right: 1px solid #E2E8F0;
            }
            QFrame#BottomBar {
                background-color: #FFFFFF;
                border-top: 1px solid #E2E8F0;
            }
            QPushButton#NavBtn {
                background-color: transparent;
                color: #475569;
                border: none;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 13px;
                font-weight: 500;
                text-align: left;
            }
            QPushButton#NavBtn:hover {
                background-color: #F1F5F9;
                color: #0F172A;
            }
            QPushButton#NavBtn[active="true"] {
                background-color: #EFF6FF;
                color: #2563EB;
                font-weight: bold;
                border-left: 3px solid #2563EB;
            }
            QPushButton#PrimaryBtn {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 9px 20px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #1D4ED8;
            }
            QPushButton#PrimaryBtn:disabled {
                background-color: #CBD5E1;
                color: #94A3B8;
            }
            QPushButton#SecondaryBtn {
                background-color: #FFFFFF;
                color: #334155;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 9px 18px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: #F8FAFC;
                border-color: #94A3B8;
            }
            QPushButton#SecondaryBtn:disabled {
                color: #CBD5E1;
                border-color: #E2E8F0;
            }
            QCheckBox {
                color: #475569;
                font-size: 13px;
                spacing: 8px;
            }
        """)

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ======================================================================
        # 1. Barre Latérale (Sidebar)
        # ======================================================================
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 24, 18, 20)
        sidebar_layout.setSpacing(8)

        # En-tête de la marque
        brand_box = QHBoxLayout()
        brand_box.setSpacing(12)
        brand_icon = QLabel()
        app_icon = QIcon.fromTheme("distributor-logo-debian")
        if app_icon.isNull():
            app_icon = QIcon.fromTheme("computer")
        brand_icon.setPixmap(app_icon.pixmap(QSize(32, 32)))
        brand_icon.setFixedSize(36, 36)

        brand_text_box = QVBoxLayout()
        brand_text_box.setSpacing(0)
        brand_title = QLabel("LyuX OS")
        brand_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #0F172A;")
        brand_sub = QLabel("Opération Manchot")
        brand_sub.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 500;")
        brand_text_box.addWidget(brand_title)
        brand_text_box.addWidget(brand_sub)

        brand_box.addWidget(brand_icon)
        brand_box.addLayout(brand_text_box)
        brand_box.addStretch()
        sidebar_layout.addLayout(brand_box)
        sidebar_layout.addSpacing(16)

        # Boutons de navigation
        self.step_buttons = []
        nav_items = [
            ("user-home", "1. Bienvenue"),
            ("folder-cloud", "2. Vos Fichiers"),
            ("applications-education", "3. Vos Outils"),
            ("security-high", "4. Charte & Règles"),
            ("system-help", "5. Assistance")
        ]

        for i, (icon_name, text) in enumerate(nav_items):
            btn = QPushButton(text)
            btn.setObjectName("NavBtn")
            icon = QIcon.fromTheme(icon_name)
            if not icon.isNull():
                btn.setIcon(icon)
                btn.setIconSize(QSize(18, 18))
            btn.clicked.connect(lambda checked, idx=i: self.stacked_widget.setCurrentIndex(idx))
            self.step_buttons.append(btn)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # Profil utilisateur en bas de sidebar
        user_card = QFrame()
        user_card.setStyleSheet("""
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
        """)
        user_layout = QHBoxLayout(user_card)
        user_layout.setContentsMargins(10, 10, 10, 10)
        user_layout.setSpacing(10)

        user_icon = QLabel()
        u_ico = QIcon.fromTheme("user-identity")
        if u_ico.isNull():
            u_ico = QIcon.fromTheme("preferences-desktop-user")
        user_icon.setPixmap(u_ico.pixmap(QSize(28, 28)))
        user_icon.setFixedSize(30, 30)

        user_info_layout = QVBoxLayout()
        user_info_layout.setSpacing(2)
        user_info_layout.setContentsMargins(0, 0, 0, 0)

        user_name_lbl = QLabel(self.user_info['display_name'])
        user_name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #0F172A; border: none;")
        user_role_lbl = QLabel(self.user_info['role_label'])
        user_role_lbl.setStyleSheet("font-size: 11px; color: #2563EB; font-weight: 600; border: none;")

        user_info_layout.addWidget(user_name_lbl)
        user_info_layout.addWidget(user_role_lbl)

        user_layout.addWidget(user_icon)
        user_layout.addLayout(user_info_layout)
        sidebar_layout.addWidget(user_card)

        main_layout.addWidget(sidebar)

        # ======================================================================
        # 2. Zone de Contenu Principal (Pages)
        # ======================================================================
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(35, 30, 35, 20)
        content_layout.setSpacing(15)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.create_welcome_page())
        self.stacked_widget.addWidget(self.create_files_page())
        self.stacked_widget.addWidget(self.create_tools_page())
        self.stacked_widget.addWidget(self.create_rules_page())
        self.stacked_widget.addWidget(self.create_help_page())
        self.stacked_widget.currentChanged.connect(self.update_nav_buttons)

        content_layout.addWidget(self.stacked_widget)

        # ======================================================================
        # 3. Barre Inférieure de Navigation
        # ======================================================================
        bottom_bar = QFrame()
        bottom_bar.setObjectName("BottomBar")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(20, 14, 20, 14)

        self.dont_show_again = QCheckBox("Ne plus afficher au démarrage")
        self.dont_show_again.setChecked(True)
        bottom_layout.addWidget(self.dont_show_again)
        bottom_layout.addStretch()

        self.prev_btn = QPushButton("Précédent")
        self.prev_btn.setObjectName("SecondaryBtn")
        icon_prev = QIcon.fromTheme("go-previous")
        if not icon_prev.isNull():
            self.prev_btn.setIcon(icon_prev)
        self.prev_btn.clicked.connect(self.go_prev)
        bottom_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Suivant")
        self.next_btn.setObjectName("PrimaryBtn")
        icon_next = QIcon.fromTheme("go-next")
        if not icon_next.isNull():
            self.next_btn.setIcon(icon_next)
        self.next_btn.clicked.connect(self.go_next)
        bottom_layout.addWidget(self.next_btn)

        content_layout.addWidget(bottom_bar)
        main_layout.addWidget(content_container)

        self.update_nav_buttons(0)

    # --------------------------------------------------------------------------
    # Pages de Contenu
    # --------------------------------------------------------------------------
    def create_welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel(f"Bienvenue, {self.user_info['display_name']} !")
        header.setStyleSheet("font-size: 24px; font-weight: 800; color: #0F172A;")
        sub = QLabel("Votre session sur le système d'exploitation libre LyuX est configurée et prête pour le travail.")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 13px; color: #64748B; margin-bottom: 8px;")

        layout.addWidget(header)
        layout.addWidget(sub)

        # Cartes visuelles
        layout.addWidget(make_card(
            "utilities-system-monitor",
            "Environnement Rapide & Moderne",
            "LyuX s'appuie sur Debian et KDE Plasma pour offrir un bureau stable, léger et fluide pour toutes vos activités scolaires."
        ))

        layout.addWidget(make_card(
            "folder-cloud",
            "Votre Session Partout au Lycée",
            "Installez-vous sur n'importe quel ordinateur d'une salle de cours, connectez-vous avec votre identifiant et retrouvez vos fichiers intacts."
        ))

        layout.addWidget(make_card(
            "security-high",
            "Sécurité & Protection des Données (RGPD)",
            "Vos informations restent hébergées localement au sein de l'établissement dans le strict respect des normes de l'Éducation Nationale."
        ))

        layout.addStretch()
        return page

    def create_files_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("Où sont enregistrés vos fichiers ?")
        header.setStyleSheet("font-size: 24px; font-weight: 800; color: #0F172A;")
        sub = QLabel("Toute votre session personnelle est synchronisée et sauvegardée en continu.")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 13px; color: #64748B; margin-bottom: 8px;")

        layout.addWidget(header)
        layout.addWidget(sub)

        # Carte 1 : Sauvegarde automatique
        layout.addWidget(make_card(
            "folder-network",
            "Sauvegarde Automatique sur le Serveur Central",
            "Tous vos dossiers personnels (Bureau, Documents, Téléchargements...) sont enregistrés directement sur le serveur du lycée. "
            "Même si un ordinateur physique est réinitialisé, vous ne perdez aucun document.",
            badge_text="Actif & Protégé",
            accent_color="#15803D"
        ))

        # Carte 2 : Distribution & Devoirs
        layout.addWidget(make_card(
            "document-send",
            "Échange de Documents & Devoirs",
            "Un module direct sera activé très prochainement pour permettre aux enseignants de distribuer les supports de cours "
            "et aux élèves de rendre leurs travaux en toute confidentialité.",
            badge_text="Bientôt Disponible",
            accent_color="#B45309"
        ))

        layout.addStretch()
        return page

    def create_tools_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("Vos Outils de Travail")
        header.setStyleSheet("font-size: 24px; font-weight: 800; color: #0F172A;")
        sub = QLabel(f"Applications préconfigurées pour votre profil ({self.user_info['role_label']}) :")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 13px; color: #64748B; margin-bottom: 8px;")

        layout.addWidget(header)
        layout.addWidget(sub)

        if self.user_info['role'] == 'enseignant':
            layout.addWidget(make_card(
                "preferences-desktop-display",
                "Supervision de Classe (Veyon Master)",
                "Visualisez les écrans des élèves en direct, verrouillez la classe pour capter l'attention ou projetez votre démonstration.",
                badge_text="Pédagogie"
            ))
            layout.addWidget(make_card(
                "dialog-password",
                "Réinitialisation Rapide des Mots de Passe",
                "Débloquez un élève qui a oublié son mot de passe en quelques secondes via le raccourci dédié sur votre bureau.",
                badge_text="Gestion"
            ))
            layout.addWidget(make_card(
                "libreoffice-writer",
                "Bureautique & Pronote",
                "Suite LibreOffice complète (Writer, Calc, Impress) et accès direct aux portails de notes et de compétences de l'établissement."
            ))
        elif self.user_info['role'] in ['viesco', 'technicien']:
            layout.addWidget(make_card(
                "system-software-install",
                "Administration & Gestion du Parc",
                "Surveillance des postes, remontée d'incidents GLPI et synchronisation automatique des logiciels via Cockpit.",
                badge_text="Technique"
            ))
            layout.addWidget(make_card(
                "libreoffice-calc",
                "Bureautique & Outils Administratifs",
                "Outils complets de traitement de données, feuilles de calcul et communication interne de l'établissement."
            ))
        else: # Élève
            layout.addWidget(make_card(
                "libreoffice-writer",
                "Bureautique Complète (LibreOffice)",
                "Tous les outils pour rédiger des comptes rendus, faire des calculs et préparer vos exposés (Writer, Calc, Impress)."
            ))
            layout.addWidget(make_card(
                "applications-development",
                "Sciences & Programmation (SNT / NSI)",
                "Python 3, Thonny, Visual Studio Code, GeoGebra, Tracker et logiciels scientifiques prêts à l'emploi."
            ))
            layout.addWidget(make_card(
                "firefox",
                "Internet & Espace Numérique (ENT)",
                "Navigateur Firefox configuré avec vos favoris lycée, l'accès direct à Pronote et aux manuels scolaires."
            ))

        layout.addStretch()
        return page

    def create_rules_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("Charte Informatique & Bonnes Pratiques")
        header.setStyleSheet("font-size: 24px; font-weight: 800; color: #0F172A;")
        sub = QLabel("Le respect de quelques règles simples garantit un environnement de travail de qualité pour tous :")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 13px; color: #64748B; margin-bottom: 8px;")

        layout.addWidget(header)
        layout.addWidget(sub)

        layout.addWidget(make_card(
            "dialog-password",
            "Compte Strictement Personnel",
            "Ne donnez jamais votre mot de passe à un camarade et pensez à vous déconnecter avant de quitter la salle."
        ))

        layout.addWidget(make_card(
            "computer",
            "Respect des Équipements",
            "Prenez soin du matériel informatique (souris, claviers, écrans, câbles). Ne branchez pas d'appareils non autorisés."
        ))

        layout.addWidget(make_card(
            "security-high",
            "Usage Pédagogique & Filtrage",
            "L'accès au réseau est destiné aux activités scolaires. Les connexions font l'objet d'un filtrage et d'un journal réglementaire."
        ))

        # Case de validation charte
        ack_box = QFrame()
        ack_box.setStyleSheet("""
            QFrame {
                background-color: #F1F5F9;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
            }
        """)
        ack_layout = QHBoxLayout(ack_box)
        ack_layout.setContentsMargins(14, 10, 14, 10)

        self.rules_checkbox = QCheckBox("J'ai pris connaissance de la charte informatique de l'établissement")
        self.rules_checkbox.setStyleSheet("font-size: 13px; font-weight: 600; color: #0F172A;")
        self.rules_checkbox.stateChanged.connect(lambda: self.update_nav_buttons(self.stacked_widget.currentIndex()))
        ack_layout.addWidget(self.rules_checkbox)

        layout.addWidget(ack_box)
        layout.addStretch()
        return page

    def create_help_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QLabel("Besoin d'aide ?")
        header.setStyleSheet("font-size: 24px; font-weight: 800; color: #0F172A;")
        sub = QLabel("L'équipe informatique est à votre disposition en cas d'incident.")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 13px; color: #64748B; margin-bottom: 8px;")

        layout.addWidget(header)
        layout.addWidget(sub)

        layout.addWidget(make_card(
            "help-browser",
            "Signaler un Problème en 1 Clic",
            "Une panne matérielle (souris, écran, clavier) ou un logiciel manquant ? "
            "Cliquez sur « Signaler un problème » sur le bureau pour envoyer un ticket automatique avec la référence de la salle et du PC."
        ))

        layout.addWidget(make_card(
            "dialog-information",
            "Tout est prêt !",
            "Vous pouvez dès maintenant commencer à travailler. Cliquez sur le bouton ci-dessous pour ouvrir votre session."
        ))

        layout.addStretch()
        return page

    # --------------------------------------------------------------------------
    # Navigation & Actions
    # --------------------------------------------------------------------------
    def update_nav_buttons(self, index):
        self.prev_btn.setEnabled(index > 0)
        is_last = (index == self.stacked_widget.count() - 1)

        if is_last:
            self.next_btn.setText("Commencer à travailler 🚀")
            self.next_btn.setIcon(QIcon())
            # Requiert que la charte soit acceptée
            self.next_btn.setEnabled(self.rules_checkbox.isChecked())
        else:
            self.next_btn.setText("Suivant")
            icon_next = QIcon.fromTheme("go-next")
            if not icon_next.isNull():
                self.next_btn.setIcon(icon_next)
            self.next_btn.setEnabled(True)

        for i, btn in enumerate(self.step_buttons):
            if i == index:
                btn.setProperty("active", "true")
            else:
                btn.setProperty("active", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def go_prev(self):
        current = self.stacked_widget.currentIndex()
        if current > 0:
            self.stacked_widget.setCurrentIndex(current - 1)

    def go_next(self):
        current = self.stacked_widget.currentIndex()
        if current < self.stacked_widget.count() - 1:
            self.stacked_widget.setCurrentIndex(current + 1)
        else:
            self.finish()

    def finish(self):
        if self.dont_show_again.isChecked():
            config_dir = Path.home() / ".config" / "lyux"
            config_dir.mkdir(parents=True, exist_ok=True)
            marker = config_dir / ".welcomed"
            marker.write_text("1")
        self.close()


def main():
    app = QApplication(sys.argv)
    window = LyuxWelcomeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
