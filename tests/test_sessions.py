"""Multi-tab session isolation tests (v1.4 core).

A "tab" is a stored session swapped into the single shared UI. These lock the
guarantee that data, control settings, trace visibility, folders and undo
stacks are isolated per session and round-trip on switch, and that closing a
tab does the right thing whether or not it is the last one.

Every session switch is a full state swap plus a replot (~1 s), so this
module opens as few tabs as the guarantees need and asserts all four kinds of
isolation on the SAME pair of tabs.  Runs against the suite's ONE shared App
(tests/conftest.py); the shared reset fixture collapses back to a single tab
after every test, which is why no test here builds its own starting point.
"""
import pytest

from conftest import gui, make_result, shared_app

USES_APP = True
pytestmark = gui


@pytest.fixture(scope="module")
def a():
    return shared_app()


def _res(label, dac, sample, pstr, pval):
    return make_result(label, pval, n=60, dac=dac, sample=sample, pstr=pstr)


def _load(a, results, dest="d"):
    a._finish_run([dict(r) for r in results], [], dest)


def test_data_settings_traces_and_undo_are_all_per_session(a):
    _load(a, [_res("A1", "D", "S", "1p0", 1.0),
              _res("A2", "D", "S", "2p0", 2.0)])
    a.in_var.set("folderA")
    a.cmap.set("viridis")
    a.trace_vars["A2"].set(False)          # hide A2 in tab 0
    a.lw.set(3.0)
    a._push_undo("lw change")
    depth0 = len(a._undo_stack)
    assert depth0 >= 2
    a._store_active()
    a.sessions[a.active]["name"] = "A"

    a._new_session(name="B")
    assert a.results == []
    assert a.in_var.get() == ""
    assert a.cmap.get() == a._defaults["cmap"]   # blank tab = defaults
    assert len(a._undo_stack) == 1               # ... and only its own snap

    _load(a, [_res("A1", "E", "T", "1p0", 1.0),
              _res("A2", "E", "T", "2p0", 2.0)])
    a.cmap.set("magma")
    assert a.trace_vars["A2"].get() is True      # new tab: all shown

    a._switch_session(0)   # back to A
    assert [r["label"] for r in a.results] == ["A1", "A2"]
    assert a.cmap.get() == "viridis"
    assert a.in_var.get() == "folderA"
    assert a.trace_vars["A2"].get() is False     # tab 0 kept A2 hidden
    assert len(a._undo_stack) == depth0          # tab 0 stack intact
    assert abs(float(a.lw.get()) - 3.0) < 1e-9

    a._switch_session(1)   # to B
    assert a.cmap.get() == "magma"
    assert a.in_var.get() == ""


def test_closing_a_tab_loads_a_neighbour_or_resets_blank(a):
    _load(a, [_res("K1", "D", "S", "1p0", 1.0)])
    a._store_active()
    a.sessions[a.active]["name"] = "keep"
    a._new_session(name="doomed")
    _load(a, [_res("D1", "E", "T", "9p0", 9.0)])
    assert a.active == 1
    a._close_session(1)                   # close the ACTIVE tab
    assert len(a.sessions) == 1
    assert [r["label"] for r in a.results] == ["K1"]   # neighbour is live

    a._close_session(0)                   # only tab -> reset blank
    assert len(a.sessions) == 1
    assert a.results == []
    assert a.active == 0
