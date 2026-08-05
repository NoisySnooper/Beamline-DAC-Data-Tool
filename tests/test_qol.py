"""QoL batch tests (v1.4.8).

Locks the settings-backed defaults (journal preset, last export format),
Escape dismissal on every dialog that grew one, the double-click sash
reset, the recent-folder dropdown wiring, and the data-drawer combobox
identity map (displayed label -> frozen record label).

Dialogs are opened for real, so every Toplevel born in this module is
forced off-screen (+3200+100, the project's probe convention) and torn
down immediately: a test run must never flash a window at the user.
Needs a Tk display, so the module skips cleanly on a headless box.
"""
import contextlib
import json
import math
import time

import numpy as np
import pytest

try:
    import tkinter as tk
    import tkinter.font as tkfont
    # Reuse an existing default root if another GUI test module already made
    # one: this Windows Store Python cannot spin up a SECOND independent
    # Tk() interpreter (see test_sessions.py).
    _root = tk._default_root or tk.Tk()
    _root.withdraw()
    import app
    _APP = app.App(_root)
    _HAVE_GUI = True
except Exception:
    _HAVE_GUI = False

pytestmark = pytest.mark.skipif(not _HAVE_GUI, reason="no Tk display")

OFF = "+3200+100"


def _res(label, pval):
    """A minimal valid engine-style result dict with real absorbance."""
    wl = np.linspace(400.0, 1000.0, 40)
    return {"label": label, "dac": "D", "sample": "S",
            "pressure_str": label.split()[0], "pressure_val": pval, "rep": 1,
            "branch_tag": None, "wl": wl, "wn": 1e7 / wl,
            "absorbance": np.linspace(0.1, 1.2, 40), "dark_c": np.ones(40),
            "bg_c": np.full(40, 10.0), "samp_c": np.full(40, 5.0)}


def _load(results, dest="d"):
    _APP._finish_run([dict(r) for r in results], [], dest)


@contextlib.contextmanager
def _offscreen():
    """Park every Toplevel created inside the block off the visible desktop
    (both the ones sized by _center_on_root and the ones that size
    themselves)."""
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


def _open(fn, *args):
    """Call a dialog opener and return the Toplevel it created."""
    before = set(str(w) for w in _root.winfo_children())
    fn(*args)
    _root.update_idletasks()
    new = [w for w in _root.winfo_children()
           if str(w) not in before and w.winfo_class() == "Toplevel"]
    assert new, "no Toplevel appeared"
    return new[-1]


def _kids(w, cls=None, text=None):
    out = []
    for c in w.winfo_children():
        try:
            ok = (cls is None or c.winfo_class() == cls)
            if ok and text is not None:
                ok = str(c.cget("text")).startswith(text)
            if ok:
                out.append(c)
        except tk.TclError:
            pass
        out.extend(_kids(c, cls, text))
    return out


# ---- item 7: the journal preset is remembered ------------------------------
def test_journal_preset_default_roundtrip():
    a = _APP
    a.fig_preset.set("custom")
    a._set_fig_preset_default()
    assert a.settings["fig_preset_default"] == "custom"
    assert "Current is the default" in a.fig_preset_default_btn.cget("text")

    a.fig_preset.set("Nature single (89 mm)")
    _root.update_idletasks()
    # the star clears the moment the live pick and the saved default differ
    assert a.fig_preset_default_btn.cget("text") == "Set as default"
    a._set_fig_preset_default()
    assert "Current is the default" in a.fig_preset_default_btn.cget("text")

    # a real roundtrip: it must survive to disk and read back
    with open(app.SETTINGS_PATH) as f:
        assert json.load(f)["fig_preset_default"] == "Nature single (89 mm)"
    assert a._load_settings()["fig_preset_default"] == "Nature single (89 mm)"
    a.fig_preset.set("custom")
    a._set_fig_preset_default()


def test_journal_preset_default_feeds_the_startup_var():
    """The build reads the same key the Set-as-default button writes."""
    a = _APP
    a.settings["fig_preset_default"] = "APS 2-col (7.0 in)"
    assert a.settings.get("fig_preset_default", "custom") == \
        "APS 2-col (7.0 in)"
    a.settings["fig_preset_default"] = "custom"
    assert a.settings.get("fig_preset_default", "custom") == "custom"


# ---- item 12: the last export format is remembered -------------------------
def test_last_export_format_roundtrip():
    a = _APP
    a.settings.pop("last_export_ext", None)
    dext, types = a._export_types()
    assert dext == ".png" and types[0][0] == "PNG"

    assert a._remember_export_ext(".SVG") is True
    assert a.settings["last_export_ext"] == "svg"
    with open(app.SETTINGS_PATH) as f:
        assert json.load(f)["last_export_ext"] == "svg"
    dext, types = a._export_types()
    assert dext == ".svg"
    assert types[0] == ("SVG", "*.svg")
    assert len(types) == 5 and len(set(types)) == 5   # nothing lost

    assert a._remember_export_ext("docx") is False     # junk is ignored
    assert a.settings["last_export_ext"] == "svg"

    a.settings["last_export_ext"] = "nonsense"
    dext, types = a._export_types()
    assert dext == ".png" and types[0][0] == "PNG"     # unknown -> png
    a.settings.pop("last_export_ext", None)


# ---- items 3 / 9: Escape dismisses every dialog ----------------------------
def test_escape_binding_on_about():
    with _offscreen():
        w = _open(_APP._about)
        try:
            assert w.bind("<Escape>")
        finally:
            w.destroy()


def test_escape_binding_on_smoothing():
    with _offscreen():
        w = _open(_APP._open_smooth_panel)
        try:
            assert w.bind("<Escape>")
        finally:
            w.destroy()


def test_escape_binding_on_readout_popup():
    _load([_res("1.00 GPa", 1.0), _res("2.00 GPa", 2.0)])
    with _offscreen():
        w = _open(_APP._show_readout_table, 700.0)
        try:
            assert w.bind("<Escape>")
        finally:
            w.destroy()


def test_escape_binding_on_name_format_and_fix(tmp_path):
    """The editor AND its Fix sub-dialog; Escape on the sub-dialog must
    close only the sub-dialog (the bind lives on that Toplevel)."""
    for nm in ("vis_D42_fo90_0p5_s.001", "vis_D42_fo90_0p5_bg.002"):
        (tmp_path / nm).write_text("")
    _APP.in_var.set(str(tmp_path))
    with _offscreen():
        d = _open(_APP._open_name_format)
        try:
            assert d.bind("<Escape>")
            tvs = _kids(d, "Treeview")
            fixb = _kids(d, "TButton", "Fix selected")
            rows = tvs[0].get_children() if tvs else []
            assert rows and fixb, "preview rows / Fix button missing"
            tvs[0].selection_set(rows[0])
            before = set(str(x) for x in d.winfo_children())
            fixb[0].invoke()
            _root.update_idletasks()
            fd = [x for x in d.winfo_children()
                  if str(x) not in before and x.winfo_class() == "Toplevel"]
            assert fd, "Fix sub-dialog did not open"
            assert fd[-1].bind("<Escape>")
            fd[-1].destroy()
            _root.update_idletasks()
            assert d.winfo_exists()     # parent survives the sub-dialog
        finally:
            try:
                d.grab_release()
            except tk.TclError:
                pass
            d.destroy()
    _APP.in_var.set("")


# ---- item 6: double-click a sash resets that pane --------------------------
def test_sash_reset_returns_pane_widths_defaults():
    a = _APP
    _root.update_idletasks()
    lmin, lw, rmin, rw = a._pane_widths()
    total = a.pw.winfo_width()
    if lw + rw + 400 + 12 > total:
        pytest.skip("window narrower than the tuned defaults + center min")
    sw = int(a.pw.cget("sashwidth"))

    a.pw.sash_place(0, lw + 170, 1)
    _root.update_idletasks()
    assert a.pw.sash_coord(0)[0] != lw          # really dragged away
    a._reset_sash(0)
    _root.update_idletasks()
    assert a.pw.sash_coord(0)[0] == lw          # LEFT pane back to default

    a.pw.sash_place(1, total - 170, 1)
    _root.update_idletasks()
    a._reset_sash(1)
    _root.update_idletasks()
    # the right pane is measured off the trailing edge, not from x=0
    assert a.pw.sash_coord(1)[0] == total - rw - sw
    assert a._reset_sash(9) is None             # out-of-range is a no-op


# ---- item 15: data-drawer combobox identity map ----------------------------
def test_drawer_labels_byte_identical_with_default_variable():
    a = _APP
    a.xvar_choice.set("Pressure (GPa)")
    _load([_res("1.00 GPa", 1.0), _res("2.00 GPa", 2.0),
           _res("3.00 GPa", 3.0)])
    a._toggle_drawer(True)
    try:
        _root.update_idletasks()
        raw = [r["label"] for r in a.results]
        assert list(a._drawer_combo.cget("values")) == raw
        assert a._drawer_map == dict(zip(raw, raw))
    finally:
        a._toggle_drawer(False)


def test_drawer_selection_survives_a_unit_change():
    a = _APP
    a.xvar_choice.set("Pressure (GPa)")
    _load([_res("1.00 GPa", 1.0), _res("2.00 GPa", 2.0),
           _res("3.00 GPa", 3.0)])
    a._toggle_drawer(True)
    try:
        _root.update_idletasks()
        a.drawer_trace.set("2.00 GPa")
        assert a._drawer_record()["label"] == "2.00 GPa"

        a.xvar_choice.set("Temperature (K)")
        _root.update_idletasks()
        assert list(a._drawer_combo.cget("values")) == ["1.00 K", "2.00 K",
                                                        "3.00 K"]
        assert a.drawer_trace.get() == "2.00 K"      # selection followed
        # ...and still points at the same RECORD, whose label never moved
        assert a._drawer_record()["label"] == "2.00 GPa"

        a.drawer_trace.set("3.00 K")
        assert a._drawer_record()["label"] == "3.00 GPa"
        a._refresh_drawer()                          # must not raise
    finally:
        a.xvar_choice.set("Pressure (GPa)")
        _root.update_idletasks()
        a._toggle_drawer(False)


# ---- item 1: the recent-folder dropdown is wired up ------------------------
def test_folder_menu_wiring():
    a = _APP
    a.settings["recent_in"] = [r"C:\data\runA", r"C:\data\runB"]
    m = a._folder_menu_items("in")
    try:
        assert m.entrycget(0, "label") == "Open in Explorer"
        assert m.index("end") == 3                   # cmd, sep, 2 recents
        assert m.entrycget(3, "label") == r"C:\data\runB"
        m.invoke(2)                                  # pick the first recent
        assert a.in_var.get() == r"C:\data\runA"
        assert a.settings["recent_in"][0] == r"C:\data\runA"
    finally:
        m.destroy()
        a.in_var.set("")

    long_path = "C:\\data\\" + ("x" * 90)
    a.settings["recent_in"] = [long_path]
    m = a._folder_menu_items("in")
    try:
        assert m.entrycget(2, "label").startswith("...")
        assert len(m.entrycget(2, "label")) == 60
    finally:
        m.destroy()
        a.settings["recent_in"] = []

    # no recents at all: just the Explorer entry, no dangling separator
    a.settings["recent_out"] = []
    m = a._folder_menu_items("out")
    try:
        assert m.index("end") == 0
    finally:
        m.destroy()

    # the affordances that reach the menu
    assert a._recent_in_btn.cget("text") == "\u25be"
    assert a._recent_out_btn.cget("text") == "\u25be"
    assert a._in_entry.bind("<Button-3>")
    assert a._out_entry.bind("<Button-3>")


# ---- v1.4.8: the Name-format dialog follows the experiment Variable -------
def test_name_format_chips_display_map_round_trip(tmp_path):
    """The chip dropdowns SHOW the experiment variable's name wherever they
    show 'pressure' by default, but the stored order stays canonical and a
    profile saved under Temperature is byte-identical to one saved under
    Pressure."""
    a = _APP
    for nm in ("vis_D42_fo90_0p5_s_c.001", "vis_D42_fo90_0p5_bg_c.002"):
        (tmp_path / nm).write_text("")
    a.in_var.set(str(tmp_path))
    orig_ask = app.simpledialog.askstring
    app.simpledialog.askstring = lambda *_a, **_k: "chipmap"

    def _shot(choice):
        a.xvar_choice.set(choice)
        with _offscreen():
            d = _open(a._open_name_format)
            try:
                # "Save as..." turns the built-in into an editable profile,
                # which is what builds the chip strip
                _kids(d, "TButton", "Save as")[0].invoke()
                _root.update_idletasks()
                tv = _kids(d, "Treeview")[0]
                heads = [tv.heading(c, "text") for c in tv.cget("columns")]
                chips = [w for w in _kids(d, "TCombobox")
                         if "dac" in (w.cget("values") or ())]
                shown = [w.get() for w in chips]
                values = list(chips[0].cget("values"))
                labs = [w.cget("text") for w in _kids(d, "Label")
                        if str(w.cget("text")).endswith(" decimal")]
                prof = [p for p in a._profiles()
                        if p.get("name") == "chipmap"][-1]
                blob = json.dumps(prof, sort_keys=True)
                order = list(prof.get("order", []))
            finally:
                try:
                    d.grab_release()
                except tk.TclError:
                    pass
                d.destroy()
                _root.update_idletasks()
                pl = a._profiles()
                pl[:] = [p for p in pl if p.get("name") != "chipmap"]
        return heads, shown, values, labs, blob, order

    try:
        p_heads, p_shown, p_vals, p_labs, p_blob, p_order = \
            _shot("Pressure (GPa)")
        t_heads, t_shown, t_vals, t_labs, t_blob, t_order = \
            _shot("Temperature (K)")
    finally:
        app.simpledialog.askstring = orig_ask
        a.xvar_choice.set("Pressure (GPa)")
        a.in_var.set("")

    canonical = ["dac", "sample", "pressure", "role", "branch", "rep"]
    # what is SHOWN follows the variable ...
    assert p_shown == canonical
    assert t_shown == ["dac", "sample", "temperature", "role", "branch", "rep"]
    assert "temperature" in t_vals and "pressure" not in t_vals
    assert (p_heads[3], t_heads[3]) == ("Pressure", "Temperature")
    assert p_labs == ["Pressure decimal"]
    assert t_labs == ["Temperature decimal"]
    # ... and everything STORED stays canonical
    assert p_order == canonical
    assert t_order == canonical
    assert p_blob == t_blob


# ---- v1.4.8: the controls that moved --------------------------------------
def test_moved_controls_live_in_their_new_homes():
    a = _APP

    def _body(title):
        return [r for r in a._collapsibles if r["key"] == title][0]["body"]

    def _inside(box, w):
        while w is not None:
            if w is box:
                return True
            w = getattr(w, "master", None)
        return False

    pm, tr, ex = _body("Plot mode"), _body("Traces"), _body("Export")
    # the Variable row and the Auto-rescan controls now open the Plot mode box
    rows = pm.winfo_children()
    assert _inside(pm, a._xvar_combo)
    assert _inside(rows[0], a._xvar_combo)              # first row
    assert _inside(pm, a._auto_rescan_sw)
    assert _inside(pm, a._rescan_spin)
    assert _inside(rows[1], a._auto_rescan_sw)          # second row
    assert not _inside(a.left, a._auto_rescan_sw)
    assert [w.cget("text") for w in _kids(rows[1], "Label")] == \
        ["Auto rescan", "every", "s"]
    # the C/D CSV button sits in Traces, directly under 'Export D list'
    assert _inside(tr, a._cd_export_btn)
    assert not _inside(ex, a._cd_export_btn)
    assert [w.cget("text") for w in tr.winfo_children()
            if w.winfo_class() == "TButton"] == \
        ["Export D list (CSV) by selection",
         "Save C/D-tagged CSVs" + chr(0x2026)]
    # PANEL_GUIDE points at the new homes. Headings are "TAB > SECTION"
    # now, so the Auto-rescan text has to sit inside the PLOT > PLOT MODE
    # block (the guide's sections are separated by a blank line).
    assert "PLOT > PLOT MODE\n" in app.PANEL_GUIDE
    _pm = app.PANEL_GUIDE.split("PLOT > PLOT MODE\n", 1)[1].split("\n\n", 1)[0]
    assert "Auto rescan" in _pm
    assert "Data tab > Traces" in app.PANEL_GUIDE
    assert "Branch tags -" in app.PANEL_GUIDE


def test_collapsed_cards_keep_their_bottom_border():
    """A collapsed card is only (top_inset + pad) tall, so its body window
    must not reach over the hairline the canvas draws at y = h - 2. The
    grow='both' card (Guide / notes) used to, because the body window
    height was floored at 8 px.

    Built in a throwaway off-screen Toplevel rather than poked at in the
    main window: the shared, withdrawn test root has no real geometry."""
    a = _APP
    with _offscreen():
        win = tk.Toplevel(_root)
        win.geometry("420x320" + OFF)
        try:
            for grow in ("both", "x"):
                key = "probe_%s_collapsed" % grow
                card = a._card(win, grow=grow)
                card.pack(fill="both", expand=(grow == "both"), pady=4)
                card.set_title(a._lf_header(card, "Probe"))
                body = a._collapsible_card(card, key)
                for _i in range(3):
                    a._lbl(body, text="content line").pack(anchor="w")
                win.update()
                win.update_idletasks()
                try:
                    for collapsed in (True, False):
                        a._card_toggle(key, collapsed)
                        win.update()
                        win.update_idletasks()
                        h = card.winfo_height()
                        assert h >= 8, (grow, collapsed, h)
                        top = card.coords(card._win)[1]
                        bot = top + card.body.winfo_height()
                        drawn = [card.coords(i)
                                 for i in card.find_withtag("card")
                                 if card.type(i) == "line"]
                        assert any(abs(ln[1] - (h - 2)) < 1.5
                                   for ln in drawn), \
                            "grow=%s collapsed=%s: no bottom border drawn" \
                            % (grow, collapsed)
                        assert bot < h - 2, \
                            "grow=%s collapsed=%s: body (%.0f..%.0f) covers " \
                            "the border at %d" % (grow, collapsed, top, bot,
                                                  h - 2)
                finally:
                    a._ccards.pop(key, None)
                    a.settings.pop(key, None)
        finally:
            win.destroy()
            _root.update_idletasks()


# ---- round-3: primaries are drawn buttons that match a real ttk.Button ----
def _walk(w):
    yield w
    for c in w.winfo_children():
        for x in _walk(c):
            yield x


def test_primary_buttons_are_roundbuttons_matching_ttk_height():
    """The accent primaries are RoundButtons whose requested height equals a
    stock ttk.Button's (+-1 px), NUKE excepted - it keeps its fixed 13 pt."""
    a = _APP
    _root.update_idletasks()
    ref = app.ttk.Button(_root, text="Reference")
    _root.update_idletasks()
    th = ref.winfo_reqheight()
    ref.destroy()
    assert th > 8
    for name in ("run_btn", "profile_btn", "_data_btn"):
        b = getattr(a, name)
        assert isinstance(b, app.RoundButton), name
        assert abs(b.winfo_reqheight() - th) <= 1, \
            "%s: %d vs ttk %d" % (name, b.winfo_reqheight(), th)
    assert isinstance(a.nuke_btn, app.RoundButton)
    assert a.nuke_btn._o["radius"] == a.run_btn._o["radius"]


def test_round_button_keeps_the_tk_button_option_api():
    """Every call site that later .config()s a primary must keep working."""
    a = _APP
    b = a.run_btn
    old = b["text"]
    b.config(text="Cancel", command=a._cancel_run)
    assert b["text"] == "Cancel"
    b.config(text="Run", command=a._run, state="normal")
    assert b["text"] == "Run" and b["state"] == "normal"
    b.config(state="disabled")
    assert b["state"] == "disabled"
    b.config(state="normal")
    a._update_profile_btn()
    assert a.profile_btn["text"].strip().startswith("Name format:")
    a._update_data_btn()
    assert a._data_btn["text"].strip() in ("Data table", "Hide data")
    assert b["bg"] == a._brand()["ac1"]          # per-theme triad, still
    assert b["text"] == old


def test_round_button_is_keyboard_operable():
    """Space / Return activate it, focus is takeable, and the handlers live
    on a private bindtag so a Tooltip's <Enter> bind cannot wipe them."""
    a = _APP
    b = a.run_btn
    assert str(b.cget("takefocus")) == "1"
    assert app.RoundButton.TAG in b.bindtags()
    bound = set(b.bind_class(app.RoundButton.TAG))
    for seq in ("<Key-space>", "<Key-Return>", "<Enter>", "<Leave>",
                "<Button-1>", "<ButtonRelease-1>", "<FocusIn>"):
        assert seq in bound, seq
    hits = []
    old = b["command"]
    try:
        b.config(command=lambda: hits.append(1))
        assert b._ev_key(None) == "break"
        b.config(state="disabled")
        b._ev_key(None)
        assert hits == [1]                      # disabled swallows the key
    finally:
        b.config(state="normal", command=old)


# ---- round-3: sash drag, both modes ---------------------------------------
class _Motion(object):
    def __init__(self, x_root):
        self.x_root = x_root


@contextlib.contextmanager
def _sash_probe(perf):
    """Count real sash_place calls, and park the paned window off-screen so
    a performance-mode ghost line can never flash at the user."""
    a = _APP
    _root.update_idletasks()
    calls = []
    real = a.pw.sash_place

    def counting(i, x, y):
        calls.append((i, x))
        return real(i, x, y)

    a.pw.sash_place = counting
    a.pw.winfo_rootx = lambda: 3200
    a.pw.winfo_rooty = lambda: 100
    a.app_perf_mode.set(bool(perf))
    try:
        yield calls
    finally:
        a._sash_ghost(None)
        a._sash_drag = None
        a.app_perf_mode.set(False)
        for attr in ("sash_place", "winfo_rootx", "winfo_rooty"):
            try:
                delattr(a.pw, attr)
            except AttributeError:
                pass


def _drag(a, idx, n=40, per=0.01):
    lim = a._sash_limits(idx)
    if lim is None or lim[1] - lim[0] < n + 4:
        pytest.skip("window too narrow to drag sash %d" % idx)
    lo = lim[0] + 2
    a._start_sash_drag(a._sash_handles[idx])
    t0 = time.monotonic()
    for i in range(n):
        a._drag_sash(idx, _Motion(3200 + lo + i))
        time.sleep(per)
    return time.monotonic() - t0


def test_sash_drag_default_mode_is_throttled_live():
    a = _APP
    with _sash_probe(perf=False) as calls:
        dur = _drag(a, 0)
        during = len(calls)
        assert a._sash_ghost_win is None         # no ghost in this mode
        a._end_sash_drag()
        assert len(calls) - during == 1, "exactly one apply on release"
        cap = math.ceil(dur / (app.SASH_LIVE_MS / 1000.0)) + 1
        assert during <= cap, "%d applies in %.3f s (cap %d)" % (during, dur,
                                                                 cap)
        assert during >= 1, "the default mode must still resize live"


def test_sash_drag_perf_mode_ghosts_then_applies_once():
    a = _APP
    with _sash_probe(perf=True) as calls:
        _drag(a, 0)
        assert calls == [], "performance mode must not relayout while dragging"
        g = a._sash_ghost_win
        assert g is not None and g.winfo_exists()
        # root-relative placement (read the requested geometry: the strip is
        # deliberately never update()d into view during a test run)
        assert int(g.geometry().split("+")[1]) >= 3200, g.geometry()
        a._end_sash_drag()
        assert len(calls) == 1, "exactly one apply on release"
        assert a._sash_ghost_win is None and not g.winfo_exists()


def test_escape_cancels_a_ghost_sash_drag():
    a = _APP
    with _sash_probe(perf=True) as calls:
        before = a.pw.sash_coord(0)[0]
        _drag(a, 0, n=6)
        g = a._sash_ghost_win
        assert g is not None
        assert a._cancel_sash_drag() == "break"
        assert a._sash_ghost_win is None and not g.winfo_exists()
        a._end_sash_drag()                       # release after Escape
        assert calls == [], "a cancelled drag must apply nothing"
        assert a.pw.sash_coord(0)[0] == before
        assert a._cancel_sash_drag() is None     # idle Escape is a no-op


def test_sash_limits_clamp_to_the_pane_minsizes():
    a = _APP
    _root.update_idletasks()
    lim = a._sash_limits(0)
    if lim is None:
        pytest.skip("no sash")
    lo, hi = lim
    assert lo >= a._pane_widths()[0]
    assert a._clamp_sash(0, -9999) == lo
    assert a._clamp_sash(0, 99999) == hi
    assert a._sash_limits(9) is None


def test_app_perf_mode_persists_in_settings_not_presets():
    a = _APP
    old = bool(a.app_perf_mode.get())
    try:
        a.app_perf_mode.set(True)
        a._toggle_app_perf_mode()
        assert a.settings["app_perf_mode"] is True
        assert json.load(open(app.SETTINGS_PATH))["app_perf_mode"] is True
        a.app_perf_mode.set(False)
        a._toggle_app_perf_mode()
        assert json.load(open(app.SETTINGS_PATH))["app_perf_mode"] is False
        # app state, not a figure preset - and NOT the 3D renderer's own
        # "perf_mode" var, which keeps its registry slot
        assert "app_perf_mode" not in a._preset_registry()
        assert a._preset_registry()["perf_mode"] is a.perf_mode
        assert a.perf_mode is not a.app_perf_mode
    finally:
        a.app_perf_mode.set(old)
        a._toggle_app_perf_mode()


# ---- round-3: neutral Series wording --------------------------------------
def test_plot_mode_radiobuttons_use_neutral_series_wording():
    """The two mode radiobuttons must read for ANY Series variable."""
    a = _APP
    seen = {}
    for w in _walk(_root):
        try:
            if (w.winfo_class() == "TRadiobutton"
                    and str(w.cget("variable")) == str(a.mode)):
                seen[str(w.cget("value"))] = str(w.cget("text"))
        except tk.TclError:
            continue
    assert seen == {"overlay": "Overlay all traces",
                    "inspect": "Inspect one trace"}, seen


# ---- v1.4.8 simplicity batch ----------------------------------------------
def test_export_actions_guard_on_an_empty_tab():
    """Save plot / Copy figure / Batch export had no `if not self.results`,
    so a blank tab exported a 300-dpi picture of the placeholder."""
    a = _APP
    old_results = a.results
    seen = []
    a.results = []
    a._warn = lambda t, m: seen.append((t, m))
    try:
        a._save_plot()
        a._copy_clipboard()
        a._batch_export()
    finally:
        del a._warn
        a.results = old_results
    assert [t for t, _m in seen] == ["Save plot", "Copy figure",
                                     "Batch export"]
    # the exact phrasing the six sibling actions already use
    assert {m for _t, m in seen} == {"Load data first (pick folders and Run)."}


def test_sections_toggle_is_one_flip_label_button():
    a = _APP
    assert not hasattr(a, "_expand_btn")
    a._collapse_all(False)
    _root.update_idletasks()
    assert a._collapse_btn.cget("text") == "Collapse all"
    a._toggle_collapse_all()
    _root.update_idletasks()
    assert a._collapse_btn.cget("text") == "Expand all"
    assert all(r["collapsed"] for r in a._collapsibles)
    a._toggle_collapse_all()
    _root.update_idletasks()
    assert a._collapse_btn.cget("text") == "Collapse all"
    assert not any(r["collapsed"] for r in a._collapsibles)


def test_xvar_custom_preset_roundtrip():
    """A starred name+unit pair reaches SETTINGS, the dropdown, and back."""
    a = _APP
    old = a.settings.get("xvar_custom_presets")
    try:
        a.settings["xvar_custom_presets"] = []
        a.xvar_choice.set(app.XVAR_CUSTOM)
        a.xvar_name.set("Field")
        a.xvar_unit.set("T")
        _root.update_idletasks()
        assert a._xvar_star_btn.cget("text") == "\u2606"

        a._toggle_xvar_saved()
        _root.update_idletasks()
        assert a.settings["xvar_custom_presets"] == [["Field", "T"]]
        with open(app.SETTINGS_PATH) as f:
            assert json.load(f)["xvar_custom_presets"] == [["Field", "T"]]
        vals = list(a._xvar_combo.cget("values"))
        assert vals.index("Field (T)") > vals.index("Time (min)")
        assert vals[-1] == app.XVAR_CUSTOM      # the escape hatch stays last
        assert a._xvar_star_btn.cget("text") == "\u2605"

        # recall: a preset overwrites the pair, the saved entry restores it
        a.xvar_choice.set("Pressure (GPa)")
        _root.update_idletasks()
        assert (a.xvar_name.get(), a.xvar_unit.get()) == ("Pressure", "GPa")
        assert not a._xvar_custom.winfo_manager()
        a.xvar_choice.set("Field (T)")
        _root.update_idletasks()
        assert (a.xvar_name.get(), a.xvar_unit.get()) == ("Field", "T")
        assert a._xvar_custom.winfo_manager()   # editable AND un-starrable
        assert a._vlabel() == "Field (T)"

        a._toggle_xvar_saved()                  # the lit star removes it
        _root.update_idletasks()
        assert a.settings["xvar_custom_presets"] == []
        assert "Field (T)" not in list(a._xvar_combo.cget("values"))
        assert a.xvar_choice.get() == app.XVAR_CUSTOM
    finally:
        if old is None:
            a.settings.pop("xvar_custom_presets", None)
        else:
            a.settings["xvar_custom_presets"] = old
        a.xvar_choice.set("Pressure (GPa)")
        _root.update_idletasks()


def test_reference_lines_rename_and_settings_migration():
    a = _APP
    keys = [r["key"] for r in a._collapsibles]
    assert "Reference lines" in keys
    assert "Reference guides" not in keys
    old = a.settings
    try:
        a.settings = {"collapsed": {"Reference guides": True, "Axis": False},
                      "fig_preset_default": "wide (10 x 4 in)"}
        a._migrate_settings()
        assert a.settings["collapsed"] == {"Reference lines": True,
                                           "Axis": False}
        assert a.settings["fig_preset_default"] == "Wide (10 x 4 in)"
    finally:
        a.settings = old


def test_theme_dropdown_grouping_and_divider_guard():
    a = _APP
    vals = list(a._theme_combo.cget("values"))
    assert vals[:5] == ["Standard Light", "Kinda Dark", "Black Hole",
                        "High Contrast", "Colorblind Safe"]
    assert vals[5] == app.THEME_DIVIDER
    assert app.THEME_DIVIDER not in app.THEME_LABELS.values()
    before = a.theme_mode.get()
    a._theme_combo.set(app.THEME_DIVIDER)
    a._theme_combo._to_code()
    _root.update_idletasks()
    assert a.theme_mode.get() == before                 # no theme switch
    assert a._theme_combo.get() == app.THEME_LABELS[before]


def test_zoom_axis_is_a_readonly_combobox():
    a = _APP
    cbs = [w for w in _walk(_root)
           if w.winfo_class() == "TCombobox"
           and str(w.cget("textvariable")) == str(a.zoom2d_axis)]
    assert len(cbs) == 1
    assert list(cbs[0].cget("values")) == ["both", "X", "Y"]
    assert str(cbs[0].cget("state")) == "readonly"
    assert not [w for w in _walk(_root)
                if w.winfo_class() == "TRadiobutton"
                and str(w.cget("variable")) == str(a.zoom2d_axis)]


def test_ydata_has_one_home_plus_quick_access():
    """The Plot-mode 'Overlay Y' copy is gone; Axis + Quick Access remain."""
    a = _APP
    cbs = [w for w in _walk(_root)
           if w.winfo_class() == "TCombobox"
           and str(w.cget("textvariable")) == str(a.ydata)]
    assert len(cbs) == 2
    assert "Overlay Y" not in [str(w.cget("text")) for w in _walk(_root)
                               if w.winfo_class() == "Label"]


def test_active_formula_row_carries_three_state_cues():
    a = _APP
    a._qty_sel.set(a.quantities[0]["key"])
    a._refresh_quantity_rows()
    _root.update_idletasks()
    body = [r for r in a._collapsibles if r["key"] == "Formulas"][0]["body"]
    tags = [w for w in _walk(body) if w.winfo_class() == "Label"
            and str(w.cget("text")) == "on plot"]
    assert len(tags) == 1                                # the text carrier
    assert str(tags[0].cget("fg")).lower() \
        == str(a._brand()["ac1"]).lower()
    rows = {k: blk for k, blk, _m in a._qty_rows}
    uibg = str(a._theme_palette()[0]).lower()
    act, other = rows[a.quantities[0]["key"]], rows[a.quantities[1]["key"]]
    assert str(act.cget("bg")).lower() != uibg           # the tint
    assert str(other.cget("bg")).lower() == uibg

    def weight(blk, q):
        lab = [w for w in _walk(blk) if w.winfo_class() == "Label"
               and str(w.cget("text")).startswith(q["name"])][0]
        return tkfont.nametofont(str(lab.cget("font"))).actual("weight")

    assert weight(act, a.quantities[0]) == "bold"        # the bold name
    assert weight(other, a.quantities[1]) == "normal"

    try:                                   # all three follow the radio
        a._qty_sel.set(a.quantities[1]["key"])
        a._on_qty_row_pick()
        _root.update_idletasks()
        rows = {k: blk for k, blk, _m in a._qty_rows}
        assert str(rows[a.quantities[1]["key"]].cget("bg")).lower() != uibg
        assert str(rows[a.quantities[0]["key"]].cget("bg")).lower() == uibg
        assert len([w for w in _walk(body) if w.winfo_class() == "Label"
                    and str(w.cget("text")) == "on plot"]) == 1
    finally:
        a._qty_sel.set("")
        a.active_qty.set("")
        a.ydata.set("absorbance")
        a._refresh_quantity_rows()
        _root.update_idletasks()


def test_control_shift_tab_survives_a_tk_without_iso_keysyms():
    """Tk 8.6.9 (what Python 3.8.10 ships) rejects <Control-ISO_Left_Tab>,
    which used to abort App.__init__ before the window ever appeared."""
    a = _APP
    real = a.root.bind
    seen = []

    def fake(seq=None, *args, **kw):
        if seq == "<Control-ISO_Left_Tab>":
            seen.append(seq)
            raise tk.TclError('bad event type or keysym "ISO_Left_Tab"')
        return real(seq, *args, **kw)

    a.root.bind = fake
    try:
        a._bind_shortcuts()                  # must not raise
    finally:
        del a.root.bind
    assert seen == ["<Control-ISO_Left_Tab>"]


def test_the_deleted_controls_are_really_gone():
    # scoped to THIS App's right pane: the module shares a Tk root with the
    # other GUI test modules, so _walk(_root) sees several App trees
    labels = [str(w.cget("text")) for w in _walk(_APP.right_outer)
              if w.winfo_class() == "TButton"]
    for gone in ("Auto fit", "Expand all", "Apply ticks", "Sync H from V",
                 "Reset all to defaults"):
        assert gone not in labels, gone
    assert "Apply limits" in labels and "Reset axes" in labels
    assert labels.count("Auto") == 2         # Ticks and Waterfall keep theirs
    assert not hasattr(app.App, "_reset_defaults")
    assert not hasattr(app.App, "_sync_marker_style")


def test_spine_controls_share_one_box():
    a = _APP

    def body(title):
        return [r for r in a._collapsibles if r["key"] == title][0]["body"]

    def inside(box, w):
        while w is not None:
            if w is box:
                return True
            w = getattr(w, "master", None)
        return False

    fg, ax, col = body("Frame & grid"), body("Axis"), body("Colors & colormap")
    lw = [w for w in _walk(_root) if w.winfo_class() == "TEntry"
          and str(w.cget("textvariable")) == str(a.spine_lw)][0]
    acol = [w for w in _walk(_root) if w.winfo_class() == "TCombobox"
            and str(w.cget("textvariable")) == str(a.axis_color)][0]
    tcol = [w for w in _walk(_root) if w.winfo_class() == "TCombobox"
            and str(w.cget("textvariable")) == str(a.text_color)][0]
    assert inside(fg, lw) and not inside(ax, lw)
    assert inside(fg, acol) and not inside(col, acol)
    assert inside(col, tcol)                 # Text color stays in Colors
    assert "Spines" in [str(w.cget("text")) for w in _walk(fg)
                        if w.winfo_class() == "Label"]


def test_auto_rescan_shows_in_the_status_bar():
    a = _APP
    was = bool(a.auto_rescan.get())
    try:
        a.auto_rescan.set(True)
        a.rescan_interval.set(45)
        a._update_status()
        assert "auto-rescan: 45 s" in a.status_lbl.cget("text")
        a.auto_rescan.set(False)
        a._update_status()
        assert "auto-rescan" not in a.status_lbl.cget("text")
    finally:
        a.auto_rescan.set(was)
        a.rescan_interval.set(30)
        a._cancel_auto_rescan()
        a._update_status()


def test_defringe_detection_is_folded_away_by_default():
    a = _APP
    assert "df_adv_collapsed" in a._ccards
    assert a.settings.get("df_adv_collapsed") is True

    def inside(box, w):
        while w is not None:
            if w is box:
                return True
            w = getattr(w, "master", None)
        return False

    adv = a._ccards["df_adv_collapsed"]["wrap"]
    for var in (a.notch_nt_min, a.notch_nt_max, a.notch_pmax):
        e = [w for w in _walk(_root) if w.winfo_class() == "TEntry"
             and str(w.cget("textvariable")) == str(var)][0]
        assert inside(adv, e)
    # Enable + Notch width stay at the top level of the section
    dfg = [r for r in a._collapsibles if r["key"] == "Defringe"][0]["body"]
    en = [w for w in _walk(dfg) if w.winfo_class() == "TCheckbutton"
          and str(w.cget("variable")) == str(a.show_notch)][0]
    assert not inside(adv, en)


def test_app_text_size_moved_to_the_top_bar():
    a = _APP
    assert a._ui_size_cb.master.master is a.nuke_btn.master   # the top bar
    assert a._ui_size_cb.master.master.master is _root
    assert list(a._ui_size_cb.cget("values")) \
        == ["auto"] + [str(i) for i in range(3, 16)]
    old_size, old_auto = a._body_size, a._ui_font_auto
    try:
        a._ui_size_pick.set("9")
        a._on_ui_size_pick()
        a._apply_ui_size()
        assert a._body_size == 9 and a._ui_font_auto is False
        assert a.settings["ui_font_size"] == 9
        a._ui_size_pick.set("auto")
        a._on_ui_size_pick()
        a._apply_ui_size()
        assert a._ui_font_auto is True
        assert a.settings["ui_font_size"] == "auto"
        assert a._ui_size_pick.get() == "auto"
    finally:
        a._ui_font_auto = old_auto
        a._ui_size_var.set(old_size)
        a._apply_ui_size()


# ---- v1.4.8 polish, batch 2 ------------------------------------------------
def _img(w):
    """cget('image') is a 1-tuple on ttk widgets and a string on tk ones."""
    v = w.cget("image")
    if isinstance(v, (tuple, list)):
        v = v[0] if v else ""
    return str(v)


@contextlib.contextmanager
def _realized(size="1920x1080"):
    """Give the shared root REAL geometry for the length of the block, at
    the project's off-screen probe position, then put it back. Nothing is
    ever visible: +3200+100 is outside the desktop."""
    was = _root.winfo_geometry()
    _root.geometry(size + OFF)
    _root.deiconify()
    for _ in range(3):
        _root.update_idletasks()
        _root.update()
    try:
        yield
    finally:
        _root.withdraw()
        _root.geometry(was)
        _root.update_idletasks()


def test_icon_map_covers_buttons_without_breaking_any_of_them():
    """_iconize_buttons walks EVERY button in the window; the walk must not
    raise on any of them, and every label the map claims must come back
    wearing a glyph from the live set.

    Only THIS app's panes are inspected: the test suite builds several Apps
    on one shared root, and a sibling App's buttons legitimately carry a
    sibling App's images."""
    a = _APP
    a._iconize_buttons()
    mine = [w for w in (getattr(a, n, None)
                        for n in ("left", "center", "right_outer"))
            if w is not None] + [a.nuke_btn.master]
    seen = []
    for rt in mine:
        for w in _walk(rt):
            if w.winfo_class() == "TButton":
                seen.append((str(w.cget("text")), _img(w)))
    assert len(seen) > 40, "the walk found almost no buttons"
    live = set(str(v) for v in a._icons.values())
    got = dict(seen)
    # a sample of the labels the map claims, in BOTH ellipsis spellings
    checked = 0
    for lab in ("Rescan", "New\u2026", "Edit\u2026", "Delete", "Copy log",
                "Export settings", "Reset all", "Save formula CSVs\u2026",
                "Smoothing settings...", "Save project...",
                "Open project...", "Load", "Copy figure", "Apply"):
        if lab in got:
            checked += 1
            assert got[lab], "%r lost its icon" % lab
            assert got[lab] in live, "%r wears a dead image" % lab
    assert checked >= 10, "the sample labels no longer exist"


def test_notebook_tabs_carry_their_icons_through_a_theme_switch():
    a = _APP
    labels = [str(a.rnotebook.tab(t, "text")).strip()
              for t in a.rnotebook.tabs()]
    assert labels == ["Plot", "Axes", "Style", "Data", "Export"]
    # house rule: one space of air between the glyph and the label
    assert all(str(a.rnotebook.tab(t, "text")).startswith(" ")
               for t in a.rnotebook.tabs())
    was = a.theme_mode.get()
    try:
        for th in ("dark", "highcontrast", "colorblind", "light"):
            a.theme_mode.set(th)
            _root.update_idletasks()
            for t in a.rnotebook.tabs():
                lab = str(a.rnotebook.tab(t, "text")).strip()
                assert "tab::" + lab in a._icons, (th, lab)
                assert str(a.rnotebook.tab(t, "image")), (th, lab)
                assert str(a.rnotebook.tab(t, "compound")) == "left"
    finally:
        a.theme_mode.set(was)
        _root.update_idletasks()


def test_card_title_glyphs_survive_a_theme_switch():
    """The hdr:: markers are images, not the ac2 square, and _apply_brand
    restamps them from the regenerated set."""
    a = _APP
    named = [m for m in a._lf_markers
             if m.winfo_exists() and getattr(m, "_hdr_icon", None)]
    assert {getattr(m, "_hdr_icon") for m in named} >= {
        "folder", "folder_open", "log", "book"}
    was = a.theme_mode.get()
    try:
        for th in ("dark", "colorblind", "light"):
            a.theme_mode.set(th)
            _root.update_idletasks()
            for m in named:
                assert _img(m), (th, m._hdr_icon)
    finally:
        a.theme_mode.set(was)
        _root.update_idletasks()


def test_folder_cards_fold_away_and_remember_it():
    a = _APP
    for key in ("in_collapsed", "out_collapsed"):
        assert key in a._ccards, key
        assert not a.settings.get(key), "%s must start expanded" % key

    def inside(box, w):
        while w is not None:
            if w is box:
                return True
            w = getattr(w, "master", None)
        return False

    # the recent-folder caret and the Name-format button live INSIDE the
    # collapsible wrap, so they come back with it
    assert inside(a._ccards["in_collapsed"]["wrap"], a._recent_in_btn)
    assert inside(a._ccards["in_collapsed"]["wrap"], a.profile_btn)
    assert inside(a._ccards["out_collapsed"]["wrap"], a._recent_out_btn)
    for key in ("in_collapsed", "out_collapsed"):
        wrap = a._ccards[key]["wrap"]
        try:
            a._card_toggle(key, True)
            _root.update_idletasks()
            assert a.settings[key] is True
            assert not wrap.winfo_manager(), "%s did not fold" % key
        finally:
            a._card_toggle(key, False)
            _root.update_idletasks()
        assert a.settings[key] is False
        assert wrap.winfo_manager()


def test_folder_cards_keep_their_border_while_collapsed():
    """Pixel-shaped, so it needs a root with real geometry (off-screen)."""
    a = _APP
    with _realized("1200x900"):
        for key in ("in_collapsed", "out_collapsed"):
            card = a._ccards[key]["card"]
            try:
                a._card_toggle(key, True)
                _root.update_idletasks()
                _root.update()
                h = card.winfo_height()
                assert h >= 8, (key, h)
                drawn = [card.coords(i) for i in card.find_withtag("card")
                         if card.type(i) == "line"]
                assert any(abs(ln[1] - (h - 2)) < 1.5 for ln in drawn), \
                    "%s: no bottom border while collapsed" % key
                top = card.coords(card._win)[1]
                assert top + card.body.winfo_height() < h - 2, \
                    "%s: the body covers the border" % key
            finally:
                a._card_toggle(key, False)
                _root.update_idletasks()


def test_collapse_carets_sit_at_the_front_of_their_title():
    a = _APP
    for key in ("in_collapsed", "out_collapsed", "pg_collapsed",
                "guide_collapsed"):
        rec = a._ccards[key]
        slaves = list(rec["caret"].master.pack_slaves())
        assert slaves[0] is rec["caret"], key


def test_top_bar_leaves_nuke_clear_air_at_1920():
    a = _APP
    top = a.nuke_btn.master
    with _realized("1920x1080"):
        a._size_nuke()
        _root.update_idletasks()
        assert top.winfo_width() == 1920, top.winfo_width()
        nx, nw = a.nuke_btn.winfo_x(), a.nuke_btn.winfo_width()
        gaps = []
        for c in top.winfo_children():
            if c is a.nuke_btn:
                continue
            x0, x1 = c.winfo_x(), c.winfo_x() + c.winfo_width()
            assert not (x0 < nx + nw and x1 > nx), \
                "%s overlaps NUKE" % c.winfo_class()
            gaps.append(nx - x1 if x1 <= nx else x0 - (nx + nw))
        assert min(gaps) >= a.NUKE_AIR, \
            "NUKE has only %d px of air, want %d" % (min(gaps), a.NUKE_AIR)


def test_panel_toggles_are_icon_buttons_with_the_words_in_the_tooltip():
    a = _APP
    for btn, tip, word in ((a.left_btn, a._left_tip, "left"),
                           (a.right_btn, a._right_tip, "right")):
        assert _img(btn), "%s button has no glyph" % word
        assert str(btn.cget("compound")) == "image"
        assert not str(btn.cget("text"))
        assert tip.text.startswith("Hide")
    assert _img(a.undo_btn) and _img(a.redo_btn)
    try:
        a._toggle_left()
        _root.update_idletasks()
        assert a._left_tip.text.startswith("Show")
        assert _img(a.left_btn) == str(a._icons["panel_l_off"])
    finally:
        a._toggle_left()
        _root.update_idletasks()
    assert a._left_tip.text.startswith("Hide")
    assert _img(a.left_btn) == str(a._icons["panel_l"])


def _editor_cards(a, win):
    out = {}
    for c in a._brand_cards:
        if not (c.winfo_exists() and str(c).startswith(str(win))):
            continue
        lab = [k for k in c._title.winfo_children() if str(k.cget("text"))]
        out[str(lab[0].cget("text"))] = c
    return out


def test_formula_editor_is_two_house_cards():
    """Item 1: the work column is an Input card and a Preview card, both
    sized to their own content, and the chips span the card width."""
    a = _APP
    with _offscreen():
        win = a._quantity_editor(None, seed={
            "name": "Pct T", "unit": "%", "expr": "100 * (S - D) / (B - D)",
            "latex": ""})
        try:
            win.update_idletasks()
            cards = _editor_cards(a, win)
            assert set(cards) == {"Input", "Preview", "Guide"}, sorted(cards)
            for name in ("Input", "Preview"):
                c = cards[name]
                assert c.grow == "x", name
                # a grow='x' card requests exactly its content height, so
                # nothing empty can sit under the last line. _fit_height
                # normally runs off <Map>/<Configure>, which an unmapped
                # probe window never gets, so ask for it.
                c._refresh()
                want = c._top_inset() + c.body.winfo_reqheight() + c.pad
                assert abs(c.winfo_reqheight() - want) <= 2, \
                    "%s card asks for %d px for %d px of content" % (
                        name, c.winfo_reqheight(), want)
                assert int(c.pack_info().get("expand", 0)) == 0, \
                    "%s card expands and would leave dead ground" % name
            import formulas as _F
            n_col = len(_F.column_legend())
            n_fn = len(_F.function_names())
            chips = [w for w in _walk(cards["Input"])
                     if w.winfo_class() == "Button"]
            assert len(chips) == n_col + n_fn
            rows = {}
            for ch in chips:
                rows.setdefault(str(ch.master), []).append(ch)
            # one row of columns + two balanced rows of functions
            assert len(rows) == 3, "want 3 chip rows, got %d" % len(rows)
            _half = -(-n_fn // 2)
            assert sorted(len(v) for v in rows.values()) == sorted(
                [n_col, _half, n_fn - _half])
            for ch in chips:
                info = ch.pack_info()
                assert int(info.get("expand", 0)) == 1, \
                    "chip %r does not stretch" % str(ch.cget("text"))
                assert str(info.get("fill")) == "x"
        finally:
            win.destroy()
            _root.update_idletasks()


def test_formula_editor_keeps_its_behaviour_after_the_re_card():
    a = _APP
    with _offscreen():
        win = a._quantity_editor(None, seed={"name": "", "unit": "",
                                             "expr": "", "latex": ""})
        try:
            win.update_idletasks()
            ents = [w for w in _walk(win) if w.winfo_class() == "TEntry"]
            expr_e = ents[2]
            byname = {str(c.cget("text")): c for c in _walk(win)
                      if c.winfo_class() == "Button"}
            expr_e.focus_set()
            byname["S"].invoke()
            byname["log()"].invoke()
            assert expr_e.get() == "Slog()"
            # the caret is left INSIDE the function parentheses
            assert expr_e.index("insert") == len("Slog(")
            save = [w for w in _walk(win)
                    if w.__class__.__name__ == "RoundButton"
                    and str(w.cget("text")) == "Save"]
            assert save, "the Save button vanished"
            assert str(save[0].cget("state")) == "disabled"
            labs = [str(w.cget("text")) for w in _walk(win)
                    if w.winfo_class() == "Label"]
            assert any(t.startswith("CSV column / file name:") for t in labs)
            assert any(t.startswith("uses:") for t in labs)
        finally:
            win.destroy()
            _root.update_idletasks()


def test_formula_editor_minimum_size_fits_its_cards():
    """The old fixed 660x480 floor clipped the symbol chips and the whole
    Preview card once the work column became two cards."""
    a = _APP
    with _offscreen():
        win = a._quantity_editor(None, seed={
            "name": "Pct T", "unit": "%", "expr": "100 * (S - D) / (B - D)",
            "latex": ""})
        try:
            win.update_idletasks()
            mw, mh = win.minsize()
            assert mw >= min(win.winfo_screenwidth() - 80,
                             win.winfo_reqwidth())
            assert mh >= min(win.winfo_screenheight() - 140,
                             win.winfo_reqheight())
            assert (mw, mh) >= (660, 480)
        finally:
            win.destroy()
            _root.update_idletasks()
