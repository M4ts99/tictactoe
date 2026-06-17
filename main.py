# =============================================================================
# main_v2.py – Hauptprogramm TicTacToe Doosan M1013
#
# Architektur:
#   - Startscreen:    Auswahl Dummy / Echter Roboter + IP-Eingabe
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
    ROBOT_IP,
    ROBOT_PORT,
)
from game.game_manager import GameManager
from robot.socket_client import DoosanSocket
from robot.robot_controller import RobotController

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

CAM_X, CAM_Y = 15, 65
CAM_W, CAM_H = 800, 450

BOARD_X, BOARD_Y = 30, 535
BOARD_SIZE       = 320
CELL             = BOARD_SIZE // 3

RIGHT_X = 835
RIGHT_W = WIN_W - RIGHT_X - 10

BOARD_RECT = (340, 60, 940, 660)

CONFIRMATION_SECONDS = 2.0
LOG_TTL_SECONDS      = 15.0
MAX_LOG_VISIBLE      = 10

DUMMY_IP   = "127.0.0.1"
DUMMY_PORT = 12345

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
DARK    = (12,  12,  22)


# =============================================================================
# Datenklassen
# =============================================================================
@dataclass
class LogEntry:
    text: str
    ts:   float
    kind: str = "info"


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
def reset_round(self):
    self._abort_robot_turn()
    # ↓ NEU: Roboter zu HOME schicken (im Hintergrund, nicht blockierend)
    if self.robot_connected:
        threading.Thread(
            target=self.robot_controller.go_home,
            daemon=True
        ).start()
        self.log("Roboter faehrt HOME (Reset)", "robot")
    # ... Rest bleibt gleich

def full_reset(self):
    self._abort_robot_turn()
    # ↓ NEU: Roboter zu HOME schicken (im Hintergrund, nicht blockierend)
    if self.robot_connected:
        threading.Thread(
            target=self.robot_controller.go_home,
            daemon=True
        ).start()
        self.log("Roboter faehrt HOME (Full Reset)", "robot")
    # ... Rest bleibt gleich


def draw_button(surface, rect, text, font, active=False, mouse_pos=(0, 0),
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
    bx = mx - BOARD_X
    by = my - BOARD_Y
    if not (0 <= bx < BOARD_SIZE and 0 <= by < BOARD_SIZE):
        return None
    col = int(bx // CELL)
    row = int(by // CELL)
    fid = row * 3 + col + 1
    return fid if 1 <= fid <= 9 else None


def frame_to_surface(frame: np.ndarray, w: int, h: int) -> pygame.Surface:
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_rgb = cv2.resize(frame_rgb, (w, h), interpolation=cv2.INTER_LINEAR)
    frame_rgb = cv2.flip(frame_rgb, 1)
    return pygame.surfarray.make_surface(np.rot90(frame_rgb))


# =============================================================================
# Vision-Thread
# =============================================================================
def vision_thread_fn(vs: VisionState):
    if not VISION_AVAILABLE:
        print("[Vision] Module nicht verfuegbar.")
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

        det_with_fields = [(det, mapper.get_field(det.center_x, det.center_y))
                           for det in detections]

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
    Zeigt beim Programmstart einen Screen:
      - Dummy-Roboter (lokal, sofort)
      - Echter Roboter (IP-Eingabe, dann Verbindungsversuch)
    Gibt (socket_client, robot_controller, mode_label) zurueck.
    """

    def __init__(self, screen: pygame.Surface, fonts: dict):
        self.screen = screen
        self.fonts  = fonts
        self.mode   = None          # "dummy" | "real"
        self.ip_text = ROBOT_IP     # Startwert aus config
        self.ip_active = False
        self.status_text = ""
        self.status_col  = DIM
        self.connecting  = False
        self.done        = False
        self.result: tuple | None = None   # (DoosanSocket, RobotController, str)
        self._btn: dict[str, pygame.Rect] = {}

    def run(self) -> tuple:
        """Blockiert bis der Nutzer eine Verbindung gewählt und bestätigt hat."""
        clock = pygame.time.Clock()
        while not self.done:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    raise SystemExit
                self._handle_event(event, mouse)

            self._draw(mouse)
            pygame.display.flip()
            clock.tick(60)

        return self.result

    def _handle_event(self, event, mouse):
        if self.connecting:
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos

            if self._btn.get("dummy") and self._btn["dummy"].collidepoint(pos):
                self.mode      = "dummy"
                self.ip_active = False
                self.status_text = "Dummy-Modus gewaehlt"
                self.status_col  = YELLOW

            elif self._btn.get("real") and self._btn["real"].collidepoint(pos):
                self.mode      = "real"
                self.ip_active = True
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

        def _connect_thread():
            client = DoosanSocket(ip=ip, port=port, timeout=5)
            ok     = client.connect()
            if ok:
                controller       = RobotController(client)
                label            = "Dummy-Roboter" if self.mode == "dummy" else f"Roboter ({ip})"
                self.result      = (client, controller, label)
                self.status_text = f"Verbunden mit {ip}:{port}"
                self.status_col  = GREEN
                self.done        = True
            else:
                self.status_text = f"Verbindung zu {ip}:{port} fehlgeschlagen!"
                self.status_col  = RED
                if self.mode == "dummy":
                    self.status_text += "  (Dummy-Server gestartet?)"
            self.connecting = False

        threading.Thread(target=_connect_thread, daemon=True).start()

    def _draw(self, mouse):
        self.screen.fill(DARK)

        cx = WIN_W // 2
        draw_text(self.screen, "TicTacToe – Doosan M1013",
                  self.fonts["title"], TEXT, cx, 80, "center")
        draw_text(self.screen, "Roboter-Verbindung einrichten",
                  self.fonts["head"], DIM, cx, 130, "center")

        pygame.draw.line(self.screen, LINE, (cx - 300, 165), (cx + 300, 165), 1)

        # Modus-Buttons
        draw_text(self.screen, "Verbindungstyp:", self.fonts["body"], DIM, cx - 300, 200)
        self._btn["dummy"] = draw_button(
            self.screen, pygame.Rect(cx - 300, 235, 220, 56),
            "Dummy-Roboter (lokal)", self.fonts["body"],
            active=(self.mode == "dummy"), mouse_pos=mouse,
            border_col=(GREEN if self.mode == "dummy" else LINE))
        self._btn["real"] = draw_button(
            self.screen, pygame.Rect(cx - 60, 235, 220, 56),
            "Echter Roboter (IP)", self.fonts["body"],
            active=(self.mode == "real"), mouse_pos=mouse,
            border_col=(BLUE if self.mode == "real" else LINE))

        # Info-Texte
        draw_text(self.screen,
                  "Startet einen lokalen Dummy-Server (dummy_robot.py muss laufen)",
                  self.fonts["small"], DIM, cx - 300, 305)
        draw_text(self.screen,
                  "Verbindet direkt mit dem echten Doosan M1013 ueber TCP",
                  self.fonts["small"], DIM, cx - 60, 305)

        pygame.draw.line(self.screen, LINE, (cx - 300, 335), (cx + 300, 335), 1)

        # IP-Eingabe
        draw_text(self.screen, "IP-Adresse des Roboters:",
                  self.fonts["body"], DIM if self.mode != "real" else TEXT,
                  cx - 300, 360)

        ip_col = (55, 55, 90) if self.mode != "real" else (40, 60, 100)
        ip_rect = pygame.Rect(cx - 300, 395, 380, 50)
        self._btn["ip_box"] = ip_rect
        pygame.draw.rect(self.screen, ip_col, ip_rect, border_radius=8)
        border = BLUE if self.ip_active else LINE
        pygame.draw.rect(self.screen, border, ip_rect, 2, border_radius=8)

        ip_display = self.ip_text if self.mode == "real" else DUMMY_IP
        draw_text(self.screen, ip_display, self.fonts["body"],
                  TEXT if self.mode == "real" else DIM,
                  ip_rect.left + 12, ip_rect.centery, "midleft")

        if self.ip_active and int(time.time() * 2) % 2 == 0:
            cursor_x = ip_rect.left + 12 + self.fonts["body"].size(self.ip_text)[0] + 2
            pygame.draw.line(self.screen, TEXT,
                             (cursor_x, ip_rect.top + 10),
                             (cursor_x, ip_rect.bottom - 10), 2)

        draw_text(self.screen, f"Port: {ROBOT_PORT}",
                  self.fonts["small"], DIM, cx - 300, 455)

        # Verbinden-Button
        connecting_now = self.connecting
        btn_col  = (30, 30, 50) if connecting_now else None
        btn_text = "Verbinde..." if connecting_now else "Verbinden & Starten"
        self._btn["connect"] = draw_button(
            self.screen, pygame.Rect(cx - 300, 490, 580, 58),
            btn_text, self.fonts["head"],
            bg_col=btn_col, mouse_pos=mouse,
            border_col=(GOLD if not connecting_now else DIM))

        # Status
        draw_text(self.screen, self.status_text,
                  self.fonts["body"], self.status_col, cx, 570, "center")

        # Hinweis
        pygame.draw.line(self.screen, LINE, (cx - 300, 610), (cx + 300, 610), 1)
        draw_text(self.screen,
                  "Tipp: Starte zuerst dummy_robot.py in einem separaten Terminal,",
                  self.fonts["small"], DIM, cx, 630, "center")
        draw_text(self.screen,
                  "dann waehle Dummy-Roboter und klicke Verbinden.",
                  self.fonts["small"], DIM, cx, 650, "center")


# =============================================================================
# Haupt-App
# =============================================================================
class MainApp:

    PHASE_SELECT_MARK     = "SELECT_MARK"
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

        self.f_title = pygame.font.SysFont("segoeui", 32, bold=True)
        self.f_head  = pygame.font.SysFont("segoeui", 24, bold=True)
        self.f_body  = pygame.font.SysFont("segoeui", 20)
        self.f_small = pygame.font.SysFont("segoeui", 17)
        self.f_tiny  = pygame.font.SysFont("segoeui", 14)

        self.socket_client      = socket_client
        self.robot_controller   = robot_controller
        self.connection_label   = connection_label
        self.robot_connected    = socket_client.is_connected()

        self.game          = GameManager(human_player="X", difficulty=DEFAULT_DIFFICULTY)
        self.phase         = self.PHASE_SELECT_MARK
        self.selected_mark = None
        self.human_side    = None
        self.robot_side    = None
        self.starter       = None

        self.ai_thinking       = False
        self.ai_pending        = False
        self.ai_started_at     = 0.0
        self.robot_move_field  = None
        self._robot_reset_flag = False

        self.marker_first_seen: dict[int, float] = {}
        self.confirmed_fields:  set[int]         = set()

        self.logs: list[LogEntry] = []
        self._btn_rects: dict[str, pygame.Rect] = {}

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
    # Spielsteuerung
    # ------------------------------------------------------------------
    def choose_mark(self, mark: str):
        self.selected_mark = mark
        self.human_side    = mark
        self.robot_side    = "O" if mark == "X" else "X"
        if self.starter:
            self._start_new_round_with_current_settings()
        else:
            self.game = GameManager(human_player=mark, difficulty=self.game.difficulty)
            self._reset_vision_state()
            self.log(f"Du spielst {mark}", "ok")
            self.phase = self.PHASE_SELECT_STARTER

    def choose_starter(self, starter: str):
        if starter == "random":
            resolved = random.choice(["human", "robot"])
            self.log(f"Zufall → {resolved} beginnt", "info")
            self.starter = starter
            self._apply_starter(resolved)
        else:
            self.starter = starter
            self._apply_starter(starter)

    def _apply_starter(self, starter: str):
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
        if not self.selected_mark or not self.starter:
            self.phase = self.PHASE_SELECT_STARTER if self.selected_mark else self.PHASE_SELECT_MARK
            return
        self._abort_robot_turn()
        self.game = GameManager(human_player=self.human_side, difficulty=self.game.difficulty)
        resolved = (random.choice(["human", "robot"])
                    if self.starter == "random" else self.starter)
        if self.starter == "random":
            self.log(f"Zufall → {resolved} beginnt", "info")
        self._apply_starter(resolved)

    def _reset_vision_state(self):
        self.marker_first_seen.clear()
        self.confirmed_fields.clear()

    def _abort_robot_turn(self):
        if self.ai_thinking:
            self._robot_reset_flag = True
        self.ai_thinking      = False
        self.ai_pending       = False
        self.robot_move_field = None

    def _trigger_robot_turn(self):
        if self.ai_thinking:
            return
        self._robot_reset_flag = False
        self.ai_thinking       = True
        self.ai_pending        = True
        self.ai_started_at     = time.time()
        self.log("Roboter denkt...", "robot")

    def _process_robot_turn(self):
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
        self.log(f"Zug berechnet: Feld {move}", "robot")
        threading.Thread(target=self._execute_robot_move,
                         args=(move, self.robot_side),
                         daemon=True).start()

    def _robot_error_recovery(self, reason: str):
        """
        Automatische Fehler-Recovery:
        1. HOME-Befehl an Roboter senden
        2. Runde auf dem PC automatisch neu starten
        """
        self.log(f"Fehler: {reason} – starte Recovery", "error")

        # Roboter-Zustand sofort zuruecksetzen
        self.ai_thinking      = False
        self.ai_pending       = False
        self.robot_move_field = None

        # HOME senden (blockierend, im selben Hintergrund-Thread)
        if self.robot_connected:
            self.log("Sende HOME (Recovery)...", "robot")
            ok = self.robot_controller.go_home()
            if ok:
                self.log("Roboter zurueck in HOME", "ok")
            else:
                self.log("HOME fehlgeschlagen – Roboter manuell pruefen!", "error")

        # Runde automatisch neu starten
        self.log("Runde wird automatisch neu gestartet", "info")
        self.reset_round()


    def _execute_robot_move(self, move: int, robot_side: str):
        if self._robot_reset_flag:
            self._robot_reset_flag = False
            self.ai_thinking       = False
            self.robot_move_field  = None
            return

        self.log(f"Sende PICK {robot_side}", "robot")

        if self.robot_connected:
            ok_pick = self.robot_controller.pick(robot_side)
        else:
            self.log("Kein Roboter – simuliere PICK", "warn")
            time.sleep(1.0)
            ok_pick = True

        if self._robot_reset_flag:
            self._robot_reset_flag = False
            self.ai_thinking       = False
            self.robot_move_field  = None
            return

        if not ok_pick:
            self._robot_error_recovery(f"PICK {robot_side} Timeout/Fehler")
            return

        self.log(f"PICK OK – sende PLACE {move}", "robot")

        if self.robot_connected:
            ok_place = self.robot_controller.place(move)
        else:
            self.log("Kein Roboter – simuliere PLACE", "warn")
            time.sleep(1.0)
            ok_place = True

        if self._robot_reset_flag:
            self._robot_reset_flag = False
            self.ai_thinking       = False
            self.robot_move_field  = None
            return

        if not ok_place:
            self._robot_error_recovery(f"PLACE {move} Timeout/Fehler")
            return

        if not self.game.board.is_empty(move):
            self.log(f"Feld {move} bereits belegt – Zug verworfen", "warn")
            self.ai_thinking      = False
            self.robot_move_field = None
            self.phase = self.PHASE_PLAYING
            return

        self.game.board.place(move, robot_side)
        self.game._after_move()
        self.log(f"Roboter fertig – Feld {move} gesetzt", "ok")
        self.ai_thinking      = False
        self.robot_move_field = None
        self._check_game_state_after_move()


    def _execute_reward_move(self):
        self.log("Sende PUSH (Belohnung)", "robot")
        if self.robot_connected:
            ok = self.robot_controller.push_reward()
        else:
            time.sleep(1.0)
            ok = True

        if ok:
            self.log("Belohnung ausgegeben!", "ok")
        else:
            self.log("PUSH fehlgeschlagen – sende HOME", "error")
            if self.robot_connected:
                threading.Thread(
                    target=self.robot_controller.go_home,
                    daemon=True
                ).start()

        self.phase = self.PHASE_GAME_OVER


    def _check_game_state_after_move(self):
        if self.game.state == "running":
            if self.game.is_ai_turn():
                self.phase = self.PHASE_ROBOT_THINKING
                self._trigger_robot_turn()
            else:
                self.phase = self.PHASE_PLAYING
        elif self.game.state in ("human_won", "ai_won"):
            self.phase = self.PHASE_ROBOT_REWARDING
            self.log("Spiel beendet – starte Belohnungs-Sequenz", "robot")
            threading.Thread(target=self._execute_reward_move, daemon=True).start()
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
        self._check_game_state_after_move()

    def reset_round(self):
        self._abort_robot_turn()
        # Roboter zu HOME schicken (im Hintergrund, nicht blockierend)
        if self.robot_connected:
            threading.Thread(
                target=self.robot_controller.go_home,
                daemon=True
            ).start()
            self.log("Roboter faehrt HOME", "robot")

        if not self.selected_mark or not self.starter:
            self.phase = (self.PHASE_SELECT_STARTER if self.selected_mark
                          else self.PHASE_SELECT_MARK)
            self.log("Bitte erst Einstellungen waehlen", "warn")
            return
        resolved = (random.choice(["human", "robot"])
                    if self.starter == "random" else self.starter)
        if self.starter == "random":
            self.log(f"Zufall → {resolved} beginnt", "info")
        start_mark = self.human_side if resolved == "human" else self.robot_side
        self.game.reset(start_player=start_mark)
        self._reset_vision_state()
        self.log("Neue Runde", "info")
        if start_mark == self.robot_side:
            self.phase = self.PHASE_ROBOT_THINKING
            self._trigger_robot_turn()
        else:
            self.phase = self.PHASE_PLAYING

    def full_reset(self):
        self._abort_robot_turn()
        # Roboter zu HOME schicken (im Hintergrund, nicht blockierend)
        if self.robot_connected:
            threading.Thread(
                target=self.robot_controller.go_home,
                daemon=True
            ).start()
            self.log("Roboter faehrt HOME", "robot")

        self.game.full_reset()
        self._reset_vision_state()
        self.selected_mark = None
        self.human_side    = None
        self.robot_side    = None
        self.starter       = None
        self.phase         = self.PHASE_SELECT_MARK
        self.log("Alles zurueckgesetzt", "info")

    # ------------------------------------------------------------------
    # Kamera-Bestätigung
    # ------------------------------------------------------------------
    def _update_confirmation(self, det_with_fields: list):
        if self.phase != self.PHASE_PLAYING:
            return
        if not self.game.is_human_turn():
            return
        now = time.time()
        seen_fields = set()
        for det, fid in det_with_fields:
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
                self.log(f"Stein erkannt auf Feld {fid}", "ok")
                self.human_move(fid)
                return
        for fid in list(self.marker_first_seen):
            if fid not in seen_fields:
                self.marker_first_seen.pop(fid, None)

    # ------------------------------------------------------------------
    # Zeichnen
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

    def _draw_status_panel(self, mouse_pos):
        px = RIGHT_X
        pw = RIGHT_W

        pygame.draw.rect(self.screen, PANEL2, (px, 65, pw, WIN_H - 75), border_radius=14)
        pygame.draw.rect(self.screen, LINE,   (px, 65, pw, WIN_H - 75), 2, border_radius=14)

        y = 85

        # Status-Text
        if self.phase == self.PHASE_SELECT_MARK:
            stxt, scol = "Waehle deine Rolle", YELLOW
        elif self.phase == self.PHASE_SELECT_STARTER:
            stxt, scol = "Wer faengt an?", YELLOW
        elif self.phase == self.PHASE_ROBOT_THINKING:
            stxt, scol = "Roboter denkt...", BLUE
        elif self.phase == self.PHASE_ROBOT_MOVING:
            stxt, scol = "Roboter faehrt...", BLUE
        elif self.phase == self.PHASE_ROBOT_REWARDING:
            stxt, scol = "Belohnung wird ausgegeben...", GOLD
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
        y += 55

        # Verbindungsinfo
        conn_col = GREEN if self.robot_connected else RED
        conn_txt = f"● {self.connection_label}" if self.robot_connected else "● Offline"
        draw_text(self.screen, conn_txt, self.f_tiny, conn_col, px + pw // 2, y, "center")
        y += 25

        hmark = self.selected_mark or "–"
        rmark = self.robot_side    or "–"
        draw_text(self.screen, f"Du: {hmark}   Roboter: {rmark}",
                  self.f_body, DIM, px + 20, y)
        y += 32

        draw_text(self.screen, f"Du: {self.game.scores['human']}",
                  self.f_body, X_COL, px + 20, y)
        draw_text(self.screen, f"Roboter: {self.game.scores['ai']}",
                  self.f_body, O_COL, px + 180, y)
        draw_text(self.screen, f"Remis: {self.game.scores['draw']}",
                  self.f_body, DIM, px + 340, y)
        y += 42

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 14

        # Rolle
        draw_text(self.screen, "Rolle waehlen:", self.f_small, DIM, px + 20, y)
        y += 26
        self._btn_rects["mark_x"] = draw_button(
            self.screen, pygame.Rect(px + 20, y, 140, 40), "Ich bin X",
            self.f_small, active=(self.selected_mark == "X"), mouse_pos=mouse_pos)
        self._btn_rects["mark_o"] = draw_button(
            self.screen, pygame.Rect(px + 175, y, 140, 40), "Ich bin O",
            self.f_small, active=(self.selected_mark == "O"), mouse_pos=mouse_pos)
        y += 52

        # Startspieler
        draw_text(self.screen, "Wer faengt an?", self.f_small, DIM, px + 20, y)
        y += 26
        self._btn_rects["start_h"] = draw_button(
            self.screen, pygame.Rect(px + 20,  y, 110, 40), "Mensch",
            self.f_small, active=(self.starter == "human"), mouse_pos=mouse_pos)
        self._btn_rects["start_r"] = draw_button(
            self.screen, pygame.Rect(px + 140, y, 110, 40), "Roboter",
            self.f_small, active=(self.starter == "robot"), mouse_pos=mouse_pos)
        self._btn_rects["start_z"] = draw_button(
            self.screen, pygame.Rect(px + 260, y, 110, 40), "Zufall",
            self.f_small, active=(self.starter == "random"), mouse_pos=mouse_pos)
        y += 52

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 14

        # Schwierigkeit
        draw_text(self.screen, "Schwierigkeit:", self.f_small, DIM, px + 20, y)
        y += 26
        self._btn_rects["easy"] = draw_button(
            self.screen, pygame.Rect(px + 20,  y, 110, 38), "Leicht",
            self.f_small, active=(self.game.difficulty == AI_DIFFICULTY_EASY),
            mouse_pos=mouse_pos)
        self._btn_rects["medium"] = draw_button(
            self.screen, pygame.Rect(px + 140, y, 110, 38), "Mittel",
            self.f_small, active=(self.game.difficulty == AI_DIFFICULTY_MEDIUM),
            mouse_pos=mouse_pos)
        self._btn_rects["hard"] = draw_button(
            self.screen, pygame.Rect(px + 260, y, 110, 38), "Schwer",
            self.f_small, active=(self.game.difficulty == AI_DIFFICULTY_HARD),
            mouse_pos=mouse_pos)
        y += 52

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 14

        # Aktions-Buttons
        self._btn_rects["new_round"] = draw_button(
            self.screen, pygame.Rect(px + 20,  y, 170, 44), "Neue Runde",
            self.f_small, mouse_pos=mouse_pos)
        self._btn_rects["full_rst"] = draw_button(
            self.screen, pygame.Rect(px + 200, y, 170, 44), "Alles Reset",
            self.f_small, mouse_pos=mouse_pos)
        y += 58

        pygame.draw.line(self.screen, LINE, (px + 15, y), (px + pw - 15, y), 1)
        y += 10

        # Log
        draw_text(self.screen, "Log:", self.f_small, DIM, px + 20, y)
        y += 20
        log_box = pygame.Rect(px + 10, y, pw - 20, WIN_H - y - 15)
        pygame.draw.rect(self.screen, (16, 16, 26), log_box, border_radius=8)
        pygame.draw.rect(self.screen, LINE, log_box, 1, border_radius=8)

        now     = time.time()
        visible = [e for e in self.logs if now - e.ts <= LOG_TTL_SECONDS][-MAX_LOG_VISIBLE:]
        ly = log_box.top + 8
        for entry in visible:
            col = {"ok": GREEN, "error": RED, "robot": BLUE,
                   "human": X_COL, "warn": YELLOW}.get(entry.kind, TEXT)
            draw_text(self.screen, f"▸ {entry.text}", self.f_tiny, col, px + 18, ly)
            ly += 19

    # ------------------------------------------------------------------
    # Klick-Handler
    # ------------------------------------------------------------------
    def _handle_click(self, pos):
        b = self._btn_rects

        if b.get("mark_x") and b["mark_x"].collidepoint(pos):
            self.choose_mark("X"); return
        if b.get("mark_o") and b["mark_o"].collidepoint(pos):
            self.choose_mark("O"); return

        if b.get("start_h") and b["start_h"].collidepoint(pos):
            if self.selected_mark:
                self.choose_starter("human")
            else:
                self.log("Bitte erst Rolle waehlen", "warn")
            return
        if b.get("start_r") and b["start_r"].collidepoint(pos):
            if self.selected_mark:
                self.choose_starter("robot")
            else:
                self.log("Bitte erst Rolle waehlen", "warn")
            return
        if b.get("start_z") and b["start_z"].collidepoint(pos):
            if self.selected_mark:
                self.choose_starter("random")
            else:
                self.log("Bitte erst Rolle waehlen", "warn")
            return

        if b.get("easy") and b["easy"].collidepoint(pos):
            self.game.set_difficulty(AI_DIFFICULTY_EASY)
            self.log("Schwierigkeit: Leicht", "info")
            self._start_new_round_with_current_settings(); return
        if b.get("medium") and b["medium"].collidepoint(pos):
            self.game.set_difficulty(AI_DIFFICULTY_MEDIUM)
            self.log("Schwierigkeit: Mittel", "info")
            self._start_new_round_with_current_settings(); return
        if b.get("hard") and b["hard"].collidepoint(pos):
            self.game.set_difficulty(AI_DIFFICULTY_HARD)
            self.log("Schwierigkeit: Schwer", "info")
            self._start_new_round_with_current_settings(); return

        if b.get("new_round") and b["new_round"].collidepoint(pos):
            self.reset_round(); return
        if b.get("full_rst") and b["full_rst"].collidepoint(pos):
            self.full_reset(); return

        fid = field_from_mouse(*pos)
        if fid is not None:
            self.human_move(fid)

    # ------------------------------------------------------------------
    # Hauptschleife
    # ------------------------------------------------------------------
    def run(self):
        self.start_vision()
        self.log(f"Verbunden: {self.connection_label}", "ok")

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
