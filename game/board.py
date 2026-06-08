# =============================================================================
# game/board.py - Spielfeld-Logik
# =============================================================================


class Board:
    """
    Repraesentiert das 3x3 Tic-Tac-Toe-Spielfeld.
    Felder 1-9, intern als Liste mit Index 0-8.
    Werte: None = leer, 'X' = X-Stein, 'O' = O-Stein
    """

    WIN_COMBINATIONS = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),  # Zeilen
        (0, 3, 6), (1, 4, 7), (2, 5, 8),  # Spalten
        (0, 4, 8), (2, 4, 6),             # Diagonalen
    ]

    def __init__(self):
        self.reset()

    def reset(self):
        self.cells = [None] * 9
        self.winner = None
        self.winning_combo = None

    def place(self, field_id: int, player: str) -> bool:
        """Setzt einen Stein auf Feld field_id (1-9). True = erfolgreich."""
        idx = field_id - 1
        if self.cells[idx] is not None:
            return False
        self.cells[idx] = player
        self._check_winner()
        return True

    def is_empty(self, field_id: int) -> bool:
        return self.cells[field_id - 1] is None

    def get_empty_fields(self) -> list:
        return [i + 1 for i, v in enumerate(self.cells) if v is None]

    def is_full(self) -> bool:
        return all(c is not None for c in self.cells)

    def is_game_over(self) -> bool:
        return self.winner is not None or self.is_full()

    def get_cell(self, field_id: int):
        return self.cells[field_id - 1]

    def _check_winner(self):
        for combo in self.WIN_COMBINATIONS:
            a, b, c = combo
            if (self.cells[a] is not None and
                    self.cells[a] == self.cells[b] == self.cells[c]):
                self.winner = self.cells[a]
                self.winning_combo = combo
                return

    def copy(self):
        new_board = Board()
        new_board.cells = self.cells.copy()
        new_board.winner = self.winner
        new_board.winning_combo = self.winning_combo
        return new_board

    def __repr__(self):
        rows = []
        for row in range(3):
            cells = []
            for col in range(3):
                v = self.cells[row * 3 + col]
                cells.append(v if v else ".")
            rows.append(" | ".join(cells))
        return "\n---------\n".join(rows)
