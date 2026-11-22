# 👋 LyuX Welcome
> **Assistant de premier démarrage et guide utilisateur interactif (PyQt6).**

`lyux-welcome` est une application graphique moderne et intuitive qui s'ouvre automatiquement à la **première ouverture de session** d'un utilisateur sur un poste LyuX.

---

## ✨ Fonctionnalités

1. **Détection automatique du profil** :
   * Identifie si l'utilisateur est **Élève**, **Enseignant**, **Vie Scolaire** ou **Technicien**.
2. **Parcours guidé personnalisé** :
   * **Bienvenue & Identité** : Présentation du compte et de l'environnement de bureau.
   * **Gestion des Fichiers** : Explication claire de l'Espace Personnel (`~/Espace_Personnel`) et des dossiers partagés qui suivent l'utilisateur sur n'importe quel poste du lycée.
   * **Sécurité & Mot de Passe** : Rappel des règles de sécurité et bouton pour définir son mot de passe définitif.
   * **Outils Pédagogiques** : Présentation des logiciels selon le rôle (Veyon pour les profs, Thonny/LibreOffice pour les élèves).
   * **Assistance & Support** : Raccourci vers le widget de signalement d'incident `lyux-report`.
3. **Mémorisation** :
   * Dépose un marqueur `~/.config/lyux/.welcomed` pour ne pas réapparaître à chaque session.
   * Reste accessible à tout moment depuis le menu des applications (*"Guide de Bienvenue LyuX"*).

---

## 🚀 Lancement & Test Local

```bash
cd projects/lyux-welcome
pip install -r requirements.txt
python src/main.py
```

---

## 📂 Structure

```
lyux-welcome/
├── requirements.txt            # Dépendances Python (PyQt6)
├── lyux-welcome.desktop        # Lanceur XDG & Autostart
├── src/
│   ├── main.py                 # Fenêtre principale et navigation par onglets
│   └── role_detector.py        # Module de détection du rôle et de l'identité
└── README.md
```
