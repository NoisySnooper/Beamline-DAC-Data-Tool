"""
export3d.py  --  the pressure x wavelength surface, and the printable solid.

Two jobs, one grid:

  build_surface()   turns a series of spectra (one per pressure) into a
                    regular wavelength x pressure grid with absorbance as
                    height.  Between two measured pressures the height is
                    interpolated, so adjacent traces read as one continuous
                    sheet instead of a stack of separate ridges.

  surface_artists() draws that grid on a Matplotlib 3D axes, shaded from the
                    same colormap the rest of the app colours traces with.
                    Two optional extras live here too: relief_shade(), which
                    hillshades the facecolours so the ridges and valleys read
                    as topography, and underside_artists(), which closes the
                    displayed sheet with side walls and a base so the screen
                    shows the same solid the printer will make.

  to_stl()          extrudes the same grid down onto a flat base slab and
                    writes it as a WATERTIGHT binary STL, ready to print.
                    Watertightness is proven, not assumed: validate_mesh()
                    checks that every edge is used exactly twice with
                    opposite orientation and that the Euler characteristic
                    is 2, and to_stl() refuses to write a mesh that fails.

Nothing here imports tkinter, matplotlib.pyplot or the application.  Every
entry point works on plain numpy arrays, so the surface and the solid can be
built, checked and rendered from a script with no GUI in sight.

Dependencies: numpy (required), scipy (only for the curved pressure-axis
interpolations -- quadratic, cubic, PCHIP -- imported lazily and degraded to
linear if it is missing), matplotlib (only inside the render helpers).

NQT / Lee Lab -- Aug 2026
"""

import datetime
import hashlib
import json
import os
import struct

import numpy as np

# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------

#: columns kept on the common wavelength axis.  400 is the interactive
#: sweet spot: finer than the eye resolves on a screen-sized 3D box, coarse
#: enough that a redraw stays under a second on the slowest supported machine.
DEFAULT_N_COLS = 400

#: rows synthesised between each pair of measured pressures.  6 turns 19 real
#: pressures into 109 rows -- smooth to the eye, still cheap.
DEFAULT_ROWS_PER_GAP = 6

#: hard ceiling on the pressure axis, whatever rows_per_gap asks for.
MAX_ROWS = 400

#: pressure-axis interpolation.  "linear" is the default and the shipped
#: behaviour; see the ship note at the bottom of this module.  The curved
#: options are offered because a user may want the sheet visibly smooth and
#: accept the extra assumption -- but linear is what the data actually says.
DEFAULT_METHOD = "linear"

#: at least this many traces before a surface means anything.
MIN_TRACES = 3

#: rendering budget: quads actually handed to plot_surface.  Measured on the
#: 19-pressure Y04_Arch29 grid (109 x 400): 43k quads = 5.1 s per draw, 14k =
#: 1.2 s, 5.3k = 0.36 s, 3.5k = 0.26 s -- and the three renders are visually
#: indistinguishable, because the strided cells are still finer than the
#: on-screen box.  8000 buys the full picture at a third of a second.
DEFAULT_MAX_CELLS = 8000

#: budget under Performance mode.
PERF_MAX_CELLS = 3000

#: relief shading (hillshade) defaults.  315 deg is the cartographic
#: convention -- light from the upper left -- and the one the eye reads as
#: "lit from above" rather than as an inverted crater.  45 deg elevation is
#: the classic compromise: low enough to throw slope contrast, high enough
#: that the far side of a ridge does not go black.
DEFAULT_LIGHT_AZDEG = 315.0
DEFAULT_LIGHT_ALTDEG = 45.0

#: the axes box the surface is drawn in, (x, y, z).  This is the app's own
#: `set_box_aspect((1.7, 1.2, 0.6))` at unit scale, and it is what makes
#: vert_exag=1.0 mean "shade the shape the eye actually sees": the hillshade
#: is computed in BOX coordinates, where every axis is its on-screen length,
#: not in data units where a nanometre and an absorbance unit are the same
#: number.  A caller with a different box aspect passes its own.
DEFAULT_BOX_ASPECT = (1.7, 1.2, 0.6)

#: relief exaggeration on top of the true box geometry.  1.0 is honest.
DEFAULT_VERT_EXAG = 1.0

#: how much of the hillshade to mix in, 0 = off, 1 = full pegtop soft light.
#: Chosen on Y04: at 0.6 the colour spread the shading introduces inside one
#: pressure row is about a third of the colour step between adjacent measured
#: pressures, so the relief reads as light and the hue still reads as
#: pressure.  See the shading note at the bottom of this module.
DEFAULT_RELIEF = 0.6

#: how much darker the underside walls and base are than the surface edge
#: they hang from.  A solid lit from above has darker sides; without this the
#: skirt reads as more surface folded down rather than as the side of a block.
WALL_DARKEN = 0.72
BOTTOM_DARKEN = 0.50

#: STL physical defaults (mm).
DEFAULT_SIZE_MM = (80.0, 80.0, 30.0)
DEFAULT_BASE_MM = 6.0

#: vertex-welding tolerance for the manifold proof, in the mesh's own units.
WELD_TOL = 1e-6

SCHEMA = "sparta_surface3d/v1"


class SurfaceError(Exception):
    """The traces cannot be made into a grid (too few, no overlap, no data)."""


class MeshError(Exception):
    """The mesh is not a closed, consistently wound solid."""


# ---------------------------------------------------------------------------
# the grid
# ---------------------------------------------------------------------------

class SurfaceGrid(object):
    """A regular grid: x (wavelength, nx), y (pressure, ny), Z (ny, nx).

    Z[i, j] is the height at pressure y[i] and wavelength x[j].  Z carries no
    NaN by construction -- build_surface trims and fills first.  `meta` records
    how it was built so the provenance sidecar can quote it.
    """

    __slots__ = ("x", "y", "Z", "meta")

    def __init__(self, x, y, Z, meta=None):
        self.x = np.asarray(x, dtype=float)
        self.y = np.asarray(y, dtype=float)
        self.Z = np.asarray(Z, dtype=float)
        if self.Z.shape != (self.y.size, self.x.size):
            raise SurfaceError("grid shape %r does not match axes (%d, %d)"
                               % (self.Z.shape, self.y.size, self.x.size))
        self.meta = dict(meta or {})

    # -- convenience -------------------------------------------------------
    @property
    def shape(self):
        return self.Z.shape

    @property
    def x_range(self):
        return (float(self.x[0]), float(self.x[-1]))

    @property
    def y_range(self):
        return (float(self.y[0]), float(self.y[-1]))

    @property
    def z_range(self):
        return (float(np.nanmin(self.Z)), float(np.nanmax(self.Z)))

    def __repr__(self):
        return ("SurfaceGrid(%d x %d, x %.4g..%.4g, y %.4g..%.4g, "
                "z %.4g..%.4g)"
                % ((self.y.size, self.x.size) + self.x_range + self.y_range
                   + self.z_range))


# ---------------------------------------------------------------------------
# per-trace cleaning
# ---------------------------------------------------------------------------

def _clean_trace(x, z):
    """One trace -> (x, z) sorted by x, x strictly increasing, z free of
    INTERIOR NaN.

    NaN policy, in order:
      * points whose X is not finite are dropped outright (no position, no
        opinion);
      * duplicate X values are averaged (a repeated wavelength is a digitiser
        artefact, not two measurements of different things);
      * NaN inside the finite span is filled by linear interpolation along
        this trace's own X -- a short dropout should not punch a hole in the
        sheet;
      * NaN at the ENDS is left as NaN and reported as the trace's valid span,
        so build_surface can trim the shared axis to where every trace really
        has data instead of extrapolating.

    Returns (x, z, lo, hi) with lo/hi the finite span, or (None, None,
    nan, nan) when nothing usable is left.
    """
    x = np.asarray(x, dtype=float).ravel()
    z = np.asarray(z, dtype=float).ravel()
    n = min(x.size, z.size)
    x, z = x[:n], z[:n]
    ok = np.isfinite(x)
    if not ok.any():
        return None, None, np.nan, np.nan
    x, z = x[ok], z[ok]

    order = np.argsort(x, kind="mergesort")
    x, z = x[order], z[order]

    # average runs of identical X
    if x.size > 1 and (np.diff(x) == 0).any():
        keep = np.empty(x.size, dtype=bool)
        keep[0] = True
        keep[1:] = np.diff(x) != 0
        starts = np.flatnonzero(keep)
        ends = np.append(starts[1:], x.size)
        xs = x[starts]
        zs = np.empty(starts.size, dtype=float)
        for k, (a, b) in enumerate(zip(starts, ends)):
            seg = z[a:b]
            fin = np.isfinite(seg)
            zs[k] = seg[fin].mean() if fin.any() else np.nan
        x, z = xs, zs

    fin = np.isfinite(z)
    if not fin.any():
        return None, None, np.nan, np.nan
    idx = np.flatnonzero(fin)
    first, last = idx[0], idx[-1]
    if idx.size != (last - first + 1):
        # interior dropouts: fill them from this trace's own neighbours
        inner = slice(first, last + 1)
        zi = z[inner]
        xi = x[inner]
        good = np.isfinite(zi)
        zi = zi.copy()
        zi[~good] = np.interp(xi[~good], xi[good], zi[good])
        z = z.copy()
        z[inner] = zi
    return x, z, float(x[first]), float(x[last])


# ---------------------------------------------------------------------------
# pressure-axis interpolation
# ---------------------------------------------------------------------------

def _interp_rows_linear(y0, Z0, y1):
    """Linear interpolation of every column of Z0 from y0 onto y1.

    Vectorised: one searchsorted for the bracketing rows, then a single
    weighted blend.  Equivalent to np.interp per column, ~100x faster on a
    400-column grid.
    """
    y0 = np.asarray(y0, dtype=float)
    y1 = np.asarray(y1, dtype=float)
    k = np.clip(np.searchsorted(y0, y1, side="right") - 1, 0, y0.size - 2)
    span = y0[k + 1] - y0[k]
    span[span == 0] = 1.0
    w = np.clip((y1 - y0[k]) / span, 0.0, 1.0)[:, None]
    return Z0[k] * (1.0 - w) + Z0[k + 1] * w


def _interp_rows_pchip(y0, Z0, y1):
    """Monotone piecewise-cubic (PCHIP) along the pressure axis.

    PCHIP is shape preserving: it will not overshoot past the measured
    values, so an interpolated slice can never invent an absorbance larger
    than both of its neighbours.  It DOES round the corners at every measured
    pressure, which is a claim about how the sample behaved between two
    points -- see the ship note at the bottom of this module.
    """
    from scipy.interpolate import PchipInterpolator
    return PchipInterpolator(np.asarray(y0, dtype=float), Z0,
                             axis=0, extrapolate=False)(np.asarray(y1,
                                                                  dtype=float))


def _interp_rows_spline(y0, Z0, y1, kind):
    """scipy's interp1d along the pressure axis, one call for all columns.

    Out-of-range rows come back NaN rather than extrapolated nonsense, in
    exactly the shape PCHIP's extrapolate=False produces -- so the single NaN
    repair in surface_from_traces covers every curved method identically.
    """
    from scipy.interpolate import interp1d
    f = interp1d(np.asarray(y0, dtype=float), Z0, kind=kind, axis=0,
                 copy=False, bounds_error=False, fill_value=np.nan,
                 assume_sorted=True)
    return f(np.asarray(y1, dtype=float))


def _interp_rows_quadratic(y0, Z0, y1):
    """2nd-degree spline along the pressure axis.  Needs >= 3 pressures.

    Curves, and CAN overshoot: a quadratic through three points that rise
    then fall bulges past the middle one.  Cheaper in that respect than a
    cubic only because it has one less degree of freedom to bulge with.
    """
    return _interp_rows_spline(y0, Z0, y1, "quadratic")


def _interp_rows_cubic(y0, Z0, y1):
    """3rd-degree spline along the pressure axis.  Needs >= 4 pressures.

    The classic smooth interpolant, and the classic overshooter: it is
    continuous in curvature, which it buys by swinging outside the measured
    values wherever the spacing or the slope changes abruptly.  See
    _interp_rows_pchip for the shape-preserving alternative and the ship note
    at the bottom of this module for what that costs on real data.
    """
    return _interp_rows_spline(y0, Z0, y1, "cubic")


_METHODS = {"linear": _interp_rows_linear,
            "quadratic": _interp_rows_quadratic,
            "cubic": _interp_rows_cubic,
            "pchip": _interp_rows_pchip}

#: how many DISTINCT measured pressures each method needs before it can be
#: fitted at all.  Below this the whole grid falls back to linear and says so
#: in grid.meta["method_fallback"] -- a half-cubic, half-linear sheet would
#: be a lie in two different directions at once.
_METHOD_MIN_SAMPLES = {"linear": 2, "quadratic": 3, "cubic": 4, "pchip": 2}

#: menu labels.  The app shows these; the keys are what goes in provenance.
METHOD_LABELS = {"linear": "Linear",
                 "quadratic": "2nd degree (quadratic)",
                 "cubic": "3rd degree (cubic)",
                 "pchip": "3rd degree, monotone (PCHIP)"}

_METHOD_ORDER = ["linear", "quadratic", "cubic", "pchip"]


def methods():
    """Names accepted by build_surface(method=...), in menu order."""
    return list(_METHOD_ORDER)


def method_labels():
    """[(name, label)] in menu order, for building the GUI's dropdown."""
    return [(m, METHOD_LABELS[m]) for m in _METHOD_ORDER]


def method_min_samples(method):
    """Distinct measured pressures `method` needs before it can be fitted."""
    if method not in _METHODS:
        raise SurfaceError("unknown interpolation method %r (have %s)"
                           % (method, ", ".join(methods())))
    return int(_METHOD_MIN_SAMPLES[method])


def resolve_method(method, n_series):
    """(method_that_will_actually_run, note_or_None) for `n_series` pressures.

    The GUI can call this before drawing to grey out or annotate an option
    instead of letting the user pick something that silently degrades.
    """
    if method not in _METHODS:
        raise SurfaceError("unknown interpolation method %r (have %s)"
                           % (method, ", ".join(methods())))
    need = _METHOD_MIN_SAMPLES[method]
    n = int(n_series)
    if n >= need:
        return method, None
    return "linear", ("%s needs at least %d distinct series values; this "
                      "surface has %d, so the whole grid was interpolated "
                      "linearly" % (METHOD_LABELS[method], need, n))


def _apply_method(method, y0, Z0, y1):
    """Run `method`, degrading to linear rather than failing.

    Returns (Z, method_used, note).  `note` is None when the requested method
    ran, and a sentence fit for a status line when it did not -- too few
    pressures, or no SciPy on this machine.  The fallback is all-or-nothing
    on purpose: a grid interpolated two different ways in two different
    places is not a measurement of anything.
    """
    n = int(np.asarray(y0, dtype=float).size)
    used, note = resolve_method(method, n)
    if note is not None:
        return _METHODS[used](y0, Z0, y1), used, note
    try:
        return _METHODS[used](y0, Z0, y1), used, None
    except ImportError as exc:
        note = ("%s needs SciPy, which is not available here (%s); the grid "
                "was interpolated linearly instead"
                % (METHOD_LABELS[method], exc))
    except ValueError as exc:
        # belt and braces: scipy's own arity complaint, in case its minimum
        # ever moves under us.
        note = ("%s could not be fitted to %d series values (%s); the grid "
                "was interpolated linearly instead"
                % (METHOD_LABELS[method], n, exc))
    return _interp_rows_linear(y0, Z0, y1), "linear", note


# ---------------------------------------------------------------------------
# building the grid
# ---------------------------------------------------------------------------

def surface_from_traces(xs, zs, yvals, n_cols=DEFAULT_N_COLS,
                        method=DEFAULT_METHOD,
                        rows_per_gap=DEFAULT_ROWS_PER_GAP, n_rows=None,
                        x_range=None, min_traces=MIN_TRACES):
    """Array-level builder.  xs/zs are per-trace 1D arrays (any lengths,
    any NaN), yvals the series value of each trace.  Returns a SurfaceGrid.

    The common wavelength axis is the INTERSECTION of the traces' finite
    spans, sampled at n_cols evenly spaced points: every column of the grid
    is then backed by real data in every trace, and no value is
    extrapolated.  Pass x_range=(lo, hi) to narrow it further.

    `method` is one of methods().  A curved method that cannot be fitted --
    too few distinct series values, or no SciPy on this machine -- degrades
    to linear for the WHOLE grid and says so in meta["method_fallback"];
    meta["method"] is then what actually ran and meta["method_requested"] is
    what was asked for, so provenance never overstates the sheet.
    """
    if len(xs) != len(zs) or len(xs) != len(yvals):
        raise SurfaceError("xs, zs and yvals must be the same length")
    if method not in _METHODS:
        raise SurfaceError("unknown interpolation method %r (have %s)"
                           % (method, ", ".join(methods())))

    cleaned, ys, lo, hi = [], [], -np.inf, np.inf
    dropped = 0
    for x, z, y in zip(xs, zs, yvals):
        cx, cz, a, b = _clean_trace(x, z)
        if cx is None or cx.size < 2:
            dropped += 1
            continue
        cleaned.append((cx, cz))
        ys.append(float(y))
        lo, hi = max(lo, a), min(hi, b)

    if len(cleaned) < min_traces:
        raise SurfaceError(
            "a surface needs at least %d traces with data; got %d"
            % (min_traces, len(cleaned)))
    if x_range is not None:
        lo = max(lo, float(min(x_range)))
        hi = min(hi, float(max(x_range)))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        raise SurfaceError("the traces share no common wavelength range")

    n_cols = int(max(8, n_cols))
    xg = np.linspace(lo, hi, n_cols)

    # resample every trace onto the shared axis, then order by series value
    Z0 = np.empty((len(cleaned), n_cols), dtype=float)
    for i, (cx, cz) in enumerate(cleaned):
        Z0[i] = np.interp(xg, cx, cz)
    yv = np.asarray(ys, dtype=float)
    order = np.argsort(yv, kind="mergesort")
    yv, Z0 = yv[order], Z0[order]

    # a repeated series value cannot be a separate row (PCHIP needs the axis
    # strictly increasing, and two heights at one pressure is a contradiction
    # either way): average them and say so in meta.
    # OPEN ITEM (R14-C): branch identity is invisible here, so a C trace and a
    # D trace at the SAME pressure average into one row and the hysteresis
    # between them disappears from the sheet. meta['series_values_merged']
    # counts it; nothing warns yet.
    merged = 0
    if yv.size > 1 and (np.diff(yv) == 0).any():
        keep = np.empty(yv.size, dtype=bool)
        keep[0] = True
        keep[1:] = np.diff(yv) != 0
        starts = np.flatnonzero(keep)
        ends = np.append(starts[1:], yv.size)
        merged = int(yv.size - starts.size)
        Z0 = np.stack([Z0[a:b].mean(axis=0) for a, b in zip(starts, ends)])
        yv = yv[starts]
    if yv.size < min_traces:
        raise SurfaceError(
            "a surface needs at least %d distinct series values; got %d"
            % (min_traces, yv.size))

    # The pressure axis is built gap by gap, not as one linspace across the
    # whole range.  That is what keeps every MEASURED pressure exactly on a
    # row: a global linspace lands wherever it lands, and two pressures
    # closer together than one step (0.1 GPa apart in a 0.5 GPa step, which
    # this dataset really has) would both be missed, so a real trace would
    # only ever appear blended with its neighbour.  Rows inside a gap are
    # spaced in proportion to the real gap, matching the app's true-value
    # ridge placement.
    n_gaps = yv.size - 1
    if n_rows is not None:
        per_gap = int(max(1, round((int(n_rows) - 1) / float(n_gaps))))
    else:
        per_gap = int(max(1, rows_per_gap))
    while n_gaps * per_gap + 1 > MAX_ROWS and per_gap > 1:
        per_gap -= 1
    yg = np.concatenate([np.linspace(yv[k], yv[k + 1], per_gap + 1)[:-1]
                         for k in range(n_gaps)] + [yv[-1:]])
    n_rows = yg.size

    Z, used, fallback = _apply_method(method, yv, Z0, yg)
    if not np.isfinite(Z).all():
        # PCHIP with extrapolate=False, and interp1d with bounds_error=False,
        # both write NaN outside [y0, y-1]; the snapping above makes that
        # impossible, but never ship a NaN.
        bad = ~np.isfinite(Z)
        Z = Z.copy()
        Z[bad] = _interp_rows_linear(yv, Z0, yg)[bad]

    meta = {"schema": SCHEMA, "method": used, "n_cols": n_cols,
            "method_requested": method, "method_fallback": fallback,
            "n_rows": int(n_rows), "n_traces": int(yv.size),
            "rows_per_gap": int(per_gap),
            "x_min": float(lo), "x_max": float(hi),
            "y_values": [float(v) for v in yv],
            "traces_dropped": int(dropped), "series_values_merged": merged}
    return SurfaceGrid(xg, yg, Z, meta)


def build_surface(records, x_key="wl", z_key="absorbance",
                  y_key="pressure_val", z_of=None, **kw):
    """Record-level builder: the app's trace records straight in.

    `records` is a list of dicts carrying at least the three keys above
    (SPARTA's records do).  Pass z_of=callable(record) to plot something the
    record does not store as a plain column -- a smoothed channel, a
    formula quantity -- without copying the array first.

    Everything else is forwarded to surface_from_traces.
    """
    recs = list(records)
    if not recs:
        raise SurfaceError("no traces given")
    xs = [np.asarray(r[x_key], dtype=float) for r in recs]
    if z_of is None:
        zs = [np.asarray(r[z_key], dtype=float) for r in recs]
    else:
        zs = [np.asarray(z_of(r), dtype=float) for r in recs]
    ys = [float(r[y_key]) for r in recs]
    return surface_from_traces(xs, zs, ys, **kw)


# ---------------------------------------------------------------------------
# render path
# ---------------------------------------------------------------------------

def surface_colors(grid, cmap, rev=False, shade_by="series", alpha=1.0,
                   color_range=None, color_values=None, color_ranks=None,
                   n_series=None):
    """(ny, nx, 4) RGBA for the grid, from SPARTA's own colormap module.

    shade_by="series" reproduces the app's rule exactly -- a row is coloured
    by its series value the same way _trace_color colours a ridge -- so the
    surface agrees with the pressure colorbar and with the other 3D looks.
    shade_by="height" colours by absorbance instead; it is only meaningful
    for a continuous map, so a categorical one falls back to "series".

    The grid's own Y axis is a DISPLAY coordinate: with even rank spacing it
    carries 0, 1, 2 ... not pressures.  Pass color_values (the real series
    value of each row) and color_ranks (its rank among the shown traces, and
    n_series how many there are) to colour exactly as _trace_color would --
    by value for a continuous map, by rank for a categorical one.
    """
    import colormaps as _cm
    ny, nx = grid.Z.shape
    vals = (grid.y if color_values is None
            else np.asarray(color_values, dtype=float))
    ranks = (np.arange(ny) if color_ranks is None
             else np.asarray(color_ranks).astype(int))
    nser = int(ny if n_series is None else n_series)
    if color_range is None:
        lo, hi = float(np.min(vals)), float(np.max(vals))
    else:
        lo, hi = float(color_range[0]), float(color_range[1])
    cmin, cmax = (hi, lo) if rev else (lo, hi)
    if shade_by == "height" and not _cm.is_categorical(cmap):
        zlo, zhi = grid.z_range
        czlo, czhi = (zhi, zlo) if rev else (zlo, zhi)
        flat = grid.Z.ravel()
        # sample the map on a 256-step ramp instead of once per cell
        ramp = np.array([_cm.color_for(cmap, czlo + (czhi - czlo) * t / 255.0,
                                       czlo, czhi, 0, 256)
                         for t in range(256)], dtype=float)
        if czhi != czlo:
            f = np.clip((flat - min(czlo, czhi)) / abs(czhi - czlo), 0, 1)
        else:
            f = np.full(flat.shape, 0.5)
        if rev:
            f = 1.0 - f
        rgba = ramp[(f * 255).astype(int)].reshape(ny, nx, 4)
    else:
        # rank handling copied from the app's _trace_color: a reversed
        # colormap walks the categorical palette backwards too
        rows = np.array(
            [_cm.color_for(cmap, float(v), cmin, cmax,
                           (nser - 1 - int(rk)) if rev else int(rk), nser)
             for v, rk in zip(vals, ranks)], dtype=float)
        rgba = np.repeat(rows[:, None, :], nx, axis=1)
    rgba = rgba.copy()
    rgba[..., 3] = float(alpha)
    return rgba


def strides_for(grid, max_cells=DEFAULT_MAX_CELLS):
    """(rstride, cstride) that keep plot_surface under `max_cells` quads.

    A 109 x 400 grid is 43k quads; matplotlib draws every one as its own
    sorted polygon, so an untuned call turns a camera drag into a slideshow.
    Striding is display-only -- the STL always uses the full grid.
    """
    ny, nx = grid.Z.shape
    rc, cc = max(1, ny - 1), max(1, nx - 1)
    rs = cs = 1
    while (rc // rs) * (cc // cs) > max_cells:
        if (cc // cs) >= (rc // rs):
            cs += 1
        else:
            rs += 1
    return int(rs), int(cs)


# ---------------------------------------------------------------------------
# relief shading
# ---------------------------------------------------------------------------

def _display_z(grid, z_clip=None):
    """(Z as drawn, zlo, zhi) -- the clamp surface_artists applies, once."""
    Z = np.asarray(grid.Z, dtype=float)
    if z_clip is not None:
        zlo, zhi = float(min(z_clip)), float(max(z_clip))
        Z = np.clip(Z, zlo, zhi)
    else:
        zlo, zhi = float(np.nanmin(Z)), float(np.nanmax(Z))
    return Z, zlo, zhi


def _box_smooth(A, ry, rx):
    """Separable box mean over a (2*ry+1) x (2*rx+1) window, edges included.

    Two cumulative sums, no SciPy: this runs on the full 109 x 400 grid in
    well under a millisecond, which is the whole point of doing it here
    instead of reaching for ndimage.
    """
    ry, rx = int(max(0, ry)), int(max(0, rx))
    if ry == 0 and rx == 0:
        return A
    out = np.asarray(A, dtype=float)
    for axis, r in ((0, ry), (1, rx)):
        if r == 0:
            continue
        n = out.shape[axis]
        r = min(r, max(0, n - 1))
        if r == 0:
            continue
        c = np.cumsum(out, axis=axis)
        c = np.concatenate([np.zeros_like(np.take(c, [0], axis=axis)), c],
                           axis=axis)
        idx = np.arange(n)
        hi = np.minimum(idx + r + 1, n)
        lo = np.maximum(idx - r, 0)
        num = np.take(c, hi, axis=axis) - np.take(c, lo, axis=axis)
        shape = [1, 1]
        shape[axis] = n
        out = num / (hi - lo).reshape(shape).astype(float)
    return out


def relief_shade(rgba, grid, z_clip=None, azdeg=DEFAULT_LIGHT_AZDEG,
                 altdeg=DEFAULT_LIGHT_ALTDEG, vert_exag=DEFAULT_VERT_EXAG,
                 blend_mode="soft", fraction=1.0, strength=DEFAULT_RELIEF,
                 neutral=True, box_aspect=DEFAULT_BOX_ASPECT, luma_only=False,
                 smooth=None, strides=None):
    """Hillshade the surface's own facecolours.  (ny, nx, 4) in, same out.

    Why this exists.  With shade_by="series" every cell in a row carries the
    SAME colour, because the row is a pressure and the colorbar is pressure.
    That is correct and it is also why the topography is invisible: nothing
    in the picture varies with absorbance except the geometry, and geometry
    alone is weak at the shallow viewing angles a 3D box is usually left at.
    Terrain maps solved this a century ago -- shade by slope.

    Why not matplotlib's own `shade=True`.  Poly3DCollection's shading takes
    each polygon's normal in DATA coordinates -- nanometres by gigapascals by
    absorbance -- so it is not lighting a shape, it is lighting an accident of
    unit choice.  On this grid the wavelength axis is ~600 units wide and the
    height axis ~3, which flattens every spectral feature out of the normal:
    measured on Y04, the wavelength component of mpl's face normals averages
    3.4% of the pressure component.  The result shades ridges ACROSS pressure
    and is nearly blind along wavelength -- exactly the half of the
    topography the user is asking to see.  It also costs colour fidelity: the
    factor it applies runs 0.45 to 0.91 (mean 0.75), which moves a drawn quad
    a mean 15.0 dE from its own colorbar swatch, against 4.9 dE for relief
    shading at the default strength.  So pass shade=False when relief shading
    is on -- surface_artists does that for you -- and note that doing so
    makes the surface match its colorbar BETTER, not worse.

    Geometry.  The hillshade is computed in BOX coordinates, not data units:
    X, Y and Z are each normalised to their span and then scaled by
    `box_aspect`, which is the axes' own set_box_aspect.  So vert_exag=1.0
    means "light the shape the eye is actually looking at", and any other
    value is a stated exaggeration rather than an accident of unit choice.

    Colour fidelity.  Two guards keep the colormap readable:

      * neutral=True re-centres the illumination on 0.5 before blending, so
        the shading has ZERO mean effect: a row's average colour still lands
        where the colorbar says it does.  Without it pegtop soft light lifts
        this surface by +8.8 L* on average, and every swatch is then a shade
        too bright for its own colorbar.
      * strength scales the whole modulation, 0 = unshaded, 1 = full.  The
        default is set so the within-row colour spread the shading introduces
        stays below the colour step between adjacent measured pressures --
        the relief is read as light, the hue is still read as pressure.

    blend_mode="soft" is matplotlib's pegtop soft light,
    ``2*I*c + (1-2*I)*c**2`` per channel: it leaves I=0.5 exactly alone and
    cannot push a channel past 0 or 1, so saturated colormap entries do not
    blow out.  It is not strictly luminance-only -- set luma_only=True to
    modulate relative luminance and rescale RGB, which holds chromaticity
    fixed but, measured on Y04, actually shifts HUE slightly more than pegtop
    does because clipping a rescaled channel is a bigger event than pegtop's
    endpoint-preserving curve.

    smooth: half-window, in grid cells, applied to the elevation before the
    gradient.  None means "match the display strides", which is what stops
    the relief turning into per-cell speckle once plot_surface samples one
    colour per drawn quad.  0 disables it.  Pass strides=(rs, cs) (from
    strides_for) so the automatic choice knows what the display will do.
    """
    from matplotlib.colors import LightSource

    rgba = np.asarray(rgba, dtype=float)
    Z, zlo, zhi = _display_z(grid, z_clip)
    ny, nx = Z.shape
    span = zhi - zlo
    if not np.isfinite(span) or span <= max(abs(zlo), abs(zhi), 1.0) * 1e-12:
        # a flat sheet has no relief to show; shading it would only tint it
        return rgba.copy()

    bx, by, bz = (float(box_aspect[0]), float(box_aspect[1]),
                  float(box_aspect[2]))
    if smooth is None:
        rs, cs = strides if strides else (1, 1)
        # Half-window: one displayed quad down the pressure axis, TWO across
        # wavelength.  Measured on Y04: the cell-to-cell height step along
        # wavelength is 2.7x the average slope across one drawn quad, i.e.
        # the sub-quad wiggle is mostly interference fringe, not shape, and
        # its dominant period is 22 nm (13 columns at 1.72 nm/column).  A
        # half-window of 2*cs = 8 columns spans 29 nm, so the fringe averages
        # out and the hillshade lights the ridge instead of the ripple.
        # Without it the relief is per-cell speckle that the display's own
        # striding then aliases into a moire.
        smooth = (int(rs), 2 * int(cs))
    elif np.isscalar(smooth):
        smooth = (int(smooth), int(smooth))
    elev = (Z - zlo) / span * bz * float(vert_exag)
    if smooth[0] or smooth[1]:
        elev = _box_smooth(elev, smooth[0], smooth[1])
    dx = bx / float(max(1, nx - 1))
    dy = by / float(max(1, ny - 1))

    ls = LightSource(azdeg=float(azdeg), altdeg=float(altdeg))
    rgb = np.clip(rgba[..., :3], 0.0, 1.0)
    # shade_rgb() is exactly hillshade() then a blend; they are called apart
    # here only so the intensity can be re-centred in between.
    illum = ls.hillshade(elev, vert_exag=1.0, dx=dx, dy=dy,
                         fraction=float(fraction))
    if neutral:
        mean = float(np.nanmean(illum))
        if np.isfinite(mean):
            illum = np.clip(illum + (0.5 - mean), 0.0, 1.0)
    illum = illum[..., None]
    if luma_only:
        y0 = (0.2126 * rgb[..., 0:1] + 0.7152 * rgb[..., 1:2]
              + 0.0722 * rgb[..., 2:3])
        y1 = 2.0 * illum * y0 + (1.0 - 2.0 * illum) * y0 ** 2
        scale = np.where(y0 > 1e-6, y1 / np.maximum(y0, 1e-6), 1.0)
        out = np.clip(rgb * scale, 0.0, 1.0)
    else:
        blend = {"soft": ls.blend_soft_light, "overlay": ls.blend_overlay,
                 "hsv": ls.blend_hsv}.get(blend_mode, blend_mode)
        if not callable(blend):
            raise SurfaceError("unknown blend_mode %r (have soft, overlay, "
                               "hsv, or a callable)" % (blend_mode,))
        out = blend(rgb, illum)
    s = float(strength)
    if s != 1.0:
        out = rgb + s * (np.asarray(out, dtype=float) - rgb)
    shaded = rgba.copy()
    shaded[..., :3] = np.clip(out, 0.0, 1.0)
    return shaded


# ---------------------------------------------------------------------------
# underside: the displayed sheet closed into the printed solid
# ---------------------------------------------------------------------------

def _stride_indices(n, step):
    """plot_surface's own sampling: 0, step, 2*step, ..., n-1 (endpoint kept).

    Matching it exactly is what makes the wall rim land on the same vertices
    the drawn surface edge does, instead of a rim that crosses it.
    """
    idx = list(range(0, n - 1, int(max(1, step))))
    if not idx or idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def _darken(rgba, f):
    """Multiply RGB by f, keep alpha.  Works on (..., 4)."""
    out = np.array(rgba, dtype=float, copy=True)
    out[..., :3] = np.clip(out[..., :3] * float(f), 0.0, 1.0)
    return out


def _camera_vector(ax3d):
    """Unit vector from the box centre towards the camera, in box axes.

    Only the SIGNS of the components matter here, and those are what decide
    which side of the solid the viewer is standing on.
    """
    try:
        el = np.radians(float(ax3d.elev))
        az = np.radians(float(ax3d.azim))
    except (AttributeError, TypeError, ValueError):
        return None
    return np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az),
                     np.sin(el)], dtype=float)


def visible_sides(ax3d, cull=True):
    """Which of ('-y', '+y', '-x', '+x', 'bottom') the camera can actually see.

    A closed opaque solid never shows more than two of its four sides at once,
    and it shows its bottom only from below, so this is the honest answer to
    "what is worth drawing from here".

    It is NOT what underside_artists does by default any more.  Culling was
    the first fix for matplotlib's depth sorting -- one collection holding all
    four walls gets ONE depth for the lot, so the far wall lands over the near
    surface -- but it fixed the artefact by deleting the geometry, and a
    solid that loses two of its four sides the moment you orbit it is not a
    solid (Nhan, R4 item 6).  The real fix is one collection PER side, which
    gives the sorter a depth per wall; underside_artists does that now and
    builds all five faces.  This helper stays for callers that want the
    culled set anyway (a cost estimate, or a deliberately open look).
    """
    names = ("-y", "+y", "-x", "+x", "bottom")
    if not cull:
        return list(names)
    v = _camera_vector(ax3d)
    if v is None:
        return list(names)
    # outward normals of the five faces, in the same order
    dots = (-v[1], v[1], -v[0], v[0], -v[2])
    return [n for n, d in zip(names, dots) if d > 0.0]


def underside_artists(ax3d, grid, rgba=None, z_clip=None, base_z=None,
                      color=None, max_cells=DEFAULT_MAX_CELLS,
                      wall_darken=WALL_DARKEN, bottom_darken=BOTTOM_DARKEN,
                      alpha=1.0, bottom=True, cull=False, sides=None,
                      zsort="average", **kw):
    """Side walls + base plane for `grid`, so the screen shows the print.

    Returns a list of Poly3DCollection.  The caller keeps it and calls
    .remove() on each before the next draw; nothing here touches the axes'
    limits, so adding or dropping the underside never moves the camera.

    Shape.  Four skirts, one per grid edge, each dropped from the surface rim
    to `base_z`, plus one quad for the base itself.  A skirt is NOT one quad
    per grid column: it is one POLYGON per displayed column block, whose top
    edge walks every full-resolution vertex in that block.  That is exactly
    the boundary plot_surface draws (it perimeters each strided block rather
    than chording it), so the wall meets the surface with no gap and no
    overlap -- at the same polygon count a strided quad strip would cost.
    The same four edges and the same base the STL writer closes, so the
    picture and the print are the one shape.

    ALL FIVE faces are built by default, and each side is its OWN
    Poly3DCollection.  That pairing is the whole trick (Nhan, R4 item 6:
    "the fill underside does not fill all side").  Matplotlib depth-sorts 3D
    artists one COLLECTION at a time, so four walls sharing a collection get
    one depth between them and the far wall lands on top of the near surface.
    The first fix was to cull the far walls, which traded the artefact for an
    open box -- and worse, the cull is computed at DRAW time from the camera,
    so orbiting the figure by hand (matplotlib re-renders without calling us)
    left the sides it had guessed.  One collection per side gives the sorter
    a depth per wall, every wall is present at every angle, and interactive
    rotation stays correct because there is nothing left to re-guess.  Pass
    cull=True (or sides=[...] from visible_sides()) for the old open look.

    Height.  base_z defaults to the LOW end of z_clip, which is the floor the
    surface itself is clamped to and the floor the Z axis is scaled to.  The
    walls therefore stand on the box floor: they cannot float above it, and
    they cannot punch through it into the tick labels.

    Colour.  Taken from the surface's own edge colours (rgba's first/last row
    and column), darkened by wall_darken, so the sides read as the sides of
    the same object on a white figure and on a black one alike -- the hue is
    the data's, only the value moves.  Pass color=... to override with one
    explicit RGBA for every wall and the base.
    """
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    x = np.asarray(grid.x, dtype=float)
    y = np.asarray(grid.y, dtype=float)
    Z, zlo, _zhi = _display_z(grid, z_clip)
    ny, nx = Z.shape
    if ny < 2 or nx < 2:
        return []
    base = float(zlo if base_z is None else base_z)

    if color is not None:
        from matplotlib.colors import to_rgba
        edge = np.array(to_rgba(color), dtype=float)
        rgba = np.repeat(np.repeat(edge[None, None, :], ny, 0), nx, 1)
    elif rgba is None:
        rgba = np.tile(np.array([0.6, 0.6, 0.6, 1.0]), (ny, nx, 1))
    else:
        rgba = np.asarray(rgba, dtype=float)

    if sides is None:
        sides = visible_sides(ax3d, cull=cull)
    sides = set(sides)
    rs, cs = strides_for(grid, max_cells)
    ci = _stride_indices(nx, cs)
    ri = _stride_indices(ny, rs)

    # one bucket per side: each becomes its own collection below, which is
    # what lets matplotlib sort a far wall behind the surface and a near
    # wall in front of it
    per_side = {}

    def _skirt(name, top_xyz, col):
        """top_xyz: (k, 3) along the rim; close it down to the base plane."""
        floor = np.array([[top_xyz[-1, 0], top_xyz[-1, 1], base],
                          [top_xyz[0, 0], top_xyz[0, 1], base]], dtype=float)
        bucket = per_side.setdefault(name, ([], []))
        bucket[0].append(np.vstack([top_xyz, floor]))
        bucket[1].append(col)

    # y = y[0] and y = y[-1]: walk the wavelength axis
    for name, i_row, flip in (("-y", 0, False), ("+y", ny - 1, True)):
        if name not in sides:
            continue
        yv = y[i_row]
        for a, b in zip(ci[:-1], ci[1:]):
            j = np.arange(a, b + 1)
            top = np.column_stack([x[j], np.full(j.size, yv), Z[i_row, j]])
            if flip:                     # keep every skirt wound the same way
                top = top[::-1]
            _skirt(name, top, rgba[i_row, a])
    # x = x[0] and x = x[-1]: walk the pressure axis
    for name, j_col, flip in (("-x", 0, True), ("+x", nx - 1, False)):
        if name not in sides:
            continue
        xv = x[j_col]
        for a, b in zip(ri[:-1], ri[1:]):
            i = np.arange(a, b + 1)
            top = np.column_stack([np.full(i.size, xv), y[i], Z[i, j_col]])
            if flip:
                top = top[::-1]
            _skirt(name, top, rgba[a, j_col])

    arts = []
    for name in ("-y", "+y", "-x", "+x"):
        polys, cols = per_side.get(name, ([], []))
        if not polys:
            continue
        wall_c = _darken(np.array(cols, dtype=float), wall_darken)
        wall_c[:, 3] = float(alpha)
        walls = Poly3DCollection(polys, facecolors=wall_c, edgecolors=wall_c,
                                 linewidths=0.0, shade=False, zsort=zsort,
                                 **kw)
        walls.set_clip_on(False)
        walls._sparta_side = name
        ax3d.add_collection3d(walls)
        arts.append(walls)

    if bottom and "bottom" in sides:
        rim = np.concatenate([rgba[0, :].reshape(-1, 4),
                              rgba[-1, :].reshape(-1, 4),
                              rgba[:, 0].reshape(-1, 4),
                              rgba[:, -1].reshape(-1, 4)])
        bc = _darken(rim.mean(axis=0), bottom_darken)
        bc[3] = float(alpha)
        # The base drops one thousandth of the height range below the wall
        # feet, and that hair is load-bearing.  Matplotlib sorts whole
        # collections by their NEAREST projected vertex (art3d's
        # do_3d_projection returns min(tzs); `zsort` only orders polygons
        # WITHIN a collection).  base_z defaults to the surface's lowest
        # value, so on any view whose near corner sits at that low point
        # the base's nearest vertex and the surface's nearest vertex are
        # the same depth to the bit -- a tie matplotlib broke in favour of
        # whichever was added last, which is how the floor came to be
        # painted over the data at azim 225.  Nudging the plane down
        # breaks the tie the honest way: from above the base is now
        # strictly farther and sorts behind everything, and from BELOW it
        # is strictly nearer and sorts in front, with no camera test to
        # get stale when the user orbits by hand.  The walls still stand
        # on it (they overlap it by the same hair, so no seam opens).
        _span = abs(float(_zhi) - float(zlo)) or 1.0
        bz = base - _span * 1e-3
        quad = np.array([[x[0], y[0], bz], [x[-1], y[0], bz],
                         [x[-1], y[-1], bz], [x[0], y[-1], bz]],
                        dtype=float)
        floor = Poly3DCollection([quad], facecolors=[bc], edgecolors=[bc],
                                 linewidths=0.0, shade=False, zsort="min",
                                 **kw)
        floor.set_clip_on(False)
        floor._sparta_side = "bottom"
        ax3d.add_collection3d(floor)
        arts.append(floor)
    return arts


def underside_quads(grid, max_cells=DEFAULT_MAX_CELLS, bottom=True,
                    culled=False):
    """How many polygons underside_artists will add at this budget.

    Cheap enough to call from the GUI when it wants to show the cost, and it
    is the number the cell budget has to absorb: the surface itself is
    already at `max_cells`, so the underside is the overhead on top.
    culled=False (the default, and what underside_artists now draws) counts
    all five faces; culled=True counts the old camera-facing subset (one wall
    of each pair, no bottom).
    """
    ny, nx = grid.Z.shape
    rs, cs = strides_for(grid, max_cells)
    per_x = len(_stride_indices(nx, cs)) - 1
    per_y = len(_stride_indices(ny, rs)) - 1
    if culled:
        return int(per_x + per_y)
    return int(2 * per_x + 2 * per_y + (1 if bottom else 0))


# ---------------------------------------------------------------------------
# drawing
# ---------------------------------------------------------------------------

def surface_artists(ax3d, grid, cmap, rev=False, alpha=1.0, shade=True,
                    shade_by="series", z_clip=None, color_range=None,
                    color_values=None, color_ranks=None, n_series=None,
                    max_cells=DEFAULT_MAX_CELLS, edgecolor="none",
                    linewidth=0.0, relief=False, relief_kw=None,
                    underside=False, underside_kw=None, return_extra=False,
                    **kw):
    """Draw `grid` on a Matplotlib 3D axes and return the Poly3DCollection.

    z_clip=(lo, hi) clamps the height the same way the ridge looks clamp it,
    so switching looks does not move the Z axis under the user.

    relief=True hillshades the facecolours through relief_shade() so the
    ridges and valleys are visible.  It also forces matplotlib's own
    `shade` OFF for this call: mpl shades from the polygon normal in data
    units, which on a nm-by-absorbance grid is a near-constant dimming that
    would only mute the relief.  relief_kw is passed straight to
    relief_shade (azdeg, altdeg, vert_exag, blend_mode, luma_only, ...).

    underside=True adds the side walls and base from underside_artists(), so
    the displayed shape closes into the same solid to_stl() writes -- all
    four walls and the base, one collection each.  underside_kw is passed
    straight through (color=... paints every face one flat colour).

    The extra artists are returned as `surf._sparta_underside` (a list, empty
    when underside is off) so an existing caller keeps working unchanged; ask
    for return_extra=True to get (surf, extras) instead and remove them
    explicitly on the next redraw.
    """
    Z = grid.Z
    if z_clip is not None:
        Z = np.clip(Z, float(z_clip[0]), float(z_clip[1]))
    X, Y = np.meshgrid(grid.x, grid.y)
    rgba = surface_colors(grid, cmap, rev=rev, shade_by=shade_by, alpha=alpha,
                          color_range=color_range, color_values=color_values,
                          color_ranks=color_ranks, n_series=n_series)
    rs, cs = strides_for(grid, max_cells)
    if relief:
        rgba = relief_shade(rgba, grid, z_clip=z_clip, strides=(rs, cs),
                            **(relief_kw or {}))
        shade = False           # see the note in relief_shade's docstring
    surf = ax3d.plot_surface(X, Y, Z, facecolors=rgba, rstride=rs, cstride=cs,
                             shade=shade, linewidth=linewidth,
                             edgecolor=edgecolor, antialiased=False, **kw)
    surf.set_clip_on(False)

    extras = []
    if underside:
        extras = underside_artists(ax3d, grid, rgba=rgba, z_clip=z_clip,
                                   max_cells=max_cells, alpha=alpha,
                                   **(underside_kw or {}))
    surf._sparta_underside = extras
    if return_extra:
        return surf, extras
    return surf


# ---------------------------------------------------------------------------
# printable solid
# ---------------------------------------------------------------------------

def height_field(grid, size_mm=DEFAULT_SIZE_MM, base_mm=DEFAULT_BASE_MM,
                 z_exaggeration=1.0, z_range=None):
    """Map the grid into millimetres.

    Returns (x_mm (nx,), y_mm (ny,), z_mm (ny, nx), info).

      * X spans 0 .. size_mm[0] along wavelength, Y spans 0 .. size_mm[1]
        along the series axis, both linear in the data coordinate.
      * The base slab is base_mm thick.  The data relief gets the REST of the
        nominal height, (size_mm[2] - base_mm), multiplied by z_exaggeration.
        So the nominal size is what you get at exaggeration 1, and asking for
        2x relief makes the print taller rather than squashing the base --
        the printed total is reported in `info` and in the sidecar.
      * A flat dataset (all one absorbance) still gets a solid: the relief
        collapses to zero and the print is a plain slab.
    """
    sx, sy, sz = (float(size_mm[0]), float(size_mm[1]), float(size_mm[2]))
    base = float(base_mm)
    if sx <= 0 or sy <= 0:
        raise MeshError("size X and Y must be positive (got %g, %g)" % (sx, sy))
    if base <= 0:
        raise MeshError("base thickness must be positive (got %g)" % base)
    if sz <= base:
        raise MeshError("total height %g mm must exceed the %g mm base"
                        % (sz, base))
    relief = (sz - base) * float(z_exaggeration)
    if relief <= 0:
        raise MeshError("Z exaggeration must be positive (got %g)"
                        % z_exaggeration)

    Z = np.asarray(grid.Z, dtype=float)
    if z_range is None:
        zlo, zhi = float(np.nanmin(Z)), float(np.nanmax(Z))
    else:
        zlo, zhi = float(min(z_range)), float(max(z_range))
        Z = np.clip(Z, zlo, zhi)
    span = zhi - zlo
    # A "constant" channel rarely lands on an exact zero span -- it lands on
    # 1e-16, and dividing by that turns a flat slab into a scale factor of
    # 1e17 in the sidecar.  Judge the span against the data's own magnitude.
    if span <= max(abs(zlo), abs(zhi), 1.0) * 1e-12:
        span = 0.0
    norm = np.zeros_like(Z) if span <= 0 else (Z - zlo) / span
    z_mm = base + norm * relief

    nx, ny = grid.x.size, grid.y.size
    x_mm = np.linspace(0.0, sx, nx)
    y_mm = np.linspace(0.0, sy, ny)
    info = {"size_mm": [sx, sy, sz], "base_mm": base,
            "z_exaggeration": float(z_exaggeration),
            "relief_mm": float(relief),
            "printed_height_mm": float(base + relief),
            "data_z_min": zlo, "data_z_max": zhi,
            "mm_per_data_unit": (float(relief / span) if span > 0 else 0.0)}
    return x_mm, y_mm, z_mm, info


def _boundary_ring(ny, nx):
    """(i, j) of the grid boundary, counter-clockwise seen from +Z, closed."""
    i0 = np.zeros(nx, dtype=np.int64)
    j0 = np.arange(nx, dtype=np.int64)                       # y = min, +x
    i1 = np.arange(1, ny, dtype=np.int64)
    j1 = np.full(ny - 1, nx - 1, dtype=np.int64)             # x = max, +y
    i2 = np.full(nx - 1, ny - 1, dtype=np.int64)
    j2 = np.arange(nx - 2, -1, -1, dtype=np.int64)           # y = max, -x
    i3 = np.arange(ny - 2, 0, -1, dtype=np.int64)
    j3 = np.zeros(ny - 2, dtype=np.int64)                    # x = min, -y
    return (np.concatenate([i0, i1, i2, i3]),
            np.concatenate([j0, j1, j2, j3]))


def build_mesh(grid, size_mm=DEFAULT_SIZE_MM, base_mm=DEFAULT_BASE_MM,
               z_exaggeration=1.0, z_range=None):
    """The closed solid, as an (M, 3, 3) array of triangle corners in mm.

    Three parts, wound so every outward normal points away from the solid:

      top     the data surface, two triangles per grid cell, normals up;
      walls   one quad (two triangles) per boundary edge, dropping the top
              rim straight down to z = 0 -- the rim's vertices are reused, so
              the wall meets the top edge for edge, never T-junction to
              T-junction;
      bottom  a triangle fan from the base centre out to the SAME rim
              vertices, normals down.  A fan (not a second full grid) keeps
              the bottom at ~1k triangles instead of ~90k while still
              sharing every boundary vertex, which is what manifoldness
              actually requires.

    Returns (tris, info).
    """
    x_mm, y_mm, z_mm, info = height_field(grid, size_mm, base_mm,
                                          z_exaggeration, z_range)
    ny, nx = z_mm.shape
    if ny < 2 or nx < 2:
        raise MeshError("need at least a 2 x 2 grid to build a solid")

    X, Y = np.meshgrid(x_mm, y_mm)
    top = np.stack([X, Y, z_mm], axis=-1)                    # (ny, nx, 3)

    a = top[:-1, :-1]
    b = top[:-1, 1:]
    c = top[1:, 1:]
    d = top[1:, :-1]
    t_top = np.concatenate([
        np.stack([a, b, c], axis=-2).reshape(-1, 3, 3),
        np.stack([a, c, d], axis=-2).reshape(-1, 3, 3)])

    ri, rj = _boundary_ring(ny, nx)
    rim_t = top[ri, rj]                                      # (R, 3)
    rim_b = rim_t.copy()
    rim_b[:, 2] = 0.0
    nxt = np.roll(np.arange(rim_t.shape[0]), -1)
    t_wall = np.concatenate([
        np.stack([rim_t, rim_b, rim_b[nxt]], axis=-2),
        np.stack([rim_t, rim_b[nxt], rim_t[nxt]], axis=-2)])

    centre = np.array([x_mm.mean(), y_mm.mean(), 0.0], dtype=float)
    t_bot = np.stack([np.repeat(centre[None, :], rim_b.shape[0], axis=0),
                      rim_b[nxt], rim_b], axis=-2)

    tris = np.concatenate([t_top, t_wall, t_bot]).astype(float)
    info = dict(info)
    info.update({"triangles": int(tris.shape[0]),
                 "triangles_top": int(t_top.shape[0]),
                 "triangles_wall": int(t_wall.shape[0]),
                 "triangles_bottom": int(t_bot.shape[0]),
                 "grid_rows": int(ny), "grid_cols": int(nx)})
    return tris, info


def face_normals(tris):
    """Unit outward normals, one per triangle.  Degenerate faces get 0."""
    v1 = tris[:, 1] - tris[:, 0]
    v2 = tris[:, 2] - tris[:, 0]
    n = np.cross(v1, v2)
    mag = np.linalg.norm(n, axis=1)
    good = mag > 0
    out = np.zeros_like(n)
    out[good] = n[good] / mag[good][:, None]
    return out


def validate_mesh(tris, tol=WELD_TOL, expect_euler=2, raise_on_fail=True):
    """Prove the triangle soup is a closed, consistently wound solid.

    The proof is edge-based, which is the only test that actually means
    watertight:

      1. weld vertices that agree to `tol` (an STL has no index buffer, so
         this is what a slicer does too);
      2. every triangle contributes three DIRECTED edges;
      3. each undirected edge must be used exactly twice -- once is a hole,
         three times is a non-manifold seam;
      4. those two uses must run in OPPOSITE directions, which is what makes
         the winding, and therefore every normal, consistent;
      5. V - E + F must equal 2 (Euler characteristic of a genus-0 closed
         surface).  A heightfield slab is genus 0, so anything else means
         the mesh grew a handle or fell into two pieces.

    Returns a dict of counts.  Raises MeshError on failure unless
    raise_on_fail=False.
    """
    tris = np.asarray(tris, dtype=float)
    if tris.ndim != 3 or tris.shape[1:] != (3, 3):
        raise MeshError("expected an (M, 3, 3) triangle array, got %r"
                        % (tris.shape,))
    report = {"triangles": int(tris.shape[0])}
    problems = []

    if not np.isfinite(tris).all():
        problems.append("mesh contains non-finite coordinates")

    flat = tris.reshape(-1, 3)
    keys = np.rint(flat / float(tol)).astype(np.int64)
    _, first, inv = np.unique(keys, axis=0, return_index=True,
                              return_inverse=True)
    inv = np.asarray(inv).ravel()
    faces = inv.reshape(-1, 3)
    nv = int(first.size)
    report["vertices"] = nv

    degenerate = int(((faces[:, 0] == faces[:, 1])
                      | (faces[:, 1] == faces[:, 2])
                      | (faces[:, 2] == faces[:, 0])).sum())
    report["degenerate"] = degenerate
    if degenerate:
        problems.append("%d degenerate triangle(s)" % degenerate)

    e0 = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2]])
    e1 = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0]])
    lo = np.minimum(e0, e1).astype(np.int64)
    hi = np.maximum(e0, e1).astype(np.int64)
    key = lo * np.int64(nv) + hi
    sign = np.where(e0 < e1, 1, -1)
    _, inv_e, counts = np.unique(key, return_inverse=True, return_counts=True)
    inv_e = np.asarray(inv_e).ravel()
    ne = int(counts.size)
    report["edges"] = ne
    report["faces"] = int(faces.shape[0])

    boundary = int((counts == 1).sum())
    nonmanifold = int((counts > 2).sum())
    report["boundary_edges"] = boundary
    report["nonmanifold_edges"] = nonmanifold
    if boundary:
        problems.append("%d boundary edge(s) -- the mesh has holes" % boundary)
    if nonmanifold:
        problems.append("%d edge(s) shared by more than two faces"
                        % nonmanifold)

    sgn = np.bincount(inv_e, weights=sign, minlength=ne)
    flipped = int(np.count_nonzero(np.rint(sgn[counts == 2])))
    report["flipped_edges"] = flipped
    if flipped:
        problems.append("%d edge(s) traversed the same way by both faces "
                        "(inconsistent winding)" % flipped)

    euler = nv - ne + int(faces.shape[0])
    report["euler"] = int(euler)
    report["euler_expected"] = int(expect_euler)
    if expect_euler is not None and euler != expect_euler:
        problems.append("Euler characteristic %d, expected %d"
                        % (euler, expect_euler))

    # a closed, correctly wound solid has positive signed volume
    v = tris
    vol = float(np.einsum("ij,ij->i",
                          v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0)
    report["signed_volume_mm3"] = vol
    if vol <= 0:
        problems.append("signed volume %.6g is not positive (normals point "
                        "inward)" % vol)

    report["watertight"] = not problems
    report["problems"] = problems
    if problems and raise_on_fail:
        raise MeshError("mesh is not printable: " + "; ".join(problems))
    return report


# ---------------------------------------------------------------------------
# binary STL
# ---------------------------------------------------------------------------

_STL_DTYPE = np.dtype([("normal", "<f4", (3,)), ("v", "<f4", (3, 3)),
                       ("attr", "<u2")])


def write_stl(tris, path, header=None):
    """Write an (M, 3, 3) triangle array as a binary STL.  Returns the path.

    The 80-byte header deliberately does not start with the word "solid":
    some readers sniff that prefix and try to parse a binary file as ASCII.
    """
    tris = np.asarray(tris, dtype=float)
    n = tris.shape[0]
    if n == 0:
        raise MeshError("refusing to write an empty STL")
    if n > 0xFFFFFFFF:
        raise MeshError("%d triangles exceeds the binary STL limit" % n)
    head = (header or "SPARTA surface solid").encode("ascii", "replace")[:79]
    head = head + b" " * (80 - len(head))

    rec = np.zeros(n, dtype=_STL_DTYPE)
    rec["normal"] = face_normals(tris).astype("<f4")
    rec["v"] = tris.astype("<f4")
    with open(path, "wb") as f:
        f.write(head)
        f.write(struct.pack("<I", n))
        f.write(rec.tobytes())
    return path


def to_stl(grid, path, size_mm=DEFAULT_SIZE_MM, base_mm=DEFAULT_BASE_MM,
           z_exaggeration=1.0, z_range=None, validate=True, header=None,
           provenance=True, provenance_writer=None, extra=None):
    """Grid -> watertight binary STL on disk.  Returns a stats dict.

    The manifold proof runs BEFORE anything is written (validate=True), so a
    mesh that would print as a leaking shell never reaches the filesystem.
    Set validate=False only if you are deliberately inspecting a broken mesh.

    A `<path>.provenance.json` sidecar is written alongside, in the same
    shape as the app's other export sidecars.  Pass provenance_writer to hand
    that job to the application's own _provenance(); the standalone default
    writes an equivalent file so a script-built STL is just as traceable.
    """
    tris, info = build_mesh(grid, size_mm=size_mm, base_mm=base_mm,
                            z_exaggeration=z_exaggeration, z_range=z_range)
    report = validate_mesh(tris) if validate else {"watertight": None}
    write_stl(tris, path, header=header)

    stats = dict(info)
    stats["mesh"] = report
    stats["bytes"] = int(os.path.getsize(path))
    stats["path"] = path
    params = stl_params(grid, stats)
    if extra:
        params.update(extra)
    if provenance:
        if provenance_writer is not None:
            stats["provenance"] = provenance_writer(path, "stl_3d", params,
                                                    [path])
        else:
            stats["provenance"] = write_provenance(path, "stl_3d", params,
                                                   files=[path])
    return stats


def stl_params(grid, stats):
    """The params block quoted in the provenance sidecar.

    Everything needed to rebuild the same solid from the same CSVs: the grid
    recipe, the physical mapping, and the manifold proof's own numbers.
    """
    m = dict(grid.meta)
    mesh = stats.get("mesh") or {}
    return {
        "schema": SCHEMA,
        "surface": {"method": m.get("method"), "n_cols": m.get("n_cols"),
                    "method_requested": m.get("method_requested"),
                    "method_fallback": m.get("method_fallback"),
                    "n_rows": m.get("n_rows"),
                    "n_traces": m.get("n_traces"),
                    "series_values": m.get("y_values"),
                    "wavelength_min": m.get("x_min"),
                    "wavelength_max": m.get("x_max"),
                    "traces_dropped": m.get("traces_dropped"),
                    "series_values_merged": m.get("series_values_merged")},
        "solid": {"size_mm": stats.get("size_mm"),
                  "base_mm": stats.get("base_mm"),
                  "z_exaggeration": stats.get("z_exaggeration"),
                  "printed_height_mm": stats.get("printed_height_mm"),
                  "relief_mm": stats.get("relief_mm"),
                  "mm_per_data_unit": stats.get("mm_per_data_unit"),
                  "data_z_min": stats.get("data_z_min"),
                  "data_z_max": stats.get("data_z_max"),
                  "triangles": stats.get("triangles"),
                  "format": "binary STL, mm"},
        "watertight": {"proven": mesh.get("watertight"),
                       "vertices": mesh.get("vertices"),
                       "edges": mesh.get("edges"),
                       "faces": mesh.get("faces"),
                       "euler_characteristic": mesh.get("euler"),
                       "boundary_edges": mesh.get("boundary_edges"),
                       "nonmanifold_edges": mesh.get("nonmanifold_edges"),
                       "flipped_edges": mesh.get("flipped_edges"),
                       "signed_volume_mm3": mesh.get("signed_volume_mm3")},
    }


def file_sha1(path, chunk=1 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def write_provenance(target, kind, params, files=None, tool="SPARTA",
                     version=None, input_folder=None, variable_name=None,
                     variable_unit=None):
    """Standalone twin of the app's _provenance(): same keys, same order.

    The application passes its own writer to to_stl() so a GUI export carries
    the real tool version, input folder and series-variable names.  This one
    documents the shape and keeps script-built exports traceable.
    """
    payload = {"tool": tool, "version": version,
               "written": datetime.datetime.now().isoformat(timespec="seconds"),
               "kind": kind, "input_folder": input_folder,
               "variable_name": variable_name, "variable_unit": variable_unit,
               "params": params}
    if files:
        payload["files"] = [{"name": os.path.basename(p),
                             "sha1": file_sha1(p)}
                            for p in files if os.path.isfile(p)]
    sidecar = (os.path.join(target, "_export.provenance.json")
               if os.path.isdir(target) else target + ".provenance.json")
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return sidecar


def export_stl_from_records(records, path, surface_kw=None, **stl_kw):
    """build_surface() then to_stl(), for callers that hold records.

    Kept here rather than in the app so the whole path -- grid recipe, NaN
    policy, physical mapping, manifold proof, sidecar -- lives in one file
    and can be exercised without a window on screen.
    """
    grid = build_surface(records, **(surface_kw or {}))
    stats = to_stl(grid, path, **stl_kw)
    stats["grid"] = grid
    return stats


# ---------------------------------------------------------------------------
# the folder divider -- ONE trace as a standing plate
# ---------------------------------------------------------------------------
#
# The surface solid needs three traces and prints a landscape.  A single
# spectrum has no second axis, so it gets its own shape: a thin upright plate
# whose TOP EDGE is that trace's silhouette, standing on a wider foot.  The
# result is a file divider / bookmark that carries one measurement.
#
# Geometry.  The cross-section in the (y, z) plane is a T: a foot of width
# `foot_mm` and height `base_mm`, and a plate of width `plate_mm` rising from
# it to the silhouette.  That profile is swept along x (the spectral axis), so
# the whole solid is a generalised prism with a fixed 10-vertex outline whose
# only varying vertex pair is the top edge.
#
# The 10 profile vertices, counter-clockwise seen from +x, hf = foot/2,
# hp = plate/2, hb = base_mm, t = the silhouette height of this column:
#
#     p0 (-hf, 0)   p1 (-hp, 0)   p2 (+hp, 0)   p3 (+hf, 0)
#     p4 (+hf, hb)  p5 (+hp, hb)  p6 (+hp, t)   p7 (-hp, t)
#     p8 (-hp, hb)  p9 (-hf, hb)
#
# p1 and p2 sit ON the bottom edge and p5, p8 ON the shoulder line, so the two
# end caps tile into four quads with no T-junction anywhere: every cap edge is
# either shared by two cap quads or used exactly once by the swept wall.  That
# is what makes the count come out at Euler 2 by construction, and
# validate_mesh() still proves it before anything is written.

#: divider defaults (mm): plate thickness, foot depth, foot height, and the
#: plate height the LOWEST point of the trace still gets.  2 mm prints solid
#: on a 0.4 mm nozzle; a 14 mm foot holds an 80 mm plate upright.
DEFAULT_PLATE_MM = 2.0
DEFAULT_FOOT_MM = 14.0
DEFAULT_DIVIDER_BASE_MM = 4.0
DEFAULT_MIN_RISE_MM = 1.0

#: columns sampled along the spectral axis for the silhouette.  400 columns
#: give ~8k triangles, which slices in a second and keeps every feature the
#: eye can see on a 120 mm plate.
DEFAULT_DIVIDER_COLS = 400

#: divider size (mm): x span, total height including the foot.
DEFAULT_DIVIDER_MM = (120.0, 80.0)


def divider_profile(x, z, n_cols=DEFAULT_DIVIDER_COLS, x_range=None):
    """One trace -> (xg, zg) on an even axis, ready to become a silhouette.

    Runs the same NaN policy as the surface (_clean_trace), then resamples
    the finite span onto n_cols evenly spaced columns.
    """
    cx, cz, lo, hi = _clean_trace(x, z)
    if cx is None or cx.size < 2:
        raise SurfaceError("the trace carries no usable data")
    if x_range is not None:
        lo = max(lo, float(min(x_range)))
        hi = min(hi, float(max(x_range)))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        raise SurfaceError("the trace has no finite wavelength range")
    n_cols = int(max(8, n_cols))
    xg = np.linspace(lo, hi, n_cols)
    return xg, np.interp(xg, cx, cz)


def divider_height_field(zg, size_mm=DEFAULT_DIVIDER_MM,
                         base_mm=DEFAULT_DIVIDER_BASE_MM,
                         min_rise_mm=DEFAULT_MIN_RISE_MM,
                         z_exaggeration=1.0, z_range=None):
    """Map one silhouette into millimetres.

    Returns (top_mm, info).  `top_mm` is the height of the plate's top edge
    at every column, measured from the table the divider stands on.  The
    lowest measured value sits `min_rise_mm` above the foot, so the thinnest
    part of the plate is still printable.
    """
    sx, sz = float(size_mm[0]), float(size_mm[1])
    base = float(base_mm)
    rise = float(min_rise_mm)
    if sx <= 0:
        raise MeshError("width X must be positive (got %g)" % sx)
    if base <= 0:
        raise MeshError("foot height must be positive (got %g)" % base)
    if rise <= 0:
        raise MeshError("the minimum plate rise must be positive (got %g)"
                        % rise)
    if sz <= base + rise:
        raise MeshError("total height %g mm must exceed the %g mm foot plus "
                        "the %g mm minimum rise" % (sz, base, rise))
    relief = (sz - base - rise) * float(z_exaggeration)
    if relief <= 0:
        raise MeshError("Z exaggeration must be positive (got %g)"
                        % z_exaggeration)

    Z = np.asarray(zg, dtype=float)
    if z_range is None:
        zlo, zhi = float(np.nanmin(Z)), float(np.nanmax(Z))
    else:
        zlo, zhi = float(min(z_range)), float(max(z_range))
        Z = np.clip(Z, zlo, zhi)
    span = zhi - zlo
    if span <= max(abs(zlo), abs(zhi), 1.0) * 1e-12:
        span = 0.0
    norm = np.zeros_like(Z) if span <= 0 else (Z - zlo) / span
    top_mm = base + rise + norm * relief
    info = {"size_mm": [sx, sz], "base_mm": base, "min_rise_mm": rise,
            "z_exaggeration": float(z_exaggeration),
            "relief_mm": float(relief),
            "printed_height_mm": float(base + rise + relief),
            "data_z_min": zlo, "data_z_max": zhi,
            "mm_per_data_unit": (float(relief / span) if span > 0 else 0.0)}
    return top_mm, info


def build_divider_mesh(x, z, size_mm=DEFAULT_DIVIDER_MM,
                       plate_mm=DEFAULT_PLATE_MM, foot_mm=DEFAULT_FOOT_MM,
                       base_mm=DEFAULT_DIVIDER_BASE_MM,
                       min_rise_mm=DEFAULT_MIN_RISE_MM,
                       z_exaggeration=1.0, z_range=None,
                       n_cols=DEFAULT_DIVIDER_COLS, x_range=None):
    """One trace -> the closed divider solid, (M, 3, 3) triangles in mm.

    See the module note above for the profile and why it is manifold by
    construction.  Returns (tris, info).
    """
    plate = float(plate_mm)
    foot = float(foot_mm)
    if plate <= 0:
        raise MeshError("plate thickness must be positive (got %g)" % plate)
    if foot <= plate:
        raise MeshError("the foot (%g mm) must be wider than the plate "
                        "(%g mm), or it is not a foot" % (foot, plate))

    xg, zg = divider_profile(x, z, n_cols=n_cols, x_range=x_range)
    top, info = divider_height_field(zg, size_mm=size_mm, base_mm=base_mm,
                                     min_rise_mm=min_rise_mm,
                                     z_exaggeration=z_exaggeration,
                                     z_range=z_range)
    nx = xg.size
    if nx < 2:
        raise MeshError("need at least two columns to sweep a divider")

    x_mm = np.linspace(0.0, float(size_mm[0]), nx)
    hp, hf, hb = plate / 2.0, foot / 2.0, float(base_mm)

    # (nx, 10, 3): the swept profile, counter-clockwise seen from +x
    P = np.empty((nx, 10, 3), dtype=float)
    P[:, :, 0] = x_mm[:, None]
    ys = np.array([-hf, -hp, hp, hf, hf, hp, hp, -hp, -hp, -hf], dtype=float)
    P[:, :, 1] = ys[None, :]
    zs = np.array([0.0, 0.0, 0.0, 0.0, hb, hb, np.nan, np.nan, hb, hb])
    P[:, :, 2] = zs[None, :]
    P[:, 6, 2] = top
    P[:, 7, 2] = top

    def _quads(q):
        """(K, 4, 3) quads -> (2K, 3, 3) triangles, winding preserved."""
        return np.concatenate([np.stack([q[:, 0], q[:, 1], q[:, 2]], axis=1),
                               np.stack([q[:, 0], q[:, 2], q[:, 3]], axis=1)])

    # swept walls: one quad per boundary edge per column step
    ring = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5),
            (5, 6), (6, 7), (7, 8), (8, 9), (9, 0)]
    walls = []
    A, B = P[:-1], P[1:]
    for k0, k1 in ring:
        walls.append(np.stack([A[:, k0], A[:, k1], B[:, k1], B[:, k0]],
                              axis=1))
    t_wall = _quads(np.concatenate(walls))

    # end caps: four quads that tile the T with no loose vertex
    cap_quads = [(0, 1, 8, 9), (1, 2, 5, 8), (2, 3, 4, 5), (8, 5, 6, 7)]
    far = np.stack([np.stack([P[-1, a], P[-1, b], P[-1, c], P[-1, d]])
                    for a, b, c, d in cap_quads])          # normal +x
    near = np.stack([np.stack([P[0, d], P[0, c], P[0, b], P[0, a]])
                     for a, b, c, d in cap_quads])         # normal -x
    t_cap = np.concatenate([_quads(far), _quads(near)])

    tris = np.concatenate([t_wall, t_cap]).astype(float)
    info = dict(info)
    info.update({"shape": "divider", "triangles": int(tris.shape[0]),
                 "triangles_wall": int(t_wall.shape[0]),
                 "triangles_cap": int(t_cap.shape[0]),
                 "plate_mm": plate, "foot_mm": foot,
                 "columns": int(nx),
                 "wavelength_min": float(xg[0]),
                 "wavelength_max": float(xg[-1])})
    return tris, info


def divider_params(info, stats):
    """The params block quoted in a divider's provenance sidecar."""
    mesh = stats.get("mesh") or {}
    return {
        "schema": SCHEMA,
        "silhouette": {"columns": info.get("columns"),
                       "wavelength_min": info.get("wavelength_min"),
                       "wavelength_max": info.get("wavelength_max"),
                       "series_value": info.get("series_value"),
                       "trace_label": info.get("trace_label")},
        "solid": {"shape": "divider",
                  "size_mm": info.get("size_mm"),
                  "plate_mm": info.get("plate_mm"),
                  "foot_mm": info.get("foot_mm"),
                  "base_mm": info.get("base_mm"),
                  "min_rise_mm": info.get("min_rise_mm"),
                  "z_exaggeration": info.get("z_exaggeration"),
                  "printed_height_mm": info.get("printed_height_mm"),
                  "relief_mm": info.get("relief_mm"),
                  "mm_per_data_unit": info.get("mm_per_data_unit"),
                  "data_z_min": info.get("data_z_min"),
                  "data_z_max": info.get("data_z_max"),
                  "triangles": info.get("triangles"),
                  "format": "binary STL, mm"},
        "watertight": {"proven": mesh.get("watertight"),
                       "vertices": mesh.get("vertices"),
                       "edges": mesh.get("edges"),
                       "faces": mesh.get("faces"),
                       "euler_characteristic": mesh.get("euler"),
                       "boundary_edges": mesh.get("boundary_edges"),
                       "nonmanifold_edges": mesh.get("nonmanifold_edges"),
                       "flipped_edges": mesh.get("flipped_edges"),
                       "signed_volume_mm3": mesh.get("signed_volume_mm3")},
    }


def divider_to_stl(x, z, path, validate=True, header=None, provenance=True,
                   provenance_writer=None, extra=None, meta=None,
                   **divider_kw):
    """One trace -> a watertight binary divider STL on disk.

    The manifold proof runs BEFORE the file is opened, exactly as to_stl()
    does, so a leaking plate never reaches the filesystem.  Returns a stats
    dict in the same shape to_stl() returns.
    """
    tris, info = build_divider_mesh(x, z, **divider_kw)
    if meta:
        info.update(meta)
    report = validate_mesh(tris) if validate else {"watertight": None}
    write_stl(tris, path, header=header)

    stats = dict(info)
    stats["mesh"] = report
    stats["bytes"] = int(os.path.getsize(path))
    stats["path"] = path
    params = divider_params(info, stats)
    if extra:
        params.update(extra)
    if provenance:
        if provenance_writer is not None:
            stats["provenance"] = provenance_writer(path, "stl_divider",
                                                    params, [path])
        else:
            stats["provenance"] = write_provenance(path, "stl_divider",
                                                   params, files=[path])
    return stats


def export_divider_from_record(record, path, x_key="wl",
                               z_key="absorbance", **kw):
    """divider_to_stl() for callers that hold one app record."""
    return divider_to_stl(record[x_key], record[z_key], path, **kw)


# ---------------------------------------------------------------------------
# Ship note 1 -- why linear is the default, and what the curves really cost
# ---------------------------------------------------------------------------
#
# All four interpolators were built from the real 19-pressure Y04_Arch29
# series (109 x 400 grid, six synthesised rows per gap) and measured, not
# assumed.  The pressure axis of that series is wildly uneven -- gaps of
# 0.1, 0.3, 2.3 ... 7.2 GPa -- and that is what decides the result.
#
# Overshoot, counted over the 36 000 interpolated cells that sit strictly
# between two measured pressures.  A cell is "outside" if its height leaves
# the [min, max] envelope of the two measured rows bracketing it.  The
# measured absorbance range is -0.235 .. 2.844, span 3.079:
#
#   method      cells outside   max excursion   as % of span   min height
#   linear                  0         0.00000          0.00%      -0.235
#   quadratic          14 853         4.82682        156.77%      -4.998
#   cubic              17 481         4.38145        142.30%      -4.553
#   pchip                   0         0.00000          0.00%      -0.235
#
# Half the interpolated sheet is invented, and it is invented at more than
# the size of the entire measurement.  A raw cubic through 0.3 and 7.1 GPa
# swings to -4.55 absorbance -- a NEGATIVE absorbance twenty times deeper
# than any measured dip -- because the knots either side are 0.3 and 7.2 GPa
# apart and a C2 spline has to pay for that with curvature somewhere.  On the
# printed solid it is worse than cosmetic: height_field normalises to the
# grid's own range, so cubic's -4.55 .. 3.18 range squeezes the real
# 3.08-unit signal into 40% of the relief and spends the other 60% on ringing.
#
# Timing, warm process, best of 5, whole build_surface() on the real grid:
#
#   linear 0.0029 s | quadratic 0.0031 s | cubic 0.0032 s | pchip 0.0035 s
#
# The old note here claimed PCHIP cost 0.63 s against linear's 0.004 s.  That
# was a cold measurement: 0.62 s of it is `import scipy.interpolate` on first
# use, which every curved method pays exactly once per session.  The
# interpolation itself is 0.10 ms (linear) to 0.61 ms (pchip) on this grid.
# So cost is NOT the reason to prefer linear, and the "150x" claim was wrong.
#
# The reason is still shape.  Linear says exactly what is known: these two
# spectra, and a straight line between them.  PCHIP is shape preserving and
# so also never invents, but it leaves and enters every measured pressure
# with zero slope, drawing a small plateau at each measurement -- a claim the
# data does not make, and a visible one on the 18.7 / 18.8 GPa pair.  Raw
# quadratic and cubic invent, at scale.
#
# LINEAR stays DEFAULT_METHOD.  The others are offered because the user asked
# to choose; resolve_method() and grid.meta["method_fallback"] make a
# degraded choice visible rather than silent.
#
# ---------------------------------------------------------------------------
# Ship note 2 -- relief shading and the underside, measured on the same grid
# ---------------------------------------------------------------------------
#
#   * matplotlib's own plot_surface(shade=True) computes face normals in DATA
#     units.  On this grid the wavelength component of those normals averages
#     3.4% of the pressure component: it shades across pressure and is nearly
#     blind along wavelength.  Its multiplier runs 0.45 .. 0.91 (mean 0.75),
#     which is a 25% flat dimming of the whole sheet.
#   * relief_shade() lights the surface in BOX coordinates instead, so both
#     axes contribute.  Luminance contrast between adjacent DRAWN quads, in
#     L* units:
#
#       shading           along pressure   along wavelength
#       none                       1.39               0.00
#       mpl shade=True             2.23               0.46
#       relief 0.6 (default)       2.79               2.39
#       relief 1.0                 4.02               3.94
#
#     Five times the wavelength-direction contrast of what ships today: that
#     is the "hills" that were not visible.
#   * Colour fidelity.  The illumination is re-centred on 0.5 (neutral=True)
#     so the shading has no net effect on a row's mean colour.  Distance of a
#     drawn quad from its own colorbar swatch, mean dE(CIELAB):
#     mpl shade=True 15.0, relief 0.6 4.9, relief 1.0 8.4.  Relief shading is
#     three times MORE faithful to the colorbar than today's default.
#   * At strength 0.6: |dh| p99 = 5.1 deg of hue, dC* p99 = +10.3, dL* p1..p99
#     = -9.7 .. +6.8.  The within-row colour spread the shading introduces is
#     3.4 dE against a median 11.5 dE step between adjacent measured
#     pressures -- 30%.  Walking the batlow path, 17 of 18 measured-pressure
#     pairs stay in order; the one that inverts is 0.0 -> 0.3 GPa, whose
#     unshaded colours are already only 1.30 dE apart.  The shading can only
#     reorder pressures the colormap could not tell apart to begin with.
#   * Elevation is box-smoothed before the gradient.  Y04's spectra carry an
#     interference fringe of dominant period 22 nm (13 columns), and an
#     unsmoothed hillshade renders that as speckle which the display's own
#     striding then aliases into a moire.  A half-window of 2*cstride (8
#     columns, 29 nm) removes it and leaves the ridge.
#   * Cost per redraw on the real grid.  The array work is relief_shade()
#     5.4 ms and underside_artists() 2.4 ms at the default 8000-cell budget
#     (5.2 / 1.8 ms at the 3000-cell Performance budget).  The extra
#     canvas.draw() time is below the run-to-run noise of the draw itself:
#     interleaved, 30 rounds, the p10 deltas are -2.5 .. +2.1 ms against a
#     296 ms plain draw (default) and a 155 ms one (Performance).  So the
#     honest figure is ~5 ms for shading, ~2 ms for the underside, ~8 ms for
#     both, on a redraw that costs 150-300 ms.  Both are affordable while
#     orbiting.
#   * The underside used to be BACKFACE CULLED, and the reason was real:
#     matplotlib depth-sorts one collection at a time, so four walls in one
#     collection get one depth for the lot and the far wall is painted over
#     the near surface at most camera angles.  Culling removed the artefact
#     by removing the geometry, which is not what a solid is -- Nhan, R4
#     item 6: "the fill underside does not fill all side".  It was also
#     computed at DRAW time from the camera, so orbiting the figure by hand
#     (matplotlib re-renders without calling us) left whichever pair it had
#     last guessed.
#     The fix is one COLLECTION PER SIDE.  Each wall then carries its own
#     depth and sorts against the surface correctly, every wall is present
#     at every angle, and there is nothing left to re-guess on rotation.
#     Cost: all five faces instead of two, 309 polygons at the default
#     budget and 209 under Performance mode -- 5.8% and 7.8% of the
#     surface's own quad count, still small change against a 150-300 ms
#     redraw.
#   * The base plane sits one thousandth of the height range BELOW the wall
#     feet.  art3d's do_3d_projection returns min(tzs) -- the collection's
#     nearest vertex -- as the sort key (`zsort` only orders polygons WITHIN
#     a collection), and base_z defaults to the surface's lowest value, so on
#     any view whose near corner sits at that low point the base and the
#     surface tie to the bit.  Matplotlib broke the tie in favour of whatever
#     was added last and painted the floor over the data (reproducible at
#     elev 28, azim 225).  The nudge is invisible, breaks the tie the honest
#     way, and gets the from-below case right for free: below the plane the
#     base really is the nearest face, and now sorts that way.
