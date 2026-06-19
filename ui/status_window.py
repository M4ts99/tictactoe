# =============================================================================
# ui/status_window.py – Zweites Statusfenster (Tkinter)
#
# Zeigt in einem separaten Fenster:
#   - Logo (logo.png) und "Schlag den Cobot"
#   - Großer Status-Text (Wer ist dran, Gewinner, etc.)
#   - Startspieler-Buttons (Mensch / Roboter / Zufall)
#   - Schwierigkeits-Buttons (Leicht / Mittel / Schwer)
#
# Weiß-Grünes Design:
#   - Konfigurierbarer Grünton am Anfang der Klasse
#   - Modernes Flat-Design für Buttons
# =============================================================================
from __future__ import annotations

import os
import threading
import tkinter as tk
from typing import Callable

# Pillow für transparente PNGs (graceful fallback falls nicht installiert)
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class StatusWindow:
    """
    Zweites Fenster mit Tkinter.
    Wird in einem eigenen Thread gestartet damit pygame nicht blockiert wird.

    Callbacks:
        on_starter(str)     – "human" | "robot" | "random"
        on_difficulty(str)  – "easy"  | "medium" | "hard"
    """

    # ------------------------------------------------------------------
    # FARBPALETTE (Weiß / Grün)
    # ------------------------------------------------------------------
    # HIER DEN GEWÜNSCHTEN GRÜNTON EINTRAGEN:
    C_MAIN_GREEN    = "#2596be"    # Modernes, frisches Grün (z.B. Doosan-ähnlich)
    C_GREEN_HOVER   = "#66bb6a"    # Etwas helleres Grün für Hover-Effekte
    
    C_BG            = "#ffffff"    # Reines Weiß für den Hintergrund
    C_TEXT          = "#2b2b2b"    # Dunkelgrau für Lesbarkeit (statt hartem Schwarz)
    C_DIM           = "#757575"    # Mittleres Grau für Beschriftungen
    C_LINE          = "#e0e0e0"    # Sehr helles Grau für Trennlinien
    C_BTN           = "#f5f5f5"    # Sehr helles Grau für inaktive Buttons
    C_BTN_HOV       = "#eeeeee"    # Etwas dunkleres Grau für inaktiven Button-Hover

    C_ACT_FG        = "#ffffff"    # Weiße Schrift auf grünem (aktivem) Button

    # Statusfarben (angepasst an hellen Hintergrund)
    C_YELLOW        = "#f57f17"    # Dunkleres Gelb/Orange
    C_BLUE          = "#1976d2"    # Modernes Blau
    C_RED           = "#d32f2f"    # Modernes Rot
    C_GOLD          = "#fbc02d"    # Gold
    C_CYAN          = "#0097a7"
    C_GREY          = "#616161"

    # ------------------------------------------------------------------
    # Basis-Schriftgrößen (werden bei Resize skaliert)
    # ------------------------------------------------------------------
    BASE_W = 560
    BASE_H = 620  # Etwas höher für Logo und Extra-Titel

    def __init__(self,
                 on_starter:    Callable[[str], None],
                 on_difficulty: Callable[[str], None]):
        self._on_starter    = on_starter
        self._on_difficulty = on_difficulty

        self._root:   tk.Tk | None = None
        self._thread: threading.Thread | None = None
        self._running   = False
        self._fullscreen = False

        self._active_starter: str | None = None
        self._active_diff:    str | None = None

        self._pending_status:  tuple[str, str] | None = None
        self._pending_starter: str | None = None
        self._pending_diff:    str | None = None
        self._pending_lock = threading.Lock()

        # Widget-Referenzen
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
        self._lbl_cobot:   tk.Label  | None = None
        self._lbl_footer:  tk.Label  | None = None
        self._btn_fs:      tk.Button | None = None
        self._logo_lbl:    tk.Label  | None = None

        self._tk_image = None  # Referenz für das Bild halten (Garbage Collection)

        self._starter_frame: tk.Frame | None = None
        self._diff_frame:    tk.Frame | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._run_tk,
            daemon=True,
            name="StatusWindow"
        )
        self._thread.start()

    def stop(self):
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
    # Öffentliche Update-Methoden
    # ------------------------------------------------------------------
    def set_status(self, text: str, color: str | None = None):
        with self._pending_lock:
            # Wenn keine Farbe angegeben, Standard-Grün nutzen
            self._pending_status = (text, color or self.C_MAIN_GREEN)

    def set_starter(self, starter: str | None):
        with self._pending_lock:
            self._pending_starter = starter if starter else ""

    def set_difficulty(self, diff: str | None):
        with self._pending_lock:
            self._pending_diff = diff if diff else ""

    def clear_selection(self):
        with self._pending_lock:
            self._pending_starter = ""
            self._pending_diff    = ""

    # ------------------------------------------------------------------
    # Tkinter-Hauptschleife
    # ------------------------------------------------------------------
    def _run_tk(self):
        self._root = tk.Tk()
        self._root.title("Schlag den Cobot – Status")
        self._root.configure(bg=self.C_BG)
        self._root.resizable(True, True)
        self._root.minsize(400, 450)

        w, h = self.BASE_W, self.BASE_H
        self._root.geometry(f"{w}x{h}+20+20")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._root.bind("<F>", lambda e: self._toggle_fullscreen())
        self._root.bind("<f>", lambda e: self._toggle_fullscreen())
        self._root.bind("<Escape>", lambda e: self._exit_fullscreen())

        self._build()
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

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        self._root.attributes("-fullscreen", self._fullscreen)
        icon = "⛶  Fenster" if self._fullscreen else "⛶  Vollbild  [F]"
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
        outer = tk.Frame(root, bg=self.C_BG)
        outer.pack(fill="both", expand=True)

        # ── Vollbild-Button ──────────────────────────────────────────
        self._btn_fs = tk.Button(
            outer, text="⛶  Vollbild  [F]",
            command=self._toggle_fullscreen,
            bg=self.C_BG, fg=self.C_DIM,
            activebackground=self.C_BTN_HOV, activeforeground=self.C_TEXT,
            relief="flat", bd=0,
            font=("Segoe UI", 9),
            cursor="hand2", padx=8, pady=4
        )
        self._btn_fs.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=8)

        # ── Logo laden (falls vorhanden) ─────────────────────────────
        logo_path = "logo.png"
        if os.path.exists(logo_path):
            if HAS_PIL:
                try:
                    img = Image.open(logo_path)
                    # Bild skalieren (z.B. auf 150px Breite, Höhe proportional)
                    basewidth = 150
                    wpercent = (basewidth / float(img.size[0]))
                    hsize = int((float(img.size[1]) * float(wpercent)))
                    img = img.resize((basewidth, hsize), Image.Resampling.LANCZOS)
                    self._tk_image = ImageTk.PhotoImage(img)
                except Exception as e:
                    print(f"[UI] Fehler beim PIL Logo-Laden: {e}")
            else:
                try:
                    self._tk_image = tk.PhotoImage(file=logo_path)
                    # Einfacher Subsample falls Bild zu groß ist (native tk-Lösung)
                    self._tk_image = self._tk_image.subsample(3, 3) 
                except Exception as e:
                    print(f"[UI] Fehler beim tk.PhotoImage Logo-Laden: {e}")

        if self._tk_image:
            self._logo_lbl = tk.Label(outer, image=self._tk_image, bg=self.C_BG)
            self._logo_lbl.pack(pady=(20, 0))
        else:
            # Platzhalter falls kein Bild da ist
            tk.Frame(outer, bg=self.C_BG, height=20).pack()

        # ── Titel "Schlag den Cobot" ──────────────────────────────────
        self._lbl_cobot = tk.Label(
            outer, text="SCHLAG DEN COBOT",
            bg=self.C_BG, fg=self.C_MAIN_GREEN,
            font=("Segoe UI", 20, "bold")
        )
        self._lbl_cobot.pack(pady=(5, 0))

        self._lbl_title = tk.Label(
            outer, text="TicTacToe – Doosan M1013",
            bg=self.C_BG, fg=self.C_DIM,
            font=("Segoe UI", 11)
        )
        self._lbl_title.pack(pady=(0, 10))

        tk.Frame(outer, bg=self.C_LINE, height=1).pack(fill="x", padx=40, pady=(0, 10))

        # ── Großer Status-Text ────────────────────────────────────────
        self._status_lbl = tk.Label(
            outer, text="Wer fängt an?",
            bg=self.C_BG, fg=self.C_MAIN_GREEN,
            font=("Segoe UI", 36, "bold"),
            wraplength=500, justify="center"
        )
        self._status_lbl.pack(pady=(10, 10), padx=24, expand=True, fill="both")

        tk.Frame(outer, bg=self.C_LINE, height=1).pack(fill="x", padx=40, pady=(0, 15))

        # ── Startspieler ──────────────────────────────────────────────
        self._lbl_starter = tk.Label(
            outer, text="Wer fängt an?  [B1]",
            bg=self.C_BG, fg=self.C_DIM,
            font=("Segoe UI", 11, "bold")
        )
        self._lbl_starter.pack(anchor="w", padx=40)

        self._starter_frame = tk.Frame(outer, bg=self.C_BG)
        self._starter_frame.pack(fill="x", padx=36, pady=(6, 0))

        self._btn_human  = self._make_btn(
            self._starter_frame, "Mensch",  lambda: self._click_starter("human"),  "starter")
        self._btn_robot  = self._make_btn(
            self._starter_frame, "Roboter", lambda: self._click_starter("robot"),  "starter")
        self._btn_random = self._make_btn(
            self._starter_frame, "Zufall",  lambda: self._click_starter("random"), "starter")

        for btn in (self._btn_human, self._btn_robot, self._btn_random):
            btn.pack(side="left", expand=True, fill="x", padx=4)

        tk.Frame(outer, bg=self.C_LINE, height=1).pack(fill="x", padx=40, pady=(20, 15))

        # ── Schwierigkeit ──────────────────────────────────────────────
        self._lbl_diff = tk.Label(
            outer, text="Schwierigkeit wählen  [B2]",
            bg=self.C_BG, fg=self.C_DIM,
            font=("Segoe UI", 11, "bold")
        )
        self._lbl_diff.pack(anchor="w", padx=40)

        self._diff_frame = tk.Frame(outer, bg=self.C_BG)
        self._diff_frame.pack(fill="x", padx=36, pady=(6, 0))

        self._btn_easy   = self._make_btn(
            self._diff_frame, "Leicht", lambda: self._click_diff("easy"),   "diff")
        self._btn_medium = self._make_btn(
            self._diff_frame, "Mittel", lambda: self._click_diff("medium"), "diff")
        self._btn_hard   = self._make_btn(
            self._diff_frame, "Schwer", lambda: self._click_diff("hard"),   "diff")

        for btn in (self._btn_easy, self._btn_medium, self._btn_hard):
            btn.pack(side="left", expand=True, fill="x", padx=4)

        # ── Fußzeile ───────────────────────────────────────────────────
        tk.Frame(outer, bg=self.C_LINE, height=1).pack(fill="x", padx=40, pady=(25, 0))
        self._lbl_footer = tk.Label(
            outer, text="Mensch = X   |   Roboter = O",
            bg=self.C_BG, fg=self.C_DIM,
            font=("Segoe UI", 10)
        )
        self._lbl_footer.pack(pady=(12, 20))

    # ------------------------------------------------------------------
    # Button-Fabrik (Modernes, flaches Design)
    # ------------------------------------------------------------------
    def _make_btn(self, parent: tk.Frame, text: str, cmd, group: str) -> tk.Button:
        # Ein Rahmen um den Button für einen leichten Border-Effekt
        border_frame = tk.Frame(parent, bg=self.C_LINE, padx=1, pady=1)
        
        btn = tk.Button(
            border_frame, text=text, command=cmd,
            bg=self.C_BTN, fg=self.C_TEXT,
            activebackground=self.C_BTN_HOV,
            activeforeground=self.C_TEXT,
            relief="flat", bd=0,
            font=("Segoe UI", 13, "bold"),
            cursor="hand2",
            padx=10, pady=12
        )
        btn.pack(expand=True, fill="both")
        
        btn.bind("<Enter>", lambda e, b=btn, g=group: self._on_hover(b, g, True))
        btn.bind("<Leave>", lambda e, b=btn, g=group: self._on_hover(b, g, False))
        
        # Speichere die Referenz zum Border-Frame im Button, 
        # damit wir die Border-Farbe später ändern können
        btn.border_frame = border_frame 
        return btn

    def _on_hover(self, btn: tk.Button, group: str, entering: bool):
        is_active = self._is_active(btn, group)
        if entering:
            if not is_active:
                btn.config(bg=self.C_BTN_HOV)
            else:
                btn.config(bg=self.C_GREEN_HOVER)
        else:
            if not is_active:
                btn.config(bg=self.C_BTN)
            else:
                btn.config(bg=self.C_MAIN_GREEN)

    def _is_active(self, btn: tk.Button, group: str) -> bool:
        if group == "starter":
            mapping = {"human": self._btn_human, "robot": self._btn_robot, "random": self._btn_random}
            return mapping.get(self._active_starter) is btn
        else:
            mapping = {"easy": self._btn_easy, "medium": self._btn_medium, "hard": self._btn_hard}
            return mapping.get(self._active_diff) is btn

    def _click_starter(self, value: str):
        self._on_starter(value)
        self._apply_highlight_starter(value)

    def _click_diff(self, value: str):
        self._on_difficulty(value)
        self._apply_highlight_diff(value)

    # ------------------------------------------------------------------
    # Highlight-Logik
    # ------------------------------------------------------------------
    def _apply_highlight_starter(self, active: str | None):
        self._active_starter = active
        mapping = {"human": self._btn_human, "robot": self._btn_robot, "random": self._btn_random}
        for key, btn in mapping.items():
            if btn is None:
                continue
            if key == active:
                btn.config(bg=self.C_MAIN_GREEN, fg=self.C_ACT_FG)
                btn.border_frame.config(bg=self.C_MAIN_GREEN) # Grüner Border
            else:
                btn.config(bg=self.C_BTN, fg=self.C_TEXT)
                btn.border_frame.config(bg=self.C_LINE)       # Grauer Border

    def _apply_highlight_diff(self, active: str | None):
        self._active_diff = active
        mapping = {"easy": self._btn_easy, "medium": self._btn_medium, "hard": self._btn_hard}
        for key, btn in mapping.items():
            if btn is None:
                continue
            if key == active:
                btn.config(bg=self.C_MAIN_GREEN, fg=self.C_ACT_FG)
                btn.border_frame.config(bg=self.C_MAIN_GREEN)
            else:
                btn.config(bg=self.C_BTN, fg=self.C_TEXT)
                btn.border_frame.config(bg=self.C_LINE)

    # ------------------------------------------------------------------
    # Resize – Schriftgröße skalieren
    # ------------------------------------------------------------------
    def _on_resize(self, event):
        if event.widget != self._root:
            return
        w = event.width
        h = event.height

        scale = min(w / self.BASE_W, h / self.BASE_H)
        scale = max(0.6, min(scale, 3.0))

        size_cobot  = max(16, int(20 * scale))
        size_status = max(18, int(36 * scale))
        size_btn    = max(10, int(13 * scale))
        size_label  = max(9,  int(11 * scale))
        size_title  = max(9,  int(11 * scale))
        size_footer = max(8,  int(10 * scale))

        if self._lbl_cobot:
            self._lbl_cobot.config(font=("Segoe UI", size_cobot, "bold"))
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
                lbl.config(font=("Segoe UI", size_label, "bold"))
        if self._lbl_title:
            self._lbl_title.config(font=("Segoe UI", size_title))
        if self._lbl_footer:
            self._lbl_footer.config(font=("Segoe UI", size_footer))

    # ------------------------------------------------------------------
    # Poll-Schleife (verarbeitet pending Updates im TK-Thread)
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
            self._apply_highlight_starter(starter if starter else None)

        if diff is not None:
            self._apply_highlight_diff(diff if diff else None)

        if self._root:
            self._root.after(50, self._poll)