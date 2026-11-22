# 🐧 LyuX Workstation & OS Interactive Suite
> **Environnement de bureau complet et interactif LyuX (KDE Plasma & Outils Scolaires).**

Ce projet fournit l'interface complète de test et d'exploitation du poste de travail **LyuX**.  
Il permet de tester immédiatement, sur votre écran, l'ensemble des scénarios de la vie d'un lycée sans attendre 30 minutes d'installation de VM :

---

## 🌟 Ce qui est Embarqué & Testable en 1 Clic

1. **🔐 Écran de Connexion (Display Manager)** :
   * Sélecteur de profil instantané : **Élèves 1G1 (B204)**, **Élèves 1G2 (S102)**, **Enseignants**, **Vie Scolaire**, **Direction**.
2. **🖥️ Bureau LyuX (Style KDE Plasma Verrouillé)** :
   * Barre des tâches moderne en bas, menu des applications, date/heure et indicateurs réseau.
   * **Espace Personnel Réseau** (`~/Espace_Personnel`) avec simulation de montage transparent.
   * **Partages de Classes** (`~/Partages_Classes`) avec boîte de dépôt de devoirs.
3. **👨‍🏫 Console Enseignant (Supervision Veyon)** :
   * Visualisation en temps réel des écrans des élèves de la classe (B204 ou S102).
   * Verrouillage des écrans des élèves en 1 clic.
   * Réinitialisation de mot de passe élève express en 1 clic.
4. **🆘 Widget Helpdesk (`lyux-report`)** :
   * Création instantanée de tickets vers l'API serveur avec capture d'écran.
5. **⚡ Enrôlement Express Nouveau PC** :
   * Attribution de salle, nom d'hôte automatique et profil de matière en 5 secondes.

---

## 🚀 Lancement Immédiat

```bash
cd projects/lyux-station
python src/main.py
```
