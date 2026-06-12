# =============================================================================
# vision/yolo_detector.py – YOLO-Inferenz fuer X und O Steine
# =============================================================================
import cv2
import numpy as np
from dataclasses import dataclass


@dataclass
class Detection:
    """Ergebnis einer einzelnen YOLO-Detektion."""
    label: str          # 'X' oder 'O'
    confidence: float   # 0.0 – 1.0
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2

    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


class YoloDetector:
    """
    Wrapper um das trainierte YOLOv8-Modell.
    Gibt eine Liste von Detection-Objekten zurueck.
    """

    CLASS_NAMES = {0: "O",1: "X"}

    def __init__(self, model_path: str, confidence: float = 0.5):
        self.model_path = model_path
        self.confidence = confidence
        self.model = None
        self._loaded = False

    def load(self):
        """Laedt das YOLO-Modell. Einmalig aufrufen."""
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
            self._loaded = True
            print(f"[YoloDetector] Modell geladen: {self.model_path}")
        except Exception as e:
            print(f"[YoloDetector] FEHLER beim Laden: {e}")
            self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        Fuehrt Inferenz auf einem OpenCV-Frame (BGR) durch.
        Gibt eine Liste von Detection-Objekten zurueck.
        """
        if not self._loaded or self.model is None:
            return []

        results = self.model(frame, conf=self.confidence, verbose=False)
        detections = []

        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf   = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label = self.CLASS_NAMES.get(cls_id, "?")
                detections.append(Detection(
                    label=label,
                    confidence=conf,
                    x1=x1, y1=y1, x2=x2, y2=y2
                ))

        return detections

    def draw_detections(self, frame: np.ndarray,
                        detections: list[Detection]) -> np.ndarray:
        """
        Zeichnet alle Bounding Boxes mit Label und Konfidenz auf den Frame.
        """
        frame = frame.copy()
        for det in detections:
            color = (0, 80, 220) if det.label == "X" else (220, 140, 0)
            cv2.rectangle(frame, (det.x1, det.y1), (det.x2, det.y2), color, 2)
            txt = f"{det.label} {det.confidence:.2f}"
            cv2.putText(frame, txt,
                        (det.x1, det.y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            # Mittelpunkt einzeichnen
            cx = int(det.center_x)
            cy = int(det.center_y)
            cv2.circle(frame, (cx, cy), 5, color, -1)
        return frame
