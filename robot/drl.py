# =============================================================================
# doosan_server.drl  - TCP-Server fuer den Doosan M1013
#
# Feste Logik:
#   - Mensch = X
#   - Roboter = O
#
# Protokoll:
#   PICK O <index>   -> O-Stein greifen (1-5), kein HOME danach
#   PLACE <1-9>      -> Stein ablegen, danach HOME
#   PUSH             -> Belohnung schieben, danach HOME
#   HOME             -> direkt zu GLOBAL_HOME
#
# Antworten:
#   OK\n    -> Befehl + Bewegung abgeschlossen
#   ERROR\n -> Befehl fehlgeschlagen
# =============================================================================

import socket

# -----------------------------------------------------------------------------
# Netzwerk
# -----------------------------------------------------------------------------
HOST = "0.0.0.0"
PORT = 5006

# -----------------------------------------------------------------------------
# Bewegungsparameter
# -----------------------------------------------------------------------------
VEL_FAST = 150
ACC_FAST = 150
VEL_SLOW = 60
ACC_SLOW = 60

APPROACH_Z = 60.0
PUSH_DISTANCE = 80.0

# -----------------------------------------------------------------------------
# Positionen
# -----------------------------------------------------------------------------
# Diese Namen muessen in deiner DRL-Umgebung als Global-Variablen existieren.
# Falls der Name anders ist, hier anpassen.
GLOBAL_HOME = Global_home

PICK_O_POSITIONS = {
    1: Global_pick1,
    2: Global_pick2,
    3: Global_pick3,
    4: Global_pick4,
    5: Global_pick5,
}

PLACE_POSITIONS = {
    1: Global_1,
    2: Global_2,
    3: Global_3,
    4: Global_4,
    5: Global_5,
    6: Global_6,
    7: Global_7,
    8: Global_8,
    9: Global_9,
}

# Belohnungsposition
PUSH_POS = Global_pick

# -----------------------------------------------------------------------------
# Hilfsfunktionen
# -----------------------------------------------------------------------------
def go_home():
    tp_log("Fahre HOME")
    movel(GLOBAL_HOME, v=VEL_FAST, a=ACC_FAST)


def approach(pos):
    """Anflugposition: pos mit Z + APPROACH_Z."""
    return posx(pos[0], pos[1], pos[2] + APPROACH_Z, pos[3], pos[4], pos[5])


def send_ok(sock):
    sock.sendall(b"OK\n")
    tp_log("-> OK")


def send_error(sock):
    sock.sendall(b"ERROR\n")
    tp_log("-> ERROR")


# -----------------------------------------------------------------------------
# Bewegungssequenzen
# -----------------------------------------------------------------------------
def pick_sequence(stone_type, idx):
    """
    Greift einen O-Stein aus dem Lager.
    stone_type ist nur noch fuer Protokoll-Kompatibilitaet da.
    """
    if stone_type != "O":
        tp_log("FEHLER: Roboter darf nur O greifen, erhalten: " + str(stone_type))
        return False

    pos = PICK_O_POSITIONS.get(idx)
    if pos is None:
        tp_log("FEHLER: Unbekannter Pick-Index " + str(idx))
        return False

    tp_log("PICK O " + str(idx))
    movel(approach(pos), v=VEL_FAST, a=ACC_FAST)
    movel(pos, v=VEL_SLOW, a=ACC_SLOW)
    wait(0.5)
    # Greifer-Aktion ggf. hier einfuegen
    movel(approach(pos), v=VEL_FAST, a=ACC_FAST)
    tp_log("PICK fertig")
    return True


def place_sequence(field_id):
    """Faehrt zu Feld field_id und legt ab."""
    pos = PLACE_POSITIONS.get(field_id)
    if pos is None:
        tp_log("FEHLER: Unbekanntes Feld " + str(field_id))
        return False

    tp_log("PLACE Feld " + str(field_id))
    movel(approach(pos), v=VEL_FAST, a=ACC_FAST)
    movel(pos, v=VEL_SLOW, a=ACC_SLOW)
    wait(0.5)
    # Greifer oeffnen / ablegen
    try:
        set_digital_output(13, ON)
    except Exception as e:
        tp_log("Greifer-Ausgang ON fehlgeschlagen: " + str(e))
    movel(approach(pos), v=VEL_FAST, a=ACC_FAST)
    try:
        set_digital_output(13, OFF)
    except Exception as e:
        tp_log("Greifer-Ausgang OFF fehlgeschlagen: " + str(e))
    tp_log("PLACE fertig")
    return True


def push_sequence():
    """Faehrt zur Belohnungsposition und schiebt."""
    pos = PUSH_POS
    tp_log("PUSH")

    movel(approach(pos), v=VEL_FAST, a=ACC_FAST)
    movel(pos, v=VEL_SLOW, a=ACC_SLOW)

    push_target = posx(pos[0], pos[1] + PUSH_DISTANCE, pos[2], pos[3], pos[4], pos[5])
    movel(push_target, v=VEL_SLOW, a=ACC_SLOW)
    movel(approach(pos), v=VEL_FAST, a=ACC_FAST)

    tp_log("PUSH fertig")
    return True


# -----------------------------------------------------------------------------
# Befehlsverarbeitung
# -----------------------------------------------------------------------------
def process_command(line):
    parts = line.strip().split()
    if not parts:
        return False

    action = parts[0].upper()

    if action == "PICK":
        if len(parts) < 3:
            tp_log("FEHLER: PICK braucht Stein (O) und Index (1-5)")
            return False

        stone = parts[1].upper()
        if stone != "O":
            tp_log("FEHLER: Roboter darf nur O greifen, erhalten: " + stone)
            return False

        try:
            idx = int(parts[2])
        except Exception:
            tp_log("FEHLER: Index ist keine Zahl: " + parts[2])
            return False

        if idx < 1 or idx > 5:
            tp_log("FEHLER: Pick-Index muss 1-5 sein")
            return False

        return pick_sequence(stone, idx)

    elif action == "PLACE":
        if len(parts) < 2:
            tp_log("FEHLER: PLACE braucht Feldnummer")
            return False
        try:
            field_id = int(parts[1])
        except Exception:
            tp_log("FEHLER: Keine Zahl: " + parts[1])
            return False
        if field_id < 1 or field_id > 9:
            tp_log("FEHLER: Feld muss 1-9 sein")
            return False
        ok = place_sequence(field_id)
        if ok:
            go_home()
        return ok

    elif action == "PUSH":
        ok = push_sequence()
        if ok:
            go_home()
        return ok

    elif action == "HOME":
        go_home()
        return True

    else:
        tp_log("FEHLER: Unbekannter Befehl: " + action)
        return False


# -----------------------------------------------------------------------------
# TCP-Server
# -----------------------------------------------------------------------------
def main():
    try:
        set_tcp([0, 0, 0, 0, 0, 0])
        tp_log("TCP gesetzt")
    except Exception as e:
        tp_log("TCP-Setzen ignoriert: " + str(e))

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass

    server_sock.settimeout(1.0)

    bound = False
    for attempt in range(1, 6):
        try:
            server_sock.bind((HOST, PORT))
            bound = True
            break
        except Exception as e:
            tp_log("Bind-Versuch " + str(attempt) + ": " + str(e))
            wait(3)

    if not bound:
        tp_popup("FEHLER: Port " + str(PORT) + " belegt!")
        return

    server_sock.listen(1)
    tp_popup("TicTacToe Server\nPort " + str(PORT) + " bereit")
    tp_log("Server gestartet, fahre HOME...")

    try:
        go_home()
        tp_log("HOME erreicht, warte auf Verbindung...")
    except Exception as e:
        tp_log("HOME fehlgeschlagen (ignoriert): " + str(e))
        tp_log("Warte auf Verbindung...")

    while True:
        try:
            client_sock, addr = server_sock.accept()
        except socket.timeout:
            continue
        except Exception as e:
            tp_log("Accept Fehler: " + str(e))
            break

        client_ip = addr[0]
        tp_log("Verbunden: " + client_ip)
        tp_popup("Client: " + client_ip)

        client_sock.settimeout(1.0)
        buf = ""

        try:
            while True:
                try:
                    data = client_sock.recv(1024)
                    if not data:
                        tp_log("Client getrennt")
                        break

                    buf += data.decode("utf-8")

                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        tp_log("Befehl: " + line)
                        try:
                            ok = process_command(line)
                        except Exception as e:
                            tp_log("FEHLER in process_command: " + str(e))
                            ok = False

                        if ok:
                            send_ok(client_sock)
                        else:
                            send_error(client_sock)

                except socket.timeout:
                    continue

        except Exception as e:
            tp_log("Verbindungsfehler: " + str(e))
        finally:
            try:
                client_sock.close()
            except Exception:
                pass
            tp_log("Warte auf naechsten Client...")


main()
