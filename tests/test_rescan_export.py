"""C/D-tagged CSV export and the auto-rescan poll (v1.4.8).

Two features that must not drift:

* 'Save C/D-tagged CSVs' writes the SAME per-point absorbance CSVs a Run
  writes, only with the branch letter in the name. The naming rule and the
  byte-for-byte identity with engine's own writer are the contract.
* Auto rescan owns exactly ONE root.after timer, cancels cleanly, and its
  two controls persist in SETTINGS (workflow state, not figure state).

Needs a Tk display, so the module skips on a headless box (like
test_legend.py / test_sessions.py).
"""
import json
import os

import numpy as np
import pytest

try:
    import tkinter as tk
    # Reuse an existing default root if another GUI test module already made
    # one: this Windows Store Python cannot spin up a SECOND independent Tk()
    # interpreter (see test_sessions.py).
    _root = tk._default_root or tk.Tk()
    _root.withdraw()
    import app
    import engine
    _APP = app.App(_root)
    _APP._save_settings = lambda: None
    _HAVE_GUI = True
except Exception:
    _HAVE_GUI = False

pytestmark = pytest.mark.skipif(not _HAVE_GUI, reason="no Tk display")


def _res(dac, sample, pstr, pval, tag=None):
    """A minimal valid engine-style result dict with real absorbance."""
    wl = np.linspace(400.0, 1000.0, 12)
    return {"label": "%s %s %.2f GPa" % (dac, sample, pval),
            "dac": dac, "sample": sample, "pressure_str": pstr,
            "pressure_val": pval, "rep": 1, "branch_tag": tag,
            "wl": wl, "wn": 1e7 / wl,
            "absorbance": np.linspace(0.1, 1.2, 12),
            "dark_c": np.ones(12), "bg_c": np.full(12, 10.0),
            "samp_c": np.full(12, 5.0)}


def _trio():
    """Three points, one of them tagged D in its file name."""
    return [_res("Y04", "Arch29", "12p5", 12.5),
            _res("Y04", "Arch29", "18p0", 18.0),
            _res("Y04", "Arch29", "9p0", 9.0, "D")]


def _load(results):
    _APP._finish_run([dict(r) for r in results], [], "dest")


@pytest.fixture(autouse=True)
def _clean_state():
    """Every test starts from the shipped defaults and leaves no timer."""
    _APP.xvar_choice.set("Pressure (GPa)")
    _APP.auto_rescan.set(False)
    _APP.rescan_interval.set(30)
    _APP._cancel_auto_rescan()
    yield
    _APP.auto_rescan.set(False)
    _APP._cancel_auto_rescan()
    _APP.xvar_choice.set("Pressure (GPa)")


# ------------------------------------------------ C/D-tagged CSV export ----
def test_tagged_csv_naming_rule(tmp_path):
    """{DAC}_{sample}_{value}_{C|D}_absorbance.csv -- the branch letter goes
    exactly where Run already puts a file-name branch tag."""
    res = _trio()
    branches = {res[0]["label"]: "C", res[1]["label"]: "C",
                res[2]["label"]: "D"}
    written = _APP._write_tagged_csvs(res, branches, str(tmp_path))
    assert [os.path.basename(p) for p in written] == [
        "Y04_Arch29_12p5_C_absorbance.csv",
        "Y04_Arch29_18p0_C_absorbance.csv",
        "Y04_Arch29_9p0_D_absorbance.csv"]
    assert all(os.path.isfile(p) for p in written)


def test_tagged_csv_default_is_compression(tmp_path):
    """Anything not explicitly marked D is compression -- including a point
    whose FILE NAME said D but whose D box the user cleared."""
    res = _trio()
    written = _APP._write_tagged_csvs(res, {}, str(tmp_path))
    assert [os.path.basename(p) for p in written] == [
        "Y04_Arch29_12p5_C_absorbance.csv",
        "Y04_Arch29_18p0_C_absorbance.csv",
        "Y04_Arch29_9p0_C_absorbance.csv"]


def test_tagged_csv_content_matches_untagged_writer(tmp_path):
    """Only the name changes: the bytes are the normal writer's."""
    res = _trio()
    tagged = tmp_path / "tagged"
    plain = tmp_path / "plain"
    tagged.mkdir()
    plain.mkdir()
    written = _APP._write_tagged_csvs(res, {res[2]["label"]: "D"},
                                      str(tagged))
    for r, p in zip(res, written):
        ref = engine.write_absorbance_csv(dict(r, branch_tag=None),
                                          str(plain))
        assert open(ref, "rb").read() == open(p, "rb").read()


def test_tagged_csv_collision_is_not_an_overwrite(tmp_path):
    """Two points that would land on one name keep both files."""
    a = _res("Y04", "Arch29", "12p5", 12.5)
    b = _res("Y04", "Arch29", "12p5", 12.5, "D")
    b["label"] = a["label"] + " [D]"          # distinct identity, same stem
    written = _APP._write_tagged_csvs([a, b], {}, str(tmp_path))
    assert [os.path.basename(p) for p in written] == [
        "Y04_Arch29_12p5_C_absorbance.csv",
        "Y04_Arch29_12p5-2_C_absorbance.csv"]
    assert len([f for f in os.listdir(str(tmp_path))
                if f.endswith(".csv")]) == 2


def test_tagged_csv_branch_follows_the_d_toggles(tmp_path, monkeypatch):
    """End to end through the button handler: branch = what the plot uses
    (auto-detected D plus the manual toggles), plus one batch sidecar."""
    _load(_trio())
    for r in _APP.results:                    # deterministic branch state
        _APP.dvars[r["label"]].set(r["pressure_str"] == "18p0")
    monkeypatch.setattr(app.filedialog, "askdirectory",
                        lambda **kw: str(tmp_path))
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *a, **kw: None)
    _APP._export_branch_csvs()
    names = sorted(os.listdir(str(tmp_path)))
    assert names == ["Y04_Arch29_12p5_C_absorbance.csv",
                     "Y04_Arch29_18p0_D_absorbance.csv",
                     "Y04_Arch29_9p0_C_absorbance.csv",
                     "_export.provenance.json"]


def test_tagged_csv_sidecar(tmp_path, monkeypatch):
    _load(_trio())
    for r in _APP.results:
        _APP.dvars[r["label"]].set(r["pressure_str"] == "9p0")
    monkeypatch.setattr(app.filedialog, "askdirectory",
                        lambda **kw: str(tmp_path))
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *a, **kw: None)
    _APP._export_branch_csvs()
    with open(os.path.join(str(tmp_path), "_export.provenance.json")) as f:
        prov = json.load(f)
    assert prov["kind"] == "branch_tagged_csv"
    assert prov["variable_name"] == "Pressure"
    assert prov["variable_unit"] == "GPa"
    assert prov["params"]["n_csv"] == 3
    assert prov["params"]["n_decompression"] == 1
    assert len(prov["files"]) == 3


def test_tagged_csv_no_data_opens_no_dialog(monkeypatch):
    """Matches the other data-dependent exports: a note, not a dialog."""
    opened, told = [], []
    monkeypatch.setattr(app.filedialog, "askdirectory",
                        lambda **kw: opened.append(kw) or "")
    monkeypatch.setattr(app.messagebox, "showinfo",
                        lambda *a, **kw: told.append(a))
    _APP.results = []
    _APP._export_branch_csvs()
    assert opened == []
    assert told and "No data" in told[0][1]


# ------------------------------------------------------- auto rescan -------
def test_rescan_settings_roundtrip(tmp_path):
    """auto_rescan / rescan_interval live in SETTINGS (like the folders),
    not in the figure-preset registry, and survive a fresh launch."""
    reg = _APP._preset_registry()
    assert "auto_rescan" not in reg and "rescan_interval" not in reg
    _APP.auto_rescan.set(True)
    _APP.rescan_interval.set(45)
    real = app.App._save_settings.__get__(_APP, app.App)
    _APP._save_settings = real
    try:
        _APP._persist_rescan()
    finally:
        _APP._save_settings = lambda: None
    with open(app.SETTINGS_PATH) as f:
        data = json.load(f)
    assert data["auto_rescan"] is True
    assert data["rescan_interval"] == 45
    fresh = app.App(_root)                 # a new launch reads it back
    try:
        fresh._save_settings = lambda: None
        assert fresh.auto_rescan.get() is True
        assert fresh.rescan_interval.get() == 45
        assert fresh._auto_rescan_job is not None   # armed on startup
    finally:
        fresh._cancel_auto_rescan()
    _APP._cancel_auto_rescan()


def test_interval_is_clamped():
    _APP.rescan_interval.set(1)
    assert _APP._auto_rescan_secs() == 5
    _APP.rescan_interval.set(99999)
    assert _APP._auto_rescan_secs() == 3600
    _APP.rescan_interval.set(30)
    assert _APP._auto_rescan_secs() == 30


def test_one_timer_only_and_cancel():
    a = _APP

    def jobs():
        return set(_root.tk.call("after", "info"))

    assert a._auto_rescan_job is None
    a.auto_rescan.set(True)
    a._toggle_auto_rescan()
    first = a._auto_rescan_job
    assert first is not None and first in jobs()
    a.rescan_interval.set(11)               # reschedules cleanly
    second = a._auto_rescan_job
    assert second is not None and second != first
    assert first not in jobs() and second in jobs()
    a._schedule_auto_rescan()               # never stacks a second job
    third = a._auto_rescan_job
    assert second not in jobs() and third in jobs()
    a.auto_rescan.set(False)
    a._toggle_auto_rescan()
    assert a._auto_rescan_job is None
    assert third not in jobs()


def test_tick_waits_for_the_first_run(tmp_path, monkeypatch):
    a = _APP
    calls = []
    monkeypatch.setattr(a, "_rescan", lambda auto=False: calls.append(auto))
    a.auto_rescan.set(True)
    a.in_var.set(str(tmp_path))
    a._last_scan = None                     # no Run has completed yet
    a._auto_rescan_tick()
    a._cancel_auto_rescan()
    assert calls == []
    a._last_scan = (str(tmp_path), set())   # ... now one has
    a._auto_rescan_tick()
    a._cancel_auto_rescan()
    assert calls == [True]                  # and it takes the silent path
    a.in_var.set("")


def test_tick_never_fires_mid_run(tmp_path, monkeypatch):
    a = _APP
    calls = []
    monkeypatch.setattr(a, "_rescan", lambda auto=False: calls.append(auto))
    monkeypatch.setattr(a, "_run_busy", lambda: True)
    a.auto_rescan.set(True)
    a.in_var.set(str(tmp_path))
    a._last_scan = (str(tmp_path), set())
    a._auto_rescan_tick()
    a._cancel_auto_rescan()
    assert calls == []
    a.in_var.set("")


def test_rescan_shortcut_bindings_exist():
    assert _root.bind("<F5>")
    assert _APP._in_entry.bind("<Return>")
    assert "F5" in app.SHORTCUTS_TEXT
    assert "Enter (input)" in app.SHORTCUTS_TEXT


# ------------------------------------------- Inspect combobox identity -----
def test_inspect_selection_survives_a_variable_change():
    """The combobox DISPLAYS the active Variable's unit; the selection still
    resolves to the same engine record."""
    a = _APP
    _load(_trio())
    vals = list(a.inspect_combo.cget("values"))
    assert vals == [r["label"] for r in a.results]      # GPa: byte-identical
    a.inspect_p.set(vals[1])
    assert a._inspect_record() is a.results[1]
    a.xvar_choice.set("Temperature (K)")
    shown = list(a.inspect_combo.cget("values"))
    assert all(v.endswith(" K") for v in shown)
    assert a._inspect_record() is a.results[1]
    a._menu_inspect(a.results[2]["label"])              # right-click Inspect
    assert a._inspect_record() is a.results[2]
    a.xvar_choice.set("Pressure (GPa)")
    assert a._inspect_record() is a.results[2]
