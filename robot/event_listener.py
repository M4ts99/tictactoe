# =============================================================================
# robot/event_listener.py – Empfängt Events vom DRL (Port 5007)
# =============================================================================
import socket
import threading
from typing import Callable


class EventListener:
    """
    Verbindet sich mit dem Event-Server des DRL (Port 5007).
    Läuft in einem eigenen Thread.
    Bei jedem eingehenden Event wird callback(event_str) aufgerufen.
    
    Event-Format:
        EVENT:STARTER:human
        EVENT:STARTER:robot
        EVENT:STARTER:random
        EVENT:DIFFICULTY:easy
        EVENT:DIFFICULTY:medium
        EVENT:DIFFICULTY:hard
        EVENT:RESET
    """

    def __init__(self, ip: str, port: int, callback: Callable[[str], None]):
        self.ip       = ip
        self.port     = port
        self.callback = callback
        self._sock    = None
        self._running = False
        self._thread: threading.Thread | None = None
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Verbindet und startet den Listener-Thread."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(10.0)
            self._sock.connect((self.ip, self.port))
            self._sock.settimeout(1.0)
            self._running = True
            self._thread = threading.Thread(
                target=self._listen_loop,
                daemon=True,
                name="EventListener"
            )
            self._thread.start()
            print(f"[EventListener] Verbunden mit {self.ip}:{self.port}")
            return True
        except Exception as e:
            print(f"[EventListener] Verbindung fehlgeschlagen: {e}")
            return False

    def stop(self):
        """Stoppt den Listener sauber."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        print("[EventListener] Gestoppt.")

    def _listen_loop(self):
        buf = ""
        while self._running:
            try:
                data = self._sock.recv(256)
                if not data:
                    print("[EventListener] Verbindung getrennt.")
                    break
                buf += data.decode("utf-8")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line.startswith("EVENT:"):
                        print(f"[EventListener] Empfangen: {line}")
                        try:
                            self.callback(line)
                        except Exception as e:
                            print(f"[EventListener] Fehler in Callback: {e}")
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[EventListener] Fehler: {e}")
                break
        self._running = False