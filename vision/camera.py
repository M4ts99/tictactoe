# =============================================================================
# vision/camera.py – Kamera-Stream via OpenCV
# =============================================================================
import cv2
from config import CAMERA_ID, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS


class Camera:
    """
    Oeffnet die Logitech-Kamera und liefert Frames.
    """

    def __init__(self):
        self.cap = None
        self._running = False

    def start(self):
        self.cap = cv2.VideoCapture(CAMERA_ID)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS,          CAMERA_FPS)
        if not self.cap.isOpened():
            raise RuntimeError(f"Kamera {CAMERA_ID} konnte nicht geoeffnet werden.")
        self._running = True
        print(f"[Camera] Gestartet: {CAMERA_WIDTH}x{CAMERA_HEIGHT} @ {CAMERA_FPS}fps")

    def read(self):
        """
        Gibt (ok, frame) zurueck.
        ok = True wenn Frame erfolgreich gelesen wurde.
        """
        if self.cap is None or not self._running:
            return False, None
        ret, frame = self.cap.read()
        return ret, frame

    def stop(self):
        self._running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        print("[Camera] Gestoppt.")

    def is_running(self):
        return self._running

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
