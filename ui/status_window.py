# =============================================================================
# ui/status_window.py – Zweites Statusfenster (Tkinter)
#
# Zeigt in einem separaten Fenster:
#   - Großer Status-Text (Wer ist dran, Gewinner, etc.)
#   - Startspieler-Buttons (Mensch / Roboter / Zufall)  – 1 Reihe
#   - Schwierigkeits-Buttons (Leicht / Mittel / Schwer) – 1 Reihe
#
# Features:
#   - Vollbild per F-Taste oder Vollbild-Button (toggle)
#   - Buttons skalieren relativ zur Fenstergröße
#   - Aktive Auswahl wird farbig markiert
#   - Reset löscht alle Markierungen
#
# Läuft in einem eigenen Thread, kommuniziert über Callbacks mit MainApp.
# =============================================================================
from __future__ import annotations

import threading
import tkinter as tk
from typing import Callable


class StatusWindow:
    """
    Zweites Fenster mit Tkinter.
    Wird in einem eigenen Thread gestartet damit pygame nicht blockiert wird.

    Callbacks (werden im Tkinter-Thread aufgerufen, landen über
    pending-Flags im Pygame-Hauptthread):
        on_starter(str)     – "human" | "robot" | "random"
        on_difficulty(str)  – "easy"  | "medium" | "hard"
    """

    # ------------------------------------------------------------------
    # Farben
    # ------------------------------------------------------------------
    C_BG        = "#12121e"
    C_PANEL     = "#1a1a28"
    C_TEXT      = "#ebebf0"
    C_DIM       = "#82829b"
    C_LINE      = "#505078"
    C_BTN       = "#282840"
    C_BTN_HOV   = "#373758"

    # Aktiv-Farben je Gruppe
    C_STARTER_ACT = "#3a5f3a"   # Grün-dunkel  – Startspieler gewählt
    C_DIFF_ACT    = "#3a3a6a"   # Blau-dunkel  – Schwierigkeit gewählt

    C_STARTER_ACT_FG = "#80e880"   # helles Grün
    C_DIFF_ACT_FG    = "#8080ff"   # helles Blau

    # Statusfarben
    C_YELLOW = "#f0c846"
    C_BLUE   = "#6499ff"
    C_RED    = "#dc5050"
    C_GOLD   = "#ffd700"
    C_CYAN   = "#50b4dc"
    C_GREY   = "#82829b"

    # ------------------------------------------------------------------
    # Basis-Schriftgrößen (werden bei Resize skaliert)
    # ------------------------------------------------------------------
    BASE_W = 560
    BASE_H = 520

    def __init__(self,
                 on_starter:    Callable[[str], None],
                 on_difficulty: Callable[[str], None]):
        self._on_starter    = on_starter
        self._on_difficulty = on_difficulty

        self._root:   tk.Tk | None = None
        self._thread: threading.Thread | None = None
        self._running   = False
        self._fullscreen = False

        # Aktuelle Auswahl (für Markierung)
        self._active_starter: str | None = None
        self._active_diff:    str | None = None

        # Pending-Updates (thread-sicher)
        self._pending_status:  tuple[str, str] | None = None
        self._pending_starter: str | None = None   # "" = clear
        self._pending_diff:    str | None = None   # "" = clear
        self._pending_lock = threading.Lock()

        # Widget-Referenzen (gesetzt in _build)
        self._status_lbl:  tk.Label  | None = None
        self._btn_human:   tk.Button | None = None
        self._btn_robot:   tk.Button | None = None
        self._btn_random:  tk.Button | None = None
        self._btn_easy:    tk.Button | None = None
        self._btn_medium:  tk.Button | None = None
        self._btn_hard:    tk.Button | None = None
        self._lbl_starter: tk.Label  | None = None
        self._lbl_diff:    tk.Label  | None = None
        self._lbl_title:   tk.Label  | None = None
        self._lbl_footer:  tk.Label  | None = None
        self._btn_fs:      tk.Button | None = None

        # alle Frames für Resize
        self._starter_frame: tk.Frame | None = None
        self._diff_frame:    tk.Frame | None = None

    # ------------------------------------------------------------------
    # Starten / Stoppen
    # ------------------------------------------------------------------
    def start(self):
        """Startet das Fenster in einem eigenen Daemon-Thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run_tk,
            daemon=True,
            name="StatusWindow"
        )
        self._thread.start()

    def stop(self):
        """Schließt das Fenster sauber."""
        self._running = False
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except Exception:
                pass

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Öffentliche Update-Methoden (thread-sicher, aus beliebigem Thread)
    # ------------------------------------------------------------------
    def set_status(self, text: str, color: str | None = None):
        """Setzt den großen Status-Text."""
        with self._pending_lock:
            self._pending_status = (text, color or self.C_TEXT)

    def set_starter(self, starter: str | None):
        """Markiert den aktiven Startspieler-Button. None / '' = alle deaktivieren."""
        with self._pending_lock:
            self._pending_starter = starter if starter else ""

    def set_difficulty(self, diff: str | None):
        """Markiert den aktiven Schwierigkeits-Button. None / '' = alle deaktivieren."""
        with self._pending_lock:
            self._pending_diff = diff if diff else ""

    def clear_selection(self):
        """Löscht beide Markierungen (z.B. nach Reset)."""
        with self._pending_lock:
            self._pending_starter = ""
            self._pending_diff    = ""

    # ------------------------------------------------------------------
    # Tkinter-Hauptschleife
    # ------------------------------------------------------------------
    def _run_tk(self):
        self._root = tk.Tk()
        self._root.title("TicTacToe – Status")
        self._root.configure(bg=self.C_BG)
        self._root.resizable(True, True)
        self._root.minsize(400, 380)

        w, h = self.BASE_W, self.BASE_H
        self._root.geometry(f"{w}x{h}+20+20")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        # F-Taste → Vollbild toggle
        self._root.bind("<F>", lambda e: self._toggle_fullscreen())
        self._root.bind("<f>", lambda e: self._toggle_fullscreen())
        self._root.bind("<Escape>", lambda e: self._exit_fullscreen())

        self._build()

        # Resize-Event
        self._root.bind("<Configure>", self._on_resize)

        self._poll()
        self._root.mainloop()
        self._running = False

    def _on_close(self):
        self._running = False
        try:
            self._root.quit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Vollbild
    # ------------------------------------------------------------------
    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        self._root.attributes("-fullscreen", self._fullscreen)
        icon = "⛶  Fenstermodus" if self._fullscreen else "⛶  Vollbild  [F]"
        if self._btn_fs:
            self._btn_fs.config(text=icon)

    def _exit_fullscreen(self):
        if self._fullscreen:
            self._fullscreen = False
            self._root.attributes("-fullscreen", False)
            if self._btn_fs:
                self._btn_fs.config(text="⛶  Vollbild  [F]")

    # ------------------------------------------------------------------
    # UI aufbauen
    # ------------------------------------------------------------------
    def _build(self):
        root = self._root

        # Haupt-Container – füllt das ganze Fenster
        outer = tk.Frame(root, bg=self.C_BG)
        outer.pack(fill="both", expand=True)

        # ── Vollbild-Button (oben rechts) ──────────────────────────────
        self._btn_fs = tk.Button(
            outer, text="⛶  Vollbild  [F]",
            command=self._toggle_fullscreen,
            bg=self.C_BTN, fg=self.C_DIM,
            activebackground=self.C_BTN_HOV, activeforeground=self.C_TEXT,
            relief="flat", bd=0,
            font=("Segoe UI", 9),
            cursor="hand2", padx=8, pady=4
        )
        self._btn_fs.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=8)

        # ── Titel ──────────────────────────────────────────────────────
        self._lbl_title = tk.Label(
            outer, text="TicTacToe – Doosan M1013",
            bg=self.C_BG, fg=self.C_DIM,
            font=("Segoe UI", 11)
        )
        self._lbl_title.pack(pady=(18, 0))

        tk.Frame(outer, bg=self.C_LINE, height=1).pack(fill="x", padx=24, pady=(8, 0))

        # ── Großer Status-Text ─────────────────────────────────────────
        self._status_lbl = tk.Label(
            outer, text="Wer fängt an?",
            bg=self.C_BG, fg=self.C_YELLOW,
            font=("Segoe UI", 36, "bold"),
            wraplength=500, justify="center"
        )
        self._status_lbl.pack(pady=(0, 0), padx=24, expand=True, fill="both")

        tk.Frame(outer, bg=self.C_LINE, height=1).pack(fill="x", padx=24, pady=(0, 12))

        # ── Startspieler ───────────────────────────────────────────────
        self._lbl_starter = tk.Label(
            outer, text="Wer fängt an?  [B1]",
            bg=self.C_BG, fg=self.C_DIM,
            font=("Segoe UI", 11)
        )
        self._lbl_starter.pack(anchor="w", padx=24)

        self._starter_frame = tk.Frame(outer, bg=self.C_BG)
        self._starter_frame.pack(fill="x", padx=24, pady=(6, 0))

        self._btn_human  = self._make_btn(
            self._starter_frame, "Mensch",  lambda: self._click_starter("human"),  "starter")
        self._btn_robot  = self._make_btn(
            self._starter_frame, "Roboter", lambda: self._click_starter("robot"),  "starter")
        self._btn_random = self._make_btn(
            self._starter_frame, "Zufall",  lambda: self._click_starter("random"), "starter")

        for btn in (self._btn_human, self._btn_robot, self._btn_random):
            btn.pack(side="left", expand=True, fill="x", padx=3)

        tk.Frame(outer, bg=self.C_LINE, height=1).pack(fill="x", padx=24, pady=(16, 12))

        # ── Schwierigkeit ──────────────────────────────────────────────
        self._lbl_diff = tk.Label(
            outer, text="Schwierigkeit  [B2 / B3 / B4]",
            bg=self.C_BG, fg=self.C_DIM,
            font=("Segoe UI", 11)
        )
        self._lbl_diff.pack(anchor="w", padx=24)

        self._diff_frame = tk.Frame(outer, bg=self.C_BG)
        self._diff_frame.pack(fill="x", padx=24, pady=(6, 0))

        self._btn_easy   = self._make_btn(
            self._diff_frame, "Leicht", lambda: self._click_diff("easy"),   "diff")
        self._btn_medium = self._make_btn(
            self._diff_frame, "Mittel", lambda: self._click_diff("medium"), "diff")
        self._btn_hard   = self._make_btn(
            self._diff_frame, "Schwer", lambda: self._click_diff("hard"),   "diff")

        for btn in (self._btn_easy, self._btn_medium, self._btn_hard):
            btn.pack(side="left", expand=True, fill="x", padx=3)

        # ── Fußzeile ───────────────────────────────────────────────────
        tk.Frame(outer, bg=self.C_LINE, height=1).pack(fill="x", padx=24, pady=(16, 0))
        self._lbl_footer = tk.Label(
            outer, text="Mensch = X   |   Roboter = O",
            bg=self.C_BG, fg=self.C_DIM,
            font=("Segoe UI", 10)
        )
        self._lbl_footer.pack(pady=(8, 14))

    # ------------------------------------------------------------------
    # Button-Fabrik
    # ------------------------------------------------------------------
    def _make_btn(self, parent: tk.Frame, text: str,
                  cmd, group: str) -> tk.Button:
        btn = tk.Button(
            parent, text=text, command=cmd,
            bg=self.C_BTN, fg=self.C_TEXT,
            activebackground=self.C_BTN_HOV,
            activeforeground=self.C_TEXT,
            relief="flat", bd=0,
            font=("Segoe UI", 13, "bold"),
            cursor="hand2",
            padx=10, pady=12
        )
        btn.bind("<Enter>", lambda e, b=btn, g=group: self._on_hover(b, g, True))
        btn.bind("<Leave>", lambda e, b=btn, g=group: self._on_hover(b, g, False))
        return btn

    def _on_hover(self, btn: tk.Button, group: str, entering: bool):
        """Hover-Effekt – nur wenn Button nicht aktiv ist."""
        is_active = self._is_active(btn, group)
        if entering and not is_active:
            btn.config(bg=self.C_BTN_HOV)
        elif not entering and not is_active:
            btn.config(bg=self.C_BTN)

    def _is_active(self, btn: tk.Button, group: str) -> bool:
        if group == "starter":
            mapping = {"human": self._btn_human,
                       "robot": self._btn_robot,
                       "random": self._btn_random}
            return mapping.get(self._active_starter) is btn
        else:
            mapping = {"easy": self._btn_easy,
                       "medium": self._btn_medium,
                       "hard": self._btn_hard}
            return mapping.get(self._active_diff) is btn

    # ------------------------------------------------------------------
    # Button-Callbacks
    # ------------------------------------------------------------------
    def _click_starter(self, value: str):
        self._on_starter(value)
        self._apply_highlight_starter(value)

    def _click_diff(self, value: str):
        self._on_difficulty(value)
        self._apply_highlight_diff(value)

    # ------------------------------------------------------------------
    # Highlight-Logik (immer im Tkinter-Thread aufrufen!)
    # ------------------------------------------------------------------
    def _apply_highlight_starter(self, active: str | None):
        self._active_starter = active
        mapping = {
            "human":  self._btn_human,
            "robot":  self._btn_robot,
            "random": self._btn_random,
        }
        for key, btn in mapping.items():
            if btn is None:
                continue
            if key == active:
                btn.config(bg=self.C_STARTER_ACT, fg=self.C_STARTER_ACT_FG,
                           relief="flat")
            else:
                btn.config(bg=self.C_BTN, fg=self.C_TEXT, relief="flat")

    def _apply_highlight_diff(self, active: str | None):
        self._active_diff = active
        mapping = {
            "easy":   self._btn_easy,
            "medium": self._btn_medium,
            "hard":   self._btn_hard,
        }
        for key, btn in mapping.items():
            if btn is None:
                continue
            if key == active:
                btn.config(bg=self.C_DIFF_ACT, fg=self.C_DIFF_ACT_FG,
                           relief="flat")
            else:
                btn.config(bg=self.C_BTN, fg=self.C_TEXT, relief="flat")

    # ------------------------------------------------------------------
    # Resize – Schriftgröße skalieren
    # ------------------------------------------------------------------
    def _on_resize(self, event):
        if event.widget != self._root:
            return
        w = event.width
        h = event.height

        # Skalierungsfaktor (Basis: 560x520)
        scale = min(w / self.BASE_W, h / self.BASE_H)
        scale = max(0.6, min(scale, 3.0))   # Grenzen: 60% … 300%

        size_status = max(18, int(36 * scale))
        size_btn    = max(10, int(13 * scale))
        size_label  = max(9,  int(11 * scale))
        size_title  = max(9,  int(11 * scale))
        size_footer = max(8,  int(10 * scale))

        if self._status_lbl:
            self._status_lbl.config(
                font=("Segoe UI", size_status, "bold"),
                wraplength=max(200, int(w * 0.85))
            )
        for btn in (self._btn_human, self._btn_robot, self._btn_random,
                    self._btn_easy, self._btn_medium, self._btn_hard):
            if btn:
                btn.config(font=("Segoe UI", size_btn, "bold"),
                           pady=max(6, int(12 * scale)))
        for lbl in (self._lbl_starter, self._lbl_diff):
            if lbl:
                lbl.config(font=("Segoe UI", size_label))
        if self._lbl_title:
            self._lbl_title.config(font=("Segoe UI", size_title))
        if self._lbl_footer:
            self._lbl_footer.config(font=("Segoe UI", size_footer))

    # ------------------------------------------------------------------
    # Poll-Schleife (alle 50ms – verarbeitet pending Updates im TK-Thread)
    # ------------------------------------------------------------------
    def _poll(self):
        if not self._running:
            return

        with self._pending_lock:
            status  = self._pending_status
            starter = self._pending_starter
            diff    = self._pending_diff
            self._pending_status  = None
            self._pending_starter = None
            self._pending_diff    = None

        if status is not None:
            text, color = status
            if self._status_lbl:
                self._status_lbl.config(text=text, fg=color)

        if starter is not None:
            # "" bedeutet: Auswahl löschen
            self._apply_highlight_starter(starter if starter else None)

        if diff is not None:
            self._apply_highlight_diff(diff if diff else None)

        if self._root:
            self._root.after(50, self._poll)
