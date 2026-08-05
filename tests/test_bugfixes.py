"""Regression tests for the v1.4.8 bug hunt (F1-F8, C1-C3).

One test (or small group) per verified finding, derived from the hunt's
own reproduction scripts. Each docstring records the symptom the fix
removed, so a future edit that reintroduces it names itself.

Needs a Tk display for everything except the pure-smoothing cases, so the
module skips on a headless box (same shape as test_rescan_export.py /
test_legend.py). Dialogs are opened for real, so every Toplevel born here
is forced off-screen (+3200+100, the project's probe convention) and torn
down immediately: a test run must never flash a window at the user.
"""
import contextlib
import json
import os
import struct
import sys

import numpy as np
import pytest

import smoothing

try:
    import tkinter as tk
    # Reuse the default root if another GUI test module already made one:
    # this Windows Store Python cannot spin up a SECOND Tk interpreter.
    _root = tk._default_root or tk.Tk()
    _root.withdraw()
    import app
    import engine
    _HAVE_GUI = True
except Exception:
    _HAVE_GUI = False

_APP = None


@pytest.fixture(scope="session", autouse=True)
def _shared_app():
    """Build the App LAZILY, at first test execution rather than at import.

    The FIRST App constructed on the shared Tk root is what gives that
    withdrawn root its geometry; anything that flushes Tk idles before it
    (another App, a bare update_idletasks) pins the root at ~200 px, and
    test_qol's sash tests then skip themselves with "window too narrow".
    This module sorts first alphabetically, so it must not build an App
    while the other GUI modules are still being imported.
    """
    global _APP
    if _HAVE_GUI and _APP is None:
        _APP = app.App(_root)
        _APP._save_settings = lambda: None
    yield


_gui = pytest.mark.skipif(not _HAVE_GUI, reason="no Tk display")
_win = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

OFF = "+3200+100"


@contextlib.contextmanager
def _offscreen():
    """Park every Toplevel created inside the block off the visible desktop
    (test_qol.py's convention, kept identical on purpose)."""
    orig_tl = tk.Toplevel
    orig_center = app.App._center_on_root

    class _Off(orig_tl):
        def __init__(self, *a, **k):
            orig_tl.__init__(self, *a, **k)
            try:
                self.geometry(OFF)
            except tk.TclError:
                pass

    def _center(win, w, h):
        win.geometry("%dx%d%s" % (int(w), int(h), OFF))

    tk.Toplevel = _Off
    _APP._center_on_root = _center
    try:
        yield
    finally:
        tk.Toplevel = orig_tl
        try:
            del _APP._center_on_root
        except AttributeError:
            pass
        assert app.App._center_on_root is orig_center


# --------------------------------------------------------------- helpers ---
def _res(dac, sample, pstr, pval):
    """A minimal valid engine-style result dict with real absorbance."""
    wl = np.linspace(400.0, 1000.0, 12)
    return {"label": "%s %s %.2f GPa" % (dac, sample, pval),
            "dac": dac, "sample": sample, "pressure_str": pstr,
            "pressure_val": pval, "rep": 1, "branch_tag": None,
            "wl": wl, "wn": 1e7 / wl,
            "absorbance": np.linspace(0.1, 1.2, 12),
            "dark_c": np.ones(12), "bg_c": np.full(12, 10.0),
            "samp_c": np.full(12, 5.0)}


def _walk(w, out=None):
    out = [] if out is None else out
    out.append(w)
    for c in w.winfo_children():
        _walk(c, out)
    return out


def _by_text(top, text):
    for w in _walk(top):
        try:
            if w.cget("text") == text:
                return w
        except tk.TclError:
            pass
    return None


def _tops():
    return [w for w in _root.winfo_children() if isinstance(w, tk.Toplevel)]


def _make_files(folder, names):
    for nm in names:
        open(os.path.join(str(folder), nm), "w").close()
    return str(folder)


_BEAMLINE_NAMES = ["vis_Y04_Arch29_12p5_bg_C.001",
                   "vis_Y04_Arch29_12p5_s_C.001",
                   "vis_Y04_Arch29_12p5_d_C.001"]


@pytest.fixture(autouse=True)
def _clean_state():
    """Every test starts from the shipped defaults and leaves no timer, no
    open dialog and no settings residue."""
    if not _HAVE_GUI:
        yield
        return
    keep = {k: json.loads(json.dumps(_APP.settings.get(k)))
            for k in ("profiles", "active_profile", "name_overrides")
            if k in _APP.settings}
    _APP.xvar_choice.set("Pressure (GPa)")
    _APP.auto_rescan.set(False)
    _APP.rescan_interval.set(30)
    _APP._cancel_auto_rescan()
    yield
    for w in _tops():
        try:
            w.grab_release()
            w.destroy()
        except tk.TclError:
            pass
    _APP.auto_rescan.set(False)
    _APP._cancel_auto_rescan()
    _APP.xvar_choice.set("Pressure (GPa)")
    _APP.in_var.set("")
    _APP.smooth_params.clear()
    _APP.smooth_params.update(smoothing.DEFAULTS)
    _APP.smooth_cache.clear()
    _APP.show_smooth.set(False)
    for k in ("profiles", "active_profile", "name_overrides"):
        _APP.settings.pop(k, None)
    _APP.settings.update(keep)
    _root.update()


# ------------------------------------------------------------------- F1 ----
@_gui
@pytest.mark.parametrize("typed", ["inf", "Inf", "INFINITY", "1e400", "-inf"])
def test_bugfix_f1_infinite_interval_never_raises(typed):
    """Tcl's double parser accepts 'inf' / '1e400', so IntVar.get() handed
    back a float infinity and int(float(...)) raised OverflowError - which
    was not in the except tuple, so it escaped once per keystroke."""
    a = _APP
    a._rescan_spin.delete(0, "end")
    a._rescan_spin.insert(0, typed)
    _root.update()
    assert a._auto_rescan_secs() == 30           # the documented fallback
    a._rescan_spin.delete(0, "end")
    a._rescan_spin.insert(0, "30")
    _root.update()


@_gui
def test_bugfix_f1_pill_still_arms_the_timer_with_a_junk_interval():
    """_toggle_auto_rescan raised inside _persist_rescan before it ever
    reached _schedule_auto_rescan, so the pill showed ON with no timer."""
    a = _APP
    a._rescan_spin.delete(0, "end")
    a._rescan_spin.insert(0, "inf")
    _root.update()
    a.auto_rescan.set(True)
    a._toggle_auto_rescan()
    try:
        assert a._auto_rescan_job is not None
        assert a.settings["rescan_interval"] == 30
    finally:
        a.auto_rescan.set(False)
        a._cancel_auto_rescan()
        a._rescan_spin.delete(0, "end")
        a._rescan_spin.insert(0, "30")
        _root.update()


# ------------------------------------------------------------------- F2 ----
@contextlib.contextmanager
def _namefmt(folder, save_as=True):
    """Open the Name-format dialog off-screen on folder; save_as leaves the
    builtin profile, which is what makes the chip row appear."""
    _APP.in_var.set(folder)
    with _offscreen():
        before = set(str(w) for w in _root.winfo_children())
        _APP._open_name_format()
        _root.update()
        d = [w for w in _root.winfo_children()
             if str(w) not in before and w.winfo_class() == "Toplevel"][-1]
        if save_as:
            _by_text(d, "Save as…").invoke()
            _root.update()
        try:
            yield d
        finally:
            for step in (d.grab_release,
                         lambda: d.winfo_exists() and d.destroy()):
                try:
                    step()
                except tk.TclError:
                    pass
            _root.update()
    _APP.in_var.set("")


def _matched_text(d):
    """The dialog's 'matched N / M files' status line."""
    out = ""
    for w in _walk(d):
        try:
            t = w.cget("text")
        except tk.TclError:
            continue
        if isinstance(t, str) and t.startswith("matched "):
            out = t
    return out


def _chip_values(d):
    for w in _walk(d):
        if w.winfo_class() == "TCombobox" and "dac" in (w.cget("values") or ()):
            return list(w.cget("values")), int(w.cget("width"))
    return [], -1


@_gui
@pytest.mark.parametrize("vname", ["Sample", "dac", "Branch", "REP", "Role",
                                   "ignore"])
def test_bugfix_f2_variable_named_like_a_field_does_not_brick_the_dialog(
        vname, tmp_path, monkeypatch):
    """A Variable called Sample / DAC / Branch / Rep / Role / Ignore aliased
    the pressure chip onto a REAL field name: the dropdown grew a duplicate
    option, _fcanon stored the user's 'sample' chip as 'pressure', the real
    field vanished from the order and validate_profile then refused 'Use
    this profile' with "'sample' missing from token order". The alias is
    dropped when it would shadow a field, so nothing aliases and nothing
    is blocked."""
    errs = []
    monkeypatch.setattr(app.simpledialog, "askstring", lambda *a, **k: "V")
    monkeypatch.setattr(app.messagebox, "showerror",
                        lambda *a, **k: errs.append(a))
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *a, **k: None)
    _APP.xvar_choice.set(app.XVAR_CUSTOM)
    _APP.xvar_name.set(vname)
    _APP.xvar_unit.set("u")
    with _namefmt(_make_files(tmp_path, _BEAMLINE_NAMES)) as d:
        vals, _w = _chip_values(d)
        assert vals == list(engine.FIELD_CHOICES)   # no alias, no duplicate
        assert len(vals) == len(set(vals))
        _by_text(d, "Use this profile").invoke()
        _root.update()
        assert errs == []                           # committed, not refused
        assert not d.winfo_exists()                 # ... and the dialog closed
    assert "pressure" in _APP._active_profile().get("order", [])


@_gui
def test_bugfix_f2_a_harmless_variable_name_still_aliases(tmp_path,
                                                          monkeypatch):
    """The display alias is the point of the feature: only COLLIDING names
    fall back to the canonical label."""
    monkeypatch.setattr(app.simpledialog, "askstring", lambda *a, **k: "V")
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *a, **k: None)
    _APP.xvar_choice.set("Temperature (K)")
    with _namefmt(_make_files(tmp_path, _BEAMLINE_NAMES)) as d:
        vals, _w = _chip_values(d)
        assert vals == ["dac", "sample", "temperature", "role", "branch",
                        "rep", "ignore"]


# ------------------------------------------------------------------- F3 ----
def _legacy_density(y, win, min_pts):
    """smoothing._density exactly as it shipped before the fix."""
    finite = np.isfinite(y).astype(float)
    half = int(win // 2)
    kernel = np.ones(2 * half + 1)
    counts = np.convolve(finite, kernel, mode="same")
    y[counts < min_pts] = np.nan


def _noisy(n, seed=1):
    rng = np.random.default_rng(seed)
    x = np.linspace(400.0, 1000.0, n)
    y = 0.8 + 0.3 * np.sin(x / 37.0) + 0.02 * rng.standard_normal(n)
    y[n // 7] = 9.9                  # saturation hit
    y[n // 5:n // 5 + 3] = np.nan    # a NaN island
    y[n // 3] += 1.5                 # a spike for Hampel
    y[2 * n // 3] += 0.9             # a jump for step 5
    return x, y


@pytest.mark.parametrize("n", [2000, 5360, 512, 101, 51])
@pytest.mark.parametrize("win", [50, 1, 2, 49])
def test_bugfix_f3_normal_traces_are_byte_identical(n, win, monkeypatch):
    """The window clamp must be invisible on every trace long enough for
    the requested window: the output is compared BYTE FOR BYTE against the
    pre-fix _density, not merely 'close'."""
    x, y = _noisy(n)
    params = dict(smoothing.DEFAULTS, density_win=win)
    monkeypatch.setattr(smoothing, "_density", _legacy_density)
    before = smoothing.smooth_curve(x, y, params)
    monkeypatch.undo()
    after = smoothing.smooth_curve(x, y, params)
    assert (np.ascontiguousarray(before, dtype="<f8").tobytes()
            == np.ascontiguousarray(after, dtype="<f8").tobytes())


@pytest.mark.parametrize("n", [0, 1, 2, 12, 50, 51])
def test_bugfix_f3_short_trace_does_not_crash(n):
    """np.convolve(mode='same') returns max(len(y), len(kernel)), so a
    kernel longer than the trace produced a mask longer than y:
    'IndexError: boolean index did not match indexed array' for any trace
    of <= density_win points (and ValueError at length 0)."""
    x, y = (np.linspace(400.0, 1000.0, n), np.linspace(0.1, 1.0, n))
    out = smoothing.smooth_curve(x, y)
    assert len(out) == n


@pytest.mark.parametrize("win", [6000, 100000, 0, -5])
def test_bugfix_f3_oversize_or_negative_window_does_not_crash(win):
    """A 5360-point spectrum with density_win >= 5360 crashed; the clamp
    turns it into 'the whole trace', which is what the user asked for."""
    x, y = _noisy(5360)
    out = smoothing.smooth_curve(x, y, dict(smoothing.DEFAULTS,
                                            density_win=win))
    assert len(out) == 5360


@_gui
def test_bugfix_f3_smoothing_dialog_clamps_the_point_counts():
    """'Window (pts)' is free text with a per-keystroke live preview; an
    absurd value must be clamped on parse rather than reaching the
    filters."""
    a = _APP
    a._finish_run([_res("Y04", "Arch29", "12p5", 12.5)], [], "dest")
    with _offscreen():
        before = set(str(w) for w in _root.winfo_children())
        a._open_smooth_panel()
        _root.update()
        win = [w for w in _root.winfo_children()
               if str(w) not in before and w.winfo_class() == "Toplevel"][-1]
        try:
            _by_text(win, "Live preview").invoke()  # live trace on
            ent = None
            for w in _walk(win):
                if w.winfo_class() == "TEntry":
                    v = w.cget("textvariable")
                    if v and str(win.getvar(v)) == str(
                            smoothing.DEFAULTS["density_win"]):
                        ent = w
                        break
            assert ent is not None
            ent.delete(0, "end")
            for ch in "999999999":                  # one live redraw per key
                ent.insert("end", ch)
                _root.update()
            assert a.smooth_params["density_win"] == app.SMOOTH_INT_BOUNDS[
                "density_win"][1]
        finally:
            _by_text(win, "Cancel").invoke()
            _root.update()


@_gui
def test_bugfix_f3_export_smoothed_survives_a_short_trace(tmp_path,
                                                          monkeypatch):
    """_export_smoothed has no try/except, so the crash escaped into the
    Tk button callback and the export silently did nothing."""
    a = _APP
    a._finish_run([_res("Y04", "Arch29", "12p5", 12.5)], [], "dest")
    for r in a.results:
        a.trace_vars[r["label"]].set(True)
    a.smooth_params["density_win"] = 6000           # > the 12-point trace
    a.smooth_cache.clear()
    a.show_smooth.set(True)
    monkeypatch.setattr(app.filedialog, "askdirectory",
                        lambda **k: str(tmp_path))
    a._export_smoothed()
    assert [f for f in os.listdir(str(tmp_path)) if f.endswith("_smoothed.csv")]


# ------------------------------------------------------------------- F4 ----
@_gui
@pytest.mark.parametrize("unit", ["$\\mu$m", "\\AA", "a\\b", "\\1", "x\\",
                                  "\\n", "\\g<0>", "\\\\", "&", "\\g<name>"])
def test_bugfix_f4_unit_is_a_literal_replacement(unit):
    """The unit was passed as re.sub's REPLACEMENT TEMPLATE, so backslash
    escapes were expanded: '$\\mu$m' and '\\AA' raised re.error once per
    keystroke and 'a\\b' silently became 'a<backspace>'."""
    a = _APP
    a.xvar_choice.set(app.XVAR_CUSTOM)
    a.xvar_unit.set(unit)
    assert a._relabel("Y04 Arch29 12.50 GPa") == "Y04 Arch29 12.50 " + unit
    assert a._relabel("Y04 Arch29 12.50 GPa [C]") == \
        "Y04 Arch29 12.50 " + unit + " [C]"


@_gui
def test_bugfix_f4_blank_and_default_units_are_unchanged():
    a = _APP
    a.xvar_choice.set(app.XVAR_CUSTOM)
    a.xvar_unit.set("")
    assert a._relabel("Y04 Arch29 12.50 GPa") == "Y04 Arch29 12.50"
    a.xvar_choice.set("Pressure (GPa)")
    assert a._relabel("Y04 Arch29 12.50 GPa") == "Y04 Arch29 12.50 GPa"


# ------------------------------------------------------------------- F5 ----
def _collide():
    """Four records, two distinct engine labels: 12.500 / 12.501 / 12.504
    all print '12.50 GPa'."""
    return [_res("Y04", "A", "12p5", 12.500),
            _res("Y04", "A", "12p50", 12.501),
            _res("Y04", "A", "12p500", 12.504),
            _res("Y04", "B", "20p0", 20.0)]


@_gui
def test_bugfix_f5_counts_match_the_files_on_disk(tmp_path, monkeypatch):
    """The branch dict was keyed by engine label, and labels are not
    unique: 4 files were written but the log line and the provenance
    sidecar counted the 2 distinct LABELS, claiming 2 compression CSVs
    that do not exist."""
    a = _APP
    a._finish_run([dict(r) for r in _collide()], [], "dest")
    for r in a.results:
        a.dvars[r["label"]].set(True)               # everything decompression
    monkeypatch.setattr(app.filedialog, "askdirectory",
                        lambda **k: str(tmp_path))
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *a, **k: None)
    a._export_branch_csvs()
    csvs = sorted(f for f in os.listdir(str(tmp_path)) if f.endswith(".csv"))
    assert len(csvs) == 4
    assert all("_d_" in f.lower() for f in csvs)
    with open(os.path.join(str(tmp_path), "_export.provenance.json")) as f:
        prov = json.load(f)
    p = prov["params"]
    assert p["n_csv"] == 4
    assert p["n_decompression"] == 4                # was 2
    assert p["n_compression"] == 0                  # was 2 (files that never existed)
    assert len(p["branches"]) == 4                  # one entry per FILE
    assert sorted(p["branches"]) == csvs
    assert len(prov["files"]) == 4


@_gui
def test_bugfix_f5_write_tagged_csvs_takes_a_per_record_sequence(tmp_path):
    """The positional form is what makes colliding labels tag correctly;
    the legacy {label: branch} mapping still works for existing callers."""
    res = _collide()
    seq = _APP._write_tagged_csvs(res, ["C", "D", "D", "C"], str(tmp_path))
    assert [os.path.basename(p) for p in seq] == [
        "Y04_A_12p5_C_absorbance.csv",
        "Y04_A_12p50_D_absorbance.csv",
        "Y04_A_12p500_D_absorbance.csv",
        "Y04_B_20p0_C_absorbance.csv"]
    d2 = tmp_path / "dict"
    d2.mkdir()
    byname = _APP._write_tagged_csvs(res, {res[3]["label"]: "D"}, str(d2))
    assert os.path.basename(byname[3]) == "Y04_B_20p0_D_absorbance.csv"
    assert os.path.basename(byname[0]) == "Y04_A_12p5_C_absorbance.csv"


# ------------------------------------------------------------------- F6 ----
@_gui
def test_bugfix_f6_tick_skips_while_a_modal_is_open(tmp_path, monkeypatch):
    """Tk after-jobs fire normally during a grab_set(), so a poll that
    landed while a dialog was open re-ran the pipeline and replaced
    self.results / trace_vars / dvars underneath it."""
    a = _APP
    calls = []
    monkeypatch.setattr(a, "_rescan", lambda auto=False: calls.append(auto))
    a.auto_rescan.set(True)
    a.in_var.set(str(tmp_path))
    a._last_scan = (str(tmp_path), set())
    modal = tk.Toplevel(_root)
    modal.geometry("100x100+3200+100")
    _root.update()
    modal.grab_set()
    try:
        assert _root.grab_current() is not None
        a._auto_rescan_tick()
        a._cancel_auto_rescan()
        assert calls == []                      # not under the modal
    finally:
        modal.grab_release()
        modal.destroy()
        _root.update()
    a._auto_rescan_tick()                       # ... and it resumes after
    a._cancel_auto_rescan()
    assert calls == [True]


# ------------------------------------------------------------------- F7 ----
@_gui
def test_bugfix_f7_tick_does_not_orphan_its_own_timer(tmp_path, monkeypatch):
    """The tick DROPPED its handle instead of cancelling it, so any entry
    that was not the timer firing left a queued job behind and the
    finally: armed a second one - 20 stray ticks took the after-queue from
    1 job to 21, of which 20 survived _cancel_auto_rescan()."""
    a = _APP

    def jobs():
        return set(_root.tk.call("after", "info"))

    monkeypatch.setattr(a, "_rescan", lambda auto=False: None)
    a.in_var.set(str(tmp_path))
    a._last_scan = (str(tmp_path), set())
    a.auto_rescan.set(True)
    a._schedule_auto_rescan()
    base = jobs()
    assert a._auto_rescan_job in base
    for _ in range(20):
        a._auto_rescan_tick()
    assert len(jobs()) == len(base)             # exactly one job, still
    job = a._auto_rescan_job
    a._cancel_auto_rescan()
    a.auto_rescan.set(False)
    left = jobs()
    assert job not in left
    assert len(left) == len(base) - 1           # nothing survived the cancel


# ------------------------------------------------------------------- F8 ----
def _fake_hdrop(paths):
    """A genuine DROPFILES block, byte-for-byte what Explorer hands over."""
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.GlobalAlloc.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    blob = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    data = struct.pack("<IiiII", 20, 0, 0, 0, 1) + blob   # fWide = 1
    h = k32.GlobalAlloc(0x0002, len(data))
    p = k32.GlobalLock(ctypes.c_void_p(h))
    ctypes.memmove(p, data, len(data))
    k32.GlobalUnlock(ctypes.c_void_p(h))
    return h


def _real_shell32():
    import ctypes
    from ctypes import wintypes
    sh = ctypes.windll.shell32
    sh.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                  wintypes.LPWSTR, wintypes.UINT]
    sh.DragQueryFileW.restype = wintypes.UINT
    sh.DragFinish.argtypes = [wintypes.HANDLE]
    return sh


@_gui
@_win
@pytest.mark.parametrize("hdrop", [0, 1, 2, 0xDEADBEEF, -1, 0x7FFFFFFFFFFF])
def test_bugfix_f8_bogus_hdrop_is_rejected(hdrop, monkeypatch):
    """The window has DragAcceptFiles on, so any process can PostMessage
    WM_DROPFILES with a garbage wparam. DragQueryFileW on an invalid
    handle fail-fasted the whole process with 0xC0000409 - uncatchable by
    the try/except in _drop_wndproc. Measured before the fix: hdrop=1 and
    hdrop=2 both killed the interpreter (returncode 0xC0000409)."""
    monkeypatch.setattr(_APP, "_shell32", _real_shell32(), raising=False)
    assert _APP._drop_paths(hdrop) == []


@_gui
@_win
def test_bugfix_f8_a_real_drop_still_works(tmp_path, monkeypatch):
    """Positive control: the validation must not break the feature."""
    monkeypatch.setattr(_APP, "_shell32", _real_shell32(), raising=False)
    want = [str(tmp_path), os.path.join(str(tmp_path), "a.txt")]
    assert _APP._drop_paths(_fake_hdrop(want)) == want


# ------------------------------------------------------------------- C1 ----
@_gui
def test_bugfix_c1_branch_label_is_one_capped_line():
    """legend_branch_c / _d are free-text entries whose value went into the
    legend verbatim: 'a\\nb' gave a two-line key and 'X'*500 a
    500-character one."""
    a = _APP
    a.legend_branch_tags.set(True)
    try:
        a.legend_branch_c.set("a\nb")
        assert a._branch_label("C") == "a b"
        a.legend_branch_c.set("first\r\n\tsecond")
        assert a._branch_label("C") == "first second"
        a.legend_branch_c.set("X" * 500)
        assert len(a._branch_label("C")) == app.BRANCH_LABEL_MAX
        a.legend_branch_c.set("  \n  ")
        assert a._branch_label("C") == "C"          # blank -> the letter
        a.legend_branch_c.set(" comp ")
        assert a._branch_label("C") == "comp"       # ordinary case unchanged
        a.legend_branch_c.set("two  spaces")
        assert a._branch_label("C") == "two  spaces"
    finally:
        a.legend_branch_c.set("")
        a.legend_branch_tags.set(False)


# ------------------------------------------------------------------- C2 ----
@_gui
def test_bugfix_c2_chip_width_is_capped(tmp_path, monkeypatch):
    """_FIELD_W followed the Variable name, so a 120-character name gave
    EVERY chip combobox width=120 and blew the dialog layout."""
    monkeypatch.setattr(app.simpledialog, "askstring", lambda *a, **k: "V")
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *a, **k: None)
    _APP.xvar_choice.set(app.XVAR_CUSTOM)
    _APP.xvar_name.set("V" * 120)
    with _namefmt(_make_files(tmp_path, _BEAMLINE_NAMES)) as d:
        vals, width = _chip_values(d)
        assert vals and width == 24


# ------------------------------------------------------------------- C3 ----
@_gui
def test_bugfix_c3_preview_cap_is_disclosed(tmp_path, monkeypatch):
    """The preview parses at most 500 files, and 'matched N / 500' looked
    like the whole folder."""
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *a, **k: None)
    n = app.NAMEFMT_PREVIEW_CAP + 20
    _make_files(tmp_path, ["vis_Y04_Arch29_%dp5_s_C.001" % i
                           for i in range(n)])
    with _namefmt(str(tmp_path), save_as=False) as d:
        lbl = _matched_text(d)
    assert lbl.startswith("matched ")
    assert "/ %d files" % app.NAMEFMT_PREVIEW_CAP in lbl
    assert "first %d of %d" % (app.NAMEFMT_PREVIEW_CAP, n) in lbl


@_gui
def test_bugfix_c3_small_folder_says_nothing_extra(tmp_path, monkeypatch):
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *a, **k: None)
    with _namefmt(_make_files(tmp_path, _BEAMLINE_NAMES), save_as=False) as d:
        lbl = _matched_text(d)
    assert lbl == "matched 3 / 3 files"
