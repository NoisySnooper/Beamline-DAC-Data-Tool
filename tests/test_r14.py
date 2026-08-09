"""Round R14: the surfaces this round moved, added or renamed.

One lean file for the whole round, in the shape the earlier round files
take (tests/TESTING_POLICY.md rule 5). Each test pins ONE contract and
nothing else, because every one of these was reported by a user:

  - the top bar's Settings dropdown really holds the controls that left
    the bar (app font, text size, helper tips, performance mode, the
    tutorial and About), and it opens and shuts;
  - Detection is a card in the Fringe column again, with its own gates,
    and the Panels row reveals it;
  - the Defringe switch at the head of that column holds the App's own
    ``show_notch``, so the two boxes cannot disagree;
  - the four new 3D switches exist at their measured defaults and are
    remembered;
  - a settings file that says Graphics 'rich' converts to 'best', and so
    does every saved preset;
  - the marked measured traces draw above the sheet;
  - the workbench pop-out can fill the screen.

Nothing here is ever visible: the Settings panel is a Toplevel the app
positions for itself, so the one test that opens it builds it fully
transparent (rule: the GUI is never visible during a test run).
"""
import contextlib

import pytest

import app
import export3d
import fringe_panel
import fringe_popout
import ui_prefs
from conftest import ROOT, by_text, gui, shared_app, walk

USES_APP = True
pytestmark = gui


@pytest.fixture(scope="module")
def a():
    return shared_app()


@contextlib.contextmanager
def ghost():
    """Build every Toplevel of the block fully transparent.

    ``conftest.offscreen`` parks a window at +3200+100, but the Settings
    panel sets its own position under the gear and clamps that to the
    monitor, so parking it is not enough. Alpha 0 is.
    """
    import tkinter as tk
    orig = tk.Toplevel

    class _Ghost(orig):
        def __init__(self, *args, **kw):
            orig.__init__(self, *args, **kw)
            try:
                self.attributes("-alpha", 0.0)
            except tk.TclError:
                pass

    tk.Toplevel = _Ghost
    try:
        yield
    finally:
        tk.Toplevel = orig


# ---------------------------------------------------------------------------
# A3: the top bar's Settings dropdown
# ---------------------------------------------------------------------------
def test_settings_dropdown_holds_the_controls_that_left_the_bar(a):
    assert a._settings_gear_btn.winfo_exists()
    assert not a._settings_menu_open()
    with ghost():
        a._toggle_settings_menu()
        ROOT.update_idletasks()
        assert a._settings_menu_open()
        win = a._settings_win
        try:
            for label in ("Settings", "Font", "Text size", "Helper tips",
                          "Performance mode", "Tutorial", "About"):
                assert by_text(win, label) is not None, label
            # the widgets are the app's own, on the app's own variables
            assert a._app_font_cb.cget("textvariable") == str(a.app_font)
            assert a._ui_size_cb.cget("textvariable") == str(a._ui_size_pick)
            switches = [w for w in walk(win)
                        if w.winfo_class() == "TCheckbutton"]
            held = {str(w.cget("variable")) for w in switches}
            assert str(a.tooltips_on) in held
            assert str(a.app_perf_mode) in held
        finally:
            a._toggle_settings_menu()
    ROOT.update_idletasks()
    assert not a._settings_menu_open()
    # and the moved controls left no widget behind on the bar
    assert not a._ui_size_cb.winfo_exists()


# ---------------------------------------------------------------------------
# B1 / B2: the Detection card and the Defringe switch
# ---------------------------------------------------------------------------
def test_detection_is_a_card_again_and_panels_reveals_it(a):
    fw = a._fringe
    fw.build()
    assert "Detection" in fringe_panel.FRINGE_SECTIONS
    rec = next((r for r in a._collapsibles if r["key"] == "Detection"), None)
    assert rec is not None, "Detection is not a collapsible card"
    assert rec["cat"] == "Fringe"
    # it sits above FFT removal in the column
    order = [r["key"] for r in a._collapsibles if r["cat"] == "Fringe"]
    assert order.index("Detection") < order.index("FFT removal")
    # its gates are the panel's own variables
    for var in ("wlmin_v", "wlmax_v", "ntmin_v", "ntmax_v", "pmax_v",
                "tol_v", "suppress_v"):
        assert getattr(fw, var, None) is not None, var
    for cap in ("Window (nm)", "n*t band (um)", "Fisher p", "Agree tol"):
        assert by_text(rec["body"], cap) is not None, cap
    assert set(fw._rep) == {"nt", "p", "corr"}
    # the Panels row opens the card rather than a window
    was = len(ROOT.winfo_children())
    a._set_collapsed(rec, True)
    assert fw._open_detection() is rec["cont"]
    ROOT.update_idletasks()
    assert not rec["collapsed"]
    assert len(ROOT.winfo_children()) == was, "a window opened"


def test_the_defringe_switch_is_the_apps_own_variable(a):
    fw = a._fringe
    fw.build()
    assert fw._df_cb.winfo_exists()
    assert str(fw._df_cb.cget("variable")) == str(a.show_notch)
    assert fw._df_cb.cget("text") == "Defringe (df)"


# ---------------------------------------------------------------------------
# C: the 3D switches, the Graphics rename, the ridge lines
# ---------------------------------------------------------------------------
def test_the_new_3d_switches_default_and_are_remembered(a):
    reg = a._preset_registry()
    wanted = {"wf3d_aa": False, "wf3d_draft_orbit": True,
              "wf3d_grid_mesh": False,
              "wf3d_relief_strength": export3d.DEFAULT_RELIEF}
    for key, want in wanted.items():
        var = getattr(a, key, None)
        assert var is not None, key
        assert key in reg, key
        assert a._defaults[key] == want, key
        assert var.get() == want, key
    keep = a.settings.get("wf3d_grid_mesh")
    try:
        a.wf3d_grid_mesh.set(True)
        a._wf3d_store_opt("wf3d_grid_mesh", a.wf3d_grid_mesh)
        assert a.settings["wf3d_grid_mesh"] is True
    finally:
        a.wf3d_grid_mesh.set(False)
        if keep is None:
            a.settings.pop("wf3d_grid_mesh", None)
        else:
            a.settings["wf3d_grid_mesh"] = keep


def test_graphics_rich_becomes_best_in_settings_and_in_a_preset(a):
    assert app.App.GFX_ORDER[-1] == "best"
    assert "rich" not in app.App.GFX_ORDER
    assert app.App.GFX_RENAMED == {"rich": "best"}
    keep = dict(a.settings)
    try:
        a.settings["wf3d_graphics"] = "rich"
        a.settings["presets"] = {"MyOld3D": {"wf3d_graphics": "rich"},
                                 "Fine": {"wf3d_graphics": "high"}}
        a._migrate_settings()
        assert a.settings["wf3d_graphics"] == "best"
        assert a.settings["presets"]["MyOld3D"]["wf3d_graphics"] == "best"
        assert a.settings["presets"]["Fine"]["wf3d_graphics"] == "high"
        assert any("best" in line for line in a._gfx_migrated)
    finally:
        a.settings.clear()
        a.settings.update(keep)


def test_the_marked_traces_draw_above_the_sheet():
    # mplot3d leaves a Line3D out of its collection depth sort, so the
    # lines are pinned above every polygon of the surface (R14 item C).
    assert app.App.WF3D_RIDGE_Z == 100
    src = app.App._surface_marked_ridges.__doc__ or ""
    assert "WF3D_RIDGE_Z" in src
    import inspect
    body = inspect.getsource(app.App._surface_marked_ridges)
    assert "set_zorder(self.WF3D_RIDGE_Z)" in body


# ---------------------------------------------------------------------------
# B3: the pop-out fills the screen
# ---------------------------------------------------------------------------
def test_the_popout_can_fill_the_screen():
    assert callable(getattr(fringe_popout.MatthewWindow,
                            "toggle_fullscreen", None))
    tips = fringe_popout.TIPS
    assert "F11" in tips["full_on"]
    assert "F11" in tips["full_off"] and "Escape" in tips["full_off"]


# ---------------------------------------------------------------------------
# the guided tour covers the round
# ---------------------------------------------------------------------------
def test_the_tour_teaches_every_r14_surface():
    import guide_tour
    keys = [s.key for s in guide_tour.TOUR_STEPS]
    for key in ("settings", "settings_rows", "fringe_df", "fringe_detect",
                "surface3d_look"):
        assert key in keys, key
    assert "advanced" not in keys
    assert not hasattr(guide_tour, "open_adv")
    assert guide_tour.SETTINGS_STEPS == frozenset(("settings",
                                                   "settings_rows"))
    # ui_prefs no longer carries the tier table the removed step read
    assert not hasattr(ui_prefs, "SECTION_TIERS")
