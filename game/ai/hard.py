# =============================================================================
# game/ai/medium.py - Heuristik: Gewinnen > Blockieren > Zufaellig
# =============================================================================
import random
from game.board import Board


def get_move(board: Board, player: str) -> int:
    opponent = "O" if player == "X" else "X"

    # 1. Kann der KI-Spieler gewinnen?
    win = _find_winning_move(board, player)
    if win:
        return win

    # 2. Muss der Gegner blockiert werden?
    block = _find_winning_move(board, opponent)
    if block:
        return block

    # 3. Mitte bevorzugen
    if board.is_empty(5):
        return 5

    # 4. Ecken bevorzugen
    corners = [f for f in [1, 3, 7, 9] if board.is_empty(f)]
    if corners:
        return random.choice(corners)

    # 5. Zufaellig
    return random.choice(board.get_empty_fields())


def _find_winning_move(board: Board, player: str):
    for field in board.get_empty_fields():
        test = board.copy()
        test.place(field, player)
        if test.winner == player:
            return field
    return None
