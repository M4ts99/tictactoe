# =============================================================================
# main_v2.py – Hauptprogramm TicTacToe Doosan M1013
#
# Regeln (hardcoded):
#   - Mensch  = immer X
#   - Roboter = immer O
#
# Architektur:
#   - Startscreen:   Auswahl Dummy / Echter Roboter + IP-Eingabe
#   - Vision-Thread: Kamera lesen + YOLO-Inferenz (separater Thread)
#   - Pygame-Thread: UI zeichnen + Events (Hauptthread)
#   - Shared State:  frame + detections via threading.Lock
#
# Digital Inputs (5 Buttons am Roboter-Controller):
#   B1 – Startspieler-Toggle (kurz: Mensch/Roboter wechseln | >3s: Zufallsmodus)
#   B2 – Schwierigkeit Leicht  → startet Runde sofort
#   B3 – Schwierigkeit Mittel  → startet Runde sofort
#   B4 – Schwierigkeit Schwer  → startet Runde sofort
#   B5 – Vollständiger Reset   → alle Einstellungen löschen, Roboter → HOME
# =============================================================================
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
import pygame

from robot.event_listener import EventListener
from config import (
    AI_DIFFICULTY_EASY,
    AI_DIFFICULTY_HARD,
    AI_DIFFICULTY_MEDIUM,
    DEFAULT_DIFFICULTY,
    YOLO_MODEL_PATH,
    YOLO_CONFIDENCE,
    YOLO_CLASSES,
    ROBOT_IP,
    ROBOT_PORT,
    ROBOT_EVENT_PORT,
)
from game.game_manager import GameManager
from robot.socket_client import DoosanSocket
from robot.robot_controller import RobotController

try:
    from vision.camera import Camera
    from vision.yolo_detector import YoloDetector
    from vision.board_mapper import BoardMapper
    VISION_AVAILABLE = True
except Exception as _e:
    print(f"[WARN] Vision-Module nicht geladen: {_e}")
    VISION_AVAILABLE = False

# =============================================================================
# Spieler-Konstanten (fest verdrahtet)
# =============================================================================
HUMAN_MARK = "X"
ROBOT_MARK = "O"

# =============================================================================
# Layout
# =============================================================================
WIN_W, WIN_H = 1500, 860

CAM_X, CAM_Y = 15, 65
CAM_W, CAM_H = 800, 450

BOARD_X, BOARD_Y = 30, 535
BOARD_SIZE       = 320
CELL             = BOARD_SIZE // 3

RIGHT_X = 835
RIGHT_W = WIN_W - RIGHT_X - 10

BOARD_RECT = (340, 60, 940, 660)   # Kamerabild-Ausschnitt fuer den Board-Mapper

CONFIRMATION_SECONDS = 2.0   # Sekunden bis ein erkannter X-Stein bestaetigt wird
LOG_TTL_SECONDS      = 15.0
MAX_LOG_VISIBLE      = 10

DUMMY_IP   = "127.0.0.1"
DUMMY_PORT = 12345

# =============================================================================
# Farben
# =============================================================================
BG     = (18,  18,  30)
PANEL  = (26,  26,  40)
PANEL2 = (32,  32,  50)
LINE   = (80,  80, 120)
TEXT   = (235, 235, 240)
DIM    = (130, 130, 155)
X_COL  = (220,  80,  80)
O_COL  = (80,  180, 220)
GOLD   = (255, 215,   0)
GREEN  = (80,  210, 110)
RED    = (235,  80,  80)
YELLOW = (240, 200,  70)
BLUE   = (100, 155, 255)
DARK   = (12,  12,  22)

# =============================================================================
# Feld-Zuordnung fuer die 2D-Ansicht
# (row=0 oben, row=2 unten | col=0 links, col=2 rechts)
# =============================================================================
FIELD_MAP = {
    1: (2, 2), 2: (2, 1), 3: (2, 0),
    4: (1, 2), 5: (1, 1), 6: (1, 0),
    7: (0, 2), 8: (0, 1), 9: (0, 0),
}


# =============================================================================
# Datenklassen
# =============================================================================
@dataclass
class LogEntry:
    text: str
    ts:   float
    kind: str = "info"   # info | ok | error | robot | human | warn


@dataclass
class VisionState:
    frame:      np.ndarray | None = None
    detections: list              = field(default_factory=list)
    lock:       threading.Lock    = field(default_factory=threading.Lock)
    running:    bool              = True
    ready:      bool              = False


# =============================================================================
# Hilfsfunktionen
# =============================================================================
def draw_text(surface, text, font, color, x, y, anchor="topleft"):
    surf = font.render(text, True, color)
    rect = surf.get_rect()
    setattr(rect,
            anchor if anchor in ("center", "midleft", "midright",
                                 "topleft", "topright") else "topleft",
            (x, y))
    surface.blit(surf, rect)
    return rect


def draw_button(surface, rect, text, font,
                active=False, mouse_pos=(0, 0),
                bg_col=None, border_col=None):
    r = pygame.Rect(rect)
    if bg_col:
        col = bg_col
    elif active:
        col = (65, 100, 170)
    elif r.collidepoint(mouse_pos):
        col = (55, 55, 90)
    else:
        col = (40, 40, 65)
    pygame.draw.rect(surface, col, r, border_radius=10)
    pygame.draw.rect(surface, border_col or LINE, r, 2, border_radius=10)
    lbl = font.render(text, True, TEXT)
    surface.blit(lbl, lbl.get_rect(center=r.center))
    return r


def field_from_mouse(mx, my):
    """Gibt Feld-ID (1-9) zurueck wenn die Maus auf dem 2D-Brett ist."""
    bx = mx - BOARD_X
    by = my - BOARD_Y
    if not (0 <= bx < BOARD_SIZE and 0 <= by < BOARD_SIZE):
        return None
    col = int(bx // CELL)
    row = int(by // CELL)
    for fid, (r, c) in FIELD_MAP.items():
        if r == row and c == col:
            return fid
    return None


def frame_to_surface(frame: np.ndarray, w: int, h: int) -> pygame.Surface:
    """Konvertiert OpenCV BGR-Frame → Pygame Surface."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.flip(rgb, 0)
    return pygame.surfarray.make_surface(np.rot90(rgb))


# =============================================================================
# Vision-Thread
# =============================================================================
def vision_thread_fn(vs: VisionState):
    if not VISION_AVAILABLE:
        print("[Vision] Module nicht verfuegbar – Thread beendet.")
        return

    camera   = Camera()
    detector = YoloDetector(model_path=YOLO_MODEL_PATH, confidence=YOLO_CONFIDENCE)
    mapper   = BoardMapper(board_rect=BOARD_RECT)
    detector.CLASS_NAMES = YOLO_CLASSES

    print("[Vision] Lade YOLO-Modell ...")
    detector.load()
    print("[Vision] Starte Kamera ...")
    camera.start()

    with vs.lock:
        vs.ready = True

    print("[Vision] Thread laeuft.")

    while vs.running:
        ok, frame = camera.read()
        if not ok or frame is None:
            time.sleep(0.01)
            continue

        detections = detector.detect(frame) if detector.is_loaded() else []
        annotated  = mapper.draw_grid(frame)
        annotated  = detector.draw_detections(annotated, detections)

        det_with_fields = [
            (det, mapper.get_field(det.center_x, det.center_y))
            for det in detections
        ]

        with vs.lock:
            vs.frame      = annotated
            vs.detections = det_with_fields

        time.sleep(0.01)

    camera.stop()
    print("[Vision] Thread beendet.")


# =============================================================================
# Startscreen – Verbindungsauswahl
# =============================================================================
class StartScreen:
    """
    Erster Bildschirm beim Programmstart.
    Auswahl: Dummy-Roboter (lokal) oder Echter Roboter (IP-Eingabe).
    Gibt (DoosanSocket, RobotController, label) zurueck.
    """

    def __init__(self, screen: pygame.Surface, fonts: dict):
        self.screen      = screen
        self.fonts       = fonts
        self.mode        = None        # "dummy" | "real"
        self.ip_text     = ROBOT_IP
        self.ip_active   = False
        self.status_text = ""
        self.status_col  = DIM
        self.connecting  = False
        self.done        = False
        self.result: tuple | None = None
        self._btn: dict[str, pygame.Rect] = {}

    def run(self) -> tuple:
        clock = pygame.time.Clock()
        while not self.done:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    raise SystemExit
                self._handle_pygame_event(event, mouse)
            self._draw(mouse)
            pygame.display.flip()
            clock.tick(60)
        return self.result

    def _handle_pygame_event(self, event, mouse):
        """Verarbeitet pygame-Events (Maus, Tastatur) im StartScreen."""
        if self.connecting:
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self._btn.get("dummy") and self._btn["dummy"].collidepoint(pos):
                self.mode        = "dummy"
                self.ip_active   = False
                self.status_text = "Dummy-Modus gewaehlt"
                self.status_col  = YELLOW
            elif self._btn.get("real") and self._btn["real"].collidepoint(pos):
                self.mode        = "real"
                self.ip_active   = True
                self.status_text = "IP eingeben und Verbinden druecken"
                self.status_col  = YELLOW
            elif self._btn.get("ip_box") and self._btn["ip_box"].collidepoint(pos):
                self.ip_active = (self.mode == "real")
            elif self._btn.get("connect") and self._btn["connect"].collidepoint(pos):
                self._do_connect()

        if event.type == pygame.KEYDOWN and self.ip_active and self.mode == "real":
            if event.key == pygame.K_BACKSPACE:
                self.ip_text = self.ip_text[:-1]
            elif event.key == pygame.K_RETURN:
                self._do_connect()
            elif event.unicode and len(self.ip_text) < 40:
                self.ip_text += event.unicode

    def _do_connect(self):
        if self.mode is None:
            self.status_text = "Bitte erst Dummy oder Echter Roboter waehlen"
            self.status_col  = RED
            return

        if self.mode == "dummy":
            ip, port = DUMMY_IP, DUMMY_PORT
        else:
            ip   = self.ip_text.strip()
            port = ROBOT_PORT
            if not ip:
                self.status_text = "Bitte eine IP-Adresse eingeben"
                self.status_col  = RED
                return

        self.connecting  = True
        self.status_text = f"Verbinde mit {ip}:{port} ..."
        self.status_col  = YELLOW

        def _thread():
            client = DoosanSocket(ip=ip, port=port, timeout=5)
            ok     = client.connect()
            if ok:
                controller       = RobotController(client)
                label            = ("Dummy-Roboter" if self.mode == "dummy"
                                    else f"Roboter ({ip})")
                self.result      = (client, controller, label)
                self.status_text = f"Verbunden mit {ip}:{port}"
                self.status_col  = GREEN
                self.done        = True
            else:
                self.status_text = f"Verbindung zu {ip}:{port} fehlgeschlagen!"
                if self.mode == "dummy":
                    self.status_text += "  (dummy_robot.py gestartet?)"
                self.status_col = RED
            self.connecting = False

        threading.Thread(target=_thread, daemon=True).start()

    def _draw(self, mouse):
        self.screen.fill(DARK)
        cx = WIN_W // 2

        draw_text(self.screen, "TicTacToe – Doosan M1013",
                  self.fonts["title"], TEXT, cx, 80, "center")
        draw_text(self.screen, "Mensch = X   |   Roboter = O",
                  self.fonts["head"], DIM, cx, 135, "center")
        pygame.draw.line(self.screen, LINE, (cx - 320, 170), (cx + 320, 170), 1)

        draw_text(self.screen, "Verbindungstyp:", self.fonts["body"], DIM, cx - 320, 200)
        self._btn["dummy"] = draw_button(
            self.screen, pygame.Rect(cx - 320, 235, 230, 56),
            "Dummy-Roboter (lokal)", self.fonts["body"],
            active=(self.mode == "dummy"), mouse_pos=mouse,
            border_col=(GREEN if self.mode == "dummy" else LINE))
        self._btn["real"] = draw_button(
            self.screen, pygame.Rect(cx - 70, 235, 230, 56),
            "Echter Roboter (IP)", self.fonts["body"],
            active=(self.mode == "real"), mouse_pos=mouse,
            border_col=(BLUE if self.mode == "real" else LINE))

        draw_text(self.screen, "dummy_robot.py muss laufen",
                  self.fonts["small"], DIM, cx - 320, 302)
        draw_text(self.screen, "Verbindet direkt mit dem Doosan M1013",
                  self.fonts["small"], DIM, cx - 70, 302)

        pygame.draw.line(self.screen, LINE, (cx - 320, 330), (cx + 320, 330), 1)

        ip_label_col = TEXT if self.mode == "real" else DIM
        draw_text(self.screen, "IP-Adresse des Roboters:",
                  self.fonts["body"], ip_label_col, cx - 320, 355)

        ip_rect = pygame.Rect(cx - 320, 390, 390, 50)
        self._btn["ip_box"] = ip_rect
        ip_bg = (40, 60, 100) if self.mode == "real" else (35, 35, 55)
        pygame.draw.rect(self.screen, ip_bg, ip_rect, border_radius=8)
        pygame.draw.rect(self.screen, BLUE if self.ip_active else LINE,
                         ip_rect, 2, border_radius=8)
        ip_display = self.ip_text if self.mode == "real" else DUMMY_IP
        draw_text(self.screen, ip_display, self.fonts["body"],
                  TEXT if self.mode == "real" else DIM,
                  ip_rect.left + 12, ip_rect.centery, "midleft")
        if self.ip_active and int(time.time() * 2) % 2 == 0:
            cx_cur = ip_rect.left + 12 + self.fonts["body"].size(self.ip_text)[0] + 2
            pygame.draw.line(self.screen, TEXT,
                             (cx_cur, ip_rect.top + 10),
                             (cx_cur, ip_rect.bottom - 10), 2)

        draw_text(self.screen, f"Port: {ROBOT_PORT}",
                  self.fonts["small"], DIM, cx - 320, 450)

        btn_text = "Verbinde..." if self.connecting else "Verbinden & Starten"
        btn_bg   = (30, 30, 50) if self.connecting else None
        self._btn["connect"] = draw_button(
            self.screen, pygame.Rect(cx - 320, 485, 600, 58),
            btn_text, self.fonts["head"],
            bg_col=btn_bg, mouse_pos=mouse,
            border_col=(DIM if self.connecting else GOLD))

        draw_text(self.screen, self.status_text,
                  self.fonts["body"], self.status_col, cx, 565, "center")

        pygame.draw.line(self.screen, LINE, (cx - 320, 600), (cx + 320, 600), 1)
        draw_text(self.screen,
                  "Tipp: Starte zuerst dummy_robot.py in einem separaten Terminal,",
                  self.fonts["small"], DIM, cx, 620, "center")
        draw_text(self.screen,
                  "dann waehle Dummy-Roboter und klicke Verbinden.",
                  self.fonts["small"], DIM, cx, 640, "center")


# =============================================================================
# Haupt-App
# =============================================================================
class MainApp:

    # Phasen des Spielablaufs
    PHASE_SELECT_STARTER  = "SELECT_STARTER"
    PHASE_PLAYING         = "PLAYING"
    PHASE_ROBOT_THINKING  = "ROBOT_THINKING"
    PHASE_ROBOT_MOVING    = "ROBOT_MOVING"
    PHASE_ROBOT_REWARDING = "ROBOT_REWARDING"
    PHASE_GAME_OVER       = "GAME_OVER"

    def __init__(self, socket_client: DoosanSocket,
                 robot_controller: RobotController,
                 connection_label: str):
        pygame.display.set_caption("TicTacToe – Doosan M1013")
        self.screen = pygame.display.get_surface()
        self.clock  = pygame.time.Clock()

        # Fonts
        self.f_title = pygame.font.SysFont("segoeui", 32, bold=True)
        self.f_head  = pygame.font.SysFont("segoeui", 24, bold=True)
        self.f_body  = pygame.font.SysFont("segoeui", 20)
        self.f_small = pygame.font.SysFont("segoeui", 17)
        self.f_tiny  = pygame.font.SysFont("segoeui", 14)

        # Roboter
        self.socket_client    = socket_client
        self.robot_controller = robot_controller
        self.connection_label = connection_label
        self.robot_connected  = socket_client.is_connected()

        # Spiel – Rollen fest: Mensch=X, Roboter=O
        self.game    = GameManager(human_player=HUMAN_MARK,
                                   difficulty=DEFAULT_DIFFICULTY)
        self.starter = None   # "human" | "robot" | "random"  – vom Nutzer gewaehlt
        self.phase   = self.PHASE_SELECT_STARTER

        # Roboter-Zug-Steuerung
        self.ai_thinking       = False
        self.ai_pending        = False
        self.ai_started_at     = 0.0
        self.robot_move_field  = None
        self._robot_reset_flag = False

        # Kamera-Bestaetigungslogik
        self.marker_first_seen: dict[int, float] = {}
        self.confirmed_fields:  set[int]         = set()

        # Log
        self.logs: list[LogEntry] = []

        # Button-Rects (werden pro Frame neu gesetzt)
        self._btn_rects: dict[str, pygame.Rect] = {}

        # Vision
        self.vs = VisionState()
        self._vision_thread: threading.Thread | None = None

        # ------------------------------------------------------------------
        # Pending Events (von Button-Thread gesetzt, im Hauptthread verarbeitet)
        # Wird thread-sicher über einen Lock geschützt
        # ------------------------------------------------------------------
        self._pending_lock:       threading.Lock = threading.Lock()
        self._pending_starter:    str | None     = None   # "human"|"robot"|"random"
        self._pending_difficulty: str | None     = None   # difficulty-Konstante
        self._pending_reset:      bool           = False

        # Event-Listener (DRL → PC, Port 5007)
        self._event_listener: EventListener | None = None

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def log(self, text: str, kind: str = "info"):
        self.logs.append(LogEntry(text=text, ts=time.time(), kind=kind))
        self.logs = self.logs[-60:]
        print(f"[{kind.upper()}] {text}")

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------
    def start_vision(self):
        if not VISION_AVAILABLE:
            self.log("Vision-Module fehlen – Kamera deaktiviert", "warn")
            return
        self.vs.running = True
        self._vision_thread = threading.Thread(
            target=vision_thread_fn, args=(self.vs,),
            daemon=True, name="VisionThread")
        self._vision_thread.start()
        self.log("Vision-Thread gestartet", "ok")

    def stop_vision(self):
        self.vs.running = False
        if self._vision_thread:
            self._vision_thread.join(timeout=3.0)

    # ------------------------------------------------------------------
    # Event-Listener (Digital Inputs vom DRL)
    # ------------------------------------------------------------------
    def _start_event_listener(self):
        """
        Startet den TCP-Listener auf Port 5007.
        Events vom DRL werden über _on_button_event() verarbeitet.
        """
        self._event_listener = EventListener(
            ip=self.socket_client.ip,
            port=ROBOT_EVENT_PORT,
            callback=self._on_button_event
        )
        ok = self._event_listener.start()
        if ok:
            self.log("Button-Listener aktiv (Port 5007)", "ok")
        else:
            self.log("Button-Listener nicht verbunden – physische Buttons deaktiviert", "warn")

    def _stop_event_listener(self):
        if self._event_listener:
            self._event_listener.stop()
            self._event_listener = None

    def _on_button_event(self, event_str: str):
        """
        Callback des EventListener-Threads – läuft NICHT im Hauptthread!
        Deshalb: nur Pending-Flags setzen, kein direktes pygame-/Spiellogik-Aufruf.

        Erwartete Event-Formate:
            EVENT:STARTER:human
            EVENT:STARTER:robot
            EVENT:STARTER:random
            EVENT:STARTER:toggle      ← B1 kurz: aktuellen Starter umschalten
            EVENT:DIFFICULTY:easy
            EVENT:DIFFICULTY:medium
            EVENT:DIFFICULTY:hard
            EVENT:RESET
        """
        parts = event_str.strip().split(":")
        if len(parts) < 2 or parts[0].upper() != "EVENT":
            return

        kind = parts[1].upper()

        with self._pending_lock:

            # --- B1: Startspieler ---
            if kind == "STARTER" and len(parts) >= 3:
                value = parts[2].lower()
                if value == "toggle":
                    # Kurzdruck: Mensch ↔ Roboter wechseln (Zufall bleibt)
                    if self._pending_starter == "human" or self.starter == "human":
                        self._pending_starter = "robot"
                    elif self._pending_starter == "robot" or self.starter == "robot":
                        self._pending_starter = "human"
                    else:
                        # Noch kein Starter gewählt → Mensch als Standard
                        self._pending_starter = "human"
                    print(f"[Button] Starter toggle → {self._pending_starter}")
                elif value in ("human", "robot", "random"):
                    self._pending_starter = value
                    print(f"[Button] Starter: {value}")

            # --- B2/B3/B4: Schwierigkeit ---
            elif kind == "DIFFICULTY" and len(parts) >= 3:
                diff_map = {
                    "easy":   AI_DIFFICULTY_EASY,
                    "medium": AI_DIFFICULTY_MEDIUM,
                    "hard":   AI_DIFFICULTY_HARD,
                }
                diff = parts[2].lower()
                if diff in diff_map:
                    self._pending_difficulty = diff_map[diff]
                    print(f"[Button] Schwierigkeit: {diff}")

            # --- B5: Reset ---
            elif kind == "RESET":
                self._pending_reset = True
                print("[Button] Reset")

    def _process_pending_events(self):
        """
        Wird jeden Frame im Hauptthread aufgerufen.
        Verarbeitet Pending-Flags aus _on_button_event() thread-sicher.

        Reihenfolge:
          1. Reset hat höchste Priorität
          2. Schwierigkeit (setzt auch Runde neu, falls Starter bekannt)
          3. Starter (speichert Wahl; Runde startet erst mit Schwierigkeitsbutton)
        """
        with self._pending_lock:
            do_reset      = self._pending_reset
            do_difficulty = self._pending_difficulty
            do_starter    = self._pending_starter

            self._pending_reset      = False
            self._pending_difficulty = None
            self._pending_starter    = None

        # --- Reset ---
        if do_reset:
            self.log("[Button B5] Vollständiger Reset", "warn")
            self.full_reset()
            return   # Reset überschreibt alles andere

        # --- Schwierigkeit (B2/B3/B4) ---
        # NEU
        if do_difficulty is not None:
            diff_label = {
                AI_DIFFICULTY_EASY:   "Leicht",
                AI_DIFFICULTY_MEDIUM: "Mittel",
                AI_DIFFICULTY_HARD:   "Schwer",
            }.get(do_difficulty, do_difficulty)
            self.game.set_difficulty(do_difficulty)
            self.log(f"[Button] Schwierigkeit: {diff_label}", "info")
        
            # Falls noch kein Starter gewählt → automatisch Mensch
            if self.starter is None:
                self.starter = "human"
                self.log("Kein Startspieler gesetzt – Mensch beginnt automatisch", "info")
        
            self.log("Runde wird gestartet...", "ok")
            self.reset_round()

        # --- Starter (B1) ---
        if do_starter is not None:
            self.starter = do_starter
            label = {"human": "Mensch", "robot": "Roboter",
                     "random": "Zufall"}.get(do_starter, do_starter)
            self.log(f"[Button B1] Startspieler: {label} – "
                     f"Drücke B2/B3/B4 zum Starten", "info")
            # Runde startet NICHT hier – erst wenn Schwierigkeit gewählt wird

    # ------------------------------------------------------------------
    # Startspieler-Auswahl
    # ------------------------------------------------------------------
    def choose_starter(self, starter: str):
        """Wird aufgerufen wenn der Nutzer einen Startspieler-Button drueckt."""
        self.starter = starter
        resolved = (random.choice(["human", "robot"])
                    if starter == "random" else starter)
        if starter == "random":
            self.log(f"Zufall → {resolved} beginnt", "info")
        self._begin_round(resolved)

    def _begin_round(self, starter: str):
        """Startet eine Runde mit dem angegebenen Startspieler."""
        self._abort_robot_turn()
        start_mark = HUMAN_MARK if starter == "human" else ROBOT_MARK
        self.game.reset(start_player=start_mark)
        self._reset_vision_state()
        self.robot_controller.reset_counters()
        self.log(f"Neue Runde – {starter} beginnt", "ok")

        if starter == "robot":
            self.phase = self.PHASE_ROBOT_THINKING
            self._trigger_robot_turn()
        else:
            self.phase = self.PHASE_PLAYING

    # ------------------------------------------------------------------
    # Runden-Reset
    # ------------------------------------------------------------------
    def reset_round(self):
        """
        Neue Runde mit denselben Einstellungen.
        Startspieler-Auswahl bleibt erhalten, Runde wird direkt neu gestartet.
        """
        self._abort_robot_turn()
        self._send_home_async()

        if self.starter is None:
            self.phase = self.PHASE_SELECT_STARTER
            self.log("Bitte erst Startspieler waehlen", "warn")
            return

        resolved = (random.choice(["human", "robot"])
                    if self.starter == "random" else self.starter)
        if self.starter == "random":
            self.log(f"Zufall → {resolved} beginnt", "info")
        self._begin_round(resolved)

    def full_reset(self):
        """
        Vollstaendiger Reset:
        Alle Einstellungen zurueck, Startspieler muss neu gewaehlt werden.
        """
        self._abort_robot_turn()
        self._send_home_async()

        self.game.full_reset()
        self._reset_vision_state()
        self.robot_controller.reset_counters()
        self.starter = None
        self.phase   = self.PHASE_SELECT_STARTER
        self.log("Alles zurueckgesetzt", "info")

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------
    def _reset_vision_state(self):
        self.marker_first_seen.clear()
        self.confirmed_fields.clear()

    def _send_home_async(self):
        """Schickt den Roboter zu HOME (nicht-blockierend)."""
        if self.robot_connected:
            threading.Thread(
                target=self.robot_controller.go_home,
                daemon=True).start()
            self.log("Roboter faehrt HOME", "robot")

    def _abort_robot_turn(self):
        """Bricht einen laufenden Roboter-Zug ab (nur Python-Seite)."""
        if self.ai_thinking:
            self._robot_reset_flag = True
        self.ai_thinking      = False
        self.ai_pending       = False
        self.robot_move_field = None

    # ------------------------------------------------------------------
    # Roboter-Zug-Logik
    # ------------------------------------------------------------------
    def _trigger_robot_turn(self):
        if self.ai_thinking:
            return
        self._robot_reset_flag = False
        self.ai_thinking       = True
        self.ai_pending        = True
        self.ai_started_at     = time.time()
        self.log("Roboter denkt...", "robot")

    def _process_robot_turn(self):
        """Wird jeden Frame aufgerufen wenn phase == ROBOT_THINKING."""
        if not self.ai_pending:
            return
        if time.time() - self.ai_started_at < 0.8:
            return

        self.ai_pending = False

        if self._robot_reset_flag:
            self._robot_reset_flag = False
            self.ai_thinking       = False
            return

        move = self.game._get_ai_move()
        if move is None:
            self.ai_thinking = False
            self.phase = self.PHASE_GAME_OVER
            return

        self.robot_move_field = move
        self.phase = self.PHASE_ROBOT_MOVING
        self.log(f"KI waehlt Feld {move}", "robot")

        threading.Thread(
            target=self._execute_robot_move,
            args=(move,),
            daemon=True).start()

    def _execute_robot_move(self, move: int):
        """Laeuft im Hintergrund-Thread: PICK → PLACE → Spielzustand aktualisieren."""
        if self._robot_reset_flag:
            self._clear_robot_state()
            return

        self.log(f"Sende PICK {ROBOT_MARK}", "robot")
        ok_pick = (self.robot_controller.pick()
                   if self.robot_connected
                   else self._simulate_delay())

        if self._robot_reset_flag:
            self._clear_robot_state()
            return

        if not ok_pick:
            self._robot_error_recovery(f"PICK {ROBOT_MARK} fehlgeschlagen")
            return

        self.log(f"PICK OK – sende PLACE {move}", "robot")
        ok_place = (self.robot_controller.place(move)
                    if self.robot_connected
                    else self._simulate_delay())

        if self._robot_reset_flag:
            self._clear_robot_state()
            return

        if not ok_place:
            self._robot_error_recovery(f"PLACE {move} fehlgeschlagen")
            return

        if not self.game.board.is_empty(move):
            self.log(f"Feld {move} bereits belegt – Zug verworfen", "warn")
            self._clear_robot_state()
            self.phase = self.PHASE_PLAYING
            return

        self.game.board.place(move, ROBOT_MARK)
        self.game._after_move()
        self.log(f"Roboter setzt O auf Feld {move}", "ok")
        self._clear_robot_state()
        self._check_game_state()

    def _execute_reward_move(self):
        """Laeuft im Hintergrund-Thread: PUSH → GAME_OVER."""
        self.log("Sende PUSH (Belohnung)", "robot")
        ok = (self.robot_controller.push_reward()
              if self.robot_connected
              else self._simulate_delay(1.0))
        if ok:
            self.log("Belohnung ausgegeben!", "ok")
        else:
            self.log("PUSH fehlgeschlagen", "error")
            self._send_home_async()
        self.phase = self.PHASE_GAME_OVER

    def _robot_error_recovery(self, reason: str):
        """Bei Fehler: HOME fahren und Runde neu starten."""
        self.log(f"Fehler: {reason} – Recovery", "error")
        self._clear_robot_state()
        if self.robot_connected:
            self.log("Sende HOME (Recovery)...", "robot")
            ok = self.robot_controller.go_home()
            self.log("HOME OK" if ok else "HOME fehlgeschlagen!", "ok" if ok else "error")
        self.log("Runde wird neu gestartet", "info")
        self.reset_round()

    def _clear_robot_state(self):
        self._robot_reset_flag = False
        self.ai_thinking       = False
        self.robot_move_field  = None

    @staticmethod
    def _simulate_delay(seconds: float = 1.5) -> bool:
        time.sleep(seconds)
        return True

    # ------------------------------------------------------------------
    # Spielzustand pruefen
    # ------------------------------------------------------------------
    def _check_game_state(self):
        if self.game.state == "running":
            if self.game.is_ai_turn():
                self.phase = self.PHASE_ROBOT_THINKING
                self._trigger_robot_turn()
            else:
                self.phase = self.PHASE_PLAYING
        elif self.game.state == "human_won":
            self.phase = self.PHASE_ROBOT_REWARDING
            self.log("Mensch gewinnt! Starte Belohnungs-Sequenz...", "robot")
            threading.Thread(target=self._execute_reward_move, daemon=True).start()
        elif self.game.state == "ai_won":
            self.log("Roboter gewinnt – keine Belohnung.", "info")
            self.phase = self.PHASE_GAME_OVER
        else:
            self.phase = self.PHASE_GAME_OVER

    # ------------------------------------------------------------------
    # Mensch-Zug (Maus oder Kamera)
    # ------------------------------------------------------------------
    def human_move(self, fid: int):
        if self.phase != self.PHASE_PLAYING:
            return
        if self.game.state != "running":
            return
        if not self.game.is_human_turn():
            return
        if not self.game.board.is_empty(fid):
            return
        self.game.human_move(fid)
        self.log(f"Mensch setzt X auf Feld {fid}", "human")
        self._check_game_state()

    # ------------------------------------------------------------------
    # Kamera-Bestaetigungslogik (nur X-Steine akzeptieren)
    # ------------------------------------------------------------------
    def _update_confirmation(self, det_with_fields: list):
        if self.phase != self.PHASE_PLAYING:
            return
        if not self.game.is_human_turn():
            return

        now         = time.time()
        seen_fields = set()

        for det, fid in det_with_fields:
            # Nur X-Steine zaehlen – O-Steine werden ignoriert
            if getattr(det, "label", None) != HUMAN_MARK:
                continue
            if fid is None or fid in self.confirmed_fields:
                continue
            if not self.game.board.is_empty(fid):
                continue

            seen_fields.add(fid)
            if fid not in self.marker_first_seen:
                self.marker_first_seen[fid] = now
            elif now - self.marker_first_seen[fid] >= CONFIRMATION_SECONDS:
                self.confirmed_fields.add(fid)
                self.marker_first_seen.pop(fid, None)
                self.log(f"X-Stein bestaetigt auf Feld {fid}", "ok")
                self.human_move(fid)
                return

        # Felder aus dem Timer entfernen, die nicht mehr sichtbar sind
        for fid in list(self.marker_first_seen):
            if fid not in seen_fields:
                self.marker_first_seen.pop(fid, None)

    # ------------------------------------------------------------------
    # Zeichnen – Kamera-Panel
    # ------------------------------------------------------------------
    def _draw_camera_panel(self):
        with self.vs.lock:
            frame      = self.vs.frame
            ready      = self.vs.ready
            det_fields = list(self.vs.detections)

        if frame is not None and ready:
            surf = frame_to_surface(frame, CAM_W, CAM_H)
        else:
            surf = pygame.Surface((CAM_W, CAM_H))
            surf.fill((18, 18, 28))
            msg = ("Vision-Thread startet..."
                   if VISION_AVAILABLE else "Kein Kamera-Modul")
            draw_text(surf, msg, self.f_head, DIM, CAM_W // 2, CAM_H // 2, "center")

        self.screen.blit(surf, (CAM_X, CAM_Y))
        pygame.draw.rect(self.screen, LINE, (CAM_X, CAM_Y, CAM_W, CAM_H), 2)

        # Bestaetigungs-Fortschrittsbalken
        now = time.time()
        for fid, ts in self.marker_first_seen.items():
            progress = min(1.0, (now - ts) / CONFIRMATION_SECONDS)
            bar_x = CAM_X + 10 + (fid - 1) * 85
            bar_y = CAM_Y + CAM_H - 22
            pygame.draw.rect(self.screen, (50, 50, 70),
                             (bar_x, bar_y, 75, 14), border_radius=4)
            pygame.draw.rect(self.screen, GREEN,
                             (bar_x, bar_y, int(75 * progress), 14), border_radius=4)
            draw_text(self.screen, f"F{fid}", self.f_tiny, TEXT, bar_x + 2, bar_y - 14)

        return det_fields

    # ------------------------------------------------------------------
    # Zeichnen – 2D-Brett
    # ------------------------------------------------------------------
    def _draw_board(self, mouse_pos):
        # Hintergrund
        pygame.draw.rect(self.screen, PANEL,
                         (BOARD_X - 15, BOARD_Y - 15,
                          BOARD_SIZE + 30, BOARD_SIZE + 30),
                         border_radius=14)
        pygame.draw.rect(self.screen, LINE,
                         (BOARD_X - 15, BOARD_Y - 15,
                          BOARD_SIZE + 30, BOARD_SIZE + 30),
                         2, border_radius=14)

        # Gitterlinien
        for i in range(1, 3):
            x = BOARD_X + i * CELL
            y = BOARD_Y + i * CELL
            pygame.draw.line(self.screen, LINE,
                             (x, BOARD_Y), (x, BOARD_Y + BOARD_SIZE), 4)
            pygame.draw.line(self.screen, LINE,
                             (BOARD_X, y), (BOARD_X + BOARD_SIZE, y), 4)
        pygame.draw.rect(self.screen, LINE,
                         (BOARD_X, BOARD_Y, BOARD_SIZE, BOARD_SIZE), 4)

        # Steine zeichnen
        for fid in range(1, 10):
            val      = self.game.board.get_cell(fid)
            row, col = FIELD_MAP[fid]
            cx       = BOARD_X + col * CELL + CELL // 2
            cy       = BOARD_Y + row * CELL + CELL // 2
            if val == "X":
                r = CELL // 2 - 18
                pygame.draw.line(self.screen, X_COL,
                                 (cx - r, cy - r), (cx + r, cy + r), 7)
                pygame.draw.line(self.screen, X_COL,
                                 (cx + r, cy - r), (cx - r, cy + r), 7)
            elif val == "O":
                pygame.draw.circle(self.screen, O_COL,
                                   (cx, cy), CELL // 2 - 18, 7)

        # Gewinner-Linie
        if self.game.board.winning_combo:
            def center(fid):
                rr, cc = (fid - 1) // 3, (fid - 1) % 3
                return (BOARD_X + cc * CELL + CELL // 2,
                        BOARD_Y + rr * CELL + CELL // 2)
            pygame.draw.line(self.screen, GOLD,
                             center(self.game.board.winning_combo[0]),
                             center(self.game.board.winning_combo[2]), 8)

        # Hover-Effekt (nur wenn Mensch am Zug)
        if self.phase == self.PHASE_PLAYING and self.game.is_human_turn():
            fid = field_from_mouse(*mouse_pos)
            if fid and self.game.board.is_empty(fid):
                row, col = FIELD_MAP[fid]
                s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                s.fill((255, 255, 255, 20))
                self.screen.blit(s, (BOARD_X + col * CELL, BOARD_Y + row * CELL))

        # Roboter-Ziel-Highlight (blinkt)
        if self.robot_move_field and self.phase == self.PHASE_ROBOT_MOVING:
            fid      = self.robot_move_field
            row, col = FIELD_MAP[fid]
            if int(time.time() * 2) % 2 == 0:
                s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                s.fill((80, 180, 220, 40))
                self.screen.blit(s, (BOARD_X + col * CELL, BOARD_Y + row * CELL))

    # ------------------------------------------------------------------
    # Zeichnen – Status-Panel (rechts)
    # ------------------------------------------------------------------
    def _draw_status_panel(self, mouse_pos):
        px = RIGHT_X
        pw = RIGHT_W

        pygame.draw.rect(self.screen, PANEL2,
                         (px, 65, pw, WIN_H - 75), border_radius=14)
        pygame.draw.rect(self.screen, LINE,
                         (px, 65, pw, WIN_H - 75), 2, border_radius=14)

        y = 85

        # --- Haupt-Status-Text ---
        if self.phase == self.PHASE_SELECT_STARTER:
            stxt, scol = "Wer faengt an?", YELLOW
        elif self.phase == self.PHASE_ROBOT_THINKING:
            stxt, scol = "Roboter denkt...", BLUE
        elif self.phase == self.PHASE_ROBOT_MOVING:
            stxt, scol = "Roboter faehrt...", BLUE
        elif self.phase == self.PHASE_ROBOT_REWARDING:
            stxt, scol = "Belohnung laeuft...", GOLD
        elif self.game.state == "human_won":
            stxt, scol = "Du hast gewonnen!", GOLD
        elif self.game.state == "ai_won":
            stxt, scol = "Roboter gewinnt!", O_COL
        elif self.game.state == "draw":
            stxt, scol = "Unentschieden!", DIM
        elif self.game.is_human_turn():
            stxt, scol = "Dein Zug!", X_COL
        else:
            stxt, scol = "Roboter am Zug", O_COL

        draw_text(self.screen, stxt, self.f_title, scol,
                  px + pw // 2, y + 20, "center")
        y += 55

        # --- Verbindungsstatus ---
        conn_col = GREEN if self.robot_connected else RED
        conn_txt = f"● {self.connection_label}" if self.robot_connected else "● Offline"
        draw_text(self.screen, conn_txt, self.f_tiny, conn_col,
                  px + pw // 2, y, "center")
        y += 22

        # --- Button-Listener-Status ---
        listener_ok = (self._event_listener is not None and
                       self._event_listener.is_running())
        listener_col = GREEN if listener_ok else DIM
        listener_txt = "● Buttons aktiv" if listener_ok else "○ Buttons inaktiv"
        draw_text(self.screen, listener_txt, self.f_tiny, listener_col,
                  px + pw // 2, y, "center")
        y += 22

        # --- Rollen-Info (fest) ---
        draw_text(self.screen, "Mensch: X     Roboter: O",
                  self.f_body, DIM, px + pw // 2, y, "center")
        y += 30

        # --- Punkte ---
        draw_text(self.screen, f"Du: {self.game.scores['human']}",
                  self.f_body, X_COL, px + 20, y)
        draw_text(self.screen, f"Roboter: {self.game.scores['ai']}",
                  self.f_body, O_COL, px + 180, y)
        draw_text(self.screen, f"Remis: {self.game.scores['draw']}",
                  self.f_body, DIM, px + 350, y)
        y += 40

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 14

        # --- Startspieler-Buttons (UI) ---
        draw_text(self.screen, "Wer faengt an?  [B1]", self.f_small, DIM, px + 20, y)
        y += 26
        self._btn_rects["start_h"] = draw_button(
            self.screen, pygame.Rect(px + 20,  y, 120, 42), "Mensch",
            self.f_small, active=(self.starter == "human"),
            mouse_pos=mouse_pos)
        self._btn_rects["start_r"] = draw_button(
            self.screen, pygame.Rect(px + 150, y, 120, 42), "Roboter",
            self.f_small, active=(self.starter == "robot"),
            mouse_pos=mouse_pos)
        self._btn_rects["start_z"] = draw_button(
            self.screen, pygame.Rect(px + 280, y, 120, 42), "Zufall",
            self.f_small, active=(self.starter == "random"),
            mouse_pos=mouse_pos)
        y += 56

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 14

        # --- Schwierigkeit (UI) ---
        draw_text(self.screen, "Schwierigkeit  [B2 / B3 / B4]",
                  self.f_small, DIM, px + 20, y)
        y += 26
        self._btn_rects["easy"] = draw_button(
            self.screen, pygame.Rect(px + 20,  y, 120, 40), "Leicht",
            self.f_small, active=(self.game.difficulty == AI_DIFFICULTY_EASY),
            mouse_pos=mouse_pos)
        self._btn_rects["medium"] = draw_button(
            self.screen, pygame.Rect(px + 150, y, 120, 40), "Mittel",
            self.f_small, active=(self.game.difficulty == AI_DIFFICULTY_MEDIUM),
            mouse_pos=mouse_pos)
        self._btn_rects["hard"] = draw_button(
            self.screen, pygame.Rect(px + 280, y, 120, 40), "Schwer",
            self.f_small, active=(self.game.difficulty == AI_DIFFICULTY_HARD),
            mouse_pos=mouse_pos)
        y += 56

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 14

        # --- Aktions-Buttons (UI) ---
        self._btn_rects["new_round"] = draw_button(
            self.screen, pygame.Rect(px + 20,  y, 175, 46), "Neue Runde",
            self.f_body, mouse_pos=mouse_pos)
        self._btn_rects["full_rst"] = draw_button(
            self.screen, pygame.Rect(px + 210, y, 175, 46), "Alles Reset  [B5]",
            self.f_body, mouse_pos=mouse_pos)
        y += 62

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 10

        # --- Log ---
        draw_text(self.screen, "Log:", self.f_small, DIM, px + 20, y)
        y += 20
        log_box = pygame.Rect(px + 10, y, pw - 20, WIN_H - y - 15)
        pygame.draw.rect(self.screen, (16, 16, 26), log_box, border_radius=8)
        pygame.draw.rect(self.screen, LINE, log_box, 1, border_radius=8)

        now     = time.time()
        visible = [e for e in self.logs
                   if now - e.ts <= LOG_TTL_SECONDS][-MAX_LOG_VISIBLE:]
        ly = log_box.top + 8
        for entry in visible:
            col = {"ok": GREEN, "error": RED, "robot": BLUE,
                   "human": X_COL, "warn": YELLOW}.get(entry.kind, TEXT)
            draw_text(self.screen, f"▸ {entry.text}",
                      self.f_tiny, col, px + 18, ly)
            ly += 19

    # ------------------------------------------------------------------
    # Klick-Handler (Maus-UI)
    # ------------------------------------------------------------------
    def _handle_click(self, pos):
        b = self._btn_rects

        # Startspieler (nur speichern, Runde startet erst mit Schwierigkeit)
        if b.get("start_h") and b["start_h"].collidepoint(pos):
            self.starter = "human"
            self.log("Startspieler: Mensch – wähle Schwierigkeit zum Starten", "info")
            return
        if b.get("start_r") and b["start_r"].collidepoint(pos):
            self.starter = "robot"
            self.log("Startspieler: Roboter – wähle Schwierigkeit zum Starten", "info")
            return
        if b.get("start_z") and b["start_z"].collidepoint(pos):
            self.starter = "random"
            self.log("Startspieler: Zufall – wähle Schwierigkeit zum Starten", "info")
            return

        # Schwierigkeit – startet sofort Runde wenn Starter bekannt
        if b.get("easy") and b["easy"].collidepoint(pos):
            self.game.set_difficulty(AI_DIFFICULTY_EASY)
            self.log("Schwierigkeit: Leicht", "info")
            if not self.starter:
                self.starter = "human"
                self.log("Kein Startspieler – Mensch beginnt automatisch", "info")
            self.reset_round()
            return
        if b.get("medium") and b["medium"].collidepoint(pos):
            self.game.set_difficulty(AI_DIFFICULTY_MEDIUM)
            self.log("Schwierigkeit: Mittel", "info")
            if self.starter:
                self.reset_round()
            else:
                self.log("Bitte erst Startspieler waehlen", "warn")
            return
        if b.get("hard") and b["hard"].collidepoint(pos):
            self.game.set_difficulty(AI_DIFFICULTY_HARD)
            self.log("Schwierigkeit: Schwer", "info")
            if self.starter:
                self.reset_round()
            else:
                self.log("Bitte erst Startspieler waehlen", "warn")
            return

        # Reset-Buttons
        if b.get("new_round") and b["new_round"].collidepoint(pos):
            self.reset_round()
            return
        if b.get("full_rst") and b["full_rst"].collidepoint(pos):
            self.full_reset()
            return

        # Maus-Klick auf das 2D-Brett
        fid = field_from_mouse(*pos)
        if fid is not None:
            self.human_move(fid)

    # ------------------------------------------------------------------
    # Hauptschleife
    # ------------------------------------------------------------------
    def run(self):
        self.start_vision()
        self.log(f"Verbunden: {self.connection_label}", "ok")
        self.log("Mensch = X  |  Roboter = O", "info")

        # Event-Listener starten (Digital Inputs vom DRL)
        self._start_event_listener()

        running = True
        while running:
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self.reset_round()
                    elif event.key == pygame.K_F1:
                        self.full_reset()

            # Pending Events aus Button-Thread verarbeiten
            self._process_pending_events()

            if self.phase == self.PHASE_ROBOT_THINKING:
                self._process_robot_turn()

            self.screen.fill(BG)
            draw_text(self.screen, "TicTacToe – Doosan M1013",
                      self.f_head, TEXT, WIN_W // 2, 22, "center")

            det_fields = self._draw_camera_panel()
            self._update_confirmation(det_fields)
            self._draw_board(mouse)
            self._draw_status_panel(mouse)

            pygame.display.flip()
            self.clock.tick(60)

        # Aufräumen
        self._stop_event_listener()
        self.stop_vision()
        self.socket_client.disconnect()
        pygame.quit()


# =============================================================================
# Einstiegspunkt
# =============================================================================
if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("TicTacToe – Doosan M1013")

    fonts = {
        "title": pygame.font.SysFont("segoeui", 36, bold=True),
        "head":  pygame.font.SysFont("segoeui", 26, bold=True),
        "body":  pygame.font.SysFont("segoeui", 20),
        "small": pygame.font.SysFont("segoeui", 16),
    }

    screen = pygame.display.get_surface()
    start  = StartScreen(screen, fonts)

    try:
        client, controller, label = start.run()
    except SystemExit:
        raise

    app = MainApp(client, controller, label)
    app.run()
