# Comment créer un poste LyuX Client

Procédure opérationnelle, de l'ISO à la machine installée. Pour **construire l'ISO**, voir [METHODE_BUILD_CLIENT.md](METHODE_BUILD_CLIENT.md).

## 0. Prérequis

- Le **serveur LyuX est allumé** et son API répond : `curl http://192.168.10.1:8000/api/v1/parc/status`. Sans lui, l'installateur refuse de continuer (les bâtiments et les salles viennent du serveur).
- Une ISO `lyux-client-autonomous-installer.iso` produite dans `lyux-desktop/build/`.
- Une VM (VirtualBox/Vagrant) ou une machine physique avec disque vierge, amorçage BIOS ou UEFI.

## 1. Démarrer l'installateur

1. Créer la VM : 2 Go de RAM, 2 vCPU, disque de 25 Go minimum.
2. Attacher l'ISO comme lecteur optique, démarrer.
3. L'installateur se lance **automatiquement sur `/dev/tty1`** via `lyux-installer.service`, avec un repli sur `/root/.profile` si le service échoue. Aucun menu à choisir : le bootloader démarre directement.

## 2. Répondre aux questions de l'assistant

L'assistant `lyux-installer.sh` enchaîne les écrans suivants :

| Étape | Ce qui se passe | Ce que tu fais |
| :--- | :--- | :--- |
| 1. Bienvenue | Message d'accueil | Entrée |
| 2. Serveur central | Probe d'IP sur le réseau `192.168.10.0/24` puis `GET /api/v1/parc/status` | Vérifier l'IP affichée, Entrée ; si échec, l'assistant reboucle |
| 3. Bâtiment | `GET /api/v1/buildings` | Choisir le bâtiment dans la liste |
| 4. Salle | `GET /api/v1/rooms` | Choisir la salle |
| 5. Nom du poste | `GET /api/v1/enroll/suggest-hostname?room_id=<id>` | Accepter le nom suggéré ou le modifier |
| 6. Réseau | Choix DHCP ou IP statique | En statique : IP, masque `/24`, passerelle = IP serveur, DNS = serveur + `1.1.1.1` |
| 7. Disque | Liste des disques détectés | Choisir le disque cible (**tout son contenu sera effacé**) |
| 8. Récapitulatif | Serveur, bâtiment, salle, nom, réseau, disque | Confirmer pour lancer l'installation |

## 3. Ce que fait le déploiement

Une fois confirmé, l'installateur (jauge de progression) :

1. Écrit la table de partitions **MBR** (`parted`) et formate une partition **`ext4`** unique étiquetée `LYUX_ROOT`.
2. Cherche le SquashFS dans l'ordre : `/run/live/medium/live/filesystem.squashfs`, `/live/…`, `/cdrom/live/…`, `/opt/lyux/lyux-master.squashfs`, puis extrait avec `unsquashfs`.
3. Configure le système : hostname, `/etc/hosts`, `/etc/fstab`, réseau, suppression des services spécifiques à la VM de capture, `RESUME=none`.
4. Écrit les métadonnées :
   - `/etc/lyux/enrollment.json` (hostname, bâtiment, salle, IP du serveur, mode réseau, IP, date)
   - `/etc/lyux/version` (`LYUX_VERSION`, `LYUX_BUILD`, `LYUX_EDITION=Client`, base Debian)
   - `/etc/os-release` personnalisé (`NAME="LyuX Client OS"`, `SUPPORT_URL` vers le serveur)
   - `/usr/local/bin/lyux-info` pour afficher ces infos en console
5. Installe **GRUB** (`grub-install --target=i386-pc`) avec le bon UUID racine, active `graphical.target` et SDDM.
6. Prévient le serveur : `POST /api/v1/parc/enroll` avec hostname / bâtiment / salle / mode réseau / IP.
7. Affiche l'écran final puis **éteint la machine**.

## 4. Premiers contrôles

Retirer l'ISO, redémarrer, puis vérifier sur le poste :

```bash
lyux-info                      # version + métadonnées d'enrôlement
hostnamectl                    # nom du poste attendu
ip a                           # IP DHCP ou statique conforme au choix
systemctl status sddm          # écran de connexion actif
systemctl list-timers          # lyux-app-sync.timer et lyux-storage-manager.timer
ls -l /home                    # liens vers /srv/samba/homes/<user>
```

Côté serveur : le poste doit apparaître dans le parc avec le bon bâtiment/salle (API `/api/v1/parc` ou interface d'administration).

Vérifications graphiques attendues : KDE Plasma verrouillé (Discover masqué), lanceurs *Ma Classe* et *Casiers d'échange & Devoirs* présents dans Dolphin, liste des utilisateurs masquée sur SDDM.

## 5. Dépannage rapide

| Symptôme | Cause probable | Action |
| :--- | :--- | :--- |
| L'assistant boucle sur « serveur introuvable » | API `:8000` inaccessible ou IP probe incorrecte | Vérifier le serveur et le réseau `192.168.10.0/24` |
| « Aucun fichier SquashFS trouvé » | ISO mal construite | Relancer `build-autonomous-iso.sh` puis `create-overlay-iso.sh` **dans cet ordre** |
| « unsquashfs introuvable » | Overlay incomplet | Vérifier `zz-installer.squashfs` dans `build/` de l'ISO |
| Le poste ne boot pas après installation | GRUB ou UUID racine erroné | Réinstaller en vérifiant `grub-install` dans le log `/var/log/lyux-install.log` (sur le live) |
| Le poste n'apparaît pas dans le parc | `POST /api/v1/parc/enroll` échoué | Vérifier le log d'installation et la connectivité vers `:8000` |

## 6. Point à corriger dans le code actuel

`lyux-installer.sh` écrit encore `LYUX_BASE="Debian GNU/Linux 13 (Trixie)"` alors que le README de `lyux-iso-builder` annonce Debian 12 Bookworm. Aligner les deux avant la prochaine release (le guide de build part sur Debian 12 + KDE).

De même, les mots de passe présents dans `capture-master.sh` et les anciens scripts de test doivent être remplacés par des variables d'environnement ou un coffre Ansible Vault.
