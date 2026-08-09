"""Feedback round R6a (usability-probe triage, app.py lane).

Eight findings, one file, grouped asserts (tests/TESTING_POLICY.md). Each
test pins the invariant the probe's repro turned on, not the pixels of one
window size.
"""
import tkinter as tk

import pytest

import app
from conftest import gui, shared_app, quiesce

USES_APP = True
pytestmark = gui


@pytest.fixture(scope="module")
def a():
    return shared_app()


class mapped(object):
    """Map the shared root OFF-SCREEN for the asserts that need real pixel
    geometry (rule 58: +3200+100, never visible), then put it back."""

    def __init__(self, root, geom="1400x860+3200+100"):
        self.root, self.geom = root, geom

    def __enter__(self):
        self.old = self.root.geometry()
        self.root.geometry(self.geom)
        self.root.deiconify()
        self.root.update_idletasks()
        self.root.update()
        return self.root

    def __exit__(self, *exc):
        self.root.withdraw()
        try:
            self.root.geometry(self.old)
        except tk.TclError:
            pass
        self.root.update_idletasks()
        return False


# ------------------------------------------------------------------- B2 ---
def test_a_mouse_orbit_is_written_back_to_the_camera_fields(a):
    """Dragging the 3D view moves Elevation / Azimuth, so the next redraw
    keeps the angle instead of restoring the old one (B2)."""
    a.wf_mode.set("3D ridge")
    a.wf3d_elev.set(22.0)
    a.wf3d_azim.set(-60.0)
    assert a._wf3d_active()
    # the shared App carries no data, so stand the 3D axes up directly -
    # a drag only ever changes matplotlib's own camera, which is the whole
    # input this method has
    old_ax = a.ax
    a.fig.clf()
    a.ax = a.fig.add_subplot(111, projection="3d")
    try:
        a.ax.view_init(elev=-23.8, azim=130.4)
        assert a._capture_3d_camera() is True
        assert abs(a.wf3d_azim.get() - 130.4) < 1e-6
        assert abs(a.wf3d_elev.get() - (-23.8)) < 1e-6

        # a release that moved nothing rewrites nothing
        assert a._capture_3d_camera() is False

        # azimuth stays wrapped into the slider's range
        a.ax.view_init(elev=22.0, azim=300.0)
        a._capture_3d_camera()
        assert -180.0 <= a.wf3d_azim.get() <= 180.0

        # an elevation the mouse can reach is one the slider can show
        scales = [s for s in a._theme_scales if s.var is a.wf3d_elev]
        assert scales and scales[0].lo == -90 and scales[0].hi == 90
    finally:
        a.ax = old_ax
        a.wf_mode.set("off")
        a.wf3d_elev.set(22.0)
        a.wf3d_azim.set(-60.0)
        a._redraw_now()
        quiesce(a)


# ------------------------------------------------------------------- F1 ---
def test_the_status_line_elides_instead_of_clipping(a):
    """The counts survive every width, the preset name gives way first, and
    the tooltip carries the whole sentence (F1)."""
    long_preset = "★ Nature double column (183 mm), large fonts"
    with mapped(a.root, "1400x860+3200+100"):
        a.preset_sel.set(long_preset)
        a._skipped_count = 7
        a._update_status()
        a.root.update_idletasks()
        full = a._status_full
        assert "skipped: 7" in full and "shown:" in full

        for geom in ("1366x768+3200+100", "1600x900+3200+100",
                     "1920x1080+3200+100"):
            a.root.geometry(geom)
            a.root.update_idletasks()
            a.root.update()
            a._update_status()
            a.root.update_idletasks()
            shown = a.status_lbl.cget("text")
            room = a.status_lbl.winfo_width()
            # what is on the label fits the label - no hard clip
            assert a._F(-1).measure(shown) <= room, geom
            # the two counts are never the casualty
            assert "shown:" in shown and "skipped: 7" in shown, geom
            # anything cut is cut in the MIDDLE, or a whole low-value
            # segment leaves - an ellipsis is never allowed to eat across
            # a separator ("mode: overlay" came out "mode...y" that way).
            # Either way the whole line is one hover away.
            if shown != full:
                gone = [k for k in ("preset: ", "tab: ")
                        if k in full and k not in shown]
                assert ("…" in shown) or gone, geom
                assert full in a._status_tip.text, geom
            else:
                assert a._status_tip.text == a.STATUS_TIP, geom

    # the silent cursor readout costs the status line nothing
    a._set_cursor_readout("")
    assert int(a.cursor_lbl.cget("width")) == 0
    a._set_cursor_readout("x = -12345.678    y = -1.2345")
    assert int(a.cursor_lbl.cget("width")) == a.CURSOR_COLS
    a._set_cursor_readout("")
    quiesce(a)


def test_the_row_split_ignores_whether_the_pointer_is_on_the_plot(a):
    """The cursor readout's RESERVE decides the split, so the bar cannot
    change shape under the pointer (R4 item 1 held through F1)."""
    with mapped(a.root, "1400x860+3200+100"):
        a._set_cursor_readout("")
        a._fit_center_bar()
        a.root.update_idletasks()
        empty = a._bar_split
        a._set_cursor_readout("x = -12345.678    y = -1.2345")
        a.root.update_idletasks()
        assert a._bar_split is empty
        a._set_cursor_readout("")
        a.root.update_idletasks()
        assert a._bar_split is empty
    quiesce(a)


def test_mid_elide_keeps_both_ends(a):
    f = a._F(-1)
    text = "Nature double column (183 mm)"
    out = a._mid_elide(text, f, f.measure(text) // 2)
    assert out.startswith("Nat") and out.endswith(")")
    assert "…" in out
    assert f.measure(out) <= f.measure(text) // 2
    assert a._mid_elide(text, f, f.measure(text) + 20) == text
    assert a._mid_elide(text, f, 0) == "…"


# ------------------------------------------------------------------- F5 ---
def test_a_folders_own_notes_do_not_raise_the_skip_warning(a):
    """A README is paperwork, not a spectrum that failed to read (F5)."""
    for name in ("README.txt", "notes.md", "settings.json", "cover.png",
                 "thumbs.db"):
        assert a._skip_looks_like_data(name) is False, name
    for name in ("vis_Y04_Arch29_12p5_bg_C.001", "Y04_x_absorbance.csv",
                 "Arch29 D List.csv", "no_extension_at_all"):
        assert a._skip_looks_like_data(name) is True, name


# ------------------------------------------------------------------- F9 ---
def test_the_slow_draws_announce_themselves(a):
    """A draw that blocks the loop for seconds says so first, and only
    those draws do (F9)."""
    assert a._draw_cue() == ""             # nothing loaded
    root = a.root
    before = root.cget("cursor")
    a._begin_busy("building the surface…")
    assert root.cget("cursor") == "watch"
    assert a.status_lbl.cget("text") == "building the surface…"
    a._end_busy()
    assert root.cget("cursor") == ""
    # the cue does not become the status line
    a._update_status()
    assert a.status_lbl.cget("text") != "building the surface…"
    root.configure(cursor=before)
    quiesce(a)


# ------------------------------------------------------------------ F11 ---
def test_a_narrow_canvas_pulls_the_3d_scene_in(a):
    """A 3D axes draws its labels outside the cube, so a narrow canvas has
    to shrink the scene rather than the axes rectangle (F11)."""
    fig = a.fig
    old = fig.get_size_inches()
    dpi = float(fig.dpi)
    try:
        fig.set_size_inches(a.WF3D_FIT_W / dpi + 1.0, 6.0)
        assert a._wf3d_fit_zoom() == 1.0        # wide enough: nothing happens
        fig.set_size_inches(436.0 / dpi, 6.0)   # the 1400x860 centre pane
        z = a._wf3d_fit_zoom()
        assert 0.55 <= z < 1.0
        assert abs(z - 436.0 / a.WF3D_FIT_W) < 0.02
        fig.set_size_inches(60.0 / dpi, 6.0)
        assert a._wf3d_fit_zoom() == 0.55       # floored, never inverted
    finally:
        fig.set_size_inches(*old)
    quiesce(a)


# ------------------------------------------------------------------ F12 ---
def test_a_dialog_is_never_bigger_than_the_window_it_belongs_to(a):
    """_dialog_size caps on the app window as well as the screen (F12)."""
    with mapped(a.root, "1000x700+3200+100"):
        rw, rh = a.root.winfo_width(), a.root.winfo_height()
        w, h = a._dialog_size(126, 97)
        assert w <= max(int(a._em() * 60), int(rw * 0.94)) + 2
        assert h <= max(int(a._em() * 46), int(rh * 0.94)) + 2
        # a dialog asking for less than the window keeps what it asked for
        w2, h2 = a._dialog_size(40, 30)
        assert w2 == a._em() * 40 and h2 == a._em() * 30
    # ... and a deliberately tiny window still gets a usable dialog
    with mapped(a.root, "420x320+3200+100"):
        w, h = a._dialog_size(126, 97)
        assert w >= a._em() * 60 - 2 and h >= a._em() * 46 - 2

    # and the correction only ever shrinks
    with mapped(a.root, "1400x860+3200+100"):
        win = tk.Toplevel(a.root)
        try:
            win.geometry("900x700+3200+100")
            win.minsize(300, 200)
            tk.Frame(win, width=400, height=250).pack()
            a._shrink_to_content(win)
            win.update_idletasks()
            assert win.winfo_width() <= 900 and win.winfo_height() <= 700
            assert win.winfo_width() >= 300 and win.winfo_height() >= 200
        finally:
            win.destroy()
    quiesce(a)


# ------------------------------------------------------------------ F14 ---
def test_both_panel_buttons_sit_together_at_the_right(a):
    """R8 reverted F14 on Nhan's call: the pair lives at the FAR RIGHT of
    the top bar, left-panel control first and right-panel control
    outermost, with nothing parked beside the wordmark."""
    with mapped(a.root, "1366x768+3200+100"):
        top = a._titles_f.master
        x0 = top.winfo_rootx()
        left = a.left_btn.winfo_rootx() - x0
        right = a.right_btn.winfo_rootx() - x0
        mark_end = (a._titles_f.winfo_rootx() - x0
                    + a._titles_f.winfo_width())
        assert mark_end < left < right
        assert left > top.winfo_width() * 0.8
        # a pair, one PAD_X apart, in the order the panels sit on screen
        assert (a.right_btn.winfo_rootx()
                - (a.left_btn.winfo_rootx() + a.left_btn.winfo_width())
                == app.PAD_X)
        # and the mapping is still each button to its own panel
        assert a.left_btn.cget("command") != a.right_btn.cget("command")
    quiesce(a)


# ------------------------------------------------------------------- P8 ---
def test_thickness_mode_says_what_it_is_waiting_for(a):
    """Thickness with nothing loaded gets a line, and gives it back on the
    way out of the mode (P8)."""
    a.mode.set("thickness")
    a._redraw_now()
    quiesce(a)
    assert "Run a folder first" in a._thick_status.cget("text")
    # packed (the tab it lives on need not be the visible one here)
    assert a._thick_status.winfo_manager() == "pack"
    a.mode.set("overlay")
    a._redraw_now()
    quiesce(a)
    assert a._thick_status.cget("text") == ""
    assert a._thick_status.winfo_manager() == ""
