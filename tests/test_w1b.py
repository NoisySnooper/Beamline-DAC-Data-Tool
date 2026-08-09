"""W1b: dropdown step arrows, app-wide popup singletons, the surface-
interpolation [?] box, and the Guide box's fringe-style tags.

Contract, not pixels (tests/TESTING_POLICY.md - shared App, grouped
asserts, no per-test relaunch):
  - _step_combo walks the SHOWN list, wraps, skips divider rows, and
    fires <<ComboboxSelected>> so a mapped combo's canonical var follows;
  - every registered arrow pair carries a drawn glyph after _apply_brand;
  - a second open of any app-owned dialog focuses the ONE window instead
    of spawning a twin (the fringe workbench's _raise_existing pattern);
  - the [?] window holds typeset math (or its honest mono fallback);
  - the Guide box classifies views into h/s/b/i/m segments and styles
    them, while My notes stays editable.
"""
import tkinter as tk
from tkinter import ttk

import pytest

from conftest import ROOT, gui, offscreen, quiesce, shared_app

USES_APP = True
pytestmark = gui


@pytest.fixture(scope="module")
def a():
    return shared_app()


# ---------------------------------------------------------------------------
# arrows
# ---------------------------------------------------------------------------
def test_step_combo_steps_wraps_and_skips_dividers(a):
    # plain combo: the Waterfall mode row
    a.wf_mode.set("off")
    wfcb = None

    def _walk(w):
        nonlocal wfcb
        for c in w.winfo_children():
            if (isinstance(c, ttk.Combobox)
                    and str(c.cget("textvariable")) == str(a.wf_mode)):
                wfcb = wfcb or c
            _walk(c)
    _walk(ROOT)
    assert wfcb is not None
    a._step_combo(wfcb, 1)
    assert a.wf_mode.get() == "2D stacked"
    a._step_combo(wfcb, -2)          # -1 twice would redraw twice
    a._step_combo(wfcb, 1)
    a.wf_mode.set("off")
    a._step_combo(wfcb, -1)
    assert a.wf_mode.get() == "3D shape", "the list wraps"
    a.wf_mode.set("off")
    quiesce(a)

    # divider rows: a throwaway combo shaped like the theme dropdown
    v = tk.StringVar(value="A")
    cb = ttk.Combobox(ROOT, textvariable=v, state="readonly",
                      values=["A", "B", "─" * 12, "C"])
    try:
        a._step_combo(cb, 1)
        a._step_combo(cb, 1)
        assert v.get() == "C", "the divider is never landed on"
        a._step_combo(cb, 1)
        assert v.get() == "A"
    finally:
        cb.destroy()


def test_mapped_combo_arrow_syncs_canonical_var(a):
    a.wf3d_look.set("Walls + traces")
    ROOT.update_idletasks()
    lkc = None

    def _walk(w):
        nonlocal lkc
        for c in w.winfo_children():
            if isinstance(c, ttk.Combobox):
                vals = [str(x) for x in c.cget("values")]
                if vals[:2] == ["walls + traces", "walls only"]:
                    lkc = lkc or c
            _walk(c)
    _walk(ROOT)
    assert lkc is not None
    a._step_combo(lkc, 1)
    assert a.wf3d_look.get() == "Walls only", \
        "display step must reach the canonical var through to_code"
    a.wf3d_look.set("Walls + traces")
    quiesce(a)


def test_arrow_registry_complete_and_stamped(a):
    pairs = a._combo_arrow_btns
    # 41 rows x (prev, next). Every combo with spare room on its line
    # takes a pair; a call that reaches an unpacked combo registers
    # nothing, which is why the count is not the call-site count.
    # R9a/R9b added the App-font picker, Shades, the direct labels'
    # Backing and the 3D Printing shape picker to the earlier 38.
    assert len(pairs) == 82, len(pairs)
    for b, glyph in pairs:
        assert glyph in ("chev_l", "chev_r")
        im = b.cget("image")
        if isinstance(im, (tuple, list)):
            im = im[0] if im else ""
        assert str(im), "arrow without a drawn glyph"


# ---------------------------------------------------------------------------
# singletons
# ---------------------------------------------------------------------------
def _titled(title):
    return [w for w in ROOT.winfo_children()
            if isinstance(w, tk.Toplevel) and w.winfo_exists()
            and w.title() == title]


@pytest.mark.parametrize("opener,title", [
    ("_open_smooth_panel", "Smoothing settings (Igor 5-step)"),
    ("_about", "About"),
    ("_open_name_format", "Name format"),
    # R9b item 8 dropped 'the math' from every [?] title
    ("_open_interp_info", "Surface interpolation"),
])
def test_second_open_never_spawns_a_twin(a, opener, title):
    with offscreen(a):
        fn = getattr(a, opener)
        fn()
        ROOT.update_idletasks()
        fn()
        ROOT.update_idletasks()
        wins = _titled(title)
        n = len(wins)
        for w in wins:
            try:
                w.grab_release()
            except tk.TclError:
                pass
            w.destroy()
        ROOT.update_idletasks()
        assert n == 1, "%s spawned %d windows" % (opener, n)


def test_formula_editor_singleton_but_duplicate_flow_survives(a):
    with offscreen(a):
        a._quantity_editor(None)
        ROOT.update_idletasks()
        a._quantity_editor(None)
        ROOT.update_idletasks()
        wins = _titled("New formula")
        assert len(wins) == 1
        # the Duplicate flow destroys the window first, so a fresh one
        # must still be allowed through the guard
        wins[0].grab_release()
        wins[0].destroy()
        ROOT.update_idletasks()
        a._quantity_editor(None)
        ROOT.update_idletasks()
        wins = _titled("New formula")
        assert len(wins) == 1
        wins[0].grab_release()
        wins[0].destroy()
        ROOT.update_idletasks()


# ---------------------------------------------------------------------------
# the [?] box
# ---------------------------------------------------------------------------
def test_interp_info_carries_the_math(a):
    with offscreen(a):
        a._open_interp_info()
        ROOT.update_idletasks()
        win = a._interp_info_win
        texts = []

        def _walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Text):
                    texts.append(c)
                _walk(c)
        _walk(win)
        assert texts, "no text body in the [?] window"
        t = texts[0]
        body = t.get("1.0", "end")
        assert "STRAIGHT (LINEAR)" in body
        assert "SMOOTH (MONOTONE CUBIC)" in body
        # The box teaches HOW the two bridges are built. R5 item 4 took
        # the "splines we rejected" section out of it: a guide says what
        # a control does, never why another one is absent.
        assert "STAYED HOME" not in body
        assert "41%" not in body
        assert len(t.image_names()) >= 3 or "z(p)" in body, \
            "typeset formulas or their mono fallback"
        win.destroy()
        ROOT.update_idletasks()


# ---------------------------------------------------------------------------
# guide box styling
# ---------------------------------------------------------------------------
def test_guide_segments_and_tags(a):
    segs = a._ref_segments("Quick start")
    tags = {t for t, _x in segs}
    assert "h" in tags, "headings classified"
    assert tags & {"b", "i"}, "prose classified"
    assert a.ref.tag_cget("h", "foreground"), "heading carries the accent"
    assert "bold" in str(a.ref.tag_cget("h", "font")).lower() or \
        str(a.ref.tag_cget("h", "font")), "heading font set"
    # fallback classifier on a raw block
    fb = a._guide_fallback_segments(
        "SOME HEADING\n\nplain prose line\njoins up\n\n      x = 1\n")
    kinds = [k for k, _t in fb]
    assert kinds[0] == "h" and "m" in kinds and "b" in kinds


def test_my_notes_stays_editable(a):
    prev = a.ref_kind.get()
    a.ref_kind.set("My notes")
    ROOT.update_idletasks()
    assert str(a.ref.cget("state")) == "normal"
    a.ref_kind.set(prev if prev and prev != "My notes" else "Quick start")
    ROOT.update_idletasks()
    assert str(a.ref.cget("state")) == "disabled"
