import sys
sys.path.insert(0, ".")
from game.board import Board
from game.ai import easy, medium, hard

def test_hard_wins_when_possible():
    b = Board()
    b.place(1, "O"); b.place(2, "O")
    move = hard.get_move(b, "O")
    assert move == 3, f"Erwartet Feld 3, bekam {move}"
    print("  [OK] test_hard_wins_when_possible")

def test_medium_blocks():
    b = Board()
    b.place(1, "X"); b.place(2, "X")
    move = medium.get_move(b, "O")
    assert move == 3, f"Erwartet Feld 3 (blockieren), bekam {move}"
    print("  [OK] test_medium_blocks")

def test_easy_returns_valid():
    b = Board()
    move = easy.get_move(b, "X")
    assert 1 <= move <= 9
    print("  [OK] test_easy_returns_valid")

def test_hard_does_not_lose():
    """Hard-KI darf gegen optimalen Spieler nie verlieren (Minimax)."""
    import random
    for _ in range(20):
        b = Board()
        turn = "X"
        while not b.is_game_over():
            if turn == "O":
                field = hard.get_move(b, "O")
            else:
                field = random.choice(b.get_empty_fields())
            b.place(field, turn)
            turn = "O" if turn == "X" else "X"
        assert b.winner != "X", "Hard-KI (O) hat verloren!"
    print("  [OK] test_hard_does_not_lose (20 Runden)")

if __name__ == "__main__":
    print("KI-Tests:")
    test_hard_wins_when_possible()
    test_medium_blocks()
    test_easy_returns_valid()
    test_hard_does_not_lose()
    print("\nAlle KI-Tests bestanden!")
