# =============================================================================
# vision_test_app.py – Test-Applikation: Kamera + YOLO + Board-Anzeige
#
# Steuerung:
#   Q        – Beenden
#   K        – Kalibrierungsmodus umschalten (zeigt Feld-IDs)
#   R        – Board zuruecksetzen
#   S        – Screenshot speichern
# =============================================================================
import cv2
import numpy as np
import sys
import os
import time
from datetime import datetime

# Projektpfad sicherstellen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vision.camera       import Camera
from vision.yolo_detector import YoloDetector
from vision.board_mapper  import BoardMapper
from config import (
    YOLO_MODEL_PATH, YOLO_CONFIDENCE,
    CAMERA_ID, CAMERA_WIDTH, CAMERA_HEIGHT
)

# =============================================================================
# Konfiguration – HIER ANPASSEN nach Kalibrierung
# =============================================================================
# Spielfeld-Bereich im Kamerabild (x1, y1, x2, y2) in Pixel
# Einmalig anpassen bis das Raster genau auf das physische Spielfeld passt
BOARD_RECT = (150, 80, 1130, 650)

# Wie viele aufeinanderfolgende Frames muss ein Stein erkannt werden
# bevor er als "platziert" gilt (verhindert Flackern)
CONFIRMATION_FRAMES = 8

# =============================================================================
# Board-Zustand Klasse
# =============================================================================
class BoardState:
    def __init__(self):
        self.cells = {i: None for i in range(1, 10)}
        self.pending = {i: {"label": None, "count": 0} for i in range(1, 10)}

    def update(self, detections_per_field: dict):
        """
        detections_per_field: {field_id: label oder None}
        Bestaetigt einen Stein erst nach CONFIRMATION_FRAMES Frames.
        """
        changed = False
        for fid in range(1, 10):
            label = detections_per_field.get(fid)

            if label is not None and self.cells[fid] is None:
                if self.pending[fid]["label"] == label:
                    self.pending[fid]["count"] += 1
                else:
                    self.pending[fid] = {"label": label, "count": 1}

                if self.pending[fid]["count"] >= CONFIRMATION_FRAMES:
                    self.cells[fid] = label
                    self.pending[fid] = {"label": None, "count": 0}
                    changed = True
                    print(f"[Board] Stein '{label}' auf Feld {fid} bestaetigt.")
            else:
                self.pending[fid] = {"label": None, "count": 0}

        return changed

    def reset(self):
        self.cells = {i: None for i in range(1, 10)}
        self.pending = {i: {"label": None, "count": 0} for i in range(1, 10)}
        print("[Board] Zurueckgesetzt.")

    def get_confirmation_progress(self, fid: int) -> float:
        """Gibt 0.0 – 1.0 zurueck wie weit die Bestaetigung ist."""
        if self.cells[fid] is not None:
            return 1.0
        return min(self.pending[fid]["count"] / CONFIRMATION_FRAMES, 1.0)


# =============================================================================
# Board-Grafik zeichnen (rechte Seite)
# =============================================================================
def draw_board_panel(board: BoardState, panel_w=400, panel_h=640) -> np.ndarray:
    panel = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
    panel[:] = (18, 18, 30)

    # Titel
    cv2.putText(panel, "Spielfeld", (panel_w // 2 - 80, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (230, 230, 230), 2)

    # Board-Gitter
    bx, by = 40, 70
    bs = 300
    cell = bs // 3

    # Raster
    cv2.rectangle(panel, (bx, by), (bx + bs, by + bs), (80, 80, 120), 2)
    for i in range(1, 3):
        cv2.line(panel, (bx + i * cell, by), (bx + i * cell, by + bs), (80, 80, 120), 2)
        cv2.line(panel, (bx, by + i * cell), (bx + bs, by + i * cell), (80, 80, 120), 2)

    # Steine zeichnen
    for fid in range(1, 10):
        row = (fid - 1) // 3
        col = (fid - 1) % 3
        cx = bx + col * cell + cell // 2
        cy = by + row * cell + cell // 2
        val = board.cells[fid]

        # Fortschrittsbalken fuer pending
        prog = board.get_confirmation_progress(fid)
        if prog > 0 and val is None:
            pend_label = board.pending[fid]["label"]
            bar_color = (0, 80, 220) if pend_label == "X" else (220, 140, 0)
            bar_len = int((cell - 20) * prog)
            bar_y = cy + cell // 2 - 12
            cv2.rectangle(panel,
                          (cx - (cell - 20) // 2, bar_y),
                          (cx - (cell - 20) // 2 + bar_len, bar_y + 8),
                          bar_color, -1)

        if val == "X":
            r = cell // 2 - 15
            cv2.line(panel, (cx - r, cy - r), (cx + r, cy + r), (80, 80, 220), 5)
            cv2.line(panel, (cx + r, cy - r), (cx - r, cy + r), (80, 80, 220), 5)
        elif val == "O":
            r = cell // 2 - 15
            cv2.circle(panel, (cx, cy), r, (0, 180, 220), 5)

    # Legende
    ly = by + bs + 30
    cv2.circle(panel, (bx + 15, ly + 10), 10, (0, 180, 220), 3)
    cv2.putText(panel, "= O-Stein", (bx + 32, ly + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    r = 10
    cv2.line(panel, (bx + 5, ly + 45), (bx + 25, ly + 65), (80, 80, 220), 3)
    cv2.line(panel, (bx + 25, ly + 45), (bx + 5, ly + 65), (80, 80, 220), 3)
    cv2.putText(panel, "= X-Stein", (bx + 32, ly + 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

    # Belegte Felder zaehlen
    filled = sum(1 for v in board.cells.values() if v is not None)
    cv2.putText(panel, f"Steine: {filled}/9", (bx, panel_h - 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (120, 120, 150), 1)
    cv2.putText(panel, "Q=Beenden  R=Reset  K=Kalibrierung  S=Screenshot",
                (10, panel_h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (80, 80, 100), 1)

    return panel


# =============================================================================
# Haupt-Applikation
# =============================================================================
def main():
    print("=" * 60)
    print("  TicTacToe Vision Test-App")
    print("=" * 60)

    # Kamera starten
    cam = Camera()
    try:
        cam.start()
    except RuntimeError as e:
        print(f"FEHLER: {e}")
        sys.exit(1)

    # YOLO laden
    detector = YoloDetector(YOLO_MODEL_PATH, confidence=YOLO_CONFIDENCE)
    detector.load()
    if not detector.is_loaded():
        print("[WARNUNG] YOLO-Modell nicht geladen – nur Kamera-Feed wird angezeigt.")

    # Board-Mapper und Zustand
    mapper = BoardMapper(BOARD_RECT)
    board  = BoardState()

    # Modus-Flags
    calibration_mode = False
    screenshot_dir = "screenshots"
    os.makedirs(screenshot_dir, exist_ok=True)

    print("\nSteuerung:")
    print("  Q – Beenden")
    print("  K – Kalibrierungsmodus (Feld-IDs einblenden)")
    print("  R – Board zuruecksetzen")
    print("  S – Screenshot speichern")
    print()

    fps_time = time.time()
    fps = 0
    frame_count = 0

    while True:
        ret, frame = cam.read()
        if not ret or frame is None:
            print("[WARNUNG] Kein Frame empfangen.")
            continue

        # FPS berechnen
        frame_count += 1
        elapsed = time.time() - fps_time
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            fps_time = time.time()
            frame_count = 0

        # YOLO-Detektion
        detections = detector.detect(frame) if detector.is_loaded() else []
        if detections:
            for det in detections:
                print(f"[DEBUG] Label={det.label} Conf={det.confidence:.2f} Center=({det.center_x:.0f}, {det.center_y:.0f})")
        else:
            pass  # nichts erkannt - kein Spam

        # Bounding Boxes zeichnen
        frame_vis = detector.draw_detections(frame, detections)

        # Raster einzeichnen
        frame_vis = mapper.draw_grid(frame_vis)

        # Kalibrierungsmodus: Feld-IDs einblenden
        if calibration_mode:
            frame_vis = mapper.draw_field_labels(frame_vis)

        # Detektionen auf Felder mappen
        detections_per_field = {}
        for det in detections:
            fid = mapper.get_field(det.center_x, det.center_y)
            if fid is not None:
                # Feld hervorheben
                frame_vis = mapper.draw_detection(frame_vis, fid, det.label)
                # Nur behalten wenn noch kein Stein bestaetigt
                if board.cells[fid] is None:
                    detections_per_field[fid] = det.label

        # Board-Zustand aktualisieren
        board.update(detections_per_field)

        # FPS anzeigen
        cv2.putText(frame_vis, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 0), 2)

        # Modus-Anzeige
        mode_txt = "KALIBRIERUNG" if calibration_mode else "LIVE"
        mode_col = (0, 220, 255) if calibration_mode else (0, 220, 0)
        cv2.putText(frame_vis, mode_txt, (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, mode_col, 2)

        # YOLO-Status
        yolo_txt = "YOLO: aktiv" if detector.is_loaded() else "YOLO: nicht geladen"
        yolo_col = (0, 220, 0) if detector.is_loaded() else (0, 80, 220)
        cv2.putText(frame_vis, yolo_txt, (10, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, yolo_col, 2)

        # Board-Panel (rechte Seite)
        board_panel = draw_board_panel(board,
                                       panel_w=400,
                                       panel_h=frame_vis.shape[0])

        # Zusammenfuehren: Kamera links, Board rechts
        combined = np.hstack([frame_vis, board_panel])

        cv2.imshow("TicTacToe – Vision Test", combined)

        # Tasteneingaben
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break
        elif key == ord('k'):
            calibration_mode = not calibration_mode
            print(f"[App] Kalibrierungsmodus: {'AN' if calibration_mode else 'AUS'}")
        elif key == ord('r'):
            board.reset()
        elif key == ord('s'):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(screenshot_dir, f"screenshot_{ts}.png")
            cv2.imwrite(path, combined)
            print(f"[App] Screenshot gespeichert: {path}")

    cam.stop()
    cv2.destroyAllWindows()
    print("[App] Beendet.")


if __name__ == "__main__":
    main()
