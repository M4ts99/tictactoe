# =============================================================================
# game/ai/medium.py - Heuristik: "Abgelenkter" Roboter
# =============================================================================
import random
from game.board import Board


def get_move(board: Board, player: str) -> int:
    opponent = "O" if player == "X" else "X"

    # 1. Kann der KI-Spieler sofort gewinnen? -> Macht er immer!
    win = _find_winning_move(board, player)
    if win:
        return win

    # 2. Muss der Gegner blockiert werden?
    # Die KI ist auf "Mittel" manchmal abgelenkt und blockiert nur zu 70%.
    # Wenn du sie noch dümmer/schlauer machen willst, ändere einfach die 0.70
    block = _find_winning_move(board, opponent)
    if block and random.random() < 0.70:
        return block

    # 3. Keine Priorität mehr für Mitte oder Ecken.
    # Wenn sie weder gewinnt noch blockiert, setzt sie völlig blind.
    return random.choice(board.get_empty_fields())


def _find_winning_move(board: Board, player: str):
    for field in board.get_empty_fields():
        test = board.copy()
        test.place(field, player)
        if test.winner == player:
            return field
    return None