# =============================================================================
# Doosan M1013 - TCP Server Skript (DRL)
# =============================================================================
import socket

# IP des Roboters (0.0.0.0 bedeutet: höre auf allen Netzwerkschnittstellen)
HOST = "0.0.0.0" 
PORT = 12345

def pick_sequence(x, y, z):
    """Die Choreografie zum Aufheben eines Steins."""
    # Anflugposition (Z + 50mm)
    movel([x, y, z + 50, 0, 180, 0], v=100, a=100)
    
    # Runterfahren
    movel([x, y, z, 0, 180, 0], v=50, a=50)
    
    # Greifer schließen (Beispiel: Port 1 auf ON setzen)
    # set_tool_digital_output(1, ON)
    wait(0.5)
    
    # Wieder hochfahren
    movel([x, y, z + 50, 0, 180, 0], v=100, a=100)

def place_sequence(x, y, z):
    """Die Choreografie zum Ablegen eines Steins."""
    movel([x, y, z + 50, 0, 180, 0], v=100, a=100)
    movel([x, y, z, 0, 180, 0], v=50, a=50)
    
    # Greifer öffnen
    # set_tool_digital_output(1, OFF)
    wait(0.5)
    
    movel([x, y, z + 50, 0, 180, 0], v=100, a=100)

def main():
    # TCP Server aufbauen
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind((HOST, PORT))
    server_sock.listen(1)
    
    tp_popup("Warte auf Verbindung von Python...")
    
    while True:
        client_sock, addr = server_sock.accept()
        tp_log(f"Verbunden mit {addr}")
        
        try:
            while True:
                data = client_sock.recv(1024)
                if not data:
                    break
                
                # Befehl entschlüsseln (z.B. "PICK 200.0 150.0 50.0\n")
                command_str = data.decode('utf-8').strip()
                parts = command_str.split()
                
                if len(parts) >= 4:
                    action = parts[0]
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    
                    if action == "PICK":
                        pick_sequence(x, y, z)
                        client_sock.sendall(b"OK\n")
                        
                    elif action == "PLACE":
                        place_sequence(x, y, z)
                        client_sock.sendall(b"OK\n")
                        
        except Exception as e:
            tp_log(f"Fehler: {e}")
        finally:
            client_sock.close()
            tp_log("Verbindung getrennt, warte auf neue...")

if __name__ == "__main__":
    main()