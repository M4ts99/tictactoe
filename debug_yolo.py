# =============================================================================
# debug_yolo.py – Minimaler YOLO-Test direkt auf Kamera
# Zeigt RAW-Output von YOLO ohne jegliche Filterung
# Starte mit: python debug_yolo.py
# =============================================================================
import cv2
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH  = "vision/best.pt"
CONFIDENCE  = 0.1          # sehr niedrig – alles anzeigen was YOLO sieht
CAMERA_ID   = 0

print("=" * 60)
print("  YOLO Debug-Test")
print("=" * 60)

# --- Modell laden ---
try:
    from ultralytics import YOLO
    model = YOLO(MODEL_PATH)
    print(f"[OK] Modell geladen: {MODEL_PATH}")
    print(f"[INFO] Klassen im Modell: {model.names}")
    print(f"[INFO] Anzahl Klassen: {len(model.names)}")
except Exception as e:
    print(f"[FEHLER] Modell konnte nicht geladen werden: {e}")
    sys.exit(1)

# --- Kamera oeffnen ---
cap = cv2.VideoCapture(CAMERA_ID)
if not cap.isOpened():
    print(f"[FEHLER] Kamera {CAMERA_ID} nicht verfuegbar.")
    sys.exit(1)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
print(f"[OK] Kamera geoeffnet.")
print()
print("Steuerung:")
print("  Q / ESC  – Beenden")
print("  S        – Screenshot speichern")
print()
print("Detektionen werden LIVE in der Konsole ausgegeben...")
print("-" * 60)

frame_nr = 0

while True:
    ret, frame = cap.read()
    if not ret or frame is None:
        print("[WARNUNG] Kein Frame.")
        continue

    frame_nr += 1

    # YOLO Inferenz – KEINE Filterung, conf sehr niedrig
    results = model(frame, conf=CONFIDENCE, verbose=False)

    # Alle Detektionen ausgeben
    total_dets = 0
    vis_frame = frame.copy()

    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue
        for box in boxes:
            total_dets += 1
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            label = model.names.get(cls_id, f"cls_{cls_id}")

            # Konsolen-Ausgabe
            print(f"Frame {frame_nr:04d} | Klasse: {cls_id} ({label}) | "
                  f"Conf: {conf:.3f} | Box: ({x1},{y1})-({x2},{y2}) | "
                  f"Center: ({cx},{cy})")

            # Auf Frame zeichnen
            color = (0, 220, 80)
            cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 3)
            cv2.circle(vis_frame, (cx, cy), 8, (0, 0, 255), -1)
            txt = f"{label} {conf:.2f}"
            cv2.putText(vis_frame, txt, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    # Info-Overlay
    cv2.putText(vis_frame, f"Frame: {frame_nr}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
    cv2.putText(vis_frame, f"Detektionen: {total_dets}", (10, 65),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (0, 220, 80) if total_dets > 0 else (0, 80, 220), 2)
    cv2.putText(vis_frame, f"Conf-Schwelle: {CONFIDENCE}", (10, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
    cv2.putText(vis_frame,
                f"Modell-Klassen: {list(model.names.values())}", (10, 135),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 2)
    cv2.putText(vis_frame, "Q=Beenden  S=Screenshot", (10, 170),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 150), 2)

    cv2.imshow("YOLO Debug", vis_frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break
    elif key == ord('s'):
        path = f"debug_screenshot_frame{frame_nr}.png"
        cv2.imwrite(path, vis_frame)
        print(f"[Screenshot] gespeichert: {path}")

cap.release()
cv2.destroyAllWindows()
print("-" * 60)
print("[Debug] Beendet.")
