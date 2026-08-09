"""guide_tour.py: the welcome card, the guided tour, and the honesty gate.

A new feature area in v1.4.9 (Phase D2).  What is locked here is the DATA
the tour and the guide are built from, because that is what silently rots
when a control is renamed:

  - the settings keys the module owns, and the one that decides whether a
    first run shows the welcome card;
  - every tour step: unique key, real words, and a target that still
    RESOLVES on the live window -- a step pointing at a control that no
    longer exists is a spotlight on empty chrome;
  - the honesty gate is FALSIFIABLE.  `--selftest` asserts it passes; that
    proves nothing unless a renamed section can be shown to fail it, so the
    negative case is asserted here instead of trusted.

Runs against the suite's ONE shared App (tests/conftest.py); no Toplevel
here is ever mapped on the visible desktop.
"""
import pytest

import app
import guide_tour
from conftest import ROOT, close_toplevels, gui, offscreen, shared_app

USES_APP = True
pytestmark = gui


@pytest.fixture(scope="module")
def a():
    return shared_app()


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------
def test_the_welcome_card_is_first_run_only_and_owns_its_settings_key(a):
    """One key decides it, the App defaults it, and 'Don't show this again'
    is the only thing that flips it."""
    assert set(guide_tour.D2_SETTINGS_DEFAULTS) == {"welcome_seen",
                                                    "tour_done"}
    assert guide_tour.D2_SETTINGS_DEFAULTS["welcome_seen"] is False
    assert "welcome_seen" in a.settings and "tour_done" in a.settings

    was = a.settings.get("welcome_seen")
    try:
        a.settings["welcome_seen"] = True
        assert guide_tour.maybe_show_welcome(a) is None, \
            "a returning user must never see the welcome card again"

        a.settings["welcome_seen"] = False
        with offscreen(a):
            win = guide_tour.maybe_show_welcome(a)
            ROOT.update_idletasks()
            assert win is not None and win.winfo_exists()
            # house law: every real dialog answers Escape (DESIGN_RULES #2)
            assert win.bind("<Escape>")
            win.destroy()
    finally:
        a.settings["welcome_seen"] = was
        close_toplevels()


# ---------------------------------------------------------------------------
# the tour
# ---------------------------------------------------------------------------
def test_every_tour_step_has_words_and_a_target_that_still_resolves(a):
    """The whole path in one walk: the steps are well formed, and each one
    that points at a control can still find it on the live window."""
    steps = guide_tour.TOUR_STEPS
    assert len(steps) >= 10
    keys = [s.key for s in steps]
    assert len(set(keys)) == len(keys), "step keys are identifiers"
    assert keys[0] == "welcome" and keys[-1] == "finish"

    for s in steps:
        assert s.title.strip(), s.key
        assert len(s.body.strip()) > 40, s.key
        # peer voice: a step is not allowed to shout or to ask itself a
        # question it then answers (DESIGN_RULES #38, #39)
        assert not s.title.endswith("?"), s.key
        if s.wait is not None:
            assert s.wait_hint.strip(), "a waiting step must say what for"

    # a target is one widget or a span of them (`guide_tour.span_from`), and
    # either way every widget in it has to still be alive: the spotlight is
    # cut from their union rectangle
    unresolved = []
    for s in steps:
        if s.target is None:
            continue
        try:
            got = s.target(a)
        except Exception as exc:                      # noqa: BLE001
            unresolved.append("%s: raised %r" % (s.key, exc))
            continue
        if got is None:
            unresolved.append("%s: target resolved to None" % s.key)
            continue
        ws = list(got) if isinstance(got, (list, tuple)) else [got]
        if not ws:
            unresolved.append("%s: target resolved to an empty span" % s.key)
        for w in ws:
            if not guide_tour._alive(w):
                unresolved.append("%s: %r is not a live widget" % (s.key, w))
    assert not unresolved, unresolved


def test_the_tour_can_be_started_and_left_without_leaving_chrome_behind(a):
    """Esc is the exit, and it has to take the scrim and the card with it:
    an overrideredirect Toplevel left standing would sit over the app with
    no way to close it."""
    before = {str(w) for w in ROOT.winfo_children()}
    with offscreen(a):
        tour = guide_tour.start_tour(a)
        ROOT.update_idletasks()
        assert tour is not None
        tour.stop()
        ROOT.update_idletasks()
    left = [str(w) for w in ROOT.winfo_children() if str(w) not in before]
    close_toplevels()
    assert not left, "the tour left %r behind" % left
    assert not ROOT.grab_current(), "the tour left a grab set"


# ---------------------------------------------------------------------------
# the honesty gate
# ---------------------------------------------------------------------------
def test_the_gate_passes_today(a):
    assert guide_tour.bad_headings(a, app.PANEL_GUIDE) == []


def test_the_gate_really_fails_when_a_live_section_is_renamed(a):
    """The falsification `--selftest` cannot do for itself.

    Rename the Fringe tab's "FFT removal" section the way a careless edit
    would and the gated view that documents it must be REPORTED --
    otherwise the gate is decorative and every guide heading could be
    stale.  (This was the "Notches" card before the R7 workbench rebuild
    regrouped the sidebar; the point of the test is unchanged.)
    """
    live = "FFT removal"
    rec = next(r for r in a._collapsibles if r["key"] == live)
    cat = a._section_cat[live]
    try:
        rec["key"] = "Notch list"
        del a._section_cat[live]
        a._section_cat["Notch list"] = cat
        bad = guide_tour.bad_headings(a, app.PANEL_GUIDE)
        assert "30_fringe_workbench.md: FRINGE > FFT REMOVAL" in bad, bad
    finally:
        rec["key"] = live
        a._section_cat.pop("Notch list", None)
        a._section_cat[live] = cat
    assert guide_tour.bad_headings(a, app.PANEL_GUIDE) == []


def test_every_gated_guide_view_is_live_and_readable():
    """A view the dropdown offers must have real text behind it, and a
    gated one must name sections -- the two halves of 'the guide is the
    index you can look a control up in'."""
    import os

    man = guide_tour.load_manifest()
    assert man is not None, "docs/guide_content/manifest.json must ship"
    views = guide_tour.guide_views(app.REF_VIEWS)
    assert len(views) >= 10
    for name, text in views.items():
        assert text and text.strip(), name
    for e in man.get("views", []):
        assert e.get("gate") in ("exempt", "section_headings"), e
        if not e.get("file"):
            continue
        if guide_tour._view_is_live(e):
            text = guide_tour._read_text(
                os.path.join(guide_tour.GUIDE_DIR, e["file"]))
            assert text and len(text) > 200, e["file"]
