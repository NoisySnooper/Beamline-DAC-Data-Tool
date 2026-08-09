"""v1.4.9 W1c: the App font (which replaced the Dyslexic themes in
R9a), the Quick Access customizer, the collapse-all section reorder,
and the demo series' three-role physics.

Per TESTING_POLICY: the GUI tests ride the ONE shared App and avoid the
expensive full theme switch (the W1c probe scripts covered the style-font
pass end to end); what is asserted here is the contract each feature
must keep."""
import types

import pytest

import app
import fringe_optics
import ui_prefs
import make_demo_data as mk
from conftest import ROOT, gui, shared_app

USES_APP = True
pytestmark = gui


@pytest.fixture(scope="module")
def a():
    return shared_app()


# ---------------------------------------------------------------------------
# App font (R9a: the Dyslexic themes retired into this control)
# ---------------------------------------------------------------------------
def test_dyslexic_themes_are_gone(a):
    for th in ui_prefs.RETIRED_THEMES:
        assert th not in app.THEME_LABELS
        assert th not in a._themes()
    assert app.THEME_FUNCTIONAL == 6


def test_colorblind_dark_theme_rows_resolve(a):
    keep = a.theme_mode.get()
    try:
        a.theme_mode.set("colorblinddark")
        assert "colorblinddark" in app.THEME_LABELS
        assert a._themes()["colorblinddark"]["base"] == "dark"
        assert set(a._brand()) >= {"ac1", "ac2", "ac3", "ink", "hov"}
        ubg, fg, fld, _pb, _pf = a._theme_palette()
        assert ubg != fld
        assert a._section_palette() is not None
    finally:
        a.theme_mode.set(keep)


def test_app_font_switches_the_face_and_reverts(a):
    keep = a.app_font.get()
    try:
        a.app_font.set("OpenDyslexic")
        assert a._dys_on()
        assert a._ui_faces()[0] == app.DYS_FONT
    finally:
        a.app_font.set(keep)
    assert not a._dys_on()
    assert a._ui_faces()[0] == app.UI_FONT


def test_retired_theme_migrates_to_a_font(a):
    for old, (new_theme, new_font) in ui_prefs.RETIRED_THEMES.items():
        assert ui_prefs.live_theme(old) == new_theme
        assert new_theme in a._themes() or new_theme in (
            "light", "white", "dark", "black")
        assert new_font == "OpenDyslexic"
        assert ui_prefs.retired_note(old)


def test_dyslexic_font_resolved_on_this_machine():
    # fonts/ ships OpenDyslexic; the fallback is Comic Sans MS - either
    # way the face must be a real family name, never empty
    assert app.DYS_FONT in ("OpenDyslexic", "Comic Sans MS")


def test_the_advanced_tier_split_is_gone(a):
    """R14 reversed R9a: every row of every section is visible again.

    The two W1c tests this replaces asserted the tier table resolved and
    that at least eight folds were built. Nhan's ruling was "run it
    back, no restyling", so what is pinned now is the ABSENCE of the
    machinery: the table, the App methods that read it, the per-section
    records it wrote, and the settings key it saved."""
    for name in ("SECTION_TIERS", "ADV_TITLE", "ADV_KEY", "SIMPLE",
                 "ADVANCED", "tier_names"):
        assert not hasattr(ui_prefs, name), name
    for name in ("_set_adv", "_toggle_adv", "_apply_tiers", "_row_name",
                 "_build_adv_fold", "_adv_state", "_ROW_SKIP"):
        assert not hasattr(app.App, name), name
    for rec in a._collapsibles:
        for key in ("adv_hdr", "adv_rows", "adv_open", "adv_sep"):
            assert key not in rec, (rec["key"], key)
    assert "adv_collapsed" not in a.settings
    # section-level collapse is untouched by the reversal
    assert all("collapsed" in r for r in a._collapsibles)


# ---------------------------------------------------------------------------
# Quick Access customizer
# ---------------------------------------------------------------------------
def test_qa_visible_rebuild_and_reset(a):
    keep = list(a._qa_visible())
    try:
        a._qa_apply_visible(["legend", "cbar"])
        ROOT.update_idletasks()
        texts = []

        def walk(w):
            for c in w.winfo_children():
                try:
                    t = str(c.cget("text"))
                    if t:
                        texts.append(t)
                except Exception:
                    pass
                walk(c)
        walk(a._qa_wrap)
        assert "legend" in texts and "cbar" in texts
        assert "wf" not in texts and "cmap" not in texts
        assert a._qa_gear_btn.winfo_exists()
        # registries must hold no corpses after a rebuild
        assert all(c.winfo_exists() for c in a._ydata_combos)
        assert all(b.winfo_exists() for b, _g in a._combo_arrow_btns)
        # empty strip collapses to the hint + the gear
        a._qa_apply_visible([])
        ROOT.update_idletasks()
        assert a._qa_gear_btn.winfo_exists()
    finally:
        a._qa_apply_visible(keep)
    assert set(a._qa_visible()) == set(keep)


def test_qa_default_is_the_v148_strip():
    assert app.App.QA_DEFAULT == ("wf", "sm", "df", "lw", "cmap",
                                  "theme_bg", "yaxis", "xaxis")
    known = {k for k, _l, _d in app.App.QA_ITEMS}
    assert set(app.App.QA_DEFAULT) <= known


# ---------------------------------------------------------------------------
# Collapse-all section reorder
# ---------------------------------------------------------------------------
def test_section_drag_reorders_persists_and_click_still_toggles(a):
    keep_order = dict(a.settings.get("section_order") or {})
    keep_collapsed = {r["key"]: r["collapsed"] for r in a._collapsibles}
    try:
        rec = next(r for r in a._collapsibles if r["key"] == "Smoothing")
        # a plain click (press + release, no motion) still toggles
        was = rec["collapsed"]
        ev = types.SimpleNamespace(y_root=400)
        a._sec_press(rec, ev)
        a._sec_release(rec, ev)
        assert rec["collapsed"] != was
        # expanded tab: motion never goes live
        a._collapse_all(False)
        a._sec_press(rec, types.SimpleNamespace(y_root=400))
        a._sec_motion(rec, types.SimpleNamespace(y_root=460))
        assert not (a._sec_drag and a._sec_drag.get("live"))
        a._sec_release(rec, types.SimpleNamespace(y_root=460))
        # collapse-all: the same gesture reorders and persists
        a._collapse_all(True)
        ROOT.update_idletasks()
        y0 = rec["cont"].winfo_rooty()
        a._sec_press(rec, types.SimpleNamespace(y_root=y0 + 2))
        a._sec_motion(rec, types.SimpleNamespace(y_root=y0 + 30))
        assert a._sec_drag and a._sec_drag["live"]
        end = next(r for r in a._collapsibles if r["key"] == "Formulas")
        y1 = end["cont"].winfo_rooty() + end["cont"].winfo_height() + 4
        a._sec_release(rec, types.SimpleNamespace(y_root=y1))
        order = [r["key"] for r in a._sec_order_now("Data")]
        assert order[-1] == "Smoothing", order
        assert a.settings["section_order"]["Data"] == order
    finally:
        a.settings["section_order"] = keep_order
        a._reorder_sections()
        for r in a._collapsibles:
            a._set_collapsed(r, keep_collapsed[r["key"]])
        a._all_collapsed = False
        a._sync_collapse_btn()
        a._heal_tab_scroll()


def test_reorder_honors_saved_order_and_unknown_keys(a):
    keep = dict(a.settings.get("section_order") or {})
    try:
        a.settings["section_order"] = {"Data": ["Formulas", "Traces"]}
        a._reorder_sections()
        ROOT.update_idletasks()
        order = [r["key"] for r in a._sec_order_now("Data")]
        # saved keys lead in saved order; the key the saved list never
        # met (Smoothing) keeps a slot after them instead of vanishing
        assert order == ["Formulas", "Traces", "Smoothing"], order
    finally:
        a.settings["section_order"] = keep
        a._reorder_sections()
        a._heal_tab_scroll()


# ---------------------------------------------------------------------------
# Demo series: three-role solvability (pure, no GUI)
# ---------------------------------------------------------------------------
def test_demo_cell_paths_solve_clamp_free_to_ground_truth():
    for _tok, pval, branch in mk.POINTS:
        c = mk.cell_paths(pval, branch)
        sol = fringe_optics.solve_paths(c["A"], c["C"], c["iii"],
                                        c["n_ar"], c["n_ar"])
        assert sol is not None and not sol["warns"], (pval, sol)
        assert abs(sol["n_s"] - mk.N_SAMPLE) < 1e-9
        assert abs(sol["t_s"] - c["t"]) < 1e-9
        assert abs(sol["L"] - c["L"]) < 1e-9
        # the roles keep the order the Shared fit guarantees
        assert c["A"] < c["C"] and c["iii"] < c["C"]
