"""Round R6b: the workbench's split policy, grab priority and file destination.

Each test pins one finding from the v1.4.9 usability probe:

  - B1  the centre split gave the FFT canvas 160 px at 1400x860;
  - B3  the pop-out was finished and unreachable;
  - F6  Save series wrote into the bundled demo folder, i.e. the install dir;
  - F7  the empty workbench recited the mouse grammar over an empty plot;
  - F13 the results window opened 1480x840 whatever the screen;
  - F15 a role glyph lost its grab to the peak it was standing on;
  - P1  tight_layout wrote a UserWarning to stdout on every redraw;
  - P3  the Solve button's label carried a leading space.

Runs against the suite's ONE shared App (tests/conftest.py).  Nothing here
computes an FFT: the split, the destination and the grab priority are all
decided from geometry and state.
"""
import os
import warnings

import pytest

import fringe_panel
from conftest import gui, make_result, shared_app

USES_APP = True
pytestmark = gui


@pytest.fixture(scope="module")
def a():
    return shared_app()


@pytest.fixture
def fw(a):
    """The built workbench, with its split state put back afterwards."""
    w = a._fringe
    w.build()
    keep = (w._guide_fit, w.settings.get("fr_guide_w"),
            w.settings.get("fr_guide_open"), dict(w._trace), w._label,
            list(a.results))
    yield w
    w._guide_fit = keep[0]
    w.settings["fr_guide_w"] = keep[1]
    w.settings["fr_guide_open"] = keep[2]
    w._trace.clear()
    w._trace.update(keep[3])
    w._label = keep[4]
    a.results = keep[5]


# ---------------------------------------------------------------------------
# B1 -- the plot is the protagonist
# ---------------------------------------------------------------------------
def test_split_never_takes_the_plot_below_its_floor(fw):
    """The guide may have the remainder and not one pixel more."""
    em = fw.app._em()
    assert fw._plot_floor() == em * fringe_panel.PLOT_MIN_W
    assert fw._guide_floor() == em * fringe_panel.GUIDE_MIN_W

    fw._guide_fit = "auto"
    for total in (436, 636, 956, 960, 1400, 2000):
        want = fw._guide_w_want(total)
        assert total - want >= min(fw._plot_floor(), total), \
            "a %d px centre left the plot %d px" % (total, total - want)

    # a width the reader dragged is honoured up TO that floor, not past it
    fw.settings["fr_guide_w"] = 1200
    assert fw._guide_w_want(1400) == 1400 - fw._plot_floor()
    fw.settings["fr_guide_w"] = 400
    assert fw._guide_w_want(1400) == 400, "a split that fits is left alone"


def test_both_floors_or_the_guide_stands_down(fw):
    """The four sizes the probe measured, decided the same way the fitter
    decides them."""
    fw._guide_fit = "auto"
    floors = fw._plot_floor() + fw._guide_floor()
    seen = {}
    for window, centre in ((1400, 436), (1600, 636), (1920, 956),
                           (2560, 960)):
        seen[window] = fw._guide_fits(centre)
        assert seen[window] == (centre >= floors)
    assert not seen[1400] and not seen[1600], "the narrow pair stand down"
    assert seen[1920] and seen[2560], "the wide pair hold both"
    assert fw._guide_fits(0), "a pane with no width yet is not a verdict"


def test_forced_is_the_one_way_past_the_floor(fw):
    """Pressing Guide on a snug pane is the reader overruling the fitter."""
    fw.settings["fr_guide_w"] = 0
    fw._guide_fit = "auto"
    auto = fw._guide_w_want(436)
    fw._guide_fit = "forced"
    forced = fw._guide_w_want(436)
    assert forced == fw._guide_floor() > auto


def test_a_dragged_width_is_remembered_not_only_on_the_way_out(fw):
    """fr_guide_w sat at 0 for good, because only hide and deactivate ever
    wrote it.  The pane's own button release writes it now."""
    binds = fw._center_pw.bind()
    assert "<ButtonRelease-1>" in binds
    assert "<Configure>" in binds


# ---------------------------------------------------------------------------
# B3 -- the pop-out has a way in
# ---------------------------------------------------------------------------
def test_the_view_switch_carries_a_tear_off(fw):
    was = fw._active
    fw._active = True                      # the row only exists in this view
    try:
        fw.sync_view_switch()
        assert "popout" in fw._switch_lbls
        assert fw._switch_lbls["popout"].cget("text").strip() == "Pop out"
    finally:
        fw._active = was
        fw.sync_view_switch()


# ---------------------------------------------------------------------------
# F6 -- where Save series writes
# ---------------------------------------------------------------------------
def test_the_bundled_demo_folder_is_never_written_into(fw, tmp_path):
    here = os.path.dirname(os.path.abspath(fringe_panel.__file__))
    assert fw._under_program(os.path.join(here, "demo_data"))
    assert fw._under_program(here)
    assert not fw._under_program(str(tmp_path))

    keep = fw.app.in_var.get(), fw.app.out_var.get()
    try:
        fw.app.in_var.set(os.path.join(here, "demo_data"))
        fw.app.out_var.set(str(tmp_path))
        dest, why = fw._series_dest()
        assert dest == str(tmp_path)
        assert why and "output folder" in why

        # a folder of the reader's own keeps Matthew's beside-the-data rule
        src = tmp_path / "spectra"
        src.mkdir()
        fw._wr_cache.clear()
        fw.app.in_var.set(str(src))
        dest, why = fw._series_dest()
        assert dest == str(src) and why is None
        # and load looks there as well as at the destination
        assert str(src) in " ".join(fw._series_read_paths())
    finally:
        fw.app.in_var.set(keep[0])
        fw.app.out_var.set(keep[1])
        fw._wr_cache.clear()


# ---------------------------------------------------------------------------
# F7 -- an empty workbench says something true
# ---------------------------------------------------------------------------
def test_the_mouse_grammar_waits_for_data(a, fw):
    keep = list(a.results)
    try:
        a.results = []
        assert fw._hint_text() == fw.HINT_EMPTY
        a.results = [make_result("R1", 1.0)]
        assert fw._hint_text() == fw.HINT_DEFAULT
    finally:
        a.results = keep
    assert "top" in fw.HINT_DEFAULT, "the glyphs live along the top; say so"


# ---------------------------------------------------------------------------
# F13 -- no window bigger than the screen it opens on
# ---------------------------------------------------------------------------
def test_a_window_is_capped_at_a_share_of_the_screen(fw):
    sw, sh = fw._screen_cap()
    w, h = fw._dlg_size(10 ** 4, 10 ** 4)
    assert (w, h) == (sw, sh)
    assert fw._dlg_size(1, 1) == (fw.app._em(), fw.app._em())

    class _Win(object):
        geom = None

        def geometry(self, g):
            self.geom = g

    win = _Win()
    fw._clamp_geometry(win, "%dx%d+40+40" % (sw * 4, sh * 4))
    assert win.geom == "%dx%d+40+40" % (sw, sh)
    fw._clamp_geometry(win, "300x200+10+10")
    assert win.geom == "300x200+10+10", "a size that fits is left alone"


# ---------------------------------------------------------------------------
# F15 -- a glyph wins the press it is standing under
# ---------------------------------------------------------------------------
def test_a_glyph_within_reach_beats_the_notch_toggle(a, fw):
    """The glyph sits ON its peak, so the old "nearest thing wins" test
    handed the press to the very marker the glyph was standing on."""
    assert fringe_panel.ROLE_GRAB_DY > 0.25, "the band was widened"

    a.results = [make_result("R1", 1.0)]
    fw._label = "R1"
    tr = fw._tr()
    tr["roles"]["sample"] = {"nt_um": 32.0, "auto": False}
    ax = fw._axes["Sample"]
    ax.set_xlim(0.0, 100.0)
    ax.set_ylim(0.0, 1.0)
    fw._peak_xy["Sample"] = [(32.0, 0.5)]

    class _Ev(object):
        def __init__(self, yfrac, xdata):
            self.inaxes = ax
            self.xdata = xdata
            self.button = 1
            self.x = ax.transData.transform((xdata, 0.0))[0]
            self.y = ax.transAxes.transform((0.0, yfrac))[1]

    kind, role = fw._grab_at("Sample", 32.0, _Ev(0.94, 32.0))
    assert (kind, role) == ("role", "sample")
    # and well down the panel, where the probe collected three notches
    kind, role = fw._grab_at("Sample", 32.0, _Ev(0.70, 32.0))
    assert (kind, role) == ("role", "sample"), \
        "a press below the glyph fell through to the notch toggle"
    # far from any glyph the press is still a notch click
    assert fw._grab_at("Sample", 80.0, _Ev(0.94, 80.0))[0] is None


# ---------------------------------------------------------------------------
# P1 / P3 -- the quiet ones
# ---------------------------------------------------------------------------
def test_tight_layout_keeps_its_complaints_to_itself(fw):
    """A figure too small for its margins used to say so on stdout once per
    redraw; a warning from anywhere else still has to get through."""
    from matplotlib.figure import Figure
    fig = Figure(figsize=(0.4, 0.4))
    fig.add_subplot(211)
    fig.add_subplot(212)
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        fw._tight(fig, pad=1.4, h_pad=2.4)
    assert not [w for w in got if "layout" in str(w.message).lower()]

    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        fw._tight(fig, pad=1.4)
        warnings.warn("something else entirely", UserWarning)
    assert len(got) == 1


def test_the_workbench_buttons_carry_no_stray_leading_space(fw):
    from conftest import walk
    # R7: the workbench's brand buttons are Plot point (record) and
    # Compute fits (the intensity fitters)
    labels = [w.cget("text") for w in walk(fw.app.root)
              if getattr(w, "_tier", None) is not None
              and str(w.cget("text")).strip() in ("Plot point",
                                                  "Compute fits")]
    assert labels, "the two workbench brand buttons were not found"
    assert all(t == t.strip() for t in labels), labels
