import uuid
import platform
import psutil

def get_hardware_fingerprint():
    """Collecte les informations matérielles pour l'enrôlement et l'inventaire."""
    # Adresse MAC primaire
    mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0, 8*6, 8)][::-1])
    
    ram_mb = psutil.virtual_memory().total // (1024 * 1024)
    cpu_info = platform.processor() or "CPU x86_64"

    return {
        "mac_address": mac,
        "serial_number": f"SN-{mac.replace(':', '')[-6:].upper()}",
        "cpu_info": cpu_info,
        "ram_mb": ram_mb
    }
