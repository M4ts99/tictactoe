# =============================================================================
# dummy_robot.py – Ein lokaler TCP-Simulator für den Doosan M1013 Roboter
# =============================================================================
import socket
import time

HOST = "127.0.0.1"  # Lokale IP (localhost)
PORT = 12345        # Port-Nummer (muss mit main_v2.py übereinstimmen)

def handle_client(client_sock, addr):
    print(f"\n[DUMMY ROBOT] Verbindung von {addr} hergestellt.")
    try:
        while True:
            data = client_sock.recv(1024)
            if not data:
                print(f"[DUMMY ROBOT] Verbindung von {addr} getrennt.")
                break
            
            command = data.decode('utf-8').strip()
            if not command:
                continue
                
            print(f"[DUMMY ROBOT] Empfangener Befehl: '{command}'")
            
            # Hier simulieren wir die physische Bewegung des Roboters durch ein kurzes sleep
            if command.startswith("PICK"):
                print("[DUMMY ROBOT] -> Fahre zum Steinlager...")
                time.sleep(1.5)
                print("[DUMMY ROBOT] -> Schließe Greifer...")
                time.sleep(0.5)
                client_sock.sendall(b"OK\n")
                print("[DUMMY ROBOT] Sende Antwort: 'OK' (Pick beendet)")
                
            elif command.startswith("PLACE"):
                print("[DUMMY ROBOT] -> Fahre zum Ziel-Spielfeld...")
                time.sleep(1.5)
                print("[DUMMY ROBOT] -> Öffne Greifer...")
                time.sleep(0.5)
                client_sock.sendall(b"OK\n")
                print("[DUMMY ROBOT] Sende Antwort: 'OK' (Place beendet)")
                
            elif command.startswith("PUSH"):
                print("[DUMMY ROBOT] -> Schubse Belohnungs-Objekt...")
                time.sleep(1.0)
                client_sock.sendall(b"OK\n")
                print("[DUMMY ROBOT] Sende Antwort: 'OK' (Push beendet)")
                
            else:
                print(f"[DUMMY ROBOT] Unbekannter Befehl: '{command}'. Antworte standardmäßig mit OK.")
                client_sock.sendall(b"OK\n")
                
    except Exception as e:
        print(f"[DUMMY ROBOT] Fehler bei Kommunikation: {e}")
    finally:
        client_sock.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Erlaubt das sofortige Wiederverwenden des Ports nach dem Schließen
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    
    print("=====================================================================")
    print(f" Doosan M1013 Robotersimulator gestartet auf {HOST}:{PORT}")
    print(" Warte auf Verbindung von der Haupt-App (main_v2.py)...")
    print("=====================================================================")
    
    try:
        while True:
            client_sock, addr = server.accept()
            handle_client(client_sock, addr)
    except KeyboardInterrupt:
        print("\n[DUMMY ROBOT] Simulator wird beendet.")
    finally:
        server.close()

if __name__ == "__main__":
    main()
