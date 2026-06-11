import sys
sys.path.insert(0, ".")
from game.board import Board

def test_place_and_win():
    b = Board()
    b.place(1, "X"); b.place(2, "X"); b.place(3, "X")
    assert b.winner == "X", "X sollte gewonnen haben"
    print("  [OK] test_place_and_win")

def test_draw():
    b = Board()
    # X: 1,6,8  |  O: 2,3,4,7,9  |  Kein Gewinner
    for p, f in [("X",1),("O",2),("O",3),("X",6),("O",4),("X",8),("O",7),("O",9),("X",5)]:
        b.place(f, p)
    assert b.is_full(), "Feld sollte voll sein"
    assert b.winner is None, f"Kein Gewinner erwartet, aber {b.winner} hat gewonnen"
    print("  [OK] test_draw")


def test_block():
    b = Board()
    b.place(1, "X"); b.place(2, "X")
    assert 3 in b.get_empty_fields()
    print("  [OK] test_block")

def test_invalid_place():
    b = Board()
    b.place(1, "X")
    result = b.place(1, "O")
    assert result == False
    print("  [OK] test_invalid_place")

if __name__ == "__main__":
    print("Board-Tests:")
    test_place_and_win()
    test_draw()
    test_block()
    test_invalid_place()
    print("\nAlle Board-Tests bestanden!")
