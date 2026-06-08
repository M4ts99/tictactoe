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
    for p, f in [("X",1),("O",2),("X",3),("O",4),("X",6),("X",7),("O",8),("X",9),("O",5)]:
        b.place(f, p)
    assert b.is_full() and b.winner is None
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
