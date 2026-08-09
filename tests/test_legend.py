"""
Legend ordering / dedup / channel-tag tests for App._ordered_legend.

Locks the v1.2.2 fix that collapsed nine identical "0.00 GPa - C" entries
into distinct, tagged labels, and the v1.4.8 branch-tag controls (display
only: the internal branch keys, the D-list files, the C/D-tagged CSV export
letters and filename parsing all stay exactly C / D).

Runs against the suite's ONE shared App (tests/conftest.py); the shipped
branch defaults are restored between tests by the shared reset fixture.
"""
import numpy as np
import pytest

from conftest import gui, shared_app

USES_APP = True
pytestmark = gui


@pytest.fixture(scope="module")
def a():
    return shared_app()


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


def test_raw_traces_are_disambiguated_and_duplicates_collapse(a):
    """Same value, same branch, raw-only: the channel tag plus the sample
    name make them distinct -- unless the RECORD is literally the same one,
    which collapses.  The plain 3-tuple form still works."""
    e = [(1, 0.0, "C", _raw("gasket2", "b")),
         (2, 0.0, "C", _raw("gasket3", "b")),
         (3, 0.1, "C", _full("gasket"))]
    assert a._ordered_legend(e)[1] == ["0.00 GPa - C [B only]  gasket2",
                                       "0.00 GPa - C [B only]  gasket3",
                                       "0.10 GPa - C"]
    r = _raw("gasket2", "b")
    dup = [(1, 0.0, "C", r), (2, 0.0, "C", r), (3, 0.1, "C", _full("gasket"))]
    assert a._ordered_legend(dup)[1] == ["0.00 GPa - C [B only]  gasket2",
                                         "0.10 GPa - C"]
    # the shipped rendering of the 3-tuple form is the contract
    assert a._ordered_legend([(1, 0.5, "C"), (2, 1.0, "D")])[1] == \
        ["0.50 GPa - C", "1.00 GPa - D"]


def test_branch_tags_off_drops_the_suffix(a):
    a.legend_branch_tags.set(False)
    assert a._ordered_legend([(1, 0.5, "C"), (2, 1.0, "D")])[1] == \
        ["0.50 GPa", "1.00 GPa"]
    # and the ordering is untouched: C ascending, then D descending
    assert a._ordered_legend([(1, 2.0, "D"), (2, 0.5, "C"),
                              (3, 4.0, "D")])[1] == \
        ["0.50 GPa", "4.00 GPa", "2.00 GPa"]


def test_custom_branch_labels_are_cosmetic_only(a):
    a.legend_branch_c.set("heat")
    a.legend_branch_d.set("cool")
    assert a._ordered_legend([(1, 0.5, "C"), (2, 1.0, "D")])[1] == \
        ["0.50 GPa - heat", "1.00 GPa - cool"]
    a.legend_branch_c.set("   ")               # blank -> the canonical letter
    assert a._ordered_legend([(1, 0.5, "C")])[1] == ["0.50 GPa - C"]
    # deliberately swapped wording: sorting still keys off the real C / D
    a.legend_branch_c.set("cool")
    a.legend_branch_d.set("heat")
    assert a._ordered_legend([(1, 2.0, "D"), (2, 0.5, "C"),
                              (3, 1.0, "C")])[1] == \
        ["0.50 GPa - cool", "1.00 GPa - cool", "2.00 GPa - heat"]


def test_branch_controls_round_trip_through_the_preset_registry(a):
    reg = a._preset_registry()
    for k in ("legend_branch_tags", "legend_branch_c", "legend_branch_d"):
        assert k in reg, k
        assert k in a._defaults, k
    a.legend_branch_tags.set(False)
    a.legend_branch_c.set("inc")
    a.legend_branch_d.set("dec")
    saved = {k: v.get() for k, v in reg.items()}

    a._apply_preset_data(dict(a._defaults))             # wander off
    assert a.legend_branch_tags.get() is True
    assert (a.legend_branch_c.get(), a.legend_branch_d.get()) == ("C", "D")

    a._apply_preset_data(saved)                         # and come back
    assert a.legend_branch_tags.get() is False
    assert (a.legend_branch_c.get(), a.legend_branch_d.get()) == ("inc", "dec")

    # a pre-v1.4.8 payload has none of these keys: the defaults must survive
    a._apply_preset_data(dict(a._defaults))
    a._apply_preset_data({"cmap": "magma", "legend_on": True})
    assert a.legend_branch_tags.get() is True
    assert a._ordered_legend([(1, 0.5, "D")])[1] == ["0.50 GPa - D"]
