# =============================================================================
# game/ai/hard.py - Minimax mit Alpha-Beta-Pruning (unschlagbar)
# =============================================================================
from game.board import Board


def get_move(board: Board, player: str) -> int:
    opponent = "O" if player == "X" else "X"
    best_score = float("-inf")
    best_field = None

    for field in board.get_empty_fields():
        test = board.copy()
        test.place(field, player)
        score = _minimax(test, 0, False, player, opponent,
                         float("-inf"), float("inf"))
        if score > best_score:
            best_score = score
            best_field = field

    return best_field


def _minimax(board: Board, depth: int, is_maximizing: bool,
             ai: str, human: str, alpha: float, beta: float) -> float:
    if board.winner == ai:
        return 10 - depth
    if board.winner == human:
        return depth - 10
    if board.is_full():
        return 0

    if is_maximizing:
        best = float("-inf")
        for field in board.get_empty_fields():
            test = board.copy()
            test.place(field, ai)
            score = _minimax(test, depth + 1, False, ai, human, alpha, beta)
            best = max(best, score)
            alpha = max(alpha, best)
            if beta <= alpha:
                break
        return best
    else:
        best = float("inf")
        for field in board.get_empty_fields():
            test = board.copy()
            test.place(field, human)
            score = _minimax(test, depth + 1, True, ai, human, alpha, beta)
            best = min(best, score)
            beta = min(beta, best)
            if beta <= alpha:
                break
        return best
