# =============================================================================
# config.py - Zentrale Konfiguration fuer das TicTacToe-Doosan-Projekt
# =============================================================================

# --- Kamera ---
CAMERA_ID     = 0
CAMERA_WIDTH  = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS    = 30

# --- YOLO ---
YOLO_MODEL_PATH = "vision/best.pt"
YOLO_CONFIDENCE = 0.5
YOLO_CLASSES    = {0: "X",1:"O"}

# --- Board Mapper: Pixel-Koordinaten der 9 Felder (nach Kalibrierung anpassen) ---
# Format: Feld-ID -> (x_min, y_min, x_max, y_max) in Pixel
BOARD_REGIONS = {
    1: (100, 100, 300, 300),
    2: (300, 100, 500, 300),
    3: (500, 100, 700, 300),
    4: (100, 300, 300, 500),
    5: (300, 300, 500, 500),
    6: (500, 300, 700, 500),
    7: (100, 500, 300, 700),
    8: (300, 500, 500, 700),
    9: (500, 500, 700, 700),
}

# --- Roboter / Socket ---
ROBOT_IP      = "192.168.137.100"
ROBOT_PORT    = 5004
ROBOT_EVENT_PORT = 5005
ROBOT_TIMEOUT = 10

# --- Spielfeld-Koordinaten (Roboter-Koordinatensystem, in mm) ---
FIELD_POSITIONS = {
    1: (0.0, 0.0, 0.0),
    2: (0.0, 0.0, 0.0),
    3: (0.0, 0.0, 0.0),
    4: (0.0, 0.0, 0.0),
    5: (0.0, 0.0, 0.0),
    6: (0.0, 0.0, 0.0),
    7: (0.0, 0.0, 0.0),
    8: (0.0, 0.0, 0.0),
    9: (0.0, 0.0, 0.0),
}
STORAGE_X  = (0.0, 0.0, 0.0)
STORAGE_O  = (0.0, 0.0, 0.0)
REWARD_POS = (0.0, 0.0, 0.0)

# --- KI ---
AI_DIFFICULTY_EASY   = "easy"
AI_DIFFICULTY_MEDIUM = "medium"
AI_DIFFICULTY_HARD   = "hard"
DEFAULT_DIFFICULTY   = AI_DIFFICULTY_MEDIUM

# --- UI ---
WINDOW_TITLE_GAME   = "TicTacToe - Spielfeld"
WINDOW_TITLE_STATUS = "TicTacToe - Spieler-Interface"
WINDOW_TITLE_VISION = "TicTacToe - Kamera & YOLO"

SCREEN_GAME_SIZE   = (600, 700)
SCREEN_STATUS_SIZE = (500, 600)

# Farben (R, G, B)
COLOR_BG           = (18,  18,  30)
COLOR_LINE         = (80,  80, 120)
COLOR_X            = (220,  80,  80)
COLOR_O            = (80,  180, 220)
COLOR_WIN_LINE     = (255, 215,   0)
COLOR_TEXT         = (230, 230, 230)
COLOR_TEXT_DIM     = (120, 120, 150)
COLOR_BTN          = (50,  50,  80)
COLOR_BTN_HOVER    = (70,  70, 110)
COLOR_BTN_ACTIVE   = (100, 100, 180)
COLOR_STATUS_ROBOT = (80,  180, 220)
COLOR_STATUS_HUMAN = (220,  80,  80)
COLOR_STATUS_WIN   = (255, 215,   0)

# Schriftgroessen
FONT_LARGE  = 52
FONT_MEDIUM = 32
FONT_SMALL  = 22
FONT_TINY   = 16
# --- Digital Input Pins (am Doosan Controller) ---
DI_PIN_HUMAN_ON   = 1   # B1 – Mensch beginnt (AN)
DI_PIN_HUMAN_OFF  = 2   # B2 – Roboter beginnt (AUS)
DI_PIN_EASY       = 3   # B3 – Schwierigkeit Leicht
DI_PIN_MEDIUM     = 4   # B4 – Schwierigkeit Mittel
DI_PIN_HARD       = 5   # B5 – Schwierigkeit Schwer
DI_PIN_RESET      = 6   # B6 – Vollständiger Reset

LONG_PRESS_SECONDS = 3.0   # Haltedauer für Zufallsmodus

# --- Event-Channel ---
   # DRL sendet Events hierüber