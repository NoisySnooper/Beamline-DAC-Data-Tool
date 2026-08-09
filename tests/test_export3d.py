"""export3d.py: the pressure-interpolated surface and the printable solid.

Pure module, no Tk -- the whole file runs in well under a second, so it
carries both halves of every contract: the happy path AND the refusal.
Watertightness is the one property a 3D print actually depends on, so it is
asserted the way a slicer would check it (edge manifoldness, winding and the
Euler characteristic, through `export3d.validate_mesh`), never by eyeballing
a render.
"""
import json
import os

import numpy as np
import pytest

import export3d


# ---------------------------------------------------------------------------
# records shaped exactly like the app's, on three different wavelength grids
# on purpose: putting them on ONE axis is the resampler's whole job
# ---------------------------------------------------------------------------
def _rec(p, n=140):
    wl = np.linspace(400.0, 1000.0, n)
    a = 0.4 + 0.3 * np.exp(-((wl - (650.0 + 4.0 * p)) / 90.0) ** 2)
    return {"label": "%.2f GPa" % p, "pressure_val": float(p),
            "wl": wl, "absorbance": a}


def _records():
    return [_rec(0.0), _rec(5.0, 160), _rec(12.0), _rec(20.0, 155)]


# ---------------------------------------------------------------------------
# surface
# ---------------------------------------------------------------------------
def test_build_surface_grids_every_trace_onto_one_axis():
    """Both interpolations, in one walk: the grid is rectangular, both axes
    ascend, the wavelength axis stays inside the measured span, and the
    series axis really spans the four pressures."""
    for method in export3d.methods():
        g = export3d.build_surface(_records(), method=method)
        assert g.Z.shape == g.shape == (g.y.size, g.x.size), method
        assert g.y.size >= 4 and g.x.size >= 8, (method, g.shape)
        assert np.all(np.diff(g.x) > 0), method
        assert np.all(np.diff(g.y) > 0), method
        assert g.x_range == (400.0, 1000.0), method
        assert g.y_range == (0.0, 20.0), method
        assert np.isfinite(g.Z).all(), method
        assert g.meta["method"] == method
        assert g.meta["n_traces"] == 4, method
        # the four measured rows survive interpolation as exact rows
        for p in (0.0, 5.0, 12.0, 20.0):
            assert np.isclose(g.y, p).any(), (method, p)


def test_build_surface_refuses_what_it_cannot_grid():
    with pytest.raises(export3d.SurfaceError):
        export3d.build_surface([])
    with pytest.raises(export3d.SurfaceError):
        export3d.build_surface(_records()[:2])   # two rows are not a surface
    with pytest.raises(KeyError):
        export3d.build_surface(_records(), z_key="not_a_column")


# ---------------------------------------------------------------------------
# solid
# ---------------------------------------------------------------------------
def test_the_exported_solid_is_watertight_and_the_stl_holds_those_faces(
        tmp_path):
    grid = export3d.build_surface(_records())
    tris, stats = export3d.build_mesh(grid, size_mm=(60.0, 60.0, 24.0),
                                      base_mm=3.0)
    rep = export3d.validate_mesh(tris)               # raises on any failure
    assert rep["watertight"] and rep["problems"] == []
    assert rep["euler"] == 2 and rep["boundary_edges"] == 0
    assert rep["nonmanifold_edges"] == 0 and rep["flipped_edges"] == 0
    assert rep["signed_volume_mm3"] > 0              # normals point outward
    # top + walls + bottom, and nothing else
    assert (stats["triangles_top"] + stats["triangles_wall"]
            + stats["triangles_bottom"]) == stats["triangles"] == len(tris)

    path = str(tmp_path / "surface.stl")
    export3d.write_stl(tris, path)
    with open(path, "rb") as f:
        head = f.read(84)
    n = int(np.frombuffer(head[80:84], dtype="<u4")[0])
    assert n == len(tris)
    assert os.path.getsize(path) == 84 + 50 * n      # binary STL, exactly


def test_validate_mesh_reports_every_way_a_solid_breaks():
    grid = export3d.build_surface(_records())
    tris, _stats = export3d.build_mesh(grid)

    holed = tris[1:]                                  # an open edge loop
    with pytest.raises(export3d.MeshError):
        export3d.validate_mesh(holed)
    rep = export3d.validate_mesh(holed, raise_on_fail=False)
    assert not rep["watertight"] and rep["boundary_edges"] > 0
    assert any("hole" in p for p in rep["problems"])

    flipped = np.array(tris)
    flipped[0] = flipped[0][::-1]                     # one reversed winding
    rep = export3d.validate_mesh(flipped, raise_on_fail=False)
    assert rep["flipped_edges"] > 0 and not rep["watertight"]
    with pytest.raises(export3d.MeshError):
        export3d.validate_mesh(flipped)

    with pytest.raises(export3d.MeshError):
        export3d.validate_mesh(np.zeros((4, 3)))      # not (M, 3, 3) at all


def test_export_from_records_writes_the_stl_and_its_provenance(tmp_path):
    path = str(tmp_path / "Y04.stl")
    export3d.export_stl_from_records(_records(), path)
    assert os.path.isfile(path)
    side = path + ".provenance.json"
    assert os.path.isfile(side), "every export carries a provenance sidecar"
    meta = json.load(open(side))
    assert "SPARTA" in json.dumps(meta)
