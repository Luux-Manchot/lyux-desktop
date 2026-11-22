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
        sys.exit(1)
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
            sys.exit(1)
        data = resp.json()
    except Exception as e:
        console.print(f"[bold red]Impossible de contacter le serveur LyuX : {e}[/bold red]")
        sys.exit(1)

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

def interactive_mode():
    console.print(Panel.fit("[bold cyan]Assistant d'enrôlement LyuX (Mode Interactif)[/bold cyan]", border_style="cyan"))
    found, disc_url, _ = discover_lyux_server()
    default_url = disc_url if found else "http://127.0.0.1:8000"
    if found:
        console.print(f"  [green]Serveur LyuX découvert automatiquement : {default_url}[/green]")

    server_url = Prompt.ask("Adresse du serveur LyuX", default=default_url).strip()

    # Vérification enrôlement
    if not check_server_enrollment_allowed(server_url):
        console.print(Panel.fit(
            "[bold red]ACCÈS REFUSÉ : L'enregistrement de nouveaux PC est actuellement désactivé sur le serveur.[/bold red]\n"
            "Veuillez activer l'option 'Ajout de nouveaux PC' dans l'Admin Panel (Parc & Salles).",
            border_style="red"
        ))
        sys.exit(1)

    # Sélection Bâtiment
    buildings = get_buildings(server_url)
    if not buildings:
        console.print("[bold red]Aucun bâtiment configuré sur le serveur LyuX.[/bold red]")
        sys.exit(1)

    console.print("\n[bold]Bâtiments disponibles :[/bold]")
    for idx, b in enumerate(buildings, 1):
        console.print(f"  [{idx}] {b['name']} ([dim]{b['id']}[/dim])")
    
    b_choice = Prompt.ask("Sélectionnez le numéro du bâtiment", choices=[str(i) for i in range(1, len(buildings)+1)], default="1")
    selected_building = buildings[int(b_choice) - 1]
    building_id = selected_building["id"]

    # Sélection Salle
    rooms = get_rooms(server_url, building_id)
    if not rooms:
        console.print(f"[bold red]Aucune salle disponible dans le bâtiment {selected_building['name']}.[/bold red]")
        sys.exit(1)

    console.print(f"\n[bold]Salles du {selected_building['name']} :[/bold]")
    for idx, r in enumerate(rooms, 1):
        console.print(f"  [{idx}] {r['name']} ([dim]{r['id']}[/dim])")
    
    r_choice = Prompt.ask("Sélectionnez le numéro de la salle", choices=[str(i) for i in range(1, len(rooms)+1)], default="1")
    selected_room = rooms[int(r_choice) - 1]
    room_id = selected_room["id"]

    # Suggestion automatique du nom d'hôte
    suggested = get_suggested_hostname(server_url, room_id, building_id)
    console.print(f"\n[cyan]Nom suggéré automatiquement : [bold]{suggested}[/bold][/cyan]")
    hostname = Prompt.ask("Nom de l'ordinateur (doit être unique)", default=suggested).strip()

    while not check_hostname_available(server_url, hostname):
        console.print(f"[bold red]Le nom '{hostname}' est déjà pris par un autre PC ![/bold red]")
        hostname = Prompt.ask("Veuillez choisir un autre nom d'ordinateur").strip()

    is_teacher = Confirm.ask("S'agit-il du poste enseignant principal de la salle ?", default=False)
    run_enrollment(server_url, building_id, room_id, hostname, is_teacher)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LyuX Machine Enrollment Tool")
    parser.add_argument("--server", help="URL du serveur LyuX (ex: http://192.168.10.1:8000)")
    parser.add_argument("--building", help="Identifiant du bâtiment (ex: BAT-C)")
    parser.add_argument("--room", help="Identifiant de la salle (ex: C14)")
    parser.add_argument("--hostname", help="Nom unique de la machine (ex: C14-PC03)")
    parser.add_argument("--teacher", action="store_true", help="Poste enseignant")

    args = parser.parse_args()

    if args.server and args.building and args.room and args.hostname:
        run_enrollment(args.server, args.building, args.room, args.hostname, args.teacher)
    else:
        interactive_mode()
