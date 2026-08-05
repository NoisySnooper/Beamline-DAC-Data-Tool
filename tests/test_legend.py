"""
Legend ordering / dedup / channel-tag tests for App._ordered_legend.

Locks the v1.2.2 fix that collapsed nine identical "0.00 GPa - C" entries
into distinct, tagged labels. Needs a Tk display, so the whole module skips
cleanly on a headless box (the lab Windows machine has one).
"""
import numpy as np
import pytest

try:
    import tkinter as tk
    # Reuse an existing default root if another GUI test module already made
    # one: this Windows Store Python cannot spin up a SECOND independent Tk()
    # interpreter (see test_sessions.py). Without this the whole module
    # silently skipped whenever it was not the FIRST GUI module imported.
    _root = tk._default_root or tk.Tk()
    _root.withdraw()
    import app
    _APP = app.App(_root)
    _HAVE_GUI = True
except Exception:                      # no display, or Tk missing
    _HAVE_GUI = False

pytestmark = pytest.mark.skipif(not _HAVE_GUI, reason="no Tk display")


def _raw(sample, ch):
    """A raw-only result dict: only one finite channel, absorbance all-NaN."""
    nan = np.full(4, np.nan)
    fin = np.ones(4)
    return {"sample": sample, "absorbance": nan,
            "samp_c": fin if ch == "s" else nan,
            "bg_c": fin if ch == "b" else nan,
            "dark_c": fin if ch == "d" else nan}


def _full(sample):
    fin = np.ones(4)
    return {"sample": sample, "absorbance": fin,
            "samp_c": fin, "bg_c": fin, "dark_c": fin}


def _labels(entries):
    return _APP._ordered_legend(entries)[1]


def test_same_pressure_raw_disambiguated_by_sample():
    e = [(1, 0.0, "C", _raw("gasket2", "b")),
         (2, 0.0, "C", _raw("gasket3", "b")),
         (3, 0.1, "C", _full("gasket"))]
    assert _labels(e) == ["0.00 GPa - C [B only]  gasket2",
                          "0.00 GPa - C [B only]  gasket3",
                          "0.10 GPa - C"]


def test_exact_duplicates_collapse():
    r = _raw("gasket2", "b")
    e = [(1, 0.0, "C", r), (2, 0.0, "C", r), (3, 0.1, "C", _full("gasket"))]
    assert _labels(e) == ["0.00 GPa - C [B only]  gasket2", "0.10 GPa - C"]


def test_three_tuple_backward_compatible():
    e = [(1, 0.5, "C"), (2, 1.0, "D")]
    assert _labels(e) == ["0.50 GPa - C", "1.00 GPa - D"]


# ------------------------------------ v1.4.8: legend branch-tag controls ---
# Display only: the internal branch keys, the D-list files, the C/D-tagged
# CSV export letters and filename parsing all stay exactly C / D.
@pytest.fixture(autouse=True)
def _default_branch_controls():
    """Every test in this module starts from the shipped defaults."""
    for var, val in ((_APP.legend_branch_tags, True),
                     (_APP.legend_branch_c, "C"),
                     (_APP.legend_branch_d, "D")):
        var.set(val)
    yield
    for var, val in ((_APP.legend_branch_tags, True),
                     (_APP.legend_branch_c, "C"),
                     (_APP.legend_branch_d, "D")):
        var.set(val)


def test_default_branch_suffix_is_unchanged():
    """The shipped rendering is the contract."""
    assert _labels([(1, 0.5, "C"), (2, 1.0, "D")]) == ["0.50 GPa - C",
                                                       "1.00 GPa - D"]


def test_branch_tags_off_drops_the_suffix():
    _APP.legend_branch_tags.set(False)
    assert _labels([(1, 0.5, "C"), (2, 1.0, "D")]) == ["0.50 GPa",
                                                       "1.00 GPa"]
    # and the ordering is untouched: C ascending, then D descending
    assert _labels([(1, 2.0, "D"), (2, 0.5, "C"), (3, 4.0, "D")]) == \
        ["0.50 GPa", "4.00 GPa", "2.00 GPa"]


def test_custom_branch_labels_appear_in_the_legend():
    _APP.legend_branch_c.set("heat")
    _APP.legend_branch_d.set("cool")
    assert _labels([(1, 0.5, "C"), (2, 1.0, "D")]) == ["0.50 GPa - heat",
                                                       "1.00 GPa - cool"]
    # a blank box falls back to the canonical letter
    _APP.legend_branch_c.set("   ")
    assert _labels([(1, 0.5, "C")]) == ["0.50 GPa - C"]


def test_custom_branch_labels_do_not_reorder_anything():
    """The words are cosmetic; sorting still keys off the real C / D."""
    _APP.legend_branch_c.set("cool")      # deliberately swapped wording
    _APP.legend_branch_d.set("heat")
    assert _labels([(1, 2.0, "D"), (2, 0.5, "C"), (3, 1.0, "C")]) == \
        ["0.50 GPa - cool", "1.00 GPa - cool", "2.00 GPa - heat"]


def test_branch_controls_round_trip_through_the_preset_registry():
    a = _APP
    reg = a._preset_registry()
    for k in ("legend_branch_tags", "legend_branch_c", "legend_branch_d"):
        assert k in reg, k
        assert k in a._defaults, k
    a.legend_branch_tags.set(False)
    a.legend_branch_c.set("inc")
    a.legend_branch_d.set("dec")
    saved = {k: v.get() for k, v in a._preset_registry().items()}

    a._apply_preset_data(dict(a._defaults))             # wander off
    assert a.legend_branch_tags.get() is True
    assert (a.legend_branch_c.get(), a.legend_branch_d.get()) == ("C", "D")

    a._apply_preset_data(saved)                         # and come back
    assert a.legend_branch_tags.get() is False
    assert (a.legend_branch_c.get(), a.legend_branch_d.get()) == ("inc", "dec")
    a._apply_preset_data(dict(a._defaults))
    assert _labels([(1, 0.5, "C")]) == ["0.50 GPa - C"]


def test_legacy_preset_without_the_branch_keys_keeps_the_defaults():
    a = _APP
    a._apply_preset_data({"cmap": "magma", "legend_on": True})
    assert a.legend_branch_tags.get() is True
    assert _labels([(1, 0.5, "D")]) == ["0.50 GPa - D"]
