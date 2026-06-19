# =============================================================================
# ui/status_window.py – Zweites Statusfenster (Tkinter)
#
# Zeigt in einem separaten Fenster:
#   - Header-Balken (Dunkelgrün) mit Logo und Titel
#   - Großer Status-Text (Wer ist dran, Gewinner, etc.)
#   - Startspieler-Buttons (Mensch / Roboter / Zufall)
#   - Schwierigkeits-Buttons (Leicht / Mittel / Schwer)
#   - Footer-Balken (Dunkelgrün)
#
# Design:
#   - Inaktive Buttons: Grün mit weißer Schrift
#   - Aktive Buttons: Schwarz mit weißer Schrift
# =============================================================================
from __future__ import annotations

import os
import threading
import tkinter as tk
from typing import Callable

# Pillow für transparente PNGs
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Hilfsfunktion: Macht aus RGB den von Tkinter benötigten Hex-Code
def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


class StatusWindow:
    # ------------------------------------------------------------------
    # FARBPALETTE (Angepasst auf dein Dunkelgrün)
    # ------------------------------------------------------------------
    #                                           R    G    B
    C_MAIN_GREEN  = rgb_to_hex(26,  62,  46 )  # Dein dunkles Wunsch-Grün
    C_GREEN_HOVER = rgb_to_hex(46,  82,  66 )  # Etwas heller für Hover-Effekt
    
    C_BLACK       = rgb_to_hex(88, 224, 163)  # Schwarz für aktive Buttons
    C_WHITE       = rgb_to_hex(255, 255, 255)  # Weiß (Hintergrund & Text)
    
    C_TEXT_DARK   = rgb_to_hex(43,  43,  43 )  # Dunkelgrau für Beschriftungen
    C_LINE        = rgb_to_hex(224, 224, 224)  # Linien
    
    # Statusfarben
    C_YELLOW      = rgb_to_hex(245, 127, 23 )
    C_BLUE        = rgb_to_hex(25,  118, 210)
    C_RED         = rgb_to_hex(211, 47,  47 )

    # ------------------------------------------------------------------
    # Basis-Schriftgrößen (werden bei Resize skaliert)
    # ------------------------------------------------------------------
    BASE_W = 560
    BASE_H = 650

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
        self._lbl_footer:  tk.Label  | None = None
        self._btn_fs:      tk.Button | None = None
        self._logo_lbl:    tk.Label  | None = None

        self._tk_image = None  

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

    def set_status(self, text: str, color: str | None = None):
        with self._pending_lock:
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
        self._root.title("TicTacToe – Status")
        self._root.configure(bg=self.C_WHITE)
        self._root.resizable(True, True)
        self._root.minsize(400, 480)

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
        outer = tk.Frame(root, bg=self.C_WHITE)
        outer.pack(fill="both", expand=True)

        # ── HEADER (Dunkelgrüner Balken oben) ──────────────────────────
        header_frame = tk.Frame(outer, bg=self.C_MAIN_GREEN)
        header_frame.pack(fill="x", side="top")

        # Vollbild-Button im Header (Farben umgekehrt, da Hintergrund dunkel ist)
        self._btn_fs = tk.Button(
            header_frame, text="⛶  Vollbild  [F]",
            command=self._toggle_fullscreen,
            bg=self.C_MAIN_GREEN, fg=self.C_WHITE,
            activebackground=self.C_GREEN_HOVER, activeforeground=self.C_WHITE,
            relief="flat", bd=0,
            font=("Segoe UI", 9),
            cursor="hand2", padx=8, pady=4
        )
        self._btn_fs.place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=8)

        # Logo laden
        logo_path = "logo.png"
        if os.path.exists(logo_path):
            if HAS_PIL:
                try:
                    img = Image.open(logo_path)
                    basewidth = 200
                    wpercent = (basewidth / float(img.size[0]))
                    hsize = int((float(img.size[1]) * float(wpercent)))
                    img = img.resize((basewidth, hsize), Image.Resampling.LANCZOS)
                    self._tk_image = ImageTk.PhotoImage(img)
                except Exception as e:
                    print(f"[UI] Fehler beim PIL Logo-Laden: {e}")
            else:
                try:
                    self._tk_image = tk.PhotoImage(file=logo_path)
                    self._tk_image = self._tk_image.subsample(2, 2) 
                except Exception as e:
                    print(f"[UI] Fehler beim tk.PhotoImage Logo-Laden: {e}")

        if self._tk_image:
            self._logo_lbl = tk.Label(header_frame, image=self._tk_image, bg=self.C_MAIN_GREEN)
            self._logo_lbl.pack(pady=(20, 0))
        else:
            tk.Frame(header_frame, bg=self.C_MAIN_GREEN, height=20).pack()

        # Titel unter Logo (weiße Schrift auf grünem Grund)
        self._lbl_title = tk.Label(
            header_frame, text="TicTacToe – Doosan M1013",
            bg=self.C_MAIN_GREEN, fg=self.C_WHITE,
            font=("Segoe UI", 12, "bold")
        )
        self._lbl_title.pack(pady=(10, 15))


        # ── CONTENT (Weißer Bereich in der Mitte) ─────────────────────
        content_frame = tk.Frame(outer, bg=self.C_WHITE)
        content_frame.pack(fill="both", expand=True, pady=10)

        # Großer Status-Text
        self._status_lbl = tk.Label(
            content_frame, text="Wer fängt an?",
            bg=self.C_WHITE, fg=self.C_MAIN_GREEN,
            font=("Segoe UI", 36, "bold"),
            wraplength=500, justify="center"
        )
        self._status_lbl.pack(pady=(15, 10), padx=24, expand=True, fill="both")

        tk.Frame(content_frame, bg=self.C_LINE, height=1).pack(fill="x", padx=40, pady=(0, 15))

        # Startspieler
        self._lbl_starter = tk.Label(
            content_frame, text="Wer fängt an?  [B1]",
            bg=self.C_WHITE, fg=self.C_TEXT_DARK,
            font=("Segoe UI", 11, "bold")
        )
        self._lbl_starter.pack(anchor="w", padx=40)

        self._starter_frame = tk.Frame(content_frame, bg=self.C_WHITE)
        self._starter_frame.pack(fill="x", padx=36, pady=(6, 0))

        self._btn_human  = self._make_btn(
            self._starter_frame, "Mensch",  lambda: self._click_starter("human"),  "starter")
        self._btn_robot  = self._make_btn(
            self._starter_frame, "Roboter", lambda: self._click_starter("robot"),  "starter")
        self._btn_random = self._make_btn(
            self._starter_frame, "Zufall",  lambda: self._click_starter("random"), "starter")

        for btn in (self._btn_human, self._btn_robot, self._btn_random):
            btn.pack(side="left", expand=True, fill="x", padx=4)

        tk.Frame(content_frame, bg=self.C_LINE, height=1).pack(fill="x", padx=40, pady=(20, 15))

        # Schwierigkeit
        self._lbl_diff = tk.Label(
            content_frame, text="Schwierigkeit wählen  [B2]",
            bg=self.C_WHITE, fg=self.C_TEXT_DARK,
            font=("Segoe UI", 11, "bold")
        )
        self._lbl_diff.pack(anchor="w", padx=40)

        self._diff_frame = tk.Frame(content_frame, bg=self.C_WHITE)
        self._diff_frame.pack(fill="x", padx=36, pady=(6, 0))

        self._btn_easy   = self._make_btn(
            self._diff_frame, "Leicht", lambda: self._click_diff("easy"),   "diff")
        self._btn_medium = self._make_btn(
            self._diff_frame, "Mittel", lambda: self._click_diff("medium"), "diff")
        self._btn_hard   = self._make_btn(
            self._diff_frame, "Schwer", lambda: self._click_diff("hard"),   "diff")

        for btn in (self._btn_easy, self._btn_medium, self._btn_hard):
            btn.pack(side="left", expand=True, fill="x", padx=4)

        # Abstand nach unten im Content-Bereich
        tk.Frame(content_frame, bg=self.C_WHITE, height=20).pack()


        # ── FOOTER (Dunkelgrüner Balken unten) ─────────────────────────
        footer_frame = tk.Frame(outer, bg=self.C_MAIN_GREEN)
        footer_frame.pack(fill="x", side="bottom")

        self._lbl_footer = tk.Label(
            footer_frame, text="Mensch = X   |   Roboter = O",
            bg=self.C_MAIN_GREEN, fg=self.C_WHITE,
            font=("Segoe UI", 10, "bold")
        )
        self._lbl_footer.pack(pady=(12, 12))

    # ------------------------------------------------------------------
    # Button-Fabrik
    # ------------------------------------------------------------------
    def _make_btn(self, parent: tk.Frame, text: str, cmd, group: str) -> tk.Button:
        btn = tk.Button(
            parent, text=text, command=cmd,
            bg=self.C_MAIN_GREEN, fg=self.C_WHITE,      # Standard: Grün mit weißer Schrift
            activebackground=self.C_GREEN_HOVER,        # Beim Klicken
            activeforeground=self.C_WHITE,
            relief="flat", bd=0,
            font=("Segoe UI", 13, "bold"),
            cursor="hand2",
            padx=10, pady=12
        )
        btn.bind("<Enter>", lambda e, b=btn, g=group: self._on_hover(b, g, True))
        btn.bind("<Leave>", lambda e, b=btn, g=group: self._on_hover(b, g, False))
        return btn

    def _on_hover(self, btn: tk.Button, group: str, entering: bool):
        is_active = self._is_active(btn, group)
        if is_active:
            # Button ist ausgewählt -> bleibt schwarz
            btn.config(bg=self.C_BLACK, fg=self.C_WHITE)
        else:
            # Button ist NICHT ausgewählt -> Grün-Logik
            if entering:
                btn.config(bg=self.C_GREEN_HOVER, fg=self.C_WHITE)
            else:
                btn.config(bg=self.C_MAIN_GREEN, fg=self.C_WHITE)

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
    # Highlight-Logik (Schwarz = Aktiv / Grün = Inaktiv)
    # ------------------------------------------------------------------
    def _apply_highlight_starter(self, active: str | None):
        self._active_starter = active
        mapping = {"human": self._btn_human, "robot": self._btn_robot, "random": self._btn_random}
        for key, btn in mapping.items():
            if btn is None: continue
            
            if key == active:
                btn.config(bg=self.C_BLACK, fg=self.C_WHITE)
            else:
                btn.config(bg=self.C_MAIN_GREEN, fg=self.C_WHITE)

    def _apply_highlight_diff(self, active: str | None):
        self._active_diff = active
        mapping = {"easy": self._btn_easy, "medium": self._btn_medium, "hard": self._btn_hard}
        for key, btn in mapping.items():
            if btn is None: continue
            
            if key == active:
                btn.config(bg=self.C_BLACK, fg=self.C_WHITE)
            else:
                btn.config(bg=self.C_MAIN_GREEN, fg=self.C_WHITE)

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

        size_status = max(18, int(36 * scale))
        size_btn    = max(10, int(13 * scale))
        size_label  = max(9,  int(11 * scale))
        size_title  = max(9,  int(12 * scale))
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
                lbl.config(font=("Segoe UI", size_label, "bold"))
        if self._lbl_title:
            self._lbl_title.config(font=("Segoe UI", size_title, "bold"))
        if self._lbl_footer:
            self._lbl_footer.config(font=("Segoe UI", size_footer, "bold"))

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