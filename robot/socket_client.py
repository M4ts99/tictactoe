# =============================================================================
# robot/socket_client.py – TCP Socket zum Doosan M1013
# =============================================================================
import socket
import threading
import time


class DoosanSocket:
    """
    Verwaltet die TCP-Verbindung zum Roboter.
    Sendet Befehle und wartet auf 'OK\n' oder 'ERROR\n'.
    Baut die Verbindung bei Abbruch automatisch neu auf.
    """

    TIMEOUT_PER_CMD = {
        "PICK":    120.0,
        "PLACE":   120.0,
        "PUSH":    120.0,
        "HOME":     60.0,
        "DEFAULT": 120.0,
    }

    def __init__(self, ip: str, port: int, timeout: float = 10.0):
        self.ip              = ip
        self.port            = port
        self.connect_timeout = timeout
        self.sock            = None
        self._connected      = False
        self._shutdown       = False
        self._lock           = threading.Lock()

    # ------------------------------------------------------------------
    # Verbindung
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.connect_timeout)
            self.sock.connect((self.ip, self.port))
            self._connected = True
            print(f"[Socket] Verbunden mit {self.ip}:{self.port}")
            return True
        except Exception as e:
            print(f"[Socket] Verbindung fehlgeschlagen: {e}")
            self._connected = False
            self.sock = None
            return False

    def reconnect(self, retries: int = 5, delay: float = 2.0) -> bool:
        """
        Versucht die Verbindung neu aufzubauen.
        Wartet 'delay' Sekunden zwischen den Versuchen.
        """
        if self._shutdown:
            return False
        print(f"[Socket] Starte Reconnect zu {self.ip}:{self.port}...")
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self._connected = False

        for attempt in range(1, retries + 1):
            if self._shutdown:
                return False
            print(f"[Socket] Reconnect-Versuch {attempt}/{retries}...")
            if self.connect():
                print(f"[Socket] Reconnect erfolgreich")
                return True
            time.sleep(delay)

        print(f"[Socket] Reconnect nach {retries} Versuchen fehlgeschlagen")
        return False

    def disconnect(self):
        """Trennt die Verbindung sauber. Weckt blockierende recv()-Aufrufe auf."""
        self._shutdown  = True
        self._connected = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        print("[Socket] Verbindung getrennt.")

    def is_connected(self) -> bool:
        return self._connected and self.sock is not None and not self._shutdown

    # ------------------------------------------------------------------
    # Befehle senden
    # ------------------------------------------------------------------
    def send_command(self, cmd: str) -> bool:
        """
        Sendet einen Befehl und wartet auf 'OK\n'.
        Bei Verbindungsabbruch wird EINMAL automatisch reconnectet und
        der Befehl wiederholt.
        """
        if self._shutdown:
            return False

        for attempt in range(2):   # 1. Versuch normal, 2. Versuch nach Reconnect
            if not self.is_connected():
                if attempt == 0 and not self._shutdown:
                    print(f"[Socket] Nicht verbunden – versuche Reconnect...")
                    if not self.reconnect():
                        return False
                else:
                    return False

            cmd_type = cmd.strip().split()[0].upper() if cmd.strip() else "DEFAULT"
            timeout  = self.TIMEOUT_PER_CMD.get(cmd_type, self.TIMEOUT_PER_CMD["DEFAULT"])

            with self._lock:
                try:
                    self.sock.settimeout(timeout)
                    payload = (cmd.strip() + "\n").encode("utf-8")
                    self.sock.sendall(payload)
                    print(f"[Socket] Gesendet: {cmd.strip()}  (Timeout: {timeout}s)")

                    response = self._recv_line()

                    if self._shutdown:
                        return False

                    if response.strip().upper() == "OK":
                        print(f"[Socket] OK empfangen fuer: {cmd.strip()}")
                        return True
                    else:
                        print(f"[Socket] ERROR empfangen fuer: {cmd.strip()}")
                        return False

                except socket.timeout:
                    print(f"[Socket] TIMEOUT ({timeout}s) fuer: {cmd.strip()}")
                    self._connected = False
                    # Bei Timeout kein Retry – Roboter koennte noch fahren
                    return False

                except (ConnectionError, OSError) as e:
                    if self._shutdown:
                        return False
                    print(f"[Socket] Verbindungsabbruch bei '{cmd.strip()}': {e}")
                    self._connected = False
                    # Retry nach Reconnect (naechste Iteration der for-Schleife)
                    if attempt == 0:
                        print(f"[Socket] Versuche Reconnect und wiederhole Befehl...")
                        if not self.reconnect():
                            return False
                        continue   # Befehl wiederholen
                    return False

        return False

    def _recv_line(self) -> str:
        """Liest Bytes bis '\n'. Bricht bei Shutdown sofort ab."""
        buf = b""
        while not self._shutdown:
            try:
                chunk = self.sock.recv(1)
            except OSError:
                raise
            if not chunk:
                raise ConnectionError("Verbindung unterbrochen beim Empfang")
            buf += chunk
            if buf.endswith(b"\n"):
                return buf.decode("utf-8")
        raise OSError("Shutdown waehrend recv")
