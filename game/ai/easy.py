# =============================================================================
# game/ai/easy.py - Zufaelliger Zug
# =============================================================================
import random
from game.board import Board


def get_move(board: Board, player: str) -> int:
    """Waehlt einen zufaelligen freien Feld."""
    empty = board.get_empty_fields()
    return random.choice(empty)
