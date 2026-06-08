# =============================================================================
# robot/robot_controller.py – Roboter-Steuerung (STUB)
# =============================================================================
from robot.socket_client import DoosanSocket
from robot.positions import FIELD_POSITIONS, STORAGE_X, STORAGE_O, REWARD_POS
from utils.logger import get_logger

log = get_logger("robot_controller")

class RobotController:
    def __init__(self, socket_client: DoosanSocket):
        self.client = socket_client

    def pick_stone(self, stone_type: str):
        """Greift einen Stein aus dem Lager."""
        pos = STORAGE_X if stone_type == "X" else STORAGE_O
        log.info(f"[STUB] pick_stone({stone_type}) @ {pos}")
        # self.client.send_command(f"MOVE {pos[0]} {pos[1]} {pos[2]}")
        # self.client.send_command("GRIP_CLOSE")

    def place_stone(self, field_id: int):
        """Setzt einen Stein auf das Spielfeld."""
        pos = FIELD_POSITIONS[field_id]
        log.info(f"[STUB] place_stone(Feld {field_id}) @ {pos}")
        # self.client.send_command(f"MOVE {pos[0]} {pos[1]} {pos[2]}")
        # self.client.send_command("GRIP_OPEN")

    def push_reward(self):
        """Schubst das Belohnungs-Objekt die Rutsche runter."""
        log.info(f"[STUB] push_reward() @ {REWARD_POS}")

    def do_move(self, field_id: int, stone_type: str):
        """Vollstaendiger Zug: Stein holen + platzieren."""
        self.pick_stone(stone_type)
        self.place_stone(field_id)
