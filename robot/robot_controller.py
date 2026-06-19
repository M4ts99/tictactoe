# =============================================================================
# robot/robot_controller.py
#
# Neue feste Logik:
#   - Mensch spielt immer X
#   - Roboter spielt immer O
#
# Protokoll:
#   PICK O <index>   - Stein greifen (Index 1-5), kein HOME danach
#   PLACE <1-9>      - Stein ablegen, HOME danach im DRL
#   PUSH             - Belohnung schieben, HOME danach im DRL
#   HOME             - Roboter faehrt zu GLOBAL_HOME
#
# Die gesamte Bewegungslogik liegt im DRL-Script auf dem Roboter.
# =============================================================================
from robot.socket_client import DoosanSocket


class RobotController:
    """
    Steuert den Doosan M1013 ueber einfache TCP-Befehle.
    Der Controller sendet nur noch das feste O-Protokoll.
    """

    def __init__(self, socket_client: DoosanSocket):
        self.client = socket_client
        self.pick_counter = 1

    def reset_counters(self):
        """Setzt den Stein-Zaehler fuer O wieder auf 1 zurueck."""
        self.pick_counter = 1
        print("[Robot] Stein-Zaehler zurueckgesetzt (O=1)")

    # ------------------------------------------------------------------
    # Einzelbefehle
    # ------------------------------------------------------------------
    def pick(self) -> bool:
        """
        Greift einen O-Stein aus dem Lager.
        Der Zaehler wird nach jedem erfolgreichen Versand erhoeht.
        """
        cmd = f"PICK O {self.pick_counter}"
        print(f"[Robot] {cmd}")

        if self.pick_counter < 5:
            self.pick_counter += 1

        return self.client.send_command(cmd)

    def place(self, field_id: int) -> bool:
        """Legt den gegriffenen Stein auf Feld 1-9 ab."""
        if field_id < 1 or field_id > 9:
            print(f"[Robot] Ungueltige Feldnummer: {field_id}")
            return False
        cmd = f"PLACE {field_id}"
        print(f"[Robot] {cmd}")
        return self.client.send_command(cmd)

    def push_reward(self) -> bool:
        """Schiebt das Belohnungs-Objekt."""
        cmd = "PUSH"
        print(f"[Robot] {cmd}")
        return self.client.send_command(cmd)
    def push_lose(self) -> bool:
        """Fake-Belohnung wenn der Mensch verloren hat."""
        cmd = "PUSH_LOSE"
        print(f"[Robot] {cmd}")
        return self.client.send_command(cmd)

    def go_home(self) -> bool:
        """Faehrt den Roboter zu GLOBAL_HOME."""
        cmd = "HOME"
        print(f"[Robot] {cmd}")
        return self.client.send_command(cmd)

    # ------------------------------------------------------------------
    # Vollstaendiger Spielzug
    # ------------------------------------------------------------------
    def do_move(self, field_id: int) -> bool:
        """
        Fuehrt einen kompletten Zug aus:
          1. PICK O <index>
          2. PLACE <field_id>

        Wichtig:
          - Das DRL sendet nach PICK sofort OK.
          - Erst nach PLACE + HOME kommt das zweite OK.
        """
        print(f"[Robot] do_move: Feld={field_id}, Stein=O")

        if not self.pick():
            print("[Robot] PICK fehlgeschlagen (Stein=O)")
            return False

        if not self.place(field_id):
            print(f"[Robot] PLACE fehlgeschlagen (Feld={field_id})")
            return False

        return True
