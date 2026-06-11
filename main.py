# =============================================================================
# main.py - Einstiegspunkt
# Einzelnes Pygame-Fenster, kein Threading fuer UI.
# =============================================================================
import sys
import time
import threading
import pygame

from game.game_manager import GameManager
from config import (
    AI_DIFFICULTY_EASY, AI_DIFFICULTY_MEDIUM, AI_DIFFICULTY_HARD,
    DEFAULT_DIFFICULTY
)

WIN_W, WIN_H = 1100, 700
BOARD_X, BOARD_Y = 50, 80
BOARD_SIZE = 500
CELL = BOARD_SIZE // 3
STATUS_X = 640

BG = (18, 18, 30)
LINE_COL = (80, 80, 120)
COL_X = (220, 80, 80)
COL_O = (80, 180, 220)
COL_WIN = (255, 215, 0)
COL_TEXT = (230, 230, 230)
COL_DIM = (120, 120, 150)
COL_BTN = (50, 50, 80)
COL_HOVER = (70, 70, 110)
COL_ACTIVE = (100, 100, 180)
COL_HUMAN = (220, 80, 80)
COL_ROBOT = (80, 180, 220)
COL_GOLD = (255, 215, 0)


def draw_text(surface, text, font, color, cx, cy, anchor="center"):
    surf = font.render(text, True, color)
    if anchor == "center":
        rect = surf.get_rect(center=(cx, cy))
    else:
        rect = surf.get_rect(midleft=(cx, cy))
    surface.blit(surf, rect)
    return rect


def draw_button(surface, rect, text, font, active=False, mouse_pos=(0, 0)):
    r = pygame.Rect(rect)
    if active:
        color = COL_ACTIVE
    elif r.collidepoint(mouse_pos):
        color = COL_HOVER
    else:
        color = COL_BTN
    pygame.draw.rect(surface, color, r, border_radius=10)
    pygame.draw.rect(surface, LINE_COL, r, 2, border_radius=10)
    lbl = font.render(text, True, COL_TEXT)
    surface.blit(lbl, lbl.get_rect(center=r.center))
    return r


def field_from_mouse(mx, my):
    bx = mx - BOARD_X
    by = my - BOARD_Y
    if not (0 <= bx < BOARD_SIZE and 0 <= by < BOARD_SIZE):
        return None
    col = int(bx // CELL)
    row = int(by // CELL)
    field_id = row * 3 + col + 1
    if 1 <= field_id <= 9:
        return field_id
    return None


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("TicTacToe - Doosan M1013")
    clock = pygame.time.Clock()

    f_large = pygame.font.SysFont("segoeui", 48, bold=True)
    f_medium = pygame.font.SysFont("segoeui", 30, bold=True)
    f_small = pygame.font.SysFont("segoeui", 22)
    f_tiny = pygame.font.SysFont("segoeui", 16)

    gm = GameManager(human_player="X", difficulty=DEFAULT_DIFFICULTY)
    ai_thinking = False
    ai_started = False

    def trigger_ai():
        nonlocal ai_thinking, ai_started
        ai_thinking = True
        time.sleep(0.7)
        gm.ai_move()
        ai_thinking = False
        ai_started = False

    running = True
    while running:
        mouse = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                fid = field_from_mouse(mx, my)
                if fid is not None and gm.is_human_turn() and not ai_thinking:
                    if gm.board.is_empty(fid):
                        gm.human_move(fid)
                        if not gm.board.is_game_over() and gm.is_ai_turn() and not ai_started:
                            ai_started = True
                            threading.Thread(target=trigger_ai, daemon=True).start()

                if pygame.Rect(STATUS_X, 430, 120, 44).collidepoint(mx, my):
                    gm.set_difficulty(AI_DIFFICULTY_EASY)
                if pygame.Rect(STATUS_X + 135, 430, 120, 44).collidepoint(mx, my):
                    gm.set_difficulty(AI_DIFFICULTY_MEDIUM)
                if pygame.Rect(STATUS_X + 270, 430, 120, 44).collidepoint(mx, my):
                    gm.set_difficulty(AI_DIFFICULTY_HARD)
                if pygame.Rect(STATUS_X, 510, 185, 48).collidepoint(mx, my):
                    gm.reset(); ai_thinking = False; ai_started = False
                if pygame.Rect(STATUS_X + 205, 510, 185, 48).collidepoint(mx, my):
                    gm.full_reset(); ai_thinking = False; ai_started = False

        screen.fill(BG)
        draw_text(screen, "TicTacToe - Doosan M1013", f_medium, COL_TEXT, WIN_W // 2, 30)
        pygame.draw.line(screen, LINE_COL, (610, 60), (610, WIN_H - 20), 2)

        for i in range(1, 3):
            x = BOARD_X + i * CELL
            y = BOARD_Y + i * CELL
            pygame.draw.line(screen, LINE_COL, (x, BOARD_Y), (x, BOARD_Y + BOARD_SIZE), 5)
            pygame.draw.line(screen, LINE_COL, (BOARD_X, y), (BOARD_X + BOARD_SIZE, y), 5)
        pygame.draw.rect(screen, LINE_COL, (BOARD_X, BOARD_Y, BOARD_SIZE, BOARD_SIZE), 5)

        for fid in range(1, 10):
            val = gm.board.get_cell(fid)
            if val is None:
                continue
            row = (fid - 1) // 3
            col = (fid - 1) % 3
            cx = BOARD_X + col * CELL + CELL // 2
            cy = BOARD_Y + row * CELL + CELL // 2
            r = CELL // 2 - 28
            if val == "X":
                pygame.draw.line(screen, COL_X, (cx - r, cy - r), (cx + r, cy + r), 9)
                pygame.draw.line(screen, COL_X, (cx + r, cy - r), (cx - r, cy + r), 9)
            else:
                pygame.draw.circle(screen, COL_O, (cx, cy), r, 9)

        if gm.board.winning_combo:
            def center(idx):
                rr = idx // 3
                cc = idx % 3
                return (BOARD_X + cc * CELL + CELL // 2, BOARD_Y + rr * CELL + CELL // 2)
            pygame.draw.line(screen, COL_WIN, center(gm.board.winning_combo[0]), center(gm.board.winning_combo[2]), 10)

        if gm.is_human_turn() and not ai_thinking:
            fid = field_from_mouse(mouse[0], mouse[1])
            if fid is not None and gm.board.is_empty(fid):
                row = (fid - 1) // 3
                col = (fid - 1) % 3
                s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                s.fill((255, 255, 255, 18))
                screen.blit(s, (BOARD_X + col * CELL, BOARD_Y + row * CELL))

        y_sc = BOARD_Y + BOARD_SIZE + 20
        draw_text(screen, f"Du (X): {gm.scores['human']}", f_small, COL_HUMAN, BOARD_X, y_sc, anchor="left")
        draw_text(screen, f"Roboter (O): {gm.scores['ai']}", f_small, COL_ROBOT, BOARD_X, y_sc + 32, anchor="left")
        draw_text(screen, f"Unentschieden: {gm.scores['draw']}", f_small, COL_DIM, BOARD_X, y_sc + 64, anchor="left")

        state = gm.state
        if state == "human_won":
            status_txt, status_col = "Du hast gewonnen!", COL_GOLD
        elif state == "ai_won":
            status_txt, status_col = "Roboter hat gewonnen!", COL_ROBOT
        elif state == "draw":
            status_txt, status_col = "Unentschieden!", COL_DIM
        elif ai_thinking:
            status_txt, status_col = "Roboter denkt...", COL_ROBOT
        else:
            status_txt, status_col = "Dein Zug!", COL_HUMAN

        draw_text(screen, status_txt, f_large, status_col, STATUS_X + 195, 140)
        if ai_thinking:
            draw_text(screen, "Roboter macht seinen Zug...", f_tiny, COL_DIM, STATUS_X + 195, 195)
        elif state == "running" and gm.is_human_turn():
            draw_text(screen, "Klicke auf ein Feld um zu spielen", f_tiny, COL_DIM, STATUS_X + 195, 195)
        else:
            draw_text(screen, "Neue Runde starten?", f_tiny, COL_DIM, STATUS_X + 195, 195)

        mini_x, mini_y = STATUS_X + 90, 240
        mini_cell = 55
        for i in range(1, 3):
            x = mini_x + i * mini_cell
            y = mini_y + i * mini_cell
            pygame.draw.line(screen, LINE_COL, (x, mini_y), (x, mini_y + mini_cell * 3), 2)
            pygame.draw.line(screen, LINE_COL, (mini_x, y), (mini_x + mini_cell * 3, y), 2)
        pygame.draw.rect(screen, LINE_COL, (mini_x, mini_y, mini_cell * 3, mini_cell * 3), 2)

        for fid in range(1, 10):
            val = gm.board.get_cell(fid)
            if val is None:
                continue
            row = (fid - 1) // 3
            col = (fid - 1) % 3
            cx = mini_x + col * mini_cell + mini_cell // 2
            cy = mini_y + row * mini_cell + mini_cell // 2
            mr = mini_cell // 2 - 8
            if val == "X":
                pygame.draw.line(screen, COL_X, (cx - mr, cy - mr), (cx + mr, cy + mr), 3)
                pygame.draw.line(screen, COL_X, (cx + mr, cy - mr), (cx - mr, cy + mr), 3)
            else:
                pygame.draw.circle(screen, COL_O, (cx, cy), mr, 3)

        draw_text(screen, "Schwierigkeit:", f_small, COL_DIM, STATUS_X, 408, anchor="left")
        draw_button(screen, pygame.Rect(STATUS_X, 430, 120, 44), "Leicht", f_small, active=(gm.difficulty == AI_DIFFICULTY_EASY), mouse_pos=mouse)
        draw_button(screen, pygame.Rect(STATUS_X + 135, 430, 120, 44), "Mittel", f_small, active=(gm.difficulty == AI_DIFFICULTY_MEDIUM), mouse_pos=mouse)
        draw_button(screen, pygame.Rect(STATUS_X + 270, 430, 120, 44), "Schwer", f_small, active=(gm.difficulty == AI_DIFFICULTY_HARD), mouse_pos=mouse)
        draw_button(screen, pygame.Rect(STATUS_X, 510, 185, 48), "Neue Runde", f_small, mouse_pos=mouse)
        draw_button(screen, pygame.Rect(STATUS_X + 205, 510, 185, 48), "Alles Reset", f_small, mouse_pos=mouse)
        draw_text(screen, "Phase 1 - Kamera & Roboter noch nicht aktiv", f_tiny, COL_DIM, STATUS_X + 195, WIN_H - 25)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
