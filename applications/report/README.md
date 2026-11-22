# 🆘 LyuX Report
> **Widget de signalement d'incidents instantané avec capture d'écran et intégration GLPI (PyQt6).**

`lyux-report` permet à n'importe quel élève ou enseignant de déclarer un dysfonctionnement matériel ou logiciel en quelques secondes directement depuis son bureau.

---

## ✨ Fonctionnalités

1. **Pré-remplissage automatique des données techniques** :
   * Nom d'hôte de la machine (ex: `B204-03`)
   * Salle et emplacement
   * Identifiant de l'utilisateur connecté
   * Adresse IP locale et date/heure précise
   * Version du système d'exploitation et charge CPU/Mémoire
2. **Formulaire simplifié** :
   * Choix de la catégorie : *Écran / Affichage*, *Logiciel / Application*, *Clavier / Souris*, *Impression*, *Compte / Mot de passe*, *Autre*.
   * Zone de texte pour décrire brièvement le problème.
   * Case à cocher pour joindre automatiquement une **capture d'écran** de l'anomalie.
3. **Transmission instantanée** :
   * Envoi direct du ticket vers l'API REST de **GLPI** ou l'API centrale **LyuX Control**.
   * Affichage immédiat du numéro de ticket attribué à l'utilisateur pour le suivi.

---

## 🚀 Lancement & Test Local

```bash
cd projects/lyux-report
pip install -r requirements.txt
python src/main.py
```

---

## 📂 Structure

```
lyux-report/
├── requirements.txt            # Dépendances Python (PyQt6, requests)
├── lyux-report.desktop         # Lanceur XDG
├── src/
│   ├── main.py                 # Interface graphique PyQt6
│   ├── system_info.py          # Collecte des métadonnées système et réseau
│   └── glpi_client.py          # Client API REST GLPI
└── README.md
```
