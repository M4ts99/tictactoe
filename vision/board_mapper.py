# =============================================================================
# vision/board_mapper.py – Mapping: Pixel-Koordinaten -> Feld-ID (1-9)
# =============================================================================
import cv2
import numpy as np

CUSTOM_FIELD_MAP = {
    7: (0, 2), 8: (0, 1), 9: (0, 0),
    4: (1, 2), 5: (1, 1), 6: (1, 0),
    1: (2, 2), 2: (2, 1), 3: (2, 0)
}

class BoardMapper:
    """
    Teilt das Kamerabild in 9 Felder auf und bestimmt
    anhand des Mittelpunkts einer Bounding Box das zugehoerige Feld.

    Konfiguration:
        board_rect = (x1, y1, x2, y2) in Pixel
        Das ist das Rechteck das das gesamte Spielfeld umschliesst.
        Wird einmalig kalibriert und in config.py gespeichert.
    """

    def __init__(self, board_rect: tuple):
        """
        board_rect: (x1, y1, x2, y2) – Pixel-Koordinaten des Spielfelds
        """
        self.x1, self.y1, self.x2, self.y2 = board_rect
        self.w = self.x2 - self.x1
        self.h = self.y2 - self.y1
        self.cell_w = self.w / 3
        self.cell_h = self.h / 3

    def get_field(self, cx: float, cy: float) -> int | None:
        """
        Gibt die Feld-ID zurueck basierend auf CUSTOM_FIELD_MAP.
        """
        if not (self.x1 <= cx <= self.x2 and self.y1 <= cy <= self.y2):
            return None
        col = int((cx - self.x1) / self.cell_w)
        row = int((cy - self.y1) / self.cell_h)
        col = min(col, 2)
        row = min(row, 2)
        
        for fid, (r, c) in CUSTOM_FIELD_MAP.items():
            if r == row and c == col:
                return fid
        return None

    def get_cell_rect(self, field_id: int) -> tuple:
        """
        Gibt (x1, y1, x2, y2) des Felds zurueck.
        """
        row, col = CUSTOM_FIELD_MAP.get(field_id, (0, 0))
        x1 = int(self.x1 + col * self.cell_w)
        y1 = int(self.y1 + row * self.cell_h)
        x2 = int(x1 + self.cell_w)
        y2 = int(y1 + self.cell_h)
        return x1, y1, x2, y2

    def draw_grid(self, frame: np.ndarray,
                  color=(80, 80, 200), thickness=2) -> np.ndarray:
        """
        Zeichnet das 3x3-Raster auf den Frame.
        """
        frame = frame.copy()
        # Aeusserer Rahmen
        cv2.rectangle(frame,
                      (int(self.x1), int(self.y1)),
                      (int(self.x2), int(self.y2)),
                      color, thickness)
        # Innere Linien
        for i in range(1, 3):
            # Vertikal
            x = int(self.x1 + i * self.cell_w)
            cv2.line(frame, (x, int(self.y1)), (x, int(self.y2)),
                     color, thickness)
            # Horizontal
            y = int(self.y1 + i * self.cell_h)
            cv2.line(frame, (int(self.x1), y), (int(self.x2), y),
                     color, thickness)
        return frame

    def draw_field_labels(self, frame: np.ndarray,
                          color=(60, 60, 180)) -> np.ndarray:
        """
        Beschriftet jedes Feld mit seiner ID (1-9).
        Hilfreich beim Kalibrieren.
        """
        frame = frame.copy()
        for fid in range(1, 10):
            x1, y1, x2, y2 = self.get_cell_rect(fid)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            cv2.putText(frame, str(fid), (cx - 10, cy + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 2)
        return frame

    def draw_detection(self, frame: np.ndarray,
                       field_id: int, label: str,
                       color_x=(0, 80, 220), color_o=(220, 140, 0)) -> np.ndarray:
        """
        Hebt ein erkanntes Feld farbig hervor.
        """
        frame = frame.copy()
        x1, y1, x2, y2 = self.get_cell_rect(field_id)
        color = color_x if label == "X" else color_o
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
        cv2.putText(frame, label, (x1 + 15, y2 - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.0, color, 4)
        return frame
