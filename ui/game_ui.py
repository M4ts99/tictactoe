# =============================================================================
# ui/game_ui.py - 2D Spielfeld-Grafik (Pygame)
# =============================================================================
import pygame
import sys
import threading
from game.game_manager import GameManager
from config import (
    SCREEN_GAME_SIZE, WINDOW_TITLE_GAME,
    COLOR_BG, COLOR_LINE, COLOR_X, COLOR_O, COLOR_WIN_LINE,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_STATUS_HUMAN, COLOR_STATUS_ROBOT,
    FONT_LARGE, FONT_MEDIUM, FONT_SMALL, FONT_TINY
)


class GameUI:
    BOARD_OFFSET_X = 50
    BOARD_OFFSET_Y = 50
    BOARD_SIZE     = 500
    CELL_SIZE      = 500 // 3
    LINE_WIDTH     = 5
    PIECE_MARGIN   = 30

    def __init__(self, game_manager: GameManager):
        self.gm = game_manager
        self._running = False
        self._click_callback = None

    def set_click_callback(self, cb):
        """Callback wird aufgerufen wenn der Spieler ein Feld klickt: cb(field_id)"""
        self._click_callback = cb

    def start(self):
        """Startet die UI in einem eigenen Thread."""
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # Haupt-Loop
    # ------------------------------------------------------------------

    def _run(self):
        pygame.init()
        self.screen = pygame.display.set_mode(SCREEN_GAME_SIZE)
        pygame.display.set_caption(WINDOW_TITLE_GAME)
        self.clock = pygame.time.Clock()
        self._load_fonts()
        self._running = True

        while self._running:
            self._handle_events()
            self._draw()
            self.clock.tick(30)

        pygame.quit()

    def _load_fonts(self):
        self.font_large  = pygame.font.SysFont("segoeui", FONT_LARGE,  bold=True)
        self.font_medium = pygame.font.SysFont("segoeui", FONT_MEDIUM, bold=True)
        self.font_small  = pygame.font.SysFont("segoeui", FONT_SMALL)
        self.font_tiny   = pygame.font.SysFont("segoeui", FONT_TINY)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                field = self._pixel_to_field(event.pos)
                if field and self._click_callback:
                    self._click_callback(field)

    def _pixel_to_field(self, pos):
        mx, my = pos
        bx = mx - self.BOARD_OFFSET_X
        by = my - self.BOARD_OFFSET_Y
        if not (0 <= bx < self.BOARD_SIZE and 0 <= by < self.BOARD_SIZE):
            return None
        col = bx // self.CELL_SIZE
        row = by // self.CELL_SIZE
        return int(row * 3 + col + 1)

    # ------------------------------------------------------------------
    # Zeichnen
    # ------------------------------------------------------------------

    def _draw(self):
        self.screen.fill(COLOR_BG)
        self._draw_grid()
        self._draw_pieces()
        if self.gm.board.winning_combo:
            self._draw_win_line()
        self._draw_scores()
        pygame.display.flip()

    def _draw_grid(self):
        ox, oy = self.BOARD_OFFSET_X, self.BOARD_OFFSET_Y
        cs = self.CELL_SIZE

        for i in range(1, 3):
            x = ox + i * cs
            pygame.draw.line(self.screen, COLOR_LINE,
                             (x, oy), (x, oy + self.BOARD_SIZE), self.LINE_WIDTH)
        for i in range(1, 3):
            y = oy + i * cs
            pygame.draw.line(self.screen, COLOR_LINE,
                             (ox, y), (ox + self.BOARD_SIZE, y), self.LINE_WIDTH)
        pygame.draw.rect(self.screen, COLOR_LINE,
                         (ox, oy, self.BOARD_SIZE, self.BOARD_SIZE), self.LINE_WIDTH)

    def _draw_pieces(self):
        ox, oy = self.BOARD_OFFSET_X, self.BOARD_OFFSET_Y
        cs = self.CELL_SIZE
        m  = self.PIECE_MARGIN

        for field_id in range(1, 10):
            val = self.gm.board.get_cell(field_id)
            if val is None:
                continue
            row = (field_id - 1) // 3
            col = (field_id - 1) % 3
            cx = ox + col * cs + cs // 2
            cy = oy + row * cs + cs // 2
            if val == "X":
                self._draw_x(cx, cy, cs // 2 - m)
            else:
                self._draw_o(cx, cy, cs // 2 - m)

    def _draw_x(self, cx, cy, r):
        lw = 8
        pygame.draw.line(self.screen, COLOR_X,
                         (cx - r, cy - r), (cx + r, cy + r), lw)
        pygame.draw.line(self.screen, COLOR_X,
                         (cx + r, cy - r), (cx - r, cy + r), lw)

    def _draw_o(self, cx, cy, r):
        pygame.draw.circle(self.screen, COLOR_O, (cx, cy), r, 8)

    def _draw_win_line(self):
        combo = self.gm.board.winning_combo
        if not combo:
            return
        ox, oy = self.BOARD_OFFSET_X, self.BOARD_OFFSET_Y
        cs = self.CELL_SIZE

        def center(idx):
            row = idx // 3
            col = idx % 3
            return (ox + col * cs + cs // 2, oy + row * cs + cs // 2)

        start = center(combo[0])
        end   = center(combo[2])
        pygame.draw.line(self.screen, COLOR_WIN_LINE, start, end, 10)

    def _draw_scores(self):
        y = self.BOARD_OFFSET_Y + self.BOARD_SIZE + 20
        human_txt = self.font_small.render(
            f"Du: {self.gm.scores['human']}", True, COLOR_STATUS_HUMAN)
        ai_txt = self.font_small.render(
            f"Roboter: {self.gm.scores['ai']}", True, COLOR_STATUS_ROBOT)
        draw_txt = self.font_small.render(
            f"Unentschieden: {self.gm.scores['draw']}", True, COLOR_TEXT_DIM)

        self.screen.blit(human_txt, (self.BOARD_OFFSET_X, y))
        self.screen.blit(ai_txt,    (self.BOARD_OFFSET_X, y + 35))
        self.screen.blit(draw_txt,  (self.BOARD_OFFSET_X, y + 70))
