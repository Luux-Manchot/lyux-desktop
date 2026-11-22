# LyuX Applications

Suite logicielle et utilitaires graphiques pour les postes clients LyuX (Debian / KDE Plasma).

> Les dossiers sont nommés sans préfixe `lyux-` : `welcome/`, `station/`, `report/`, `enrollment/`. Les noms des fichiers `.desktop` et du service systemd conservent leur préfixe historique pour rester compatibles avec les scripts de déploiement.

## Applications

- **`station/`** : station de travail graphique PyQt6 (supervision Veyon, gestion des logiciels, réinitialisation de mot de passe, alertes).
- **`welcome/`** : écran d'accueil et premier démarrage adaptatif (détection du rôle élève / enseignant).
- **`report/`** : diagnostic matériel et signalement d'incidents connecté à GLPI (`POST /api/v1/tickets`).
- **`enrollment/`** : outil d'appairage et d'enrôlement via OTP. Chemin historique (preseed / Calamares) ; le nouvel installateur autonome enrôle directement via `POST /api/v1/parc/enroll`.

`lyux-cli` a été supprimé : il n'était utilisé que par les tests.

## Démarrage rapide

```bash
# Depuis ce dossier
python station/src/main.py

# Vérifier les métadonnées de la machine
python report/src/system_info.py
```

## Déploiement

Ces applications sont installées dans `/opt/lyux/apps/<nom>/` par la chaîne de build (voir [`../docs/METHODE_BUILD_CLIENT.md`](../docs/METHODE_BUILD_CLIENT.md)). Les lanceurs `.desktop` pointent vers `/opt/lyux/apps/welcome/src/main.py` et `/opt/lyux/apps/report/src/main.py`.
