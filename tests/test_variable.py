"""Generic experiment-variable tests (v1.5.0).

The number parsed out of a file name IS the variable's value (still stored as
pressure_val / pressure_str); only the LABELING is dynamic. These lock the
default (Pressure / GPa) against regression, the preset and Custom paths,
persistence through a save/load preset cycle, and that presets written before
v1.5.0 still load. Needs a Tk display, so the module skips on a headless box.
"""
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
    _APP = app.App(_root)
    _APP._save_settings = lambda: None
    _HAVE_GUI = True
except Exception:
    _HAVE_GUI = False

pytestmark = pytest.mark.skipif(not _HAVE_GUI, reason="no Tk display")


def _res(label, pval):
    """A minimal valid engine-style result dict with real absorbance."""
    wl = np.linspace(400.0, 1000.0, 60)
    a = np.linspace(0.1, 1.2, 60)
    return {"label": label, "dac": "D42", "sample": "fo90",
            "pressure_str": "%gp0" % pval, "pressure_val": pval, "rep": 1,
            "branch_tag": None, "wl": wl, "wn": 1e7 / wl,
            "absorbance": a, "dark_c": np.ones(60),
            "bg_c": np.full(60, 10.0), "samp_c": np.full(60, 5.0)}


@pytest.fixture(autouse=True)
def _default_variable():
    """Every test starts from the shipped default."""
    _APP.xvar_choice.set("Pressure (GPa)")
    _APP.cbar_label.set("Pressure (GPa)")
    yield
    _APP.xvar_choice.set("Pressure (GPa)")
    _APP.cbar_label.set("Pressure (GPa)")


def _load(results):
    _APP._finish_run([dict(r) for r in results], [], "dest")


# ---------------------------------------------------------------- defaults --
def test_default_is_pressure_gpa():
    a = _APP
    assert a._vname() == "Pressure"
    assert a._vunit() == "GPa"
    assert a._vlabel() == "Pressure (GPa)"
    assert a._vfmt(12.5) == "12.50 GPa"          # legend / trace-row format
    assert a._vfmt(26.0, "%.0f") == "26 GPa"     # recent-runs format
    assert a.cbar_label.get() == "Pressure (GPa)"


def test_default_legend_text_unchanged():
    """The pre-v1.5.0 legend wording is the contract (see test_legend.py)."""
    assert _APP._ordered_legend([(1, 0.5, "C"), (2, 1.0, "D")])[1] == \
        ["0.50 GPa - C", "1.00 GPa - D"]


# ----------------------------------------------------------------- presets --
def test_temperature_preset_updates_labels():
    a = _APP
    a.xvar_choice.set("Temperature (K)")
    assert a._vname() == "Temperature"
    assert a._vunit() == "K"
    assert a._vlabel() == "Temperature (K)"
    assert a._vfmt(300.0, "%g") == "300 K"
    assert a._vfmt(12.5) == "12.50 K"
    # the colorbar label followed, because the user had not typed their own
    assert a.cbar_label.get() == "Temperature (K)"
    assert a._ordered_legend([(1, 0.5, "C")])[1] == ["0.50 K - C"]


def test_preset_pick_does_not_stomp_a_hand_typed_bar_label():
    a = _APP
    a.cbar_label.set("My own scale")
    a.xvar_choice.set("Dose (Gy)")
    assert a._vlabel() == "Dose (Gy)"
    assert a.cbar_label.get() == "My own scale"


def test_custom_reveals_boxes_and_blank_unit_drops_the_suffix():
    a = _APP
    assert not a._xvar_custom.winfo_manager()      # hidden for a preset
    a.xvar_choice.set(app.XVAR_CUSTOM)
    assert a._xvar_custom.winfo_manager() == "pack"
    a.xvar_name.set("Field")
    a.xvar_unit.set("T")
    assert a._vlabel() == "Field (T)"
    assert a._vfmt(12.5) == "12.50 T"
    a.xvar_unit.set("")                            # unitless variable
    assert a._vlabel() == "Field"
    assert a._vfmt(12.5) == "12.50"
    a.xvar_choice.set("Time (min)")
    assert not a._xvar_custom.winfo_manager()      # hidden again


# ------------------------------------------------------------- persistence --
def test_all_three_vars_are_in_the_preset_registry():
    reg = _APP._preset_registry()
    for k in ("xvar_choice", "xvar_name", "xvar_unit"):
        assert k in reg
        assert k in _APP._defaults


def test_custom_round_trips_through_a_save_load_preset_cycle():
    a = _APP
    a.xvar_choice.set(app.XVAR_CUSTOM)
    a.xvar_name.set("Dose rate")
    a.xvar_unit.set("Gy/s")
    saved = {k: v.get() for k, v in a._preset_registry().items()}

    a.xvar_choice.set("Pressure (GPa)")            # wander off
    assert a._vlabel() == "Pressure (GPa)"

    a._apply_preset_data(saved)                    # and come back
    assert a.xvar_choice.get() == app.XVAR_CUSTOM
    assert a._vname() == "Dose rate"
    assert a._vunit() == "Gy/s"
    assert a._vlabel() == "Dose rate (Gy/s)"
    assert a._xvar_custom.winfo_manager() == "pack"


def test_preset_name_and_unit_win_over_the_choice_default():
    """A saved preset that says Temperature but carries hand-edited strings
    must restore the strings, not the built-in preset values."""
    a = _APP
    a._apply_preset_data({"xvar_choice": "Temperature (K)",
                          "xvar_name": "Anneal T", "xvar_unit": "degC"})
    assert a._vlabel() == "Anneal T (degC)"


def test_legacy_preset_without_xvar_keys_loads_with_pressure_defaults():
    a = _APP
    legacy = {"cmap": "magma", "lw": 1.4, "legend_on": True,
              "cbar_label": "Pressure (GPa)"}       # a pre-v1.5.0 payload
    a._apply_preset_data(legacy)                    # must not raise
    assert a._vname() == "Pressure"
    assert a._vunit() == "GPa"
    assert a._vlabel() == "Pressure (GPa)"
    assert a.cbar_label.get() == "Pressure (GPa)"
    assert a.cmap.get() == "magma"                  # the legacy keys applied


def test_starter_presets_still_apply():
    a = _APP
    for name, data in a._starter_presets().items():
        assert not (set(data) & {"xvar_choice", "xvar_name", "xvar_unit"}), \
            name
        a._apply_preset_data(data)
        assert a._vlabel() == "Pressure (GPa)"


# ------------------------------------------------------------ drawn labels --
def test_legend_and_colorbar_labels_follow_the_variable():
    a = _APP
    _load([_res("D42 fo90 1.00 GPa", 1.0),
           _res("D42 fo90 12.50 GPa", 12.5)])
    a.cmap.set("viridis")                 # continuous -> colorbar allowed
    a.wf_mode.set("off")
    a.mode.set("overlay")
    a.legend_direct.set(False)

    a.legend_on.set(True)
    a.colorbar_on.set(False)
    a._redraw_now()
    assert [t.get_text() for t in a.ax.get_legend().get_texts()] == \
        ["1.00 GPa - C", "12.50 GPa - C"]

    a.xvar_choice.set("Temperature (K)")
    a._redraw_now()
    assert [t.get_text() for t in a.ax.get_legend().get_texts()] == \
        ["1.00 K - C", "12.50 K - C"]

    a.legend_on.set(False)
    a.colorbar_on.set(True)
    a._last_cbar = None
    a._redraw_now()
    cb = a._last_cbar
    assert cb is not None
    assert (cb.ax.get_ylabel() or cb.ax.get_xlabel()) == "Temperature (K)"

    a.xvar_choice.set(app.XVAR_CUSTOM)
    a.xvar_name.set("Field")
    a.xvar_unit.set("T")
    a._last_cbar = None
    a._redraw_now()
    assert (a._last_cbar.ax.get_ylabel()
            or a._last_cbar.ax.get_xlabel()) == "Field (T)"

    a.colorbar_on.set(False)
    a.legend_on.set(True)
    a._redraw_now()


def test_trace_rows_and_readout_header_follow_the_variable():
    a = _APP
    _load([_res("D42 fo90 12.50 GPa", 12.5)])
    lbl = a.results[0]["label"]
    assert a._disp_of(lbl) == "12.50 GPa"
    a.xvar_choice.set("Dose (Gy)")
    assert a._disp_of(lbl) == "12.50 Gy"
    a._build_trace_checks()
    texts = [w.cget("text")
             for row in a.trace_frame.winfo_children()
             for w in row.winfo_children()
             if w.winfo_class() == "TCheckbutton" and w.cget("text") != "D"]
    assert texts == ["12.50 Gy"]


def test_engine_label_relabelled_for_display_only():
    """Records keep engine's ' GPa' spelling (it feeds dict keys and output
    file names); only what is DRAWN is rewritten."""
    a = _APP
    assert a._relabel("D42 fo90 12.50 GPa [C]") == "D42 fo90 12.50 GPa [C]"
    a.xvar_choice.set("Temperature (K)")
    assert a._relabel("D42 fo90 12.50 GPa [C]") == "D42 fo90 12.50 K [C]"
    a.xvar_choice.set(app.XVAR_CUSTOM)
    a.xvar_unit.set("")
    assert a._relabel("D42 fo90 12.50 GPa [C]") == "D42 fo90 12.50 [C]"


# -------------------------------------------------------------- provenance --
def test_export_metadata_carries_the_variable():
    a = _APP
    a.xvar_choice.set("Temperature (K)")
    png = a._export_metadata("png")
    assert png["variable_name"] == "Temperature"
    assert png["variable_unit"] == "K"
    assert "variable_name: Temperature" in png["Description"]
    pdf = a._export_metadata("pdf")
    assert pdf["Keywords"] == "variable_name=Temperature, variable_unit=K"
    assert a._export_metadata("svg")["Creator"].startswith(app.BRAND["name"])
    assert a._export_metadata("tif") is None
