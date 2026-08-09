"""Generic experiment-variable tests (v1.5.0).

The number parsed out of a file name IS the variable's value (still stored as
pressure_val / pressure_str); only the LABELING is dynamic. These lock the
default (Pressure / GPa) against regression, the preset and Custom paths,
persistence through a save/load preset cycle, that presets written before
v1.5.0 still load, and that the drawn labels + the export provenance follow
the variable.

Runs against the suite's ONE shared App (tests/conftest.py); the shared reset
fixture puts the variable back to Pressure (GPa) after every test.
"""
import pytest

import app
from conftest import gui, make_result, shared_app

USES_APP = True
pytestmark = gui


@pytest.fixture(scope="module")
def a():
    return shared_app()


def _res(label, pval):
    return make_result(label, pval, n=60, dac="D42", sample="fo90")


def _load(a, results):
    a._finish_run([dict(r) for r in results], [], "d")


# ---------------------------------------------------------------- defaults --
def test_default_is_pressure_gpa(a):
    assert a._vname() == "Pressure"
    assert a._vunit() == "GPa"
    assert a._vlabel() == "Pressure (GPa)"
    assert a._vfmt(12.5) == "12.50 GPa"          # legend / trace-row format
    assert a._vfmt(26.0, "%.0f") == "26 GPa"     # recent-runs format
    assert a.cbar_label.get() == "Pressure (GPa)"


# ----------------------------------------------------------------- presets --
def test_presets_and_custom_drive_every_label(a):
    """A preset renames everything the user sees; a hand-typed colorbar label
    is never stomped; Custom reveals its two boxes and a blank unit drops the
    suffix entirely."""
    a.xvar_choice.set("Temperature (K)")
    assert a._vname() == "Temperature" and a._vunit() == "K"
    assert a._vlabel() == "Temperature (K)"
    assert a._vfmt(300.0, "%g") == "300 K"
    assert a._vfmt(12.5) == "12.50 K"
    # the colorbar label followed, because the user had not typed their own
    assert a.cbar_label.get() == "Temperature (K)"
    assert a._ordered_legend([(1, 0.5, "C")])[1] == ["0.50 K - C"]

    a.cbar_label.set("My own scale")
    a.xvar_choice.set("Dose (Gy)")
    assert a._vlabel() == "Dose (Gy)"
    assert a.cbar_label.get() == "My own scale"

    a.xvar_choice.set("Time (min)")
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
def test_variable_round_trips_through_a_preset_cycle(a):
    """The three vars are registry members, a Custom pair survives a
    save/load, and hand-edited strings beat the preset's own values."""
    reg = a._preset_registry()
    for k in ("xvar_choice", "xvar_name", "xvar_unit"):
        assert k in reg and k in a._defaults, k

    a.xvar_choice.set(app.XVAR_CUSTOM)
    a.xvar_name.set("Dose rate")
    a.xvar_unit.set("Gy/s")
    saved = {k: v.get() for k, v in reg.items()}

    a.xvar_choice.set("Pressure (GPa)")            # wander off
    assert a._vlabel() == "Pressure (GPa)"

    a._apply_preset_data(saved)                    # and come back
    assert a.xvar_choice.get() == app.XVAR_CUSTOM
    assert a._vlabel() == "Dose rate (Gy/s)"
    assert a._xvar_custom.winfo_manager() == "pack"

    a._apply_preset_data({"xvar_choice": "Temperature (K)",
                          "xvar_name": "Anneal T", "xvar_unit": "degC"})
    assert a._vlabel() == "Anneal T (degC)"


def test_legacy_and_starter_presets_load_with_pressure_defaults(a):
    """A pre-v1.5.0 payload carries no xvar keys at all, and neither do the
    shipped starter presets: both must land on Pressure (GPa)."""
    a._apply_preset_data({"cmap": "magma", "lw": 1.4, "legend_on": True,
                          "cbar_label": "Pressure (GPa)"})
    assert a._vlabel() == "Pressure (GPa)"
    assert a.cbar_label.get() == "Pressure (GPa)"
    assert a.cmap.get() == "magma"                  # the legacy keys applied

    for name, data in a._starter_presets().items():
        assert not (set(data) & {"xvar_choice", "xvar_name", "xvar_unit"}), name
        a._apply_preset_data(data)
        assert a._vlabel() == "Pressure (GPa)"


# ------------------------------------------------------------ drawn labels --
def test_legend_and_colorbar_labels_follow_the_variable(a):
    _load(a, [_res("D42 fo90 1.00 GPa", 1.0), _res("D42 fo90 12.50 GPa", 12.5)])
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
    assert a._last_cbar is not None
    assert (a._last_cbar.ax.get_ylabel()
            or a._last_cbar.ax.get_xlabel()) == "Temperature (K)"

    a.xvar_choice.set(app.XVAR_CUSTOM)
    a.xvar_name.set("Field")
    a.xvar_unit.set("T")
    a._last_cbar = None
    a._redraw_now()
    assert (a._last_cbar.ax.get_ylabel()
            or a._last_cbar.ax.get_xlabel()) == "Field (T)"


def test_trace_rows_and_engine_labels_follow_the_variable(a):
    """Records keep engine's ' GPa' spelling (it feeds dict keys and output
    file names); only what is DRAWN is rewritten."""
    _load(a, [_res("D42 fo90 12.50 GPa", 12.5)])
    lbl = a.results[0]["label"]
    assert a._disp_of(lbl) == "12.50 GPa"
    assert a._relabel("D42 fo90 12.50 GPa [C]") == "D42 fo90 12.50 GPa [C]"

    a.xvar_choice.set("Dose (Gy)")
    assert a._disp_of(lbl) == "12.50 Gy"
    a._build_trace_checks()
    texts = [w.cget("text")
             for row in a.trace_frame.winfo_children()
             for w in row.winfo_children()
             if w.winfo_class() == "TCheckbutton" and w.cget("text") != "D"]
    assert texts == ["12.50 Gy"]

    a.xvar_choice.set("Temperature (K)")
    assert a._relabel("D42 fo90 12.50 GPa [C]") == "D42 fo90 12.50 K [C]"
    a.xvar_choice.set(app.XVAR_CUSTOM)
    a.xvar_unit.set("")
    assert a._relabel("D42 fo90 12.50 GPa [C]") == "D42 fo90 12.50 [C]"


# -------------------------------------------------------------- provenance --
def test_export_metadata_carries_the_variable(a):
    a.xvar_choice.set("Temperature (K)")
    png = a._export_metadata("png")
    assert png["variable_name"] == "Temperature"
    assert png["variable_unit"] == "K"
    assert "variable_name: Temperature" in png["Description"]
    pdf = a._export_metadata("pdf")
    assert pdf["Keywords"] == "variable_name=Temperature, variable_unit=K"
    assert a._export_metadata("svg")["Creator"].startswith(app.BRAND["name"])
    assert a._export_metadata("tif") is None
