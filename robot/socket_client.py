# =============================================================================
# robot/socket_client.py – TCP Socket zum Doosan M1013 (STUB)
# Wird aktiviert sobald der Roboter angeschlossen ist.
# =============================================================================
import socket
from utils.logger import get_logger

log = get_logger("socket_client")

class DoosanSocket:
    def __init__(self, ip: str, port: int, timeout: int = 10):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock = None

    def connect(self):
        log.info(f"[STUB] Verbinde mit Doosan @ {self.ip}:{self.port}")
        # self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # self.sock.settimeout(self.timeout)
        # self.sock.connect((self.ip, self.port))

    def send_command(self, cmd: str):
        log.info(f"[STUB] Sende Befehl: {cmd}")
        # self.sock.sendall((cmd + "\n").encode())

    def receive(self) -> str:
        log.info("[STUB] Empfange Antwort")
        return "OK"

    def disconnect(self):
        log.info("[STUB] Verbindung getrennt")
        # if self.sock:
        #     self.sock.close()
