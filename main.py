import time, threading
from game.game_manager import GameManager
from ui.game_ui import GameUI
from ui.status_ui import StatusUI
from utils.logger import get_logger
from config import DEFAULT_DIFFICULTY

log = get_logger("main")


def main():
    log.info("=== TicTacToe Doosan -- Start ===")

    gm        = GameManager(human_player="X", difficulty=DEFAULT_DIFFICULTY)
    game_ui   = GameUI(gm)
    status_ui = StatusUI(gm)

    def on_field_click(field_id: int):
        if not gm.is_human_turn():
            return
        if not gm.board.is_empty(field_id):
            return
        log.info(f"Spieler setzt auf Feld {field_id}")
        gm.human_move(field_id)
        if not gm.board.is_game_over():
            threading.Thread(target=_ai_turn, daemon=True).start()

    def _ai_turn():
        time.sleep(0.8)
        field = gm.ai_move()
        if field:
            log.info(f"KI setzt auf Feld {field}")
            # Spaeter: robot_controller.do_move(field, gm.ai_player)

    def on_new_game():
        log.info("Neue Runde gestartet")

    game_ui.set_click_callback(on_field_click)
    status_ui.set_new_game_callback(on_new_game)

    log.info("Starte UIs...")
    status_ui.start()
    time.sleep(0.5)
    game_ui._run()   # Blockiert bis Fenster geschlossen


if __name__ == "__main__":
    main()
