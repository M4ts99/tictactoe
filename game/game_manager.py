# =============================================================================
# game/game_manager.py - Spielablauf und Zugreihenfolge
# =============================================================================
from game.board import Board
from game.ai import easy, medium, hard
from config import (AI_DIFFICULTY_EASY, AI_DIFFICULTY_MEDIUM,
                    AI_DIFFICULTY_HARD, DEFAULT_DIFFICULTY)


class GameManager:
    """
    Steuert den Spielablauf.
    - human_player: 'X' oder 'O'
    - ai_player:    das jeweils andere Symbol
    - difficulty:   'easy', 'medium', 'hard'
    """

    def __init__(self, human_player: str = "X",
                 difficulty: str = DEFAULT_DIFFICULTY):
        self.board = Board()
        self.human_player = human_player
        self.ai_player = "O" if human_player == "X" else "X"
        self.difficulty = difficulty
        self.current_turn = "X"
        self.state = "running"   # 'running' | 'human_won' | 'ai_won' | 'draw'
        self.scores = {"human": 0, "ai": 0, "draw": 0}

    # ------------------------------------------------------------------
    # Oeffentliche API
    # ------------------------------------------------------------------

    def human_move(self, field_id: int) -> bool:
        """Verarbeitet den Zug des menschlichen Spielers. True = gueltiger Zug."""
        if self.state != "running":
            return False
        if self.current_turn != self.human_player:
            return False
        if not self.board.place(field_id, self.human_player):
            return False
        self._after_move()
        return True

    def ai_move(self):
        """Fuehrt den KI-Zug aus. Gibt das gewaehlte Feld zurueck."""
        if self.state != "running":
            return None
        if self.current_turn != self.ai_player:
            return None
        field = self._get_ai_move()
        self.board.place(field, self.ai_player)
        self._after_move()
        return field

    def is_human_turn(self) -> bool:
        return self.state == "running" and self.current_turn == self.human_player

    def is_ai_turn(self) -> bool:
        return self.state == "running" and self.current_turn == self.ai_player

    def reset(self):
        """Startet eine neue Runde (Scores bleiben erhalten)."""
        self.board.reset()
        self.current_turn = "X"
        self.state = "running"

    def full_reset(self):
        """Vollstaendiger Reset inkl. Scores."""
        self.reset()
        self.scores = {"human": 0, "ai": 0, "draw": 0}

    def set_difficulty(self, difficulty: str):
        self.difficulty = difficulty

    def get_status_text(self) -> str:
        if self.state == "human_won":
            return "Du hast gewonnen!"
        if self.state == "ai_won":
            return "Roboter hat gewonnen!"
        if self.state == "draw":
            return "Unentschieden!"
        if self.is_human_turn():
            return f"Dein Zug ({self.human_player})"
        return f"Roboter denkt... ({self.ai_player})"

    # ------------------------------------------------------------------
    # Intern
    # ------------------------------------------------------------------

    def _after_move(self):
        if self.board.winner == self.human_player:
            self.state = "human_won"
            self.scores["human"] += 1
        elif self.board.winner == self.ai_player:
            self.state = "ai_won"
            self.scores["ai"] += 1
        elif self.board.is_full():
            self.state = "draw"
            self.scores["draw"] += 1
        else:
            self.current_turn = (self.ai_player
                                 if self.current_turn == self.human_player
                                 else self.human_player)

    def _get_ai_move(self) -> int:
        if self.difficulty == AI_DIFFICULTY_EASY:
            return easy.get_move(self.board, self.ai_player)
        if self.difficulty == AI_DIFFICULTY_HARD:
            return hard.get_move(self.board, self.ai_player)
        return medium.get_move(self.board, self.ai_player)
