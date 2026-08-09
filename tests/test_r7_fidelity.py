"""R7 -- the workbench-fidelity rebuild: the sidebar mirrors Matthew's GUI.

What this file pins down, each rule taken from defringe_dac.py's
launch_fft_gui and asserted against the SPARTA port:

  - his defaults, verbatim: n_medium 1.2 (manual), n_sample 1.5,
    d2/t/d1 = 0/20/0, low-pass 15 um per channel, both on;
  - Lock In redistribution (_on_d_edit / _on_total_edit): d2 and t
    trade off, d1 splits pro rata with spill, Total grows d2 and
    drains d1 -> d2 -> t;
  - the low-pass is PER CHANNEL, in the compute signature and the
    session payload, and a pre-R7 scalar payload still loads;
  - Clear notches keeps the fundamental listed but unticked;
  - Export cleaned spectrum writes his exact columns;
  - the pressure dropdown walks compression ascending then
    decompression descending, and the folder reader orders and
    labels spectra the same way;
  - the sidebar builds his cards under their gated titles.

Runs against the suite's ONE shared App (tests/conftest.py).
"""
import os

import numpy as np
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
    w = a._fringe
    w.build()                     # the workbench is lazy; tests need it up
    keep = (dict(w._chan), dict(w._trace), list(w._series), w._label,
            list(a.results), w._local)
    w._chan.clear()
    w._trace.clear()
    w._series = []
    w._local = None
    yield w
    w._chan.clear()
    w._chan.update(keep[0])
    w._trace.clear()
    w._trace.update(keep[1])
    w._series = keep[2]
    w._label = keep[3]
    a.results = keep[4]
    w._local = keep[5]


def _set_thicks(fw, d1, t, d2, lock):
    fw.lock_v.set(False)
    fw.d1_v.set("%g" % d1)
    fw.t_v.set("%g" % t)
    fw.d2_v.set("%g" % d2)
    fw._thick_snapshot()
    fw.lock_v.set(lock)
    fw._on_lock()


# ---------------------------------------------------------------------------
# the cards + his defaults
# ---------------------------------------------------------------------------
def test_the_sidebar_builds_his_cards(a, fw):
    got = {r["key"] for r in a._collapsibles}
    for key in fringe_panel.FRINGE_SECTIONS:
        assert key in got, key
    # the pre-R7 cards are gone. R14 gave Detection a card of its own
    # again, so it is asserted PRESENT above, with the rest of
    # FRINGE_SECTIONS.
    assert "Detection" in got
    for key in ("Notches", "Roles & solve", "Series"):
        assert key not in got, key


def test_his_defaults_verbatim():
    d = fringe_panel.SETTINGS_DEFAULTS
    assert d["fr_medium"] == "Other"
    assert d["fr_medium_n"] == 1.2
    assert d["fr_n_sample"] == 1.50
    assert (d["fr_d1_um"], d["fr_t_um"], d["fr_d2_um"]) == (0.0, 20.0, 0.0)
    assert d["fr_lp_cutoff_um"] == 15.0


def test_low_pass_is_per_channel(fw):
    assert set(fw.lp_on_v) == {"Background", "Sample"}
    assert set(fw.lp_v) == {"Background", "Sample"}
    fw.lp_on_v["Background"].set(True)
    fw.lp_on_v["Sample"].set(False)
    fw.lp_v["Background"].set("22")
    fw.lp_v["Sample"].set("15")
    sig_b = fw._sig("Background")
    sig_s = fw._sig("Sample")
    assert sig_b != sig_s
    assert "22" in sig_b and True in sig_b
    assert False in sig_s


# ---------------------------------------------------------------------------
# Lock In: his redistribution rules
# ---------------------------------------------------------------------------
def test_lock_in_t_and_d2_trade_off(fw):
    _set_thicks(fw, 5.0, 20.0, 5.0, lock=True)
    fw.t_v.set("24")               # +4 to t ...
    fw._on_d_edit("t")
    assert float(fw.t_v.get()) == pytest.approx(24.0)
    assert float(fw.d2_v.get()) == pytest.approx(1.0)   # ... comes out of d2
    assert float(fw.d1_v.get()) == pytest.approx(5.0)


def test_lock_in_partner_clamps_at_zero_then_total_grows(fw):
    _set_thicks(fw, 5.0, 20.0, 5.0, lock=True)
    fw.t_v.set("30")               # +10, but d2 only holds 5
    fw._on_d_edit("t")
    assert float(fw.d2_v.get()) == pytest.approx(0.0)
    assert float(fw.t_v.get()) == pytest.approx(30.0)


def test_lock_in_d1_splits_pro_rata(fw):
    _set_thicks(fw, 5.0, 30.0, 10.0, lock=True)
    fw.d1_v.set("9")               # +4 -> d2 takes 1/4 of -4, t takes 3/4
    fw._on_d_edit("d1")
    assert float(fw.d2_v.get()) == pytest.approx(9.0)
    assert float(fw.t_v.get()) == pytest.approx(27.0)
    total = (float(fw.d1_v.get()) + float(fw.t_v.get())
             + float(fw.d2_v.get()))
    assert total == pytest.approx(45.0)


def test_total_edit_grows_d2_and_drains_d1_then_d2_then_t(fw):
    _set_thicks(fw, 5.0, 20.0, 5.0, lock=True)
    fw.total_v.set("40")           # +10 -> all of it to d2
    fw._on_total_edit()
    assert float(fw.d2_v.get()) == pytest.approx(15.0)
    fw.total_v.set("12")           # -28 -> d1 (5) then d2 (15) then t (8)
    fw._on_total_edit()
    assert float(fw.d1_v.get()) == pytest.approx(0.0)
    assert float(fw.d2_v.get()) == pytest.approx(0.0)
    assert float(fw.t_v.get()) == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# Clear notches: the fundamental survives, unticked
# ---------------------------------------------------------------------------
def test_clear_notches_keeps_the_fundamental_unticked(a, fw):
    a.results = [make_result("R1", 1.0)]
    fw._label = "R1"
    ch = fw._ch("Sample")
    ch["default_centers"] = [24.0, 48.0]
    ch["user_centers"] = [60.0]
    fw._clear_notches_for("Sample")
    assert 24.0 in ch["unticked"], "the fundamental stays listed, unticked"
    assert 48.0 in ch["removed"] and 60.0 in ch["removed"]
    assert fw._active_centers("Sample") == []
    assert fw._active_centers("Sample", include_unticked=True) == [24.0]


# ---------------------------------------------------------------------------
# Export cleaned spectrum: his columns
# ---------------------------------------------------------------------------
def test_export_cleaned_spectrum_writes_his_columns(a, fw, tmp_path,
                                                    monkeypatch):
    a.results = [make_result("R1", 1.0)]
    fw._label = "R1"
    rec = fw._record()
    n = len(rec["wl"])
    fake = {"Background": np.linspace(2.0, 3.0, n),
            "Sample": np.linspace(1.0, 2.0, n)}
    monkeypatch.setattr(
        fw, "_compute",
        lambda chan: {"fft_info": {"I_notch_1x": fake[chan]}})
    monkeypatch.setattr(fw, "_series_folder", lambda: str(tmp_path))
    fw._export_cleaned()
    files = [f for f in os.listdir(str(tmp_path))
             if f.startswith("cleaned_spectrum_")]
    assert len(files) == 1
    with open(os.path.join(str(tmp_path), files[0])) as f:
        head = f.readline().strip().split(",")
        row1 = f.readline().strip().split(",")
    assert head == ["Wavenumber_cm", "Background_notch", "Sample_notch",
                    "Absorbance_notch"]
    wn0 = float(row1[0])
    assert wn0 == pytest.approx(1e7 / float(rec["wl"][0]))
    assert float(row1[3]) == pytest.approx(
        np.log10(fake["Background"][0] / fake["Sample"][0]))


# ---------------------------------------------------------------------------
# the experiment's path: compression up, decompression down
# ---------------------------------------------------------------------------
def test_ordered_recs_walk_compression_up_then_decompression_down(a, fw):
    def rec(label, p, br):
        r = make_result(label, p)
        r["branch"] = br
        return r
    a.results = [rec("d low", 3.9, "D"), rec("c high", 24.4, "C"),
                 rec("d high", 12.4, "D"), rec("c low", 0.0, "C"),
                 rec("c mid", 12.4, "C")]
    got = [r["label"] for r in fw._ordered_recs()]
    assert got == ["c low", "c mid", "c high", "d high", "d low"]


def test_read_folder_parses_orders_and_labels(fw, tmp_path):
    head = ("Wavelength_nm,Wavenumber_cm-1,Absorbance,Dark,Background,"
            "Sample\n")
    wl = np.linspace(500.0, 900.0, 32)
    for stem, scale in (("y9_s_12p4_absorbance", 2.0),
                        ("y9_s_0p0_absorbance", 1.0),
                        ("y9_s_12p4D_absorbance", 3.0)):
        rows = [head]
        for w in wl:
            rows.append("%g,%g,0.1,0.0,%g,%g\n"
                        % (w, 1e7 / w, 2.0 * scale, 1.0 * scale))
        with open(os.path.join(str(tmp_path), stem + ".csv"), "w") as f:
            f.writelines(rows)
    recs = fw._read_folder(str(tmp_path))
    assert [r["label"] for r in recs] == ["0 GPa", "12.4 GPa",
                                          "12.4 GPa (D)"]
    assert [r["branch"] for r in recs] == ["C", "C", "D"]
    assert recs[0]["stem"] == "y9_s_0p0_absorbance"
    assert recs[1]["wl"][0] == pytest.approx(500.0)
    assert recs[1]["bg_c"][0] == pytest.approx(4.0)
    assert recs[1]["samp_c"][0] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# session payload: per-channel low-pass, and the pre-R7 migration
# ---------------------------------------------------------------------------
def test_save_state_carries_per_channel_lowpass_and_legacy_loads(fw):
    fw.lp_on_v["Background"].set(True)
    fw.lp_v["Background"].set("18")
    fw.lp_on_v["Sample"].set(False)
    fw.lp_v["Sample"].set("15")
    d = fw.save_state()
    lp = d["notch"]["lowpass"]
    assert lp["Background"] == [True, 18.0]
    assert lp["Sample"] == [False, 15.0]
    # a pre-R7 payload holds a scalar pair: both channels take it
    legacy = dict(d)
    legacy["notch"] = {"halfwidth": 3.0, "lowpass": True,
                       "lp_cutoff": 21.0}
    fw.load_state(legacy)
    for c in ("Background", "Sample"):
        assert fw.lp_on_v[c].get() is True
        assert float(fw.lp_v[c].get()) == pytest.approx(21.0)
