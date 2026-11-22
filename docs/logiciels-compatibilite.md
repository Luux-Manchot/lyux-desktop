# 📊 Matrice de Compatibilité Logicielle & Équivalences

Ce document recense les logiciels couramment utilisés en lycée et détaille leur statut de compatibilité sous Linux ainsi que les alternatives sélectionnées pour le projet **LyuX (Opération Manchot)**.

**Légende :**
* ✅ **Natif Linux** (Disponible dans les dépôts ou paquets officiels)
* 🌐 **Dans le navigateur** (Accessible directement via Firefox / Chromium)
* ☕ **Multiplateforme** (Java, Qt, Python)
* 🍷 **Émulation / Wine** (À tester sur salle pilote)
* ❌ **Windows uniquement** (Nécessite machine virtuelle ou poste Windows dédié)

---

## 1. Bureautique & Outils Généraux

| Logiciel Windows | Statut | Solution LyuX | Remarques |
| :--- | :---: | :--- | :--- |
| **Microsoft Office (Word, Excel, PowerPoint)** | ❌ | **LibreOffice** / **OnlyOffice** ou **Office 365 Web** 🌐 | LibreOffice couvre 95% des besoins. |
| **Microsoft Access** | ❌ | **LibreOffice Base** / **SQLite** | Pour la NSI/SNT, préférer SQLite ou MariaDB. |
| **Adobe Acrobat Reader** | ❌ | **Okular** / **Evince** | Okular supporte l'annotation complète des PDF. |
| **Navigateurs (Chrome, Edge)** | ✅ | **Firefox ESR** / **Chromium** | Profils gérés centralement. |
| **Lecteur Vidéo & Audio** | ✅ | **VLC**, **Audacity** | Natifs et très performants. |

---

## 2. Mathématiques & Informatique (SNT, NSI)

| Logiciel Windows | Statut | Solution LyuX | Remarques |
| :--- | :---: | :--- | :--- |
| **EduPython / IDLE** | ❌ | **Thonny** / **VS Code** ✅ | Thonny est plus moderne et pédagogique qu'EduPython. |
| **GeoGebra** | ✅ | **GeoGebra Desktop** ou **Web** 🌐 | Fonctionnement parfait. |
| **Capytale / Basthon** | 🌐 | Navigateur Web | Utilisé massivement pour les cours de NSI. |
| **Xcas / Scilab / Octave** | ✅ | Paquets natifs Debian | Très stables. |
| **Cisco Packet Tracer** | ✅ | Client Linux officiel (Cisco) | Nécessite un compte Cisco NetAcad. |
| **Filius / MathGraph32** | ☕ | Exécution Java (OpenJDK) | Fonctionne sans modification. |

---

## 3. Physique-Chimie & SVT

| Logiciel Windows | Statut | Solution LyuX | Remarques |
| :--- | :---: | :--- | :--- |
| **Pymecavideo / Tracker** | ✅/☕ | Paquet natif ou binaire Java | Remplacement fluide pour l'analyse vidéo. |
| **Avogadro / Stellarium / Jmol** | ✅ | Paquets natifs Debian | Excellente compatibilité 3D. |
| **QGIS** | ✅ | Paquet natif SIG | Standard de l'industrie, très puissant. |
| **Régressi** | 🍷 | Test sous Wine | Résultats variables selon les versions. |
| **Pilotes d'acquisition (Sysam, Orphy, LatisPro)** | ❌ | **Postes Windows dédiés aux paillasses** | ⚠️ **Point d'attention majeur :** Les pilotes USB propriétaires n'existent pas sous Linux. |

---

## 4. Sciences de l'Ingénieur & STI2D (Logiciels Industriels)

> [!WARNING]
> C'est le domaine qui nécessite une stratégie mixte (Linux pour la majorité des postes, Windows ou VDI pour quelques salles spécialisées).

| Logiciel Spécialisé | Statut | Stratégie Recommandée |
| :--- | :---: | :--- |
| **SolidWorks / Inventor / CATIA** | ❌ | **Salle Windows conservée** ou **Bureau Virtuel GPU (VDI)**. *FreeCAD* ou *Onshape (web)* pour l'initiation. |
| **KiCad** | ✅ | Remplace avantageusement *Proteus / Multisim* pour l'électronique. |
| **FreeCAD / Blender** | ✅ | Natifs et performants pour la modélisation 3D et le rendu. |
| **Cura / PrusaSlicer** | ✅ | Impression 3D parfaitement supportée nativement. |
| **Automates (TIA Portal, Automgen)** | ❌ | Postes Windows dédiés aux bancs d'essai industriels. |
