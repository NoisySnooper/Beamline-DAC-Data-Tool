"""Formula-editor UI tests (Phase F2): the visible half of formulas.py.

formulas.py itself is covered by test_formulas.py; what is locked here is
the wiring -- the derived column variants the App registers and fills, the
Formulas section's CRUD and its built-in protection, the row dot as the ONE
activation (formula -> Y axis -> figure), the missing-column skip and its
status line, the separate-CSV export with its single provenance sidecar,
and the preset round trip (including a preset whose formula no longer
exists, and the mid-restore gap that used to freeze the program).

Needs a Tk display, so the module skips on a headless box. Dialogs are
opened for real, so every Toplevel born here is forced off-screen
(+3200+100, the project's probe convention) and torn down immediately: a
test run must never flash a window at the user.
"""
import contextlib
import json
import os
import re
import time

import numpy as np
import pytest

import formulas as F

try:
    import tkinter as tk
    # Reuse the default root if another GUI test module already made one:
    # this Windows Store Python cannot spin up a SECOND Tk interpreter.
    _root = tk._default_root or tk.Tk()
    _root.withdraw()
    import app
    _HAVE_GUI = True
except Exception:
    _HAVE_GUI = False

_APP = None


@pytest.fixture(scope="session", autouse=True)
def _shared_app():
    """Build the App LAZILY, at first test execution rather than at import
    (test_bugfixes.py's convention: the FIRST App on the shared root is what
    gives that withdrawn root its geometry, so no module may build one while
    the others are still importing)."""
    global _APP
    if _HAVE_GUI and _APP is None:
        _APP = app.App(_root)
        _APP._save_settings = lambda: None
    yield


_gui = pytest.mark.skipif(not _HAVE_GUI, reason="no Tk display")

OFF = "+3200+100"
TOKEN = "formula: Pct T"


@contextlib.contextmanager
def _offscreen():
    """Park every Toplevel created inside the block off the visible desktop."""
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
def _res(label, pval):
    """A minimal engine-style record whose channels give a finite ratio."""
    n = 64
    wl = np.linspace(400.0, 1000.0, n)
    s = np.linspace(5.0, 9.0, n)
    b = np.linspace(10.0, 14.0, n)
    d = np.ones(n)
    with np.errstate(all="ignore"):
        a = -np.log10((s - d) / (b - d))
    return {"label": label, "dac": "Y04", "sample": "fo90",
            "pressure_str": "%gp0" % pval, "pressure_val": pval, "rep": 1,
            "branch_tag": None, "wl": wl, "wn": 1e7 / wl, "absorbance": a,
            "dark_c": d, "bg_c": b, "samp_c": s}


def _load(*records):
    _APP.results = list(records)
    _APP._build_trace_checks()
    _root.update()


def _walk(w, out=None):
    out = [] if out is None else out
    out.append(w)
    for c in w.winfo_children():
        _walk(c, out)
    return out


def _texts(w):
    got = []
    for x in _walk(w):
        try:
            t = x.cget("text")
        except tk.TclError:
            continue
        if isinstance(t, str) and t:
            got.append(t)
    return got


def _tops():
    return [w for w in _root.winfo_children() if isinstance(w, tk.Toplevel)]


def _add(name, expr, unit=""):
    """Append a custom formula the way the editor's Save does."""
    q = F.make_quantity(name, expr, unit,
                        taken=[x["key"] for x in _APP.quantities])
    _APP.quantities.append(q)
    _APP._refresh_quantity_rows()
    _APP._refresh_ydata_values()
    return q


def _pick(q):
    """Click the formula's row dot -- the one activation control."""
    _APP._qty_sel.set(q["key"])
    _APP._on_qty_row_pick()
    _root.update()


def _section():
    return [r for r in _APP._collapsibles if r["key"] == "Formulas"][0]


def _entries(win):
    return [w for w in _walk(win) if w.winfo_class() == "TEntry"]


def _round_btn(win, text):
    return [w for w in _walk(win)
            if isinstance(w, app.RoundButton) and w.cget("text") == text]


def _settle(win):
    """Let the editor's ~200 ms debounce elapse, then read the live state.

    The validation runs from a private closure on a Tk after-job, which is
    the point of the debounce; the test waits it out rather than reaching
    into the dialog for a handle that deliberately does not exist."""
    _root.update()
    time.sleep(0.3)
    _root.update()
    return _editor_state(win)


def _editor_state(win):
    """({'uses': ..., 'preview': ..., 'key': ...}, problems), read straight
    off the live editor's labels."""
    probs, state = [], {}
    for t in _texts(win):
        if t.startswith("- "):
            probs.extend(x[2:] for x in t.split("\n") if x.startswith("- "))
        if t.startswith("uses: "):
            state["uses"] = t[6:]
        if t.startswith("preview ("):
            state["preview"] = t
        if t.startswith("CSV column / file name:"):
            state["key"] = t.split(":", 1)[1].strip()
    return state, probs


@pytest.fixture(autouse=True)
def _clean_state():
    """Every test starts from the shipped formulas with nothing picked, and
    leaves no dialog, no custom formula and no loaded data behind."""
    if not _HAVE_GUI:
        yield
        return

    def _reset():
        a = _APP
        a.quantities = F.default_quantities()
        a.settings.pop("quantities", None)
        a._qty_sel.set("")
        a.active_qty.set("")
        a.ydata.set("absorbance")
        a.mode.set("overlay")
        a.wf_mode.set("off")
        a.ylabel_v.set("")
        a._label_edited["ylabel"] = False
        a.show_notch.set(False)
        a.show_smooth.set(False)
        a.notch_cache.clear()
        a.smooth_cache.clear()
        a._refresh_quantity_rows()
        a._refresh_ydata_values()
    _reset()
    yield
    for w in _tops():
        try:
            w.grab_release()
            w.destroy()
        except tk.TclError:
            pass
    _APP.results = []
    _APP.trace_vars.clear()
    _APP.dvars.clear()
    _reset()
    _root.update()


# ------------------------------------------------------- columns + arrays ---
@_gui
def test_derived_column_variants_are_registered():
    """F1's note: Phase F2 adds the defringed / smoothed variants with
    add_column, and the pure module picks them up unchanged."""
    for name in ("Sf", "Bf", "Af", "As"):
        assert F.canonical(name) == name
        assert F.COLUMNS[name]["desc"] and F.COLUMNS[name]["tex"]
    assert F.expr_to_mathtext("Af - As") == r"$A_{f} - A_{s}$"


@_gui
def test_column_dict_is_explicit_and_tracks_the_switches():
    """The arrays are built per record by the App, never left to the
    result-dict fallback: 'sample' in an engine result is the sample's NAME,
    and S must be its counts. A variant whose processing is off is simply
    absent."""
    a = _APP
    r = _res("Y04 fo90 1.39 GPa", 1.39)
    _load(r)
    cols = a._formula_columns(r)
    assert set(cols) == {"S", "B", "D", "wl", "A"}
    assert np.allclose(cols["S"], r["samp_c"])       # counts, not "fo90"
    assert np.allclose(cols["B"], r["bg_c"])
    assert np.allclose(cols["D"], r["dark_c"])
    a.show_notch.set(True)
    a.show_smooth.set(True)
    cols = a._formula_columns(r)
    assert {"Sf", "Bf", "Af", "As"} <= set(cols)
    assert cols["Sf"].shape == r["samp_c"].shape


@_gui
def test_mathtext_images_are_cached_per_color_and_survive_a_rebuild():
    """The typeset formula is the star of each row; it is cached per
    (text, color, size) so a theme switch is a lookup, not a re-render."""
    a = _APP
    tex = a.quantities[0]["latex"]
    red = a._mathtext_image(tex, "#ff0000")
    assert red is not None
    assert a._mathtext_image(tex, "#ff0000") is red      # cache hit
    green = a._mathtext_image(tex, "#00ff00")
    assert green is not None and green is not red        # recolored, not reused
    a._apply_brand()                                     # theme pass rebuilds
    _root.update()
    assert len(a._qty_rows) == len(a.quantities)


# -------------------------------------------------------- the panel (UX) ---
@_gui
def test_the_panel_speaks_formulas_and_hides_the_csv_key():
    """The user-facing word is 'formula', and the export slug is an export
    detail: it belongs in the editor, not in every list row."""
    a = _APP
    _add("Ratio SB", "S / B")
    body = _section()["cont"]
    assert not [t for t in _texts(body) if "quantit" in t.lower()]
    uses = [t for t in _texts(body) if t.startswith("uses")]
    assert uses == ["uses: B, D, S", "uses: B, D, S", "uses: B, S"]
    assert not [t for t in _texts(body) if "Ratio_SB" in t]
    assert a._qty_exp_btn.cget("text") == "Save formula CSVs…"
    # one activation mechanism: no second 'Active' control to disagree
    assert not hasattr(a, "_qty_active_cb")
    assert "Active" not in _texts(body)


@_gui
def test_nothing_is_picked_until_a_dot_is_clicked():
    a = _APP
    assert a._qty_sel.get() == "" and a.active_qty.get() == ""
    assert a.ydata.get() == "absorbance"
    for b in (a._qty_edit_btn, a._qty_del_btn, a._qty_exp_btn):
        assert str(b.cget("state")) == "disabled"
    q = _add("Ratio SB", "S / B")
    _pick(q)
    for b in (a._qty_edit_btn, a._qty_del_btn, a._qty_exp_btn):
        assert str(b.cget("state")) == "normal"
    assert a._qty_edit_btn.cget("text") == "Edit…"


# ------------------------------------------------------------------ CRUD ---
@_gui
def test_formula_crud_roundtrip_through_settings():
    a = _APP
    q = _add("Ratio SB", "S / B")
    a._save_quantities()
    stored = a.settings["quantities"]
    assert [x["name"] for x in stored] == ["Ratio SB"]   # built-ins not stored
    assert all("builtin" not in x for x in stored)
    assert stored[0]["latex"] == F.expr_to_mathtext("S / B")

    a._qty_notes = []
    back = a._load_quantities()
    assert [x["name"] for x in back] == ["Absorbance", "Transmittance",
                                         "Ratio SB"]
    assert back[-1]["expr"] == "S / B" and back[-1]["key"] == q["key"]
    assert back[0]["builtin"] and not back[-1]["builtin"]
    assert a._qty_notes == []

    # an invalid stored formula is dropped, with one line for the log
    a.settings["quantities"].append({"name": "Sneaky", "expr": "S.mean()",
                                     "key": "Sneaky"})
    a._qty_notes = []
    back = a._load_quantities()
    assert [x["name"] for x in back] == ["Absorbance", "Transmittance",
                                         "Ratio SB"]
    assert len(a._qty_notes) == 1
    assert "Sneaky" in a._qty_notes[0] and "method calls" in a._qty_notes[0]


@_gui
def test_delete_removes_the_formula_from_the_panel_and_from_settings(
        monkeypatch):
    a = _APP
    q = _add("Ratio SB", "S / B")
    a._save_quantities()
    assert len(a.settings["quantities"]) == 1
    _pick(q)
    assert str(a._qty_del_btn.cget("state")) == "normal"
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *x, **k: True)
    a._delete_quantity()
    _root.update()
    assert [x["name"] for x in a.quantities] == ["Absorbance",
                                                 "Transmittance"]
    assert a.settings["quantities"] == []
    assert a.active_qty.get() == ""          # the plotted pick went with it
    assert a.ydata.get() == "absorbance"


# ---------------------------------------------------------------- editor ---
@_gui
def test_editor_is_two_panel_and_its_symbol_chips_insert_at_the_cursor():
    a = _APP
    with _offscreen():
        win = a._new_quantity()
        _root.update()
        assert win.title() == "New formula"
        # the Guide card replaces the old in-form legend block
        guides = [w for w in _walk(win) if isinstance(w, tk.Text)]
        assert len(guides) == 1
        gtxt = guides[0].get("1.0", "end")
        for head in ("FORMULAS", "WRITING A FORMULA", "EXAMPLES",
                     "THE COLUMNS", "FUNCTIONS", "NAME AND UNIT",
                     "WHEN YOU SAVE", "CSVs", "SAFETY"):
            assert head in gtxt
        assert "100 * (S - D) / (B - D)" in gtxt        # worked example
        assert all(c["name"] in gtxt for c in F.column_legend())
        assert "Columns you may use" not in _texts(win)

        chips = {w.cget("text"): w for w in _walk(win)
                 if isinstance(w, tk.Button)
                 and str(w.cget("cursor")) == "hand2"}
        assert set(F.column_names()) <= set(chips)
        assert set(f + "()" for f in F.function_names()) <= set(chips)
        assert "click a symbol to insert it" in _texts(win)

        expr_e = _entries(win)[2]
        expr_e.delete(0, "end")
        for sym in ("S", "B"):
            chips[sym].invoke()
            _root.update()
        assert expr_e.get() == "SB"
        expr_e.delete(0, "end")
        chips["log10()"].invoke()
        _root.update()
        assert expr_e.get() == "log10()"
        assert expr_e.index("insert") == 6              # caret inside ( )
        win.destroy()
        _root.update()


@_gui
def test_editor_saves_a_valid_formula_and_refuses_an_invalid_one():
    a = _APP
    _load(_res("Y04 fo90 1.39 GPa", 1.39))
    with _offscreen():
        win = a._new_quantity()
        _root.update()
        ents = _entries(win)
        assert len(ents) == 4                     # name, unit, expr, latex
        save = _round_btn(win, "Save")
        assert len(save) == 1
        save = save[0]

        ents[0].insert(0, "Pct T")
        ents[1].insert(0, "%")
        ents[2].insert(0, "100 * (S - D) / (B - D)")
        state, probs = _settle(win)
        assert probs == []
        assert state["uses"] == "B, D, S"
        assert state["key"] == "Pct_T"            # the slug lives HERE
        assert state["preview"].startswith("preview (Y04 fo90 1.39 GPa)")
        assert str(save.cget("state")) == "normal"
        assert ents[3].get() == "auto"            # LaTeX ghost: auto-derived
        good = state["preview"]

        # an invalid expression: gentle problem list, Save off, and the last
        # good picture / preview stay on screen instead of blinking out
        ents[2].delete(0, "end")
        ents[2].insert(0, "S.mean() / B")
        state, probs = _settle(win)
        assert any("method calls" in p for p in probs)
        assert str(save.cget("state")) == "disabled"
        assert state["preview"] == good

        ents[2].delete(0, "end")
        ents[2].insert(0, "100 * (S - D) / (B - D)")
        _settle(win)
        save.invoke()
        _root.update()
    saved = a.quantities[-1]
    assert saved["name"] == "Pct T" and saved["unit"] == "%"
    assert saved["latex"] == F.expr_to_mathtext("100 * (S - D) / (B - D)")
    assert a.settings["quantities"][0]["unit"] == "%"
    assert a.ydata.get() == "absorbance"          # saving plots nothing


@_gui
def test_builtins_are_view_only_and_duplicate_starts_an_editable_copy(
        monkeypatch):
    a = _APP
    a._qty_sel.set("Absorbance")
    a._sync_qty_buttons()
    _root.update()
    assert a._qty_edit_btn.cget("text") == "View"          # not 'Edit...'
    assert str(a._qty_del_btn.cget("state")) == "disabled"

    said = []
    monkeypatch.setattr(app.messagebox, "showinfo",
                        lambda *x, **k: said.append(x))
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *x, **k: True)
    a._delete_quantity()                       # even called directly: refused
    assert [x["name"] for x in a.quantities] == ["Absorbance",
                                                 "Transmittance"]
    assert said

    with _offscreen():
        win = a._edit_quantity()
        _root.update()
        assert win.title() == "View formula"
        ents = _entries(win)
        assert ents and all(str(w.cget("state")) == "disabled" for w in ents)
        chips = [w for w in _walk(win) if isinstance(w, tk.Button)
                 and w.cget("text") in F.column_names()]
        assert chips and all(str(c.cget("state")) == "disabled"
                             for c in chips)          # nothing to insert into
        assert not _round_btn(win, "Save")
        dup = _round_btn(win, "Duplicate")
        assert len(dup) == 1
        before = set(str(w) for w in _tops())
        dup[0].invoke()
        _root.update()
        assert not win.winfo_exists()
        copy = [w for w in _tops() if str(w) not in before][-1]
        cents = _entries(copy)
        assert copy.title() == "New formula"
        assert cents[0].get() == "Absorbance copy"
        assert cents[2].get() == "-log10((S - D) / (B - D))"
        assert all(str(e.cget("state")) != "disabled" for e in cents)
        assert _round_btn(copy, "Save")
        copy.destroy()
        _root.update()


# ------------------------------------------- the dot -> Y axis -> figure ---
@_gui
def test_the_row_dot_reaches_every_y_picker_and_the_figure():
    a = _APP
    _load(_res("Y04 fo90 1.39 GPa", 1.39), _res("Y04 fo90 5.20 GPa", 5.2))
    q = _add("Pct T", "100 * (S - D) / (B - D)", "%")
    _pick(q)

    assert a.active_qty.get() == q["key"]
    assert a.ydata.get() == TOKEN
    # v1.4.8: the Plot-mode "Overlay Y" copy is gone; Axis + Quick Access
    assert len(a._ydata_combos) == 2
    for cb in a._ydata_combos:
        assert list(cb.cget("values")) == ["absorbance", "sample",
                                           "background", "dark", TOKEN]

    a._redraw_now()
    _root.update()
    assert len(a.ax.lines) == 2
    for line, r in zip(a.ax.lines, a.results):
        want = F.evaluate_quantity(q, a._formula_columns(r))
        assert np.allclose(np.asarray(line.get_ydata(), float), want)
    assert a.ax.get_ylabel() == "Pct T (%)"     # name + unit, Series style
    assert a._qty_status.cget("text") == "plotting 'Pct T' for 2 trace(s)"

    # back to absorbance: the default is never taken away
    a.ylabel_v.set("")
    a._label_edited["ylabel"] = False
    a.ydata.set("absorbance")
    a._redraw_now()
    _root.update()
    assert a.ax.get_ylabel() == "Absorbance"
    assert a._qty_status.cget("text") == ""


@_gui
def test_missing_column_skips_the_trace_once_and_never_crashes():
    a = _APP
    _load(_res("Y04 fo90 1.39 GPa", 1.39), _res("Y04 fo90 5.20 GPa", 5.2))
    q = _add("Fringe residual", "Af - A")
    a.log.delete("1.0", "end")
    _pick(q)
    a._redraw_now()
    _root.update()

    assert len(a.ax.lines) == 0                  # skipped, not crashed
    log = a.log.get("1.0", "end")
    assert log.count("no data for column 'Af'") == 1
    assert "2 of 2 trace(s) skipped" in log
    status = a._qty_status.cget("text")
    assert "skipped" in status and "Af" in status

    a._redraw_now()                              # no per-redraw spam
    _root.update()
    assert a.log.get("1.0", "end").count("no data for column 'Af'") == 1

    a.show_notch.set(True)                       # the column exists now
    a._redraw_now()
    _root.update()
    assert len(a.ax.lines) == 2
    want = F.evaluate_quantity(q, a._formula_columns(a.results[0]))
    assert np.allclose(np.asarray(a.ax.lines[0].get_ydata(), float), want)
    assert a._qty_status.cget("text") == ("plotting 'Fringe residual' for "
                                          "2 trace(s)")


# ----------------------------------------------------------------- export ---
@_gui
def test_export_writes_one_csv_per_trace_plus_one_sidecar(tmp_path,
                                                          monkeypatch):
    a = _APP
    _load(_res("Y04 fo90 1.39 GPa", 1.39), _res("Y04 fo90 5.20 GPa", 5.2))
    q = _add("Pct T", "100 * (S - D) / (B - D)", "%")
    _pick(q)
    monkeypatch.setattr(app.filedialog, "askdirectory",
                        lambda *x, **k: str(tmp_path))
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *x, **k: None)
    a._export_quantity_csvs()

    want = sorted([re.sub(r"[^A-Za-z0-9.+-]+", "_", r["label"])
                   + "_" + q["key"] + ".csv" for r in a.results]
                  + ["_export.provenance.json"])
    assert sorted(os.listdir(str(tmp_path))) == want
    # the frozen absorbance schema is untouched: nothing else was written
    assert not [n for n in os.listdir(str(tmp_path)) if "absorbance" in n]

    csv = str(tmp_path / ("Y04_fo90_1.39_GPa_%s.csv" % q["key"]))
    with open(csv, "r", newline="", encoding="utf-8") as f:
        raw = f.read()                    # newline="": keep engine's CRLF
    assert "# expr: 100 * (S - D) / (B - D)" in raw
    assert "# formula: Pct T" in raw
    assert "Wavelength_nm,%s" % q["key"] in raw
    body = [ln for ln in raw.strip().split("\r\n") if not ln.startswith("#")]
    vals = F.evaluate_quantity(q, a._formula_columns(a.results[0]))
    assert len(body) == 1 + len(vals)
    assert float(body[1].split(",")[1]) == pytest.approx(float(vals[0]))

    prov = json.loads((tmp_path / "_export.provenance.json").read_text(
        encoding="utf-8"))
    assert prov["kind"] == "quantity_csv"
    assert prov["params"]["n_csv"] == 2 and prov["params"]["n_skipped"] == 0
    qs = prov["params"]["quantities"]
    assert len(qs) == 1 and qs[0]["expr"] == q["expr"]
    assert qs[0]["key"] == q["key"] and qs[0]["unit"] == "%"
    assert len(prov["files"]) == 2


# ---------------------------------------------------------------- presets ---
@_gui
def test_preset_carries_the_picked_key_and_a_stale_one_falls_back():
    """The stale case is also the freeze regression: a restore writes ydata
    BEFORE active_qty, so for one assignment the Y picker names a formula
    that is not active. _channel used to get 'formula: ...' as a dict key,
    the KeyError reached _redraw_now, and its plot-error dialog hung the
    program."""
    a = _APP
    _load(_res("Y04 fo90 1.39 GPa", 1.39))
    q = _add("Pct T", "100 * (S - D) / (B - D)", "%")
    _pick(q)

    assert "active_qty" in a._preset_registry()
    snap = a._snapshot()
    assert snap["active_qty"] == q["key"]
    assert snap["ydata"] == TOKEN

    # the formula is gone (another machine, a cleared settings file): the
    # preset must not brick the plot -- and must not block on a dialog
    a.quantities = [x for x in a.quantities if x["key"] != q["key"]]
    a._refresh_quantity_rows()
    a._restore(snap)
    _root.update()
    assert a.active_qty.get() == ""
    assert a.ydata.get() == "absorbance"

    # with the formula present again the same preset restores it
    a.quantities.append(q)
    a._refresh_quantity_rows()
    a._restore(snap)
    _root.update()
    assert a.active_qty.get() == q["key"]
    assert a.ydata.get() == TOKEN
    a._redraw_now()
    _root.update()
    assert a.ax.get_ylabel() == "Pct T (%)"
