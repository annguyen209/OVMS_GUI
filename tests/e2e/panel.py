"""
panel.py — Floating CTkToplevel that shows E2E test progress.
"""

import time
import customtkinter as ctk
from app import theme

PENDING = "pending"
RUNNING = "running"
PASSED  = "passed"
FAILED  = "failed"
SKIPPED = "skipped"

_ICONS = {PENDING: "○", RUNNING: "⏳", PASSED: "✅", FAILED: "❌", SKIPPED: "⊘"}
_COLORS = {
    PENDING: theme.MUTED,
    RUNNING: theme.AMBER,
    PASSED:  theme.GREEN,
    FAILED:  theme.RED,
    SKIPPED: theme.MUTED,
}


class TestPanel(ctk.CTkToplevel):
    def __init__(self, app, steps: list):
        super().__init__(app)
        self._app     = app
        self._steps   = steps
        self._start_t = None
        self._ticking = False
        self._on_run  = None
        self._on_stop = None

        self.title("E2E Tests")
        self.attributes("-topmost", True)
        self.resizable(False, True)
        self.geometry("420x640")
        sw = self.winfo_screenwidth()
        self.geometry(f"+{sw - 440}+20")
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent accidental close

        self._build(steps)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build(self, steps):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=theme.BANNER, corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="OpenVINO Manager — E2E Tests",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#f8fafc").pack(padx=12, pady=8)

        # Progress bar
        pf = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=0)
        pf.pack(fill="x")
        self._prog = ctk.CTkProgressBar(pf, height=10)
        self._prog.set(0)
        self._prog.pack(fill="x", padx=10, pady=(8, 2))
        info = ctk.CTkFrame(pf, fg_color="transparent")
        info.pack(fill="x", padx=10, pady=(0, 8))
        self._prog_lbl = ctk.CTkLabel(info, text=f"0 / {len(steps)}",
                                       font=ctk.CTkFont(size=11), text_color=theme.MUTED)
        self._prog_lbl.pack(side="left")
        self._time_lbl = ctk.CTkLabel(info, text="",
                                       font=ctk.CTkFont(size=11), text_color=theme.MUTED)
        self._time_lbl.pack(side="right")

        # Current step indicator
        curr = ctk.CTkFrame(self, fg_color=theme.CARD2, corner_radius=0)
        curr.pack(fill="x")
        self._curr_lbl = ctk.CTkLabel(curr, text="Ready — click Run All",
                                       font=ctk.CTkFont(size=12, weight="bold"),
                                       text_color=theme.MUTED, anchor="w")
        self._curr_lbl.pack(fill="x", padx=14, pady=8)

        # Step list
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=6, pady=4)

        self._row_lbls:  dict[str, ctk.CTkLabel] = {}
        self._time_lbls: dict[str, ctk.CTkLabel] = {}
        for step in steps:
            row = ctk.CTkFrame(self._scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)
            lbl = ctk.CTkLabel(row, text=f"○  {step.label}",
                               font=ctk.CTkFont(size=11), text_color=theme.MUTED, anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            tlbl = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=10),
                                text_color=theme.MUTED, width=50, anchor="e")
            tlbl.pack(side="right")
            self._row_lbls[step.id]  = lbl
            self._time_lbls[step.id] = tlbl

        # Controls
        bot = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=0)
        bot.pack(fill="x", side="bottom")
        ctrl = ctk.CTkFrame(bot, fg_color="transparent")
        ctrl.pack(fill="x", padx=10, pady=8)
        self._run_btn = ctk.CTkButton(ctrl, text="Run All", width=90,
                                       fg_color=theme.BLUE, hover_color=theme.BLUE_H,
                                       command=self._click_run)
        self._run_btn.pack(side="left")
        self._stop_btn = ctk.CTkButton(ctrl, text="Stop", width=70,
                                        fg_color=theme.CARD2, hover_color=theme.BORDER,
                                        border_width=1, border_color=theme.BORDER2,
                                        text_color=theme.TEXT2,
                                        command=self._click_stop, state="disabled")
        self._stop_btn.pack(side="left", padx=4)
        self._summary_lbl = ctk.CTkLabel(ctrl, text="",
                                          font=ctk.CTkFont(size=11), text_color=theme.MUTED)
        self._summary_lbl.pack(side="right")

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    def _click_run(self):
        self._start_t = time.time()
        self._ticking = True
        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._tick()
        if self._on_run:
            self._on_run()

    def _click_stop(self):
        self._ticking = False
        self._stop_btn.configure(state="disabled")
        if self._on_stop:
            self._on_stop()

    def _tick(self):
        if self._ticking and self._start_t:
            e = time.time() - self._start_t
            self._time_lbl.configure(text=f"{int(e//60)}:{int(e%60):02d}")
            self.after(1000, self._tick)

    # ------------------------------------------------------------------
    # Public update methods — called from runner thread via app.after()
    # ------------------------------------------------------------------

    def set_callbacks(self, on_run, on_stop):
        self._on_run  = on_run
        self._on_stop = on_stop

    def mark(self, step_id: str, status: str,
             elapsed: float = None, error: str = None):
        lbl   = self._row_lbls.get(step_id)
        tlbl  = self._time_lbls.get(step_id)
        label = next((s.label for s in self._steps if s.id == step_id), step_id)
        icon  = _ICONS.get(status, "?")
        color = _COLORS.get(status, theme.MUTED)

        if lbl:
            suffix = f"  [{error[:50]}]" if (error and status == FAILED) else ""
            lbl.configure(text=f"{icon}  {label}{suffix}", text_color=color)
        if tlbl and elapsed is not None:
            tlbl.configure(text=f"{elapsed:.1f}s")
        if status == RUNNING:
            self._curr_lbl.configure(text=f"▶  {label}…", text_color=theme.AMBER)

    def update_counters(self, done: int, total: int, passed: int, failed: int):
        self._prog.set(done / total if total > 0 else 0)
        self._prog_lbl.configure(text=f"{done} / {total}")
        color = theme.RED if failed > 0 else (theme.GREEN if passed > 0 else theme.MUTED)
        self._summary_lbl.configure(text=f"✅ {passed}  ❌ {failed}", text_color=color)

    def finish(self, passed: int, failed: int, skipped: int):
        self._ticking = False
        total = passed + failed + skipped
        if failed == 0:
            msg   = f"All {passed} passed ✅"
            color = theme.GREEN
        else:
            msg   = f"{passed}/{total} passed — {failed} failed ❌"
            color = theme.RED
        self._curr_lbl.configure(text=msg, text_color=color)
        self._run_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._prog.set(1.0)
