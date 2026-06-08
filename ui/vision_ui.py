# =============================================================================
# ui/status_ui.py - Spieler-Interface: Status, Schwierigkeit, Steuerung
# =============================================================================
import pygame
import sys
import math
import time
import threading
from game.game_manager import GameManager
from config import (
    SCREEN_STATUS_SIZE, WINDOW_TITLE_STATUS,
    COLOR_BG, COLOR_LINE, COLOR_TEXT, COLOR_TEXT_DIM,
    COLOR_BTN, COLOR_BTN_HOVER, COLOR_BTN_ACTIVE,
    COLOR_STATUS_HUMAN, COLOR_STATUS_ROBOT, COLOR_STATUS_WIN,
    FONT_LARGE, FONT_MEDIUM, FONT_SMALL, FONT_TINY,
    AI_DIFFICULTY_EASY, AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_HARD
)


class Button:
    def __init__(self, rect, text, font, active=False):
        self.rect   = pygame.Rect(rect)
        self.text   = text
        self.font   = font
        self.active = active

    def draw(self, surface):
        color = COLOR_BTN_ACTIVE if self.active else COLOR_BTN
        mouse = pygame.mouse.get_pos()
        if self.rect.collidepoint(mouse) and not self.active:
            color = COLOR_BTN_HOVER
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, COLOR_LINE, self.rect, 2, border_radius=10)
        label = self.font.render(self.text, True, COLOR_TEXT)
        lx = self.rect.centerx - label.get_width() // 2
        ly = self.rect.centery - label.get_height() // 2
        surface.blit(label, (lx, ly))

    def is_clicked(self, pos):
        return self.rect.collidepoint(pos)


class StatusUI:
    """
    Pygame-Fenster mit Spieler-Interface:
    - Wer ist dran / Roboter-Status
    - Schwierigkeitsgrad-Auswahl
    - Neue Runde / Reset
    """

    def __init__(self, game_manager: GameManager):
        self.gm = game_manager
        self._running = False
        self._new_game_callback = None
        self._difficulty_callback = None

    def set_new_game_callback(self, cb):
        self._new_game_callback = cb

    def set_difficulty_callback(self, cb):
        self._difficulty_callback = cb

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # Haupt-Loop
    # ------------------------------------------------------------------

    def _run(self):
        pygame.init()
        self.screen = pygame.display.set_mode(SCREEN_STATUS_SIZE)
        pygame.display.set_caption(WINDOW_TITLE_STATUS)
        self.clock = pygame.time.Clock()
        self._load_fonts()
        self._build_buttons()
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

    def _build_buttons(self):
        bw, bh = 130, 48
        self.btn_easy   = Button((40,  260, bw, bh), "Leicht", self.font_small,
                                  self.gm.difficulty == AI_DIFFICULTY_EASY)
        self.btn_medium = Button((185, 260, bw, bh), "Mittel", self.font_small,
                                  self.gm.difficulty == AI_DIFFICULTY_MEDIUM)
        self.btn_hard   = Button((330, 260, bw, bh), "Schwer", self.font_small,
                                  self.gm.difficulty == AI_DIFFICULTY_HARD)
        self.btn_new_round  = Button((40,  360, 190, bh), "Neue Runde",  self.font_small)
        self.btn_full_reset = Button((260, 360, 190, bh), "Alles Reset", self.font_small)

        self.diff_buttons = [self.btn_easy, self.btn_medium, self.btn_hard]
        self.diff_values  = [AI_DIFFICULTY_EASY, AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_HARD]

    def _update_diff_active(self):
        for btn, val in zip(self.diff_buttons, self.diff_values):
            btn.active = (self.gm.difficulty == val)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                for btn, val in zip(self.diff_buttons, self.diff_values):
                    if btn.is_clicked(pos):
                        self.gm.set_difficulty(val)
                        self._update_diff_active()
                        if self._difficulty_callback:
                            self._difficulty_callback(val)
                if self.btn_new_round.is_clicked(pos):
                    self.gm.reset()
                    if self._new_game_callback:
                        self._new_game_callback()
                if self.btn_full_reset.is_clicked(pos):
                    self.gm.full_reset()
                    if self._new_game_callback:
                        self._new_game_callback()

    # ------------------------------------------------------------------
    # Zeichnen
    # ------------------------------------------------------------------

    def _draw(self):
        self.screen.fill(COLOR_BG)
        self._draw_header()
        self._draw_status()
        self._draw_difficulty_section()
        self._draw_control_buttons()
        self._draw_robot_indicator()
        pygame.display.flip()

    def _draw_header(self):
        title = self.font_medium.render("TicTacToe - Doosan M1013", True, COLOR_TEXT)
        self.screen.blit(title, (SCREEN_STATUS_SIZE[0] // 2 - title.get_width() // 2, 20))
        subtitle = self.font_tiny.render("Spieler vs. Roboter", True, COLOR_TEXT_DIM)
        self.screen.blit(subtitle, (SCREEN_STATUS_SIZE[0] // 2 - subtitle.get_width() // 2, 65))
        pygame.draw.line(self.screen, COLOR_LINE, (30, 100), (470, 100), 2)

    def _draw_status(self):
        status = self.gm.get_status_text()
        is_ai  = self.gm.is_ai_turn()
        is_end = self.gm.state != "running"

        if is_end and self.gm.state == "human_won":
            color = COLOR_STATUS_WIN
        elif is_end and self.gm.state == "ai_won":
            color = COLOR_STATUS_ROBOT
        elif is_end:
            color = COLOR_TEXT_DIM
        elif is_ai:
            color = COLOR_STATUS_ROBOT
        else:
            color = COLOR_STATUS_HUMAN

        txt = self.font_medium.render(status, True, color)
        self.screen.blit(txt, (SCREEN_STATUS_SIZE[0] // 2 - txt.get_width() // 2, 125))

        if is_ai and not is_end:
            sub = self.font_tiny.render("Roboter macht seinen Zug...", True, COLOR_TEXT_DIM)
            self.screen.blit(sub, (SCREEN_STATUS_SIZE[0] // 2 - sub.get_width() // 2, 180))

    def _draw_difficulty_section(self):
        lbl = self.font_small.render("Schwierigkeit:", True, COLOR_TEXT_DIM)
        self.screen.blit(lbl, (40, 225))
        self._update_diff_active()
        for btn in self.diff_buttons:
            btn.draw(self.screen)

    def _draw_control_buttons(self):
        self.btn_new_round.draw(self.screen)
        self.btn_full_reset.draw(self.screen)

    def _draw_robot_indicator(self):
        """Pulsierende Anzeige wenn der Roboter aktiv ist."""
        if not self.gm.is_ai_turn() or self.gm.state != "running":
            return
        pulse = int(128 + 127 * math.sin(time.time() * 3))
        color = (0, pulse // 2, pulse)
        pygame.draw.circle(self.screen, color,
                           (SCREEN_STATUS_SIZE[0] - 40, 40), 12)
        lbl = self.font_tiny.render("AKTIV", True, color)
        self.screen.blit(lbl, (SCREEN_STATUS_SIZE[0] - 80, 58))
