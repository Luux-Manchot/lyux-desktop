#!/usr/bin/env python3
"""
LyuX Enrollment CLI — Outil d'enrôlement et d'attribution de poste
Opération Manchot — Architecture Lycée
"""

import sys
import os
import json
import argparse
import subprocess
import requests
from pathlib import Path

# Fix universel d'encodage
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

try:
    from hardware import get_hardware_fingerprint
except ImportError:
    get_hardware_fingerprint = lambda: {"mac_address": "52:54:00:12:34:56", "serial_number": "SN-DEMO", "cpu_info": "x86_64", "ram_mb": 4096}

try:
    from discovery import discover_lyux_server
except ImportError:
    discover_lyux_server = lambda: (False, "http://127.0.0.1:8000", {})

console = Console(highlight=False)

def check_server_enrollment_allowed(server_url: str) -> bool:
    try:
        r = requests.get(f"{server_url}/api/v1/settings", timeout=5)
        if r.status_code == 200:
            return bool(r.json().get("enrollment_enabled", False))
    except Exception:
        pass
    return False

def get_buildings(server_url: str):
    try:
        r = requests.get(f"{server_url}/api/v1/buildings", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

def get_rooms(server_url: str, building_id: str = None):
    try:
        url = f"{server_url}/api/v1/rooms"
        if building_id:
            url += f"?building_id={building_id}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

def get_suggested_hostname(server_url: str, room_id: str, building_id: str = None) -> str:
    try:
        url = f"{server_url}/api/v1/enroll/suggest-hostname?room_id={room_id}"
        if building_id:
            url += f"&building_id={building_id}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return r.json().get("suggested_hostname", f"{room_id}-PC01")
    except Exception:
        pass
    return f"{room_id}-PC01"

def check_hostname_available(server_url: str, hostname: str) -> bool:
    try:
        r = requests.post(f"{server_url}/api/v1/enroll/check-hostname", json={"hostname": hostname}, timeout=5)
        if r.status_code == 200:
            return bool(r.json().get("available", False))
    except Exception:
        pass
    return True

def run_enrollment(server_url: str, building_id: str, room_id: str, hostname: str, is_teacher: bool = False):
    console.print(Panel.fit(
        "[bold cyan]LyuX Enrollment — Initialisation du Poste Client[/bold cyan]\n"
        "[dim]Opération Manchot — Affectation Bâtiment & Salle[/dim]",
        border_style="cyan"
    ))

    # 1. Vérification du verrou d'enrôlement sur le serveur
    console.print("\n[yellow]Étape 1/4 : Vérification des autorisations sur le serveur...[/yellow]")
    if not check_server_enrollment_allowed(server_url):
        console.print(Panel.fit(
            "[bold red]ACCÈS REFUSÉ : L'enregistrement de nouveaux PC est actuellement désactivé.[/bold red]\n"
            "L'administrateur a verrouillé l'enrôlement dans les Paramètres Généraux du serveur LyuX.\n"
            "Activez l'option dans l'Admin Panel (Parc & Salles) avant d'enregistrer ce poste.",
            border_style="red"
        ))
        return False
    console.print("  [green]Autorisation confirmée : Enrôlement ouvert sur le serveur LyuX[/green]")

    # 2. Collecte matérielle
    console.print("\n[yellow]Étape 2/4 : Collecte des caractéristiques de la machine...[/yellow]")
    hw = get_hardware_fingerprint()
    console.print(f"  • Adresse MAC : [bold]{hw['mac_address']}[/bold]")
    console.print(f"  • Mémoire RAM : [bold]{hw['ram_mb']} Mo[/bold]")

    # 3. Enregistrement auprès de l'API
    console.print(f"\n[yellow]Étape 3/4 : Enregistrement sur le serveur ({server_url})...[/yellow]")
    payload = {
        "hostname": hostname,
        "building_id": building_id,
        "room_id": room_id,
        "mac_address": hw["mac_address"],
        "ip_address": "",
        "role": "prof" if is_teacher else "eleve"
    }

    try:
        resp = requests.post(f"{server_url}/api/v1/enroll/client-enroll", json=payload, timeout=10)
        if resp.status_code != 200:
            console.print(f"[bold red]Erreur d'enrôlement ({resp.status_code}) : {resp.text}[/bold red]")
            return False
        data = resp.json()
    except Exception as e:
        console.print(f"[bold red]Impossible de contacter le serveur LyuX : {e}[/bold red]")
        return False

    console.print(f"  [green]Enregistrement validé avec succès ![/green]")
    console.print(f"  • Nom d'ordinateur : [bold green]{hostname}[/bold green]")
    console.print(f"  • Bâtiment         : [bold]{building_id}[/bold]")
    console.print(f"  • Salle            : [bold magenta]{room_id}[/bold magenta]")

    # 4. Application du nom d'hôte local
    console.print("\n[yellow]Étape 4/4 : Application de l'identité système locale...[/yellow]")
    try:
        subprocess.run(["hostnamectl", "set-hostname", hostname], check=True)
        console.print(f"  • Nom d'hôte appliqué : {hostname}")
    except Exception:
        console.print(f"  (Simulation d'hôte : nom d'hôte virtuel = {hostname})")

    # Clôture locale
    try:
        os.makedirs("/etc/lyux", exist_ok=True)
        with open("/etc/lyux/enrolled.json", "w", encoding="utf-8") as f:
            json.dump({
                "hostname": hostname,
                "building_id": building_id,
                "room_id": room_id,
                "role": "prof" if is_teacher else "eleve"
            }, f, indent=2)
        subprocess.run(["systemctl", "disable", "lyux-enrollment.service"], check=False)
    except Exception:
        pass

    console.print(Panel.fit(
        f"[bold green]Enrôlement terminé avec succès pour {hostname} ![/bold green]\n"
        f"Affecté à la salle {room_id} ({building_id}). Le poste est prêt.",
        border_style="green"
    ))
    return True


def save_pending_config(server_url, building_id, room_id, hostname, is_teacher):
    """Enregistre les réponses OOBE même si le serveur est encore indisponible."""
    os.makedirs("/etc/lyux", exist_ok=True)
    pending = {
        "server_url": server_url,
        "hostname": hostname,
        "building_id": building_id,
        "room_id": room_id,
        "role": "prof" if is_teacher else "eleve",
        "enrollment_pending": True,
    }
    with open("/etc/lyux/enrolled.json", "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2, ensure_ascii=False)
    console.print("  [dim]Configuration enregistrée localement dans /etc/lyux/enrolled.json[/dim]")


FIRST_BOOT_FLAG = "/etc/lyux/first-boot.flag"
ENROLLED_FILE = "/etc/lyux/enrolled.json"


def load_pending_config():
    try:
        with open(ENROLLED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def retry_pending_enrollment():
    """Au boot suivant : retente l'enrôlement sans reposer les questions."""
    cfg = load_pending_config()
    if not cfg:
        return False
    console.print("[cyan]Reprise de l'enrôlement en attente...[/cyan]")
    ok = run_enrollment(cfg["server_url"], cfg["building_id"], cfg["room_id"],
                        cfg["hostname"], cfg.get("role") == "prof")
    if ok:
        cfg["enrollment_pending"] = False
        with open(ENROLLED_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    return ok


def force_admin_password_change():
    """Remplace chage -d 0 : SDDM ne sait pas gérer un mot de passe expiré."""
    console.print("\n[yellow]Sécurité : choisissez le mot de passe administrateur local.[/yellow]")
    try:
        subprocess.run(["passwd", "lyux-admin"], check=True)
        console.print("  [green]Mot de passe administrateur mis à jour.[/green]")
    except Exception as exc:
        console.print(f"  [red]Changement de mot de passe impossible : {exc}[/red]")


def interactive_mode():
    """Questions OOBE : elles sont posées même si le serveur n'est pas encore en ligne."""
    if not os.path.exists(FIRST_BOOT_FLAG) and os.path.exists(ENROLLED_FILE):
        retry_pending_enrollment()
        return True

    console.print(Panel.fit(
        "[bold cyan]Assistant de configuration initial LyuX[/bold cyan]\n"
        "[dim]Serveur • Bâtiment • Salle • Identité du poste[/dim]",
        border_style="cyan"
    ))

    found, disc_url, _ = discover_lyux_server()
    default_url = disc_url or os.getenv("LYUX_SERVER_URL", "http://serveur.lyux.lan:8000")
    if found:
        console.print(f"  [green]Serveur LyuX découvert automatiquement : {default_url}[/green]")
    else:
        console.print("  [yellow]Aucun serveur détecté : saisissez son adresse (ex: http://serveur.lyux.lan:8000).[/yellow]")

    # 1. Serveur : TOUJOURS demandé, en ligne ou non.
    server_url = Prompt.ask("Adresse du serveur LyuX", default=default_url).strip()

    allowed = check_server_enrollment_allowed(server_url)
    if not allowed:
        console.print(Panel.fit(
            "[bold yellow]SERVEUR INJOIGNABLE OU ENRÔLEMENT VERROUILLÉ[/bold yellow]\n"
            "Vous pouvez quand même choisir le bâtiment et la salle : la configuration\n"
            "sera enregistrée localement et l'enrôlement sera retenté au prochain démarrage.",
            border_style="yellow"
        ))

    # 2. Bâtiment : liste du serveur si disponible, sinon saisie libre.
    buildings = get_buildings(server_url)
    if buildings:
        console.print("\n[bold]Bâtiments disponibles :[/bold]")
        for idx, b in enumerate(buildings, 1):
            console.print(f"  [{idx}] {b['name']} ([dim]{b['id']}[/dim])")
        b_choice = Prompt.ask("Numéro du bâtiment",
                              choices=[str(i) for i in range(1, len(buildings) + 1)], default="1")
        building_id = buildings[int(b_choice) - 1]["id"]
    else:
        building_id = Prompt.ask("Identifiant du bâtiment (ex: BAT-C)", default="BAT-C").strip()

    # 3. Salle : idem.
    rooms = get_rooms(server_url, building_id)
    if rooms:
        console.print("\n[bold]Salles disponibles :[/bold]")
        for idx, r in enumerate(rooms, 1):
            console.print(f"  [{idx}] {r['name']} ([dim]{r['id']}[/dim])")
        r_choice = Prompt.ask("Numéro de la salle",
                              choices=[str(i) for i in range(1, len(rooms) + 1)], default="1")
        room_id = rooms[int(r_choice) - 1]["id"]
    else:
        room_id = Prompt.ask("Identifiant de la salle (ex: C14)", default="C14").strip()

    # 4. Identité du poste.
    suggested = get_suggested_hostname(server_url, room_id, building_id)
    hostname = Prompt.ask("Nom de l'ordinateur", default=suggested).strip()
    is_teacher = Confirm.ask("S'agit-il du poste enseignant principal de la salle ?", default=False)

    force_admin_password_change()
    save_pending_config(server_url, building_id, room_id, hostname, is_teacher)

    if allowed and run_enrollment(server_url, building_id, room_id, hostname, is_teacher):
        try:
            os.remove(FIRST_BOOT_FLAG)
        except Exception:
            pass
        return True

    console.print(Panel.fit(
        f"[bold yellow]Configuration enregistrée pour {hostname} ({building_id} / {room_id}).[/bold yellow]\n"
        "Le poste réessaiera son enrôlement au prochain démarrage.",
        border_style="yellow"
    ))
    try:
        os.remove(FIRST_BOOT_FLAG)
    except Exception:
        pass
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LyuX Machine Enrollment Tool")
    parser.add_argument("--server", help="URL du serveur LyuX (ex: http://serveur.lyux.lan:8000)")
    parser.add_argument("--building", help="Identifiant du bâtiment (ex: BAT-C)")
    parser.add_argument("--room", help="Identifiant de la salle (ex: C14)")
    parser.add_argument("--hostname", help="Nom unique de la machine (ex: C14-PC03)")
    parser.add_argument("--teacher", action="store_true", help="Poste enseignant")

    args = parser.parse_args()

    if args.server and args.building and args.room and args.hostname:
        if not run_enrollment(args.server, args.building, args.room, args.hostname, args.teacher):
            sys.exit(1)
    else:
        interactive_mode()
