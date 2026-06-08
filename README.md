# TicTacToe – Doosan M1013 Cobot

## Schnellstart

```bash
# 1. Virtuelle Umgebung erstellen & aktivieren
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# 2. Abhaengigkeiten installieren
pip install -r requirements.txt

# 3. Tests ausfuehren
python tests/test_board.py
python tests/test_ai.py

# 4. Spiel starten
python main.py
```

## Projektphasen

| Phase | Status | Beschreibung |
|-------|--------|--------------|
| 1 – Fundament | Aktiv   | Spiellogik, KI, UI (ohne Kamera/Roboter) |
| 2 – Vision    | Geplant | YOLO-Training, Kamera-Integration        |
| 3 – Roboter   | Geplant | Socket-Verbindung, Doosan-Steuerung      |
| 4 – Belohnung | Geplant | Rutsche-Feature                          |

## KI-Schwierigkeitsgrade

| Level  | Strategie |
|--------|-----------|
| Leicht | Zufaelliger Zug |
| Mittel | Gewinnt wenn moeglich, blockiert sonst |
| Schwer | Minimax + Alpha-Beta-Pruning (unschlagbar) |
