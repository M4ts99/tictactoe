# =============================================================================
# robot/socket_client.py – TCP Socket zum Doosan M1013
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

    def connect(self) -> bool:
        log.info(f"Verbinde mit Doosan @ {self.ip}:{self.port}")
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.ip, self.port))
            log.info("Verbindung erfolgreich hergestellt.")
            return True
        except Exception as e:
            log.error(f"Verbindungsfehler: {e}")
            return False

    def send_command(self, cmd: str) -> bool:
        if not self.sock:
            log.error("Kein Socket vorhanden. Senden fehlgeschlagen.")
            return False
        
        log.info(f"Sende Befehl: {cmd}")
        try:
            # Wir hängen ein Newline an, damit der Roboter weiß, wann der Befehl zu Ende ist
            self.sock.sendall((cmd + "\n").encode('utf-8'))
            return True
        except Exception as e:
            log.error(f"Fehler beim Senden: {e}")
            return False

    def receive(self, buffer_size: int = 1024) -> str:
        if not self.sock:
            return ""
        
        try:
            data = self.sock.recv(buffer_size)
            response = data.decode('utf-8').strip()
            log.info(f"Empfange Antwort: {response}")
            return response
        except socket.timeout:
            log.error("Timeout beim Warten auf Roboter-Antwort.")
            return ""
        except Exception as e:
            log.error(f"Fehler beim Empfangen: {e}")
            return ""

    def disconnect(self):
        log.info("Verbindung wird getrennt.")
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None