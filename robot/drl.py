# =============================================================================
# doosan_server.drl  - TCP-Server fuer den Doosan M1013
#
# Feste Logik:
#   - Mensch = X
#   - Roboter = O
#
# Protokoll (Command-Channel, Port 5020):
#   PICK O <index>   -> O-Stein greifen (1-5), kein HOME danach
#   PLACE <1-9>      -> Stein ablegen, danach HOME
#   PUSH             -> Belohnung schieben, danach HOME
#   HOME             -> direkt zu GLOBAL_HOME
#
# Antworten:
#   OK\n    -> Befehl + Bewegung abgeschlossen
#   ERROR\n -> Befehl fehlgeschlagen
#
# Event-Channel (Port 5021):
#   DRL sendet Button-Events an main_v2.py:
#   EVENT:STARTER:human\n
#   EVENT:STARTER:robot\n
#   EVENT:STARTER:random\n
#   EVENT:DIFFICULTY:easy\n
#   EVENT:DIFFICULTY:medium\n
#   EVENT:DIFFICULTY:hard\n
#   EVENT:RESET\n
#
# Digital Inputs (5 Buttons):
#   B1 (DI 1) – Startspieler: zyklisch umschalten (Mensch -> Roboter -> Zufall -> Mensch -> ...)
#   B2 (DI 2) – Schwierigkeit Leicht  -> startet Runde sofort
#   B3 (DI 3) – Schwierigkeit Mittel  -> startet Runde sofort
#   B4 (DI 4) – Schwierigkeit Schwer  -> startet Runde sofort
#   B5 (DI 5) – Vollstaendiger Reset  -> Roboter faehrt HOME
# =============================================================================

import socket
import time

# -----------------------------------------------------------------------------
# Netzwerk
# -----------------------------------------------------------------------------
HOST       = "0.0.0.0"
PORT       = 5002 # Command-Channel (main -> DRL)
EVENT_PORT = 5003  # Event-Channel   (DRL -> main)

# -----------------------------------------------------------------------------
# Bewegungsparameter
# -----------------------------------------------------------------------------
VEL_FAST = 300
ACC_FAST = 300
VEL_SLOW = 200
ACC_SLOW = 200

APPROACH_Z    = 60.0
PUSH_DISTANCE = 80.0

# -----------------------------------------------------------------------------
# Positionen
# -----------------------------------------------------------------------------
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

PUSH_POS = Global_pick

# -----------------------------------------------------------------------------
# Digital Input Pin-Nummern (anpassen falls Controller anders belegt)
# -----------------------------------------------------------------------------
DI_STARTER = 1   # B1 – Startspieler (zyklisch)
DI_EASY    = 2   # B2 – Schwierigkeit Leicht
DI_MEDIUM  = 3   # B3 – Schwierigkeit Mittel
DI_HARD    = 4   # B4 – Schwierigkeit Schwer
DI_RESET   = 5   # B5 – Vollstaendiger Reset

# -----------------------------------------------------------------------------
# Event-Channel: globaler Client-Socket
# -----------------------------------------------------------------------------
event_client = None   # wird in start_event_server() gesetzt


def send_event(msg):
    """
    Sendet einen Event-String an main_v2.py ueber den Event-Port.
    Bei Fehler wird event_client auf None gesetzt (Events deaktiviert).
    """
    global event_client
    if event_client is None:
        tp_log("EVENT nicht gesendet (kein Client): " + msg)
        return
    try:
        event_client.sendall((msg.strip() + "\n").encode("utf-8"))
        tp_log("EVENT gesendet: " + msg)
    except Exception as e:
        tp_log("EVENT Sendefehler: " + str(e))
        event_client = None


def start_event_server():
    """
    Oeffnet EVENT_PORT und wartet max. 30s auf einen Client (main_v2.py).
    Wird NACH dem Command-Server gestartet.
    """
    global event_client
    ev_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        ev_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    try:
        ev_sock.bind(("0.0.0.0", EVENT_PORT))
    except Exception as e:
        tp_log("Event-Port " + str(EVENT_PORT) + " Bind-Fehler: " + str(e))
        ev_sock.close()
        return
    ev_sock.listen(1)
    ev_sock.settimeout(30.0)
    tp_log("[Port " + str(EVENT_PORT) + "] FREI – warte auf Event-Client (max 30s)...")
    tp_popup("Port " + str(EVENT_PORT) + " FREI\nWarte auf Event-Client\n(main_v2.py starten)")
    try:
        client, addr = ev_sock.accept()
        event_client = client
        event_client.settimeout(None)
        tp_log("[Port " + str(EVENT_PORT) + "] Verbunden: " + str(addr[0]))
        tp_popup("Port " + str(EVENT_PORT) + " OK\nEvent-Client verbunden:\n" + str(addr[0]))
    except socket.timeout:
        tp_log("[Port " + str(EVENT_PORT) + "] Timeout – kein Client. Buttons senden keine Events.")
        tp_popup("Port " + str(EVENT_PORT) + " TIMEOUT\nKein Event-Client verbunden\nButtons deaktiviert")
    finally:
        ev_sock.close()


# -----------------------------------------------------------------------------
# Button-Polling
# -----------------------------------------------------------------------------

# Button-Zustand (Flanken-Erkennung)
_prev_state   = {}   # {pin: bool} – letzter bekannter Zustand

# B1-Zyklus: merkt sich welcher Starter gerade aktiv ist
# 0 = human (Standard), 1 = robot, 2 = random
starter_cycle = 0


def poll_buttons_once():
    """
    Liest alle 5 Digital Inputs genau einmal und sendet ggf. Events.
    Wird bei jedem socket.timeout (~1s) aufgerufen – kein eigener Loop,
    damit der Command-Server nicht blockiert wird.

    B1 – Zyklus-Logik:
      Jeder neue Tastendruck schaltet weiter:
      Mensch -> Roboter -> Zufall -> Mensch -> ...
      Standard beim Start: Mensch (cycle = 0)

    B2/B3/B4/B5 – Flanken-Erkennung:
      Event wird nur beim Uebergang OFF -> ON gesendet,
      nicht bei gehaltenem Button.
    """
    global _prev_state, starter_cycle

    # -------------------------------------------------------------------------
    # B1 – Startspieler (Zyklus-Logik)
    # -------------------------------------------------------------------------
    b1 = (get_digital_input(DI_STARTER) == ON)

    if b1 and not _prev_state.get(DI_STARTER, False):
        # Neuer Tastendruck erkannt – Zyklus weiterschalter
        starter_cycle = (starter_cycle + 1) % 3

        if starter_cycle == 0:
            send_event("EVENT:STARTER:human")
            tp_log("[B1] Startspieler: Mensch")
        elif starter_cycle == 1:
            send_event("EVENT:STARTER:robot")
            tp_log("[B1] Startspieler: Roboter")
        else:
            send_event("EVENT:STARTER:random")
            tp_log("[B1] Startspieler: Zufall")

    _prev_state[DI_STARTER] = b1

    # -------------------------------------------------------------------------
    # B2 – Schwierigkeit Leicht
    # -------------------------------------------------------------------------
    b2 = (get_digital_input(DI_EASY) == ON)
    if b2 and not _prev_state.get(DI_EASY, False):
        send_event("EVENT:DIFFICULTY:easy")
        tp_log("[B2] Schwierigkeit: Leicht")
    _prev_state[DI_EASY] = b2

    # -------------------------------------------------------------------------
    # B3 – Schwierigkeit Mittel
    # -------------------------------------------------------------------------
    b3 = (get_digital_input(DI_MEDIUM) == ON)
    if b3 and not _prev_state.get(DI_MEDIUM, False):
        send_event("EVENT:DIFFICULTY:medium")
        tp_log("[B3] Schwierigkeit: Mittel")
    _prev_state[DI_MEDIUM] = b3

    # -------------------------------------------------------------------------
    # B4 – Schwierigkeit Schwer
    # -------------------------------------------------------------------------
    b4 = (get_digital_input(DI_HARD) == ON)
    if b4 and not _prev_state.get(DI_HARD, False):
        send_event("EVENT:DIFFICULTY:hard")
        tp_log("[B4] Schwierigkeit: Schwer")
    _prev_state[DI_HARD] = b4

    # -------------------------------------------------------------------------
    # B5 – Reset
    # -------------------------------------------------------------------------
    b5 = (get_digital_input(DI_RESET) == ON)
    if b5 and not _prev_state.get(DI_RESET, False):
        send_event("EVENT:RESET")
        tp_log("[B5] Reset")
    _prev_state[DI_RESET] = b5


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
    tp_log("PUSH")
    try:
        # 200mm über Pick anfahren
        above = trans(Global_pick, posx(0, 0, 200, 0, 0, 0))
        movel(above, v=VEL_FAST, a=ACC_FAST)
 
        # Zur Pick-Position
        movel(Global_pick, v=VEL_SLOW, a=ACC_SLOW)
 
        # 50mm hoch
        up50 = trans(Global_pick, posx(0, 0, 50, 0, 0, 0))
        movel(up50, v=VEL_SLOW, a=ACC_SLOW)
 
        # 100mm positive X
        push_out = trans(Global_pick, posx(200, 0, 50, 0, 0, 0))
        movel(push_out, v=VEL_SLOW, a=ACC_SLOW)
 
        wait(10.0)
 
        # 100mm zurück
        movel(up50, v=VEL_SLOW, a=ACC_SLOW)
 
        set_digital_output(13, ON)
        wait(0.1)
        set_digital_output(13, OFF)
 
    except Exception as e:
        tp_log("PUSH Fehler: " + str(e))
        tp_popup("PUSH FEHLER:\n" + str(e))
        return False
 
    tp_log("PUSH fertig")
    return True
 
 
def push_lose_sequence():
    tp_log("PUSH_LOSE")
    try:
        above = trans(Global_picklose, posx(0, 0, 200, 0, 0, 0))
        movel(above, v=VEL_FAST, a=ACC_FAST)
 
        movel(Global_picklose, v=VEL_SLOW, a=ACC_SLOW)
 
        up50 = trans(Global_picklose, posx(0, 0, 50, 0, 0, 0))
        movel(up50, v=VEL_SLOW, a=ACC_SLOW)
 
        push_out = trans(Global_picklose, posx(200, 0, 50, 0, 0, 0))
        movel(push_out, v=VEL_SLOW, a=ACC_SLOW)
 
        wait(10.0)
 
        movel(up50, v=VEL_SLOW, a=ACC_SLOW)
 
        set_digital_output(13, ON)
        wait(0.1)
        set_digital_output(13, OFF)
 
    except Exception as e:
        tp_log("PUSH_LOSE Fehler: " + str(e))
        tp_popup("PUSH_LOSE FEHLER:\n" + str(e))
        return False
 
    tp_log("PUSH_LOSE fertig")
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
    elif action == "PUSH_LOSE":
        ok = push_lose_sequence()
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
# TCP-Server (Hauptschleife)
# -----------------------------------------------------------------------------
def main():
    # TCP-Tool-Frame setzen
    try:
        set_tcp([0, 0, 0, 0, 0, 0])
        tp_log("TCP gesetzt")
    except Exception as e:
        tp_log("TCP-Setzen ignoriert: " + str(e))

    # Command-Server auf PORT binden
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass

    server_sock.settimeout(0.05)   # Timeout fuer accept() – erlaubt Button-Polling

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
        tp_log("[Port " + str(PORT) + "] FEHLER – Port bereits belegt!")
        tp_popup("FEHLER!\nPort " + str(PORT) + " ist belegt!\nBitte neu starten.")
        return

    server_sock.listen(1)
    tp_log("[Port " + str(PORT) + "] FREI – Command-Server bereit")
    tp_popup("Port " + str(PORT) + " FREI\nCommand-Server bereit\nFahre HOME...")

    # Roboter faehrt HOME
    try:
        go_home()
        tp_log("HOME erreicht")
    except Exception as e:
        tp_log("HOME fehlgeschlagen (ignoriert): " + str(e))

    # Event-Server starten (wartet max. 30s auf main_v2.py)
    start_event_server()

    tp_popup("Ports bereit:\nPort " + str(PORT) + " (Commands) OK\nPort " + str(EVENT_PORT) + " (Events) " + ("OK" if event_client else "INAKTIV") + "\nWarte auf Verbindung...")
    tp_log("Beide Ports bereit – warte auf Command-Client...")

    # -------------------------------------------------------------------------
    # Haupt-Accept-Loop
    # -------------------------------------------------------------------------
    while True:
        # Auf neuen Command-Client warten
        try:
            client_sock, addr = server_sock.accept()
        except socket.timeout:
            # Kein Client verbunden – Buttons pollen und weiter warten
            poll_buttons_once()
            continue
        except Exception as e:
            tp_log("Accept Fehler: " + str(e))
            break

        client_ip = addr[0]
        tp_log("[Port " + str(PORT) + "] Command-Client verbunden: " + client_ip)
        tp_popup("Port " + str(PORT) + " – Client verbunden:\n" + client_ip)

        client_sock.settimeout(0.05)   # Timeout fuer recv() – erlaubt Button-Polling
        buf = ""

        # Command-Empfangs-Loop fuer diesen Client
        try:
            while True:
                try:
                    data = client_sock.recv(1024)
                    if not data:
                        tp_log("Command-Client getrennt")
                        break

                    buf += data.decode("utf-8")

                    # Alle vollstaendigen Zeilen verarbeiten
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
                    # Kein Befehl eingegangen – Buttons pollen
                    poll_buttons_once()
                    continue

        except Exception as e:
            tp_log("Verbindungsfehler: " + str(e))
        finally:
            try:
                client_sock.close()
            except Exception:
                pass
            tp_log("Warte auf naechsten Command-Client...")


main()
