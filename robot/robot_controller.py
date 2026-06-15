# =============================================================================
# robot/robot_controller.py – Roboter-Steuerung
# =============================================================================
from robot.socket_client import DoosanSocket
from robot.positions import FIELD_POSITIONS, STORAGE_X, STORAGE_O, REWARD_POS
from utils.logger import get_logger

log = get_logger("robot_controller")

class RobotController:
    def __init__(self, socket_client: DoosanSocket):
        self.client = socket_client

    def pick_stone(self, stone_type: str) -> bool:
        """Greift einen Stein aus dem Lager."""
        pos = STORAGE_X if stone_type == "X" else STORAGE_O
        cmd = f"PICK {pos[0]} {pos[1]} {pos[2]}"
        
        log.info(f"pick_stone({stone_type}) @ {pos}")
        self.client.send_command(cmd)
        
        # Warten bis der Roboter 'OK' zurückmeldet
        response = self.client.receive()
        return response == "OK"

    def place_stone(self, field_id: int) -> bool:
        """Setzt einen Stein auf das Spielfeld."""
        pos = FIELD_POSITIONS.get(field_id)
        if not pos:
            log.error(f"Ungültige Feld-ID: {field_id}")
            return False
            
        cmd = f"PLACE {pos[0]} {pos[1]} {pos[2]}"
        log.info(f"place_stone(Feld {field_id}) @ {pos}")
        
        self.client.send_command(cmd)
        
        # Warten bis der Roboter 'OK' zurückmeldet
        response = self.client.receive()
        return response == "OK"

    def push_reward(self) -> bool:
        """Schubst das Belohnungs-Objekt die Rutsche runter."""
        cmd = f"PUSH {REWARD_POS[0]} {REWARD_POS[1]} {REWARD_POS[2]}"
        log.info(f"push_reward() @ {REWARD_POS}")
        
        self.client.send_command(cmd)
        return self.client.receive() == "OK"

    def do_move(self, field_id: int, stone_type: str) -> bool:
        """Vollstaendiger Zug: Stein holen + platzieren."""
        if not self.pick_stone(stone_type):
            log.error("Zug abgebrochen: Fehler beim Pick.")
            return False
            
        if not self.place_stone(field_id):
            log.error("Zug abgebrochen: Fehler beim Place.")
            return False
            
        return True