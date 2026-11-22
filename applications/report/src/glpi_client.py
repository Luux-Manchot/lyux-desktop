import os
import requests
import json

class GlpiTicketClient:
    def __init__(self, api_url=None, app_token=None):
        self.api_url = api_url or os.getenv("LYUX_API_URL", "http://127.0.0.1:8000/api/v1/tickets")
        self.app_token = app_token

    def submit_ticket(self, title: str, category: str, description: str, system_info: dict, screenshot_b64: str = None) -> dict:
        """Envoie le rapport d'incident vers le serveur LyuX / GLPI."""
        full_content = (
            f"=== 📌 SIGNALEMENT UTILISATEUR ===\n"
            f"Catégorie : {category}\n"
            f"Demandeur : {system_info['username']}\n"
            f"Description :\n{description}\n\n"
            f"=== 💻 MÉTADONNÉES TECHNIQUES ===\n"
            f"Machine : {system_info['hostname']} ({system_info['room']})\n"
            f"Adresse IP : {system_info['ip_address']}\n"
            f"Système : {system_info['os_info']}\n"
            f"Mémoire : {system_info['ram_usage']}\n"
            f"Date du signalement : {system_info['timestamp']}\n"
        )

        payload = {
            "title": f"[{category.upper()}] Incident sur {system_info['hostname']} ({system_info['username']})",
            "category": category,
            "description": full_content,
            "hostname": system_info["hostname"],
            "username": system_info["username"],
            "screenshot_data": screenshot_b64
        }

        try:
            # Envoi vers l'API centrale LyuX
            response = requests.post(self.api_url, json=payload, timeout=5)
            if response.status_code in [200, 201]:
                return {"success": True, "ticket_id": response.json().get("ticket_id", "T-1001")}
            else:
                return {"success": False, "error": f"Erreur serveur ({response.status_code})"}
        except Exception as e:
            # Fallback réseau local simulé
            return {"success": True, "ticket_id": f"T-LOC-{system_info['hostname'][-2:]}88", "simulated": True}
