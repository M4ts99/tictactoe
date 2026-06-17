# =============================================================================
# robot/robot_controller.py
#
# Sendet einfache Befehle an den Doosan:
#   PICK X / PICK O   – Stein greifen (kein HOME danach, PLACE folgt sofort)
#   PLACE 1–9         – Stein ablegen (HOME danach im DRL)
#   PUSH              – Belohnung schieben (HOME danach im DRL)
#   HOME              – Roboter faehrt zu GLOBAL_HOME (fuer Reset)
#
# Die gesamte Bewegungslogik liegt im DRL-Script auf dem Roboter.
# =============================================================================
from robot.socket_client import DoosanSocket


class RobotController:
    """
    Steuert den Doosan M1013 ueber einfache TCP-Befehle.
    Jeder Aufruf blockiert bis der Roboter 'OK' antwortet.
    """

    def __init__(self, socket_client: DoosanSocket):
        self.client = socket_client

    # ------------------------------------------------------------------
    # Einzelbefehle
    # ------------------------------------------------------------------
    def pick(self, stone_type: str) -> bool:
        """
        Greift einen Stein aus dem Lager.
        Roboter bleibt danach mit Stein in Anflughoehe – PLACE folgt direkt.
        stone_type: "X" oder "O"
        """
        cmd = f"PICK {stone_type.upper()}"
        print(f"[Robot] {cmd}")
        return self.client.send_command(cmd)

    def place(self, field_id: int) -> bool:
        """
        Legt den gegriffenen Stein auf Feld 1–9 ab.
        Roboter faehrt danach selbst zu HOME (im DRL).
        """
        if field_id < 1 or field_id > 9:
            print(f"[Robot] Ungueltige Feldnummer: {field_id}")
            return False
        cmd = f"PLACE {field_id}"
        print(f"[Robot] {cmd}")
        return self.client.send_command(cmd)

    def push_reward(self) -> bool:
        """
        Schiebt das Belohnungs-Objekt.
        Roboter faehrt danach selbst zu HOME (im DRL).
        """
        cmd = "PUSH"
        print(f"[Robot] {cmd}")
        return self.client.send_command(cmd)

    def go_home(self) -> bool:
        """
        Faehrt den Roboter zu GLOBAL_HOME.
        Wird bei Reset und neuer Runde aufgerufen.
        """
        cmd = "HOME"
        print(f"[Robot] {cmd}")
        return self.client.send_command(cmd)

    # ------------------------------------------------------------------
    # Vollstaendiger Spielzug
    # ------------------------------------------------------------------
    def do_move(self, field_id: int, stone_type: str) -> bool:
        """
        Fuehrt einen kompletten Zug aus:
          1. PICK <stone_type>  – Stein aus Lager greifen
          2. PLACE <field_id>  – Stein auf Feld ablegen + HOME

        Wichtig: Das DRL sendet nach PICK sofort OK (Roboter haelt Stein).
                 Erst nach PLACE + HOME kommt das zweite OK.
        """
        print(f"[Robot] do_move: Feld={field_id}, Stein={stone_type}")

        if not self.pick(stone_type):
            print(f"[Robot] PICK fehlgeschlagen (Stein={stone_type})")
            return False

        if not self.place(field_id):
            print(f"[Robot] PLACE fehlgeschlagen (Feld={field_id})")
            return False

        return True
