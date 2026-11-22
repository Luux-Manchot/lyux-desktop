import socket
import getpass
import platform
import datetime
import psutil

def collect_machine_diagnostics():
    """Récupère les informations techniques utiles pour le diagnostic du poste."""
    hostname = socket.gethostname()
    username = getpass.getuser()
    
    # Extraction de la salle depuis le hostname (ex: B204-03 -> Salle B204)
    room = "Inconnue"
    if "-" in hostname:
        room = f"Salle {hostname.split('-')[0].upper()}"
    
    # Récupération de l'adresse IP locale
    ip_addr = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.100.10", 80))
        ip_addr = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    # Utilisation RAM et CPU
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    ram_usage = f"{ram.used // (1024*1024)} Mo / {ram.total // (1024*1024)} Mo ({ram.percent}%)"

    return {
        "hostname": hostname,
        "room": room,
        "username": username,
        "ip_address": ip_addr,
        "os_info": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "cpu_usage": f"{cpu_percent}%",
        "ram_usage": ram_usage,
        "timestamp": datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }
