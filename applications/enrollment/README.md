# ⚡ LyuX Enrollment
> **Assistant d'enrôlement et d'initialisation de machine par clé USB minimale ou démarrage réseau PXE.**

`enrollment` est le point d'entrée exécuté lors du premier démarrage d'un poste vierge (ou réinstallé). La clé USB ne contient presque rien : c'est le serveur LyuX de l'établissement qui lui dicte son identité, ses droits et ses logiciels.

> Chemin historique : le nouvel installateur autonome (`lyux-installer.sh`) enrôle directement via `POST /api/v1/parc/enroll`. Ce module reste utile pour l'ancien flux preseed/Calamares.

---

## 🔄 Déroulement de l'enrôlement (Annexe A.2)

```mermaid
sequenceDiagram
    participant USB as 💻 Poste Vierge (USB LyuX)
    participant API as 🌐 LyuX Control API
    participant GIT as ⚙️ Dépôt Ansible Local

    USB->>API: 1. Détection du serveur & Test connexion
    USB->>API: 2. Envoi du code OTP + Specs Hardware (MAC, RAM, CPU)
    API-->>USB: 3. Réponse : Hostname (B204-03) + Profil de salle (NSI)
    USB->>USB: 4. Application du nom d'hôte local
    USB->>GIT: 5. Exécution ansible-pull (Profil NSI)
    GIT-->>USB: 6. Installation des logiciels & jonction domaine
    USB->>USB: 7. Redémarrage du poste prêt à l'emploi
```

---

## 🚀 Utilisation & Test Manuel

```bash
cd lyux-desktop/applications/enrollment
pip install -r requirements.txt
python src/enroll.py --server http://192.168.100.10:8000 --otp LYUX-DEMO-2026 --room B204
```

---

## 📂 Structure

```
enrollment/
├── requirements.txt            # Dépendances (requests, rich/colorama)
├── systemd/
│   └── lyux-enrollment.service # Service de démarrage automatique sur l'ISO
├── src/
│   ├── enroll.py               # Script principal d'enrôlement
│   └── hardware.py             # Collecte des adresses MAC, RAM et CPU
└── README.md
```
