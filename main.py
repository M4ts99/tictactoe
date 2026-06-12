# =============================================================================
# main.py – Hauptprogramm TicTacToe Doosan M1013
#
# Architektur:
#   - Vision-Thread:  Kamera lesen + YOLO inferenz (laeuft separat)
#   - Pygame-Thread:  UI zeichnen + Events (Hauptthread)
#   - Shared State:   frame + detections via threading.Lock
# =============================================================================
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np
import pygame

from config import (
    AI_DIFFICULTY_EASY,
    AI_DIFFICULTY_HARD,
    AI_DIFFICULTY_MEDIUM,
    DEFAULT_DIFFICULTY,
    YOLO_MODEL_PATH,
    YOLO_CONFIDENCE,
    YOLO_CLASSES,
)
from game.game_manager import GameManager

# Vision-Imports – wenn nicht vorhanden, laeuft App ohne Kamera
try:
    from vision.camera import Camera
    from vision.yolo_detector import YoloDetector, Detection
    from vision.board_mapper import BoardMapper
    VISION_AVAILABLE = True
except Exception as _e:
    print(f"[WARN] Vision-Module nicht geladen: {_e}")
    VISION_AVAILABLE = False

# =============================================================================
# Layout-Konstanten
# =============================================================================
WIN_W, WIN_H = 1500, 860

# Kamera-Panel (links oben)
CAM_X, CAM_Y = 15, 65
CAM_W, CAM_H = 800, 450

# 2D-Spielbrett (links unten)
BOARD_X, BOARD_Y = 30, 535
BOARD_SIZE       = 320
CELL             = BOARD_SIZE // 3

# Status-Panel (rechts)
RIGHT_X = 835
RIGHT_W = WIN_W - RIGHT_X - 10

# Board-Mapper-Rect im Kamerabild (Pixel) – nach Kalibrierung anpassen!
# Format: (x1, y1, x2, y2) innerhalb des angezeigten CAM_W x CAM_H Bildes
BOARD_RECT = (340, 60, 940, 660)


# =============================================================================
# Timing
# =============================================================================
CONFIRMATION_SECONDS = 2.0   # Stein muss X Sekunden stabil erkannt werden
LOG_TTL_SECONDS      = 15.0  # Wie lange bleiben Log-Eintraege sichtbar
MAX_LOG_VISIBLE      = 10    # Wie viele Log-Zeilen gleichzeitig angezeigt

# =============================================================================
# Farben
# =============================================================================
BG      = (18,  18,  30)
PANEL   = (26,  26,  40)
PANEL2  = (32,  32,  50)
LINE    = (80,  80, 120)
TEXT    = (235, 235, 240)
DIM     = (130, 130, 155)
X_COL   = (220,  80,  80)
O_COL   = (80,  180, 220)
GOLD    = (255, 215,   0)
GREEN   = (80,  210, 110)
RED     = (235,  80,  80)
YELLOW  = (240, 200,  70)
BLUE    = (100, 155, 255)


# =============================================================================
# Log-Eintrag
# =============================================================================
@dataclass
class LogEntry:
    text: str
    ts:   float
    kind: str = "info"   # info | ok | error | robot | human | warn


# =============================================================================
# Shared Vision State  (zwischen Vision-Thread und Pygame-Thread)
# =============================================================================
@dataclass
class VisionState:
    frame:       np.ndarray | None = None
    detections:  list              = field(default_factory=list)
    lock:        threading.Lock    = field(default_factory=threading.Lock)
    running:     bool              = True
    ready:       bool              = False


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


def draw_button(surface, rect, text, font, active=False, mouse_pos=(0, 0)):
    r = pygame.Rect(rect)
    if active:
        col = (65, 100, 170)
    elif r.collidepoint(mouse_pos):
        col = (55, 55, 90)
    else:
        col = (40, 40, 65)
    pygame.draw.rect(surface, col, r, border_radius=10)
    pygame.draw.rect(surface, LINE, r, 2, border_radius=10)
    lbl = font.render(text, True, TEXT)
    surface.blit(lbl, lbl.get_rect(center=r.center))
    return r


def field_from_mouse(mx, my):
    bx = mx - BOARD_X
    by = my - BOARD_Y
    if not (0 <= bx < BOARD_SIZE and 0 <= by < BOARD_SIZE):
        return None
    col = int(bx // CELL)
    row = int(by // CELL)
    fid = row * 3 + col + 1
    return fid if 1 <= fid <= 9 else None


def frame_to_surface(frame: np.ndarray, w: int, h: int) -> pygame.Surface:
    """Konvertiert OpenCV BGR-Frame in eine Pygame-Surface."""
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_rgb = cv2.resize(frame_rgb, (w, h), interpolation=cv2.INTER_LINEAR)
    frame_rgb = cv2.flip(frame_rgb, 1)
    return pygame.surfarray.make_surface(np.rot90(frame_rgb))


# =============================================================================
# Vision-Thread
# =============================================================================
def vision_thread_fn(vs: VisionState):
    """
    Laeuft in einem separaten Thread.
    Liest Kamera-Frames und fuehrt YOLO-Inferenz durch.
    Ergebnisse werden thread-sicher in VisionState abgelegt.
    """
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

        annotated = mapper.draw_grid(frame)
        annotated = detector.draw_detections(annotated, detections)

        det_with_fields = []
        for det in detections:
            fid = mapper.get_field(det.center_x, det.center_y)
            det_with_fields.append((det, fid))

        with vs.lock:
            vs.frame      = annotated
            vs.detections = det_with_fields

        time.sleep(0.01)

    camera.stop()
    print("[Vision] Thread beendet.")


# =============================================================================
# Haupt-App
# =============================================================================
class MainApp:

    # Spielphasen
    PHASE_SELECT_MARK    = "SELECT_MARK"
    PHASE_SELECT_STARTER = "SELECT_STARTER"
    PHASE_PLAYING        = "PLAYING"
    PHASE_ROBOT_THINKING = "ROBOT_THINKING"
    PHASE_ROBOT_MOVING   = "ROBOT_MOVING"
    PHASE_GAME_OVER      = "GAME_OVER"

    def __init__(self):
        pygame.init()
        pygame.display.set_caption("TicTacToe – Doosan M1013")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock  = pygame.time.Clock()

        # -------------------------------------------------------------------
        # _btn_rects: wird JEDES Frame in _draw_status_panel neu befuellt.
        # Schluesselnamen muessen exakt mit _handle_click uebereinstimmen.
        # -------------------------------------------------------------------
        self._btn_rects: dict[str, pygame.Rect] = {}

        self.f_title = pygame.font.SysFont("segoeui", 32, bold=True)
        self.f_head  = pygame.font.SysFont("segoeui", 24, bold=True)
        self.f_body  = pygame.font.SysFont("segoeui", 20)
        self.f_small = pygame.font.SysFont("segoeui", 17)
        self.f_tiny  = pygame.font.SysFont("segoeui", 14)

        # Spiel
        self.game          = GameManager(human_player="X", difficulty=DEFAULT_DIFFICULTY)
        self.phase         = self.PHASE_SELECT_MARK
        self.selected_mark = None
        self.human_side    = None
        self.robot_side    = None
        self.starter       = None

        # Roboter-Zug
        self.ai_thinking       = False
        self.ai_pending        = False
        self.ai_started_at     = 0.0
        self.robot_move_field  = None
        self._robot_reset_flag = False

        # Stein-Bestätigung (Kamera -> Board)
        self.marker_first_seen: dict[int, float] = {}
        self.confirmed_fields:  set[int]         = set()

        # Log
        self.logs: list[LogEntry] = []

        # Vision (Thread)
        self.vs = VisionState()
        self._vision_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def log(self, text: str, kind: str = "info"):
        self.logs.append(LogEntry(text=text, ts=time.time(), kind=kind))
        self.logs = self.logs[-60:]
        print(f"[{kind.upper()}] {text}")

    # ------------------------------------------------------------------
    # Vision-Thread starten / stoppen
    # ------------------------------------------------------------------
    def start_vision(self):
        if not VISION_AVAILABLE:
            self.log("Vision-Module fehlen – Kamera deaktiviert", "warn")
            return
        self.vs.running = True
        self._vision_thread = threading.Thread(
            target=vision_thread_fn,
            args=(self.vs,),
            daemon=True,
            name="VisionThread",
        )
        self._vision_thread.start()
        self.log("Vision-Thread gestartet", "ok")

    def stop_vision(self):
        self.vs.running = False
        if self._vision_thread is not None:
            self._vision_thread.join(timeout=3.0)

    # ------------------------------------------------------------------
    # Spielsteuerung
    # ------------------------------------------------------------------
    def choose_mark(self, mark: str):
        """Markierung wählen – kann auch mitten im Spiel geändert werden."""
        self.selected_mark = mark
        self.human_side    = mark
        self.robot_side    = "O" if mark == "X" else "X"
        # Wenn schon ein Starter gewählt war, direkt neue Runde starten
        if self.starter:
            self._start_new_round_with_current_settings()
        else:
            self.game = GameManager(human_player=mark, difficulty=self.game.difficulty)
            self._reset_vision_state()
            self.log(f"Du spielst {mark}", "ok")
            self.phase = self.PHASE_SELECT_STARTER

    def choose_starter(self, starter: str):
        """Startspieler wählen – kann auch mitten im Spiel geändert werden."""
        if starter == "random":
            resolved = random.choice(["human", "robot"])
            self.log(f"Zufall → {resolved} beginnt", "info")
            self.starter = starter          # "random" merken fuer reset_round
            starter      = resolved
        else:
            self.starter = starter

        self._apply_starter(starter)

    def _apply_starter(self, starter: str):
        """Interne Hilfsmethode: Starter anwenden und Runde starten."""
        # ERST abbrechen, DANN reset – sonst kann der Thread noch reinschreiben
        self._abort_robot_turn()
        start_mark = self.human_side if starter == "human" else self.robot_side
        self.game.reset(start_player=start_mark)
        self._reset_vision_state()
        self.log(f"Startspieler: {starter}", "ok")

        if starter == "robot":
            self.phase = self.PHASE_ROBOT_THINKING
            self._trigger_robot_turn()
        else:
            self.phase = self.PHASE_PLAYING

    def _start_new_round_with_current_settings(self):
        """
        Startet eine neue Runde mit den aktuell gespeicherten Einstellungen
        (mark, starter, difficulty). Wird aufgerufen wenn Einstellungen
        mitten im Spiel geändert werden.
        """
        if not self.selected_mark or not self.starter:
            self.phase = self.PHASE_SELECT_STARTER if self.selected_mark else self.PHASE_SELECT_MARK
            return

        self._abort_robot_turn()
        self.game = GameManager(human_player=self.human_side, difficulty=self.game.difficulty)

        # Starter auflösen (random → konkret)
        if self.starter == "random":
            resolved = random.choice(["human", "robot"])
            self.log(f"Zufall → {resolved} beginnt", "info")
        else:
            resolved = self.starter

        self._apply_starter(resolved)

    def _reset_vision_state(self):
        self.marker_first_seen.clear()
        self.confirmed_fields.clear()

    def _abort_robot_turn(self):
        """
        Bricht einen laufenden Roboter-Zug sofort ab.
        Setzt den Reset-Flag NUR wenn wirklich ein Zug läuft,
        damit ein direkt danach gestarteter Zug nicht fälschlicherweise
        abgebrochen wird.
        """
        if self.ai_thinking:
            self._robot_reset_flag = True
        self.ai_thinking      = False
        self.ai_pending       = False
        self.robot_move_field = None

    def _trigger_robot_turn(self):
        """Startet den Roboter-Zug-Zyklus. Setzt den Reset-Flag vorher zurück."""
        if self.ai_thinking:
            return
        self._robot_reset_flag = False   # ← Flag immer zurücksetzen vor neuem Zug
        self.ai_thinking       = True
        self.ai_pending        = True
        self.ai_started_at     = time.time()
        self.log("Roboter denkt...", "robot")

    def _process_robot_turn(self):
        """
        Wird jeden Frame aufgerufen solange phase == ROBOT_THINKING.
        Berechnet den KI-Zug nach kurzer Denkpause und startet
        dann den Simulations-Thread für die Roboter-Bewegung.
        """
        if not self.ai_pending:
            return
        elapsed = time.time() - self.ai_started_at
        if elapsed < 0.8:
            return   # kurze Denkpause

        self.ai_pending = False

        # Abbruch-Check: wurde zwischenzeitlich reset gerufen?
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
        self.log(f"Zug berechnet: Feld {move}", "robot")
        self.log(f"Koordinate an Roboter gesendet: Feld {move}", "robot")

        # Simuliertes Roboter-OK in eigenem Thread
        # Wir übergeben den aktuellen robot_side-Wert als Argument,
        # damit ein zwischenzeitliches Reset nicht die falsche Seite setzt.
        threading.Thread(
            target=self._simulate_robot_ok,
            args=(move, self.robot_side),
            daemon=True,
        ).start()

    def _simulate_robot_ok(self, move: int, robot_side: str):
        """
        Läuft in separatem Thread – simuliert Roboter-Ankunft nach 1.5s.
        Prüft den Reset-Flag NACH dem Schlafen, bevor irgendwas ins Board
        geschrieben wird.
        """
        time.sleep(1.5)

        # Wurde zwischenzeitlich ein Reset ausgelöst?
        if self._robot_reset_flag:
            self._robot_reset_flag = False
            self.ai_thinking       = False
            self.robot_move_field  = None
            return

        # Nochmal prüfen ob das Feld noch frei ist (Sicherheit)
        if not self.game.board.is_empty(move):
            self.log(f"Feld {move} bereits belegt – Zug verworfen", "warn")
            self.ai_thinking      = False
            self.robot_move_field = None
            self.phase = self.PHASE_PLAYING
            return

        # Zug ins Board schreiben
        self.game.board.place(move, robot_side)
        self.game._after_move()
        self.log(f"Roboter angekommen – Feld {move} gesetzt", "ok")
        self.ai_thinking      = False
        self.robot_move_field = None

        if self.game.state == "running":
            self.phase = self.PHASE_PLAYING
        else:
            self.phase = self.PHASE_GAME_OVER

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
        self.log(f"Mensch setzt auf Feld {fid}", "human")
        if self.game.state != "running":
            self.phase = self.PHASE_GAME_OVER
        elif self.game.is_ai_turn():
            self.phase = self.PHASE_ROBOT_THINKING
            self._trigger_robot_turn()

    def reset_round(self):
        """Neue Runde mit denselben Einstellungen."""
        self._abort_robot_turn()
        if not self.selected_mark or not self.starter:
            self.phase = self.PHASE_SELECT_STARTER if self.selected_mark else self.PHASE_SELECT_MARK
            self.log("Bitte erst Einstellungen waehlen", "warn")
            return

        start_mark = self.human_side if self.starter == "human" else self.robot_side
        if self.starter == "random":
            resolved   = random.choice(["human", "robot"])
            start_mark = self.human_side if resolved == "human" else self.robot_side
            self.log(f"Zufall → {resolved} beginnt", "info")

        self.game.reset(start_player=start_mark)
        self._reset_vision_state()
        self.log("Neue Runde", "info")

        if start_mark == self.robot_side:
            self.phase = self.PHASE_ROBOT_THINKING
            self._trigger_robot_turn()   # setzt _robot_reset_flag = False intern
        else:
            self.phase = self.PHASE_PLAYING

    def full_reset(self):
        """Alles zurücksetzen – zurück zur Markierungswahl."""
        self._abort_robot_turn()
        self.game.full_reset()
        self._reset_vision_state()
        self.selected_mark = None
        self.human_side    = None
        self.robot_side    = None
        self.starter       = None
        self.phase         = self.PHASE_SELECT_MARK
        self.log("Alles zurueckgesetzt", "info")

    # ------------------------------------------------------------------
    # Kamera-Bestätigung (Vision → Board)
    # ------------------------------------------------------------------
    def _update_confirmation(self, det_with_fields: list):
        if self.phase != self.PHASE_PLAYING:
            return
        if not self.game.is_human_turn():
            return

        now = time.time()
        seen_fields = set()

        for det, fid in det_with_fields:
            if fid is None:
                continue
            if fid in self.confirmed_fields:
                continue
            if not self.game.board.is_empty(fid):
                continue
            seen_fields.add(fid)
            if fid not in self.marker_first_seen:
                self.marker_first_seen[fid] = now
            elif now - self.marker_first_seen[fid] >= CONFIRMATION_SECONDS:
                self.confirmed_fields.add(fid)
                self.marker_first_seen.pop(fid, None)
                self.log(f"Stein erkannt auf Feld {fid} – bestaetigt", "ok")
                self.human_move(fid)
                return

        for fid in list(self.marker_first_seen.keys()):
            if fid not in seen_fields:
                self.marker_first_seen.pop(fid, None)

    # ------------------------------------------------------------------
    # Zeichnen: Kamera-Panel
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
            msg = "Vision-Thread startet..." if VISION_AVAILABLE else "Kein Kamera-Modul"
            draw_text(surf, msg, self.f_head, DIM, CAM_W // 2, CAM_H // 2, "center")

        self.screen.blit(surf, (CAM_X, CAM_Y))
        pygame.draw.rect(self.screen, LINE, (CAM_X, CAM_Y, CAM_W, CAM_H), 2)

        now = time.time()
        for fid, ts in self.marker_first_seen.items():
            progress = min(1.0, (now - ts) / CONFIRMATION_SECONDS)
            bar_x = CAM_X + 10 + (fid - 1) * 85
            bar_y = CAM_Y + CAM_H - 22
            pygame.draw.rect(self.screen, (50, 50, 70), (bar_x, bar_y, 75, 14), border_radius=4)
            pygame.draw.rect(self.screen, GREEN, (bar_x, bar_y, int(75 * progress), 14), border_radius=4)
            draw_text(self.screen, f"F{fid}", self.f_tiny, TEXT, bar_x + 2, bar_y - 14)

        return det_fields

    # ------------------------------------------------------------------
    # Zeichnen: 2D-Spielbrett
    # ------------------------------------------------------------------
    def _draw_board(self, mouse_pos):
        pygame.draw.rect(self.screen, PANEL,
                         (BOARD_X - 15, BOARD_Y - 15, BOARD_SIZE + 30, BOARD_SIZE + 30),
                         border_radius=14)
        pygame.draw.rect(self.screen, LINE,
                         (BOARD_X - 15, BOARD_Y - 15, BOARD_SIZE + 30, BOARD_SIZE + 30),
                         2, border_radius=14)

        for i in range(1, 3):
            x = BOARD_X + i * CELL
            y = BOARD_Y + i * CELL
            pygame.draw.line(self.screen, LINE, (x, BOARD_Y), (x, BOARD_Y + BOARD_SIZE), 4)
            pygame.draw.line(self.screen, LINE, (BOARD_X, y), (BOARD_X + BOARD_SIZE, y), 4)
        pygame.draw.rect(self.screen, LINE, (BOARD_X, BOARD_Y, BOARD_SIZE, BOARD_SIZE), 4)

        for fid in range(1, 10):
            val = self.game.board.get_cell(fid)
            row = (fid - 1) // 3
            col = (fid - 1) % 3
            cx  = BOARD_X + col * CELL + CELL // 2
            cy  = BOARD_Y + row * CELL + CELL // 2
            if val == "X":
                r = CELL // 2 - 18
                pygame.draw.line(self.screen, X_COL, (cx - r, cy - r), (cx + r, cy + r), 7)
                pygame.draw.line(self.screen, X_COL, (cx + r, cy - r), (cx - r, cy + r), 7)
            elif val == "O":
                pygame.draw.circle(self.screen, O_COL, (cx, cy), CELL // 2 - 18, 7)

        if self.game.board.winning_combo:
            def center(idx):
                rr, cc = idx // 3, idx % 3
                return (BOARD_X + cc * CELL + CELL // 2,
                        BOARD_Y + rr * CELL + CELL // 2)
            pygame.draw.line(self.screen, GOLD,
                             center(self.game.board.winning_combo[0]),
                             center(self.game.board.winning_combo[2]), 8)

        if self.phase == self.PHASE_PLAYING and self.game.is_human_turn():
            fid = field_from_mouse(*mouse_pos)
            if fid and self.game.board.is_empty(fid):
                row = (fid - 1) // 3
                col = (fid - 1) % 3
                s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                s.fill((255, 255, 255, 20))
                self.screen.blit(s, (BOARD_X + col * CELL, BOARD_Y + row * CELL))

        if self.robot_move_field and self.phase == self.PHASE_ROBOT_MOVING:
            fid = self.robot_move_field
            row = (fid - 1) // 3
            col = (fid - 1) % 3
            if int(time.time() * 2) % 2 == 0:
                s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                s.fill((80, 180, 220, 40))
                self.screen.blit(s, (BOARD_X + col * CELL, BOARD_Y + row * CELL))

    # ------------------------------------------------------------------
    # Zeichnen: Status-Panel (rechts)
    # WICHTIG: Jeder draw_button-Aufruf speichert sein Rect sofort
    #          in self._btn_rects – so stimmen Klick-Ziele immer.
    # ------------------------------------------------------------------
    def _draw_status_panel(self, mouse_pos):
        px = RIGHT_X
        pw = RIGHT_W

        pygame.draw.rect(self.screen, PANEL2,
                         (px, 65, pw, WIN_H - 75), border_radius=14)
        pygame.draw.rect(self.screen, LINE,
                         (px, 65, pw, WIN_H - 75), 2, border_radius=14)

        y = 85

        # --- Status-Text ---
        if self.phase == self.PHASE_SELECT_MARK:
            stxt, scol = "Waehle deine Rolle", YELLOW
        elif self.phase == self.PHASE_SELECT_STARTER:
            stxt, scol = "Wer faengt an?", YELLOW
        elif self.phase == self.PHASE_ROBOT_THINKING:
            stxt, scol = "Roboter denkt...", BLUE
        elif self.phase == self.PHASE_ROBOT_MOVING:
            stxt, scol = "Roboter faehrt...", BLUE
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

        draw_text(self.screen, stxt, self.f_title, scol, px + pw // 2, y + 20, "center")
        y += 60

        # --- Rollen-Info ---
        hmark = self.selected_mark or "–"
        rmark = self.robot_side    or "–"
        draw_text(self.screen, f"Du: {hmark}   Roboter: {rmark}", self.f_body, DIM, px + 20, y)
        y += 35

        # --- Score ---
        draw_text(self.screen, f"Du: {self.game.scores['human']}",
                  self.f_body, X_COL, px + 20, y)
        draw_text(self.screen, f"Roboter: {self.game.scores['ai']}",
                  self.f_body, O_COL, px + 180, y)
        draw_text(self.screen, f"Remis: {self.game.scores['draw']}",
                  self.f_body, DIM, px + 340, y)
        y += 45

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 15

        # ---------------------------------------------------------------
        # Rolle wählen  (jederzeit klickbar)
        # ---------------------------------------------------------------
        draw_text(self.screen, "Rolle waehlen:", self.f_small, DIM, px + 20, y)
        y += 28
        self._btn_rects["mark_x"] = draw_button(
            self.screen, pygame.Rect(px + 20, y, 140, 40), "Ich bin X",
            self.f_small, active=(self.selected_mark == "X"), mouse_pos=mouse_pos)
        self._btn_rects["mark_o"] = draw_button(
            self.screen, pygame.Rect(px + 175, y, 140, 40), "Ich bin O",
            self.f_small, active=(self.selected_mark == "O"), mouse_pos=mouse_pos)
        y += 55

        # ---------------------------------------------------------------
        # Startspieler  (jederzeit klickbar)
        # ---------------------------------------------------------------
        draw_text(self.screen, "Wer faengt an?", self.f_small, DIM, px + 20, y)
        y += 28
        self._btn_rects["start_h"] = draw_button(
            self.screen, pygame.Rect(px + 20,  y, 120, 40), "Mensch",
            self.f_small, active=(self.starter == "human"), mouse_pos=mouse_pos)
        self._btn_rects["start_r"] = draw_button(
            self.screen, pygame.Rect(px + 150, y, 120, 40), "Roboter",
            self.f_small, active=(self.starter == "robot"), mouse_pos=mouse_pos)
        self._btn_rects["start_z"] = draw_button(
            self.screen, pygame.Rect(px + 280, y, 120, 40), "Zufall",
            self.f_small, active=(self.starter == "random"), mouse_pos=mouse_pos)
        y += 55

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 15

        # ---------------------------------------------------------------
        # Schwierigkeit  (jederzeit klickbar – startet neue Runde)
        # ---------------------------------------------------------------
        draw_text(self.screen, "Schwierigkeit:", self.f_small, DIM, px + 20, y)
        y += 28
        self._btn_rects["easy"] = draw_button(
            self.screen, pygame.Rect(px + 20,  y, 120, 38), "Leicht",
            self.f_small, active=(self.game.difficulty == AI_DIFFICULTY_EASY),
            mouse_pos=mouse_pos)
        self._btn_rects["medium"] = draw_button(
            self.screen, pygame.Rect(px + 150, y, 120, 38), "Mittel",
            self.f_small, active=(self.game.difficulty == AI_DIFFICULTY_MEDIUM),
            mouse_pos=mouse_pos)
        self._btn_rects["hard"] = draw_button(
            self.screen, pygame.Rect(px + 280, y, 120, 38), "Schwer",
            self.f_small, active=(self.game.difficulty == AI_DIFFICULTY_HARD),
            mouse_pos=mouse_pos)
        y += 55

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 15

        # ---------------------------------------------------------------
        # Aktions-Buttons
        # ---------------------------------------------------------------
        self._btn_rects["new_round"] = draw_button(
            self.screen, pygame.Rect(px + 20,  y, 180, 44), "Neue Runde",
            self.f_small, mouse_pos=mouse_pos)
        self._btn_rects["full_rst"] = draw_button(
            self.screen, pygame.Rect(px + 215, y, 180, 44), "Alles Reset",
            self.f_small, mouse_pos=mouse_pos)
        y += 60

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 12

        # ---------------------------------------------------------------
        # Mini-Log
        # ---------------------------------------------------------------
        draw_text(self.screen, "Log:", self.f_small, DIM, px + 20, y)
        y += 22
        log_box = pygame.Rect(px + 10, y, pw - 20, WIN_H - y - 20)
        pygame.draw.rect(self.screen, (16, 16, 26), log_box, border_radius=8)
        pygame.draw.rect(self.screen, LINE, log_box, 1, border_radius=8)

        now = time.time()
        visible = [e for e in self.logs if now - e.ts <= LOG_TTL_SECONDS]
        visible = visible[-MAX_LOG_VISIBLE:]
        ly = log_box.top + 8
        for entry in visible:
            col = {
                "ok":    GREEN,
                "error": RED,
                "robot": BLUE,
                "human": X_COL,
                "warn":  YELLOW,
            }.get(entry.kind, TEXT)
            draw_text(self.screen, f"▸ {entry.text}", self.f_tiny, col, px + 18, ly)
            ly += 19

    # ------------------------------------------------------------------
    # Event-Handler  (alle Buttons jederzeit reagieren)
    # ------------------------------------------------------------------
    def _handle_click(self, pos):
        b = self._btn_rects

        # --- Rolle wählen (jederzeit) ---
        if b.get("mark_x") and b["mark_x"].collidepoint(pos):
            self.choose_mark("X"); return
        if b.get("mark_o") and b["mark_o"].collidepoint(pos):
            self.choose_mark("O"); return

        # --- Startspieler (nur wenn Markierung gewählt) ---
        if b.get("start_h") and b["start_h"].collidepoint(pos):
            if self.selected_mark:
                self.choose_starter("human"); return
            else:
                self.log("Bitte erst eine Rolle waehlen", "warn"); return
        if b.get("start_r") and b["start_r"].collidepoint(pos):
            if self.selected_mark:
                self.choose_starter("robot"); return
            else:
                self.log("Bitte erst eine Rolle waehlen", "warn"); return
        if b.get("start_z") and b["start_z"].collidepoint(pos):
            if self.selected_mark:
                self.choose_starter("random"); return
            else:
                self.log("Bitte erst eine Rolle waehlen", "warn"); return

        # --- Schwierigkeit (jederzeit – neue Runde wird gestartet) ---
        if b.get("easy") and b["easy"].collidepoint(pos):
            self.game.set_difficulty(AI_DIFFICULTY_EASY)
            self.log("Schwierigkeit: Leicht – neue Runde", "info")
            self._start_new_round_with_current_settings(); return
        if b.get("medium") and b["medium"].collidepoint(pos):
            self.game.set_difficulty(AI_DIFFICULTY_MEDIUM)
            self.log("Schwierigkeit: Mittel – neue Runde", "info")
            self._start_new_round_with_current_settings(); return
        if b.get("hard") and b["hard"].collidepoint(pos):
            self.game.set_difficulty(AI_DIFFICULTY_HARD)
            self.log("Schwierigkeit: Schwer – neue Runde", "info")
            self._start_new_round_with_current_settings(); return

        # --- Runden-Steuerung ---
        if b.get("new_round") and b["new_round"].collidepoint(pos):
            self.reset_round(); return
        if b.get("full_rst") and b["full_rst"].collidepoint(pos):
            self.full_reset(); return

        # --- Spielfeld-Klick ---
        fid = field_from_mouse(*pos)
        if fid is not None:
            self.human_move(fid)

    # ------------------------------------------------------------------
    # Hauptschleife
    # ------------------------------------------------------------------
    def run(self):
        self.start_vision()
        self.log("Programm gestartet", "ok")

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

            # -------------------------------------------------------
            # WICHTIG: Hintergrund zuerst füllen, dann alles zeichnen
            # -------------------------------------------------------
            self.screen.fill(BG)
            draw_text(self.screen, "TicTacToe – Doosan M1013",
                      self.f_head, TEXT, WIN_W // 2, 22, "center")

            # Roboter-Zug verarbeiten
            if self.phase == self.PHASE_ROBOT_THINKING:
                self._process_robot_turn()

            # Kamera zeichnen + Detektionen holen
            det_fields = self._draw_camera_panel()

            # Bestätigung prüfen
            self._update_confirmation(det_fields)

            # Board + Status zeichnen
            self._draw_board(mouse)
            self._draw_status_panel(mouse)

            pygame.display.flip()
            self.clock.tick(60)

        self.stop_vision()
        pygame.quit()


# =============================================================================
# Einstiegspunkt
# =============================================================================
if __name__ == "__main__":
    MainApp().run()
