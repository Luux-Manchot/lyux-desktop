import os
import getpass
import subprocess

def get_current_user_info():
    """Détecte l'utilisateur actuel, son nom complet et son groupe/rôle LyuX."""
    username = getpass.getuser()
    
    # Tentative d'obtention des groupes POSIX de l'utilisateur (Linux / Unix)
    groups = []
    try:
        import grp
        groups = [g.gr_name for g in grp.getgrall() if username in g.gr_mem]
        primary_gid = os.getgid()
        groups.append(grp.getgrgid(primary_gid).gr_name)
    except (ImportError, AttributeError, Exception):
        # Fallback commande standard ou environnement Windows / dev
        try:
            res = subprocess.run(["id", "-Gn", username], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                groups = res.stdout.strip().split()
            else:
                groups = ["eleves"]
        except Exception:
            groups = ["eleves"]

    # Détermination du rôle LyuX
    if "techniciens" in groups or "sudo" in groups or "wheel" in groups:
        role = "technicien"
        role_label = "Administrateur / Équipe Technique"
    elif "enseignants" in groups or "profs" in groups:
        role = "enseignant"
        role_label = "Enseignant"
    elif "administration" in groups or "viesco" in groups:
        role = "viesco"
        role_label = "Vie Scolaire / Administration"
    else:
        role = "eleve"
        role_label = "Élève"

    # Formatage du nom d'affichage à partir du login "prenom.nom"
    parts = username.split(".")
    if len(parts) >= 2:
        display_name = f"{parts[0].capitalize()} {parts[1].capitalize()}"
    else:
        display_name = username.capitalize()

    return {
        "username": username,
        "display_name": display_name,
        "role": role,
        "role_label": role_label,
        "groups": groups
    }
