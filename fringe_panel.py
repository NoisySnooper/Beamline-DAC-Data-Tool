"""
fringe_panel.py  --  the fringe workbench: FFT view, sidebar cards, pop-out.

The whole interactive surface lives here.  app.py owns five small touchpoints
(import, the centre Plot|Fringe view switch, the right-notebook Fringe tab, the
settings defaults, the session payload) and nothing else; every widget, every
mouse gesture and all of the workbench state is built and held by
:class:`FringeWorkbench`.

Numeric core vendored from `defringe_dac.py` (DAC Absorption Fringe Analysis).
    Source module : defringe_dac.py  (launch_fft_gui, :8994-:15903)
    Author        : Matthew R. Diamond
    Repository    : github.com/matthewrdiamond/DAC-Absorption-Fringe-Analysis
    License       : vendored under MIT by permission of the author.

This module is the SPARTA-side re-implementation of that GUI's behaviour on
top of the vendored pure functions (fringe_detect / fringe_notch / fringe_fit /
fringe_optics / fringe_stack / fringe_materials / fringe_config).  The physics,
the click grammar and the state discipline are his; the widget grammar,
theming and layout are SPARTA's (DESIGN_RULES).

NQT / Lee Lab -- Aug 2026.
"""

import json
import os
import sys
import time
import tkinter as tk
import warnings
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.path import Path as _MPath
from matplotlib.ticker import AutoMinorLocator, FuncFormatter, MaxNLocator
from matplotlib.ticker import ScalarFormatter

import fringe_materials
import fringe_optics
import fringe_popout
import fringe_stack
from fringe_config import DIAMOND_MODELS, FringeConfig
from fringe_detect import compute_channel_fit
from fringe_notch import removed_fraction

# ---------------------------------------------------------------------------
# app.py's vocabulary, mirrored here and re-bound from the host module at first
# use so there is still exactly ONE source of truth (DESIGN_RULES rule 9).  The
# literals below are only the fallback the standalone harness runs on.
# ---------------------------------------------------------------------------
LBL_W = 11
LBL_W2 = 6
PAD_ROW = (4, 1)
PAD_GROUP = (8, 2)
PAD_TIGHT = (0, 1)
PAD_X = 6
PAD_X_TIGHT = 2
MUTED = None            # app.py's sentinel; rebound below
Tooltip = None          # app.py's tooltip class; rebound below

_HOST_BOUND = [False]


def _bind_host(app):
    """Adopt the host module's spacing vocabulary, MUTED sentinel and Tooltip.

    fringe_panel must not import app.py (that would be circular), so the two
    names it genuinely shares are looked up on the App's own module the first
    time a workbench is built.  Missing names keep the fallbacks, which is what
    the standalone harness relies on.
    """
    if _HOST_BOUND[0]:
        return
    mod = sys.modules.get(type(app).__module__)
    if mod is not None:
        g = globals()
        for name in ("LBL_W", "LBL_W2", "PAD_ROW", "PAD_GROUP", "PAD_TIGHT",
                     "PAD_X", "PAD_X_TIGHT", "MUTED", "Tooltip"):
            if hasattr(mod, name):
                g[name] = getattr(mod, name)
    _HOST_BOUND[0] = True


# ---------------------------------------------------------------------------
# Settings defaults -- the app patch folds these in under the "# b keys" marker.
# Every key is versioned with the fr_ prefix so nothing collides with the
# frozen v1.4.8 settings names.
# ---------------------------------------------------------------------------
SETTINGS_DEFAULTS = {
    "fr_view": "plot",              # centre view the app opens in
    "fr_anvil": "diamond",
    "fr_diamond_model": "constant",  # constant|cauchy|oscillator|eremets
    "fr_medium": "Other",          # his default: manual medium
    "fr_medium_n": 1.2,            # his n_medium default
    "fr_layer2_on": False,
    "fr_layer2": "KCl",
    "fr_sample_name": "sample",
    "fr_n_sample": 1.50,           # his defaults, verbatim
    "fr_d1_um": 0.0,
    "fr_t_um": 20.0,
    "fr_d2_um": 0.0,
    "fr_lock_total": False,
    "fr_fine_step": False,
    "fr_wl_min": 600.0,
    "fr_wl_max": 800.0,
    "fr_wl_overrides": {},          # input folder -> [wl_min, wl_max]
    "fr_nt_min_um": 8.0,
    "fr_nt_max_um": 300.0,
    "fr_pvalue_max": 1e-4,
    "fr_agree_tol": 0.15,
    "fr_halfwidth_um": 3.0,
    "fr_lowpass_on": True,         # legacy scalars (pre-R7): kept only
    "fr_lp_cutoff_um": 15.0,       #   as the per-channel migration seed
    "fr_lp_bg_on": None,           # per-channel low-pass; None = seed
    "fr_lp_bg_um": None,           #   from the legacy scalar pair once
    "fr_lp_s_on": None,
    "fr_lp_s_um": None,
    "fr_fit_mode": "distinct",      # distinct|shared
    "fr_suppress_report": False,    # keep the fringe report out of the log
    "fr_width_migrated": False,
    "fr_popout_geom": "",
}

# ---------------------------------------------------------------------------
# Phase C settings -- the app patch folds these in under the "# c keys" marker,
# the same way the "# b keys" block folds in SETTINGS_DEFAULTS.  Kept apart so
# a settings file written by a v1.4.9 build without the series level still
# reads, and so the two markers stay independently greppable.
# ---------------------------------------------------------------------------
C_SETTINGS_DEFAULTS = {
    # {DAC}_{Sample} -> {"pressures": [...], "path": str, "saved": iso}
    # Written by Data > Traces > Decompression list, read back on every
    # _build_trace_checks so a reload re-applies the same branches.
    "fr_dlists": {},
    "fr_msv_errors": False,         # multiscale-variance error bars (costly)
    "fr_res_models": [],            # alternative medium models drawn as curves
    "fr_res_eos": {},               # panel -> [EoS name, ...]
    "fr_res_anchors": {},           # "panel|eos" -> recorded point label
    "fr_res_geom": "",              # the results window's last geometry
    # The side guide beside the FFT view. Open on a first run: the
    # workbench is the one surface in the program whose mouse grammar
    # cannot be guessed from its controls, so the explanation ships showing
    # and the user turns it off, not the other way round.
    "fr_guide_open": True,
    "fr_guide_w": 0,                # px; 0 = the default share of the pane
}

# The guide beside the FFT view is the shipped workbench view, read from the
# content tree at open time so the panel and the Guide dropdown can never
# drift apart.  GUIDE_FALLBACK is what shows when that tree is not installed.
GUIDE_FILE = "30_fringe_workbench.md"
GUIDE_MIN_W = 34                 # ems: below this the text stops being prose
GUIDE_DEF_W = 44                 # ems: the width it opens at
# The FFT canvas has a floor too, and it outranks the guide's.  One pixel of
# a 160 px canvas is half a micron of n*t: nobody can aim a click at a peak
# on that, the schematic headers break mid-word, and the annotation boxes
# spill past the axes.  When the centre cannot hold this AND the prose floor
# at once, the prose is the one that steps aside.
PLOT_MIN_W = 42                  # ems: the narrowest FFT canvas worth having
SCHEM_PT = 7.0                   # the cell schematic's type size, and the
SCHEM_PT_MIN = 5.0               # smallest it may be shrunk to to fit
SCHEM_WRAP_AT = 6.0 / SCHEM_PT   # below this share of the room the stack
                                 # reads over two lines instead of shrinking
HEAD_PT = 10.0                   # the panel's own name line, and the
HEAD_PT_MIN = 8.0                # smallest it may be shrunk to to fit
DLG_MAX_FRAC = 0.9               # a workbench window may not outgrow this
                                 # share of the screen

# ---------------------------------------------------------------------------
# The 2x2 figure's own margins, in POINTS.
#
# `tight_layout` cannot lay this figure out: every FFT panel carries a
# `twinx` for the removed fraction and every spectra panel a
# `secondary_xaxis` for the wavelength scale, so matplotlib declares the
# figure incompatible, warns once per draw and leaves the DEFAULT
# subplotpars in place -- left 0.125, right 0.9, hspace 0.55.  Measured on
# the real canvas that spent 148 px between the two rows and put the FFT
# panels' "removed fraction" scale on top of the spectra panels' tick
# labels, while the panels themselves held 41% of the figure.
#
# So the grid is placed from measurement instead.  Each number is what the
# furniture on that side actually needs, taken off the rendered figure at
# both window sizes: the panel fonts are fixed sizes, so the need is a
# fixed number of points at any canvas size or DPI.
#   left   y label + tick labels of the FFT column
#   right  the spectra column's last wavelength tick, half outside
#   top    the spectra title, its pad, and the wavelength axis over it
#   bottom the x label + tick labels of the lower row
#   wgap   the FFT panel's removed-fraction scale, then the spectra
#          panel's own tick labels, then air
#   hgap   the upper row's x furniture, then the lower row's title block
GRID_PT = {"left": 46.0, "right": 13.0, "top": 50.0, "bottom": 36.0,
           "wgap": 59.0, "hgap": 84.0}
# ... but the panels always keep this share of the canvas: on a pane
# dragged very narrow the margins shrink together rather than eat the plot.
GRID_MIN_AXES = 0.30

# ---------------------------------------------------------------------------
# Series continuity on disk.  Matthew's writer's schema and file name, so a
# folder written by either program reads in the other.
# ---------------------------------------------------------------------------
SERIES_SCHEMA = "fft_gui_series/v2"
SERIES_FILE = "series_continuity.json"
SERIES_STAMP = "series_continuity_%s.json"     # timestamped session copies
NOTCH_FILE = "notch_overrides.csv"

# ---------------------------------------------------------------------------
# Results vs pressure: Matthew's 2x3 grid.  Indices on top, the thickness each
# one divides into underneath it, so a column reads as one physical quantity.
#   (grid position, point key, axis label, EoS panel?)
# ---------------------------------------------------------------------------
RES_PANELS = (
    ("n_s", (0, 0), "$n_s$  (sample)", False),
    ("n_medium", (0, 1), "$n_{medium}$", False),
    ("n_layer2", (0, 2), "$n_{layer2}$", False),
    ("t_s", (1, 0), "$t_s$  ($\\mu$m)", True),
    ("L", (1, 1), "$L = d_1{+}t{+}d_2$  ($\\mu$m)", True),
    ("t_layer2", (1, 2), "$t_{layer2} = d_1{+}d_2$  ($\\mu$m)", True),
)
RES_EOS_PANELS = ("t_s", "L", "t_layer2")
RES_MS = 34.0            # recorded-point marker area (pt^2)
RES_MS_D = 46.0          # the open x is drawn a little larger to read as one

# Media that carry a real n(P) model, so "re-solve under this instead" means
# something.  Anything else in MEDIUM_CHOICES has no curve to offer.
RES_MODEL_CHOICES = ("Ar", "ArChen", "ArChenD", "air")

RESULTS_GUIDE = [
    ("h", "WHAT THE SIX PANELS ARE"),
    ("b", "One column per physical quantity. The refractive index is "
          "on top, and the thickness it divides into is underneath. "
          "n_s over t_s is the sample. n_medium over L is the whole "
          "gap. n_layer2 over t_layer2 is the medium alone (d1 + d2)."),
    ("b", "X is pressure in GPa, from each trace's own parsed value."),
    ("h", "THE POINTS"),
    ("m", "  filled circle   compression"),
    ("m", "  open x          decompression"),
    ("b", "The branch is read live from the main window. It reads the "
          "auto-detected D tags, the D boxes in Data > Traces, and any "
          "decompression list you have loaded. Applying a list moves the "
          "markers here too. The recorded points stand."),
    ("b", "Colour is the medium the point was solved under, so a series "
          "that leaked argon to air shows both."),
    ("h", "MODEL OVERLAYS"),
    ("b", "Tick a medium. Every recorded point is solved again under "
          "that model's n(P) at its own pressure. The re-solve is "
          "exact. The three measured optical paths are what was "
          "recorded, and the solve conserves the sample path. "
          "Re-solving under the recorded model reproduces the recorded "
          "numbers to the last bit."),
    ("h", "EOS CURVES"),
    ("b", "The thickness panels take dashed equation-of-state curves, "
          "Vinet or Birch-Murnaghan 3rd order. They are scaled as the "
          "cube root of the volume ratio. A curve passes through the "
          "lowest-pressure recorded point by default. Right-click any "
          "point to anchor the curve there. Right-click the same point "
          "again to release it."),
    ("h", "ERROR BARS"),
    ("b", "Multiscale-variance bars are off by default because each point "
          "costs about 35 ms to estimate. Turned on in the Series card, "
          "they are computed once per point and cached."),
]

# ---------------------------------------------------------------------------
# Interaction constants -- Matthew's numbers, kept verbatim.
# ---------------------------------------------------------------------------
CLICK_TOL_UM = 0.8       # snap radius (um of n*t) for click-to-toggle
GRAB_TOL_UM = 1.6        # grab radius for a role glyph / the low-pass line
DEBOUNCE_MS = 110        # live redraw debounce while dragging
DIRTY_CAP = 8            # leave-guard itemisation cap

# Matthew's two radii are in DATA units, and his window put 0.8 um at a
# comfortable handful of pixels.  Embedded in SPARTA the same axes are a
# fraction of that width -- measured on the real app with the guide pane
# open, 0.8 um came out at 1.5 px and 1.6 um at 3.0 px, so a click had to
# land inside a pixel or two of the marker or it did nothing.  That is why
# the grammar read as missing.  The radius is therefore a SCREEN distance
# with his micron value as the floor: the feel is his at any window size,
# DPI or zoom level, and it never gets tighter than he specified.
PICK_PX = 9              # click-to-notch reach, in screen pixels
GRAB_PX = 15             # role glyph / low-pass line grab reach, in pixels
TOL_CAP_FRAC = 0.06      # ... but never more than this share of the x span
HOVER_MS = 4500          # how long a status message holds the hint bar

CHANNELS = ("Background", "Sample")
CHAN_KEY = {"Background": "bg_c", "Sample": "samp_c"}

# The _group titles the workbench owns, spelled as the honesty gate and the
# guide's headings spell them, in the order they stand in the column.
FRINGE_SECTIONS = ("Stack", "Session", "Pressure point", "Detection",
                   "FFT removal", "Refractive Index from Intensity",
                   "Panels")

# Which INFO_CONTENT block(s) each card's [?] shows.  The content keys keep
# their pre-R7 names so the math text needs no rewrite; the KEYS here are
# the live section titles, in FRINGE_SECTIONS order, because _build_cards
# looks each one up in the app's collapsible register and _add_info_btn
# quietly does nothing for a title that is not there.
#
# "Detection" is a card again (R14): R10 had folded its gates into a
# Panels > Detection... pop-out and parked the math text on FFT removal.
# The gates stand in the column now, so the detection block goes back to
# the card that carries them and FFT removal keeps the notch block alone.
INFO_FOR = {"Stack": ("Stack", "Roles & solve"),
            "Session": ("Series",),
            "Detection": ("Detection",),
            "FFT removal": ("Notches",),
            "Refractive Index from Intensity": ("Intensity",)}

# Two stacked rows of action buttons at PAD_TIGHT sat 1 px apart, which
# reads as one slab of chrome ("buttons too close together", R14 round 3).
# This is the gutter between them, and between a row of buttons and the
# checkbox or label under it.
PAD_BTNROW = (6, 0)

# The Stack card's own label gutter.  Wider than LBL_W because its thickness
# rows name the role as well as the symbol ("Medium d1 (um)"); one value for
# the whole card so the input and Solved columns line up down it (rule 9's
# "genuinely long labels carry their own width").
STACK_LBL_W = 19

# Role keys, their display names and which panel carries them.  A = sample,
# C = sample-diamond (loaded sample), iii = medium etalon -- the three optical
# paths fringe_optics.solve_paths inverts.
ROLES = ("sample", "sampledia", "mediumdia")
ROLE_DISP = {"sample": "Sample", "sampledia": "Sample diamonds",
             "mediumdia": "Medium diamond"}
ROLE_PANEL = {"sample": "Sample", "sampledia": "Sample",
              "mediumdia": "Background"}
ROLE_Y = {"sample": 0.94, "sampledia": 0.94, "mediumdia": 0.94}
# How far below a glyph a press still counts as reaching for it, in axes
# fraction.  The glyphs live along the top of their panel; a press at the
# right n*t but lower down used to fall straight through to the notch
# toggle and leave a notch nobody asked for.
ROLE_GRAB_DY = 0.34

# Role glyphs: a 2:1 rectangle, a half-filled diamond, a hollow diamond.
RECT_PATH = _MPath([(-1.0, -0.5), (1.0, -0.5), (1.0, 0.5), (-1.0, 0.5),
                    (-1.0, -0.5)],
                   [_MPath.MOVETO, _MPath.LINETO, _MPath.LINETO,
                    _MPath.LINETO, _MPath.CLOSEPOLY])
ROLE_MARK = {"sample": (RECT_PATH, "full"),
             "sampledia": ("D", "left"),
             "mediumdia": ("D", "none")}

# Auto-seed: how far the stack's predicted line may sit from a detected peak
# and still claim it.  The Stack boxes are a nominal guess -- the shipped
# defaults are 5 / 20 / 5 um -- so on a real trace the prediction is routinely
# a fifth of its own value out (on the demo series the worst miss is 28% of
# the predicted path).  The fraction carries that drift; the floor keeps a
# short path from having a window too narrow to catch anything.  Only the
# strongest few peaks are considered, which bounds the ordered-pair search.
SEED_TOL_FRAC = 0.35
SEED_TOL_UM = 4.0
SEED_MAX_CAND = 12

# State indicators (the two-level memory-vs-disk model).
IND_SAVED = "✓"     # saved and identical to disk
IND_DIRTY = "•"     # changed in memory
IND_NONE = "⌀"      # nothing recorded

# Okabe-Ito: used for the model stems in EVERY theme, not only Colorblind
# Safe.  The stems are the one place on the figure where colour carries an
# identity (which interface pair), so the palette that survives every kind of
# colour vision is the right default (DESIGN_RULES rule 48).
OKABE_ITO = ("#0072B2", "#D55E00", "#E69F00", "#009E73", "#CC79A7",
             "#56B4E9", "#F0E442")
STEM_DASHES = ("-", "--", "-.", ":")     # High Contrast carries identity here

MEDIUM_CHOICES = ("Ar", "ArChen", "ArChenD", "KCl", "LiF", "air", "Other")
MEDIUM_LABELS = {"Ar": "Argon (Dewaele)", "ArChen": "Argon (Chen)",
                 "ArChenD": "Argon (Chen / Dewaele rho)", "KCl": "KCl",
                 "LiF": "LiF", "air": "Air (leaked cell)",
                 "Other": "Other (type the index)"}
DIAMOND_LABELS = {"constant": "Constant 2.4168", "cauchy": "Cauchy dispersion",
                  "oscillator": "Sellmeier oscillator",
                  "eremets": "Eremets n(P)"}
FIT_MODES = (("distinct", "Distinct"), ("shared", "Shared"))

# ---------------------------------------------------------------------------
# Pop-out helper-guide copy -- the "Reading the FFT view" and "What you do with
# the mouse" blocks of docs/guide_content/30_fringe_workbench.md, trimmed to
# the Guide-card shape (DESIGN_RULES rule 21).  Kept in step with that file by
# hand; the file is the source of the wording.
# ---------------------------------------------------------------------------
GUIDE_FALLBACK = [
    ("h", "READING THE FFT VIEW"),
    ("b", "Two stacked panels, Background on top and Sample below. Both "
          "channels show at once."),
    ("b", "X axis: n*t in micron. It is the optical path of the "
          "interfering layer. Fringe frequency and n*t are related by "
          "f = 2 n*t."),
    ("b", "Y axis: the measured |FFT| amplitude on a physical modulation "
          "scale (V_m), so amplitudes are comparable between channels and "
          "between pressures."),
    ("b", "Model stems mark where the current stack model predicts a "
          "fringe. The m = 2 and m = 3 Airy harmonics are drawn "
          "dashed. A real interference pattern puts power at integer "
          "multiples of its fundamental. Seeing the harmonics is the "
          "fastest confirmation that a peak is a fringe."),
    ("b", "Notch bands are shaded over the region each notch removes. "
          "The right-hand axis reads the fraction of the signal they "
          "take out."),
    ("b", "The dashed low-pass line sets the cutoff above which everything "
          "is treated as noise. Drag it and the view follows."),
    ("h", "PEAK MARKERS"),
    ("m", "  triangle   the fundamental"),
    ("m", "  circle     found automatically"),
    ("m", "  diamond    placed by you"),
    ("m", "  hollow     present but not ticked"),
    ("h", "WHAT YOU DO WITH THE MOUSE"),
    ("b", "Left-click within 0.8 um of a feature toggles a notch there."),
    ("b", "Right-click pins that peak as the fundamental; right-click again "
          "to reset the pin. The same menu hands the peak to a role glyph, "
          "which is the quickest way to place one exactly."),
    ("b", "The three role glyphs start out parked on the workbench's best "
          "guess: the stack's predicted paths, snapped to the nearest "
          "detected peak. They are a starting point."),
    ("b", "Role glyphs drag freely along the axis. A drag lands where you "
          "release it. Fit peaks then fits a Gaussian to the local peak and "
          "moves the glyph to the fitted centre. Distinct fits each role "
          "independently. Shared ties them to one centre. The tool keeps the "
          "fitted offsets ordered, so the solve gets a physical ordering."),
]

# ---------------------------------------------------------------------------
# The Info pop-out (Panels > Info) -- his View > Info panel: the marker
# key, the mouse grammar, and where the files go.
# ---------------------------------------------------------------------------
WB_INFO = [
    ("h", "MARKER SHAPES"),
    ("m", "      rectangle       Sample  (A = n_s t)"),
    ("m", "      half diamond    Sample diamonds  (C)"),
    ("m", "      hollow diamond  Medium diamond  (iii)"),
    ("m", "      triangle        the fundamental peak"),
    ("m", "      circle          peak found automatically"),
    ("m", "      diamond         peak you added"),
    ("m", "      hollow          listed but unticked"),
    ("h", "THE MOUSE"),
    ("b", "Left-click a peak to notch it, or to take the notch "
          "away. Right-click a peak to pin it as the fundamental or "
          "to hand it to a role glyph. Drag a glyph, or the dashed "
          "low-pass line, with the left button."),
    ("h", "FILES"),
    ("b", "Save session writes series_continuity.json beside the data, "
          "plus a timestamped copy. Export cleaned spectrum and Write "
          "notches file for batch land in the CSV folder. That folder "
          "is named at the bottom of the panel."),
]

# ---------------------------------------------------------------------------
# The [?] boxes -- the math behind each card, for the curious.
#
# One entry per card.  Content is sourced from the vendored fringe_* module
# docstrings (Matthew R. Diamond's defringe_dac.py port), citations included.
# A ("f", mathtext, plain) row renders as a typeset formula through the
# host's _mathtext_image and falls back to the plain form when mathtext is
# unavailable; the other tags are the guide renderer's own.  Headline
# formula first, prose after -- each box should be scannable.
# ---------------------------------------------------------------------------
INFO_TIP = ("This opens what the card computes: the formulas, the "
            "clamps and the citations, in a small window of its own.")

INFO_CONTENT = {
    "Stack": [
        ("b", "Five layers, four interfaces. Every PAIR of interfaces "
              "is a little etalon of its own. One sample therefore "
              "gives six lines."),
        ("h", "THE SIX LINES"),
        ("m", "      12  lower layer2      n_m d1"),
        ("m", "      23  sample            n_s t"),
        ("m", "      34  upper layer2      n_m d2"),
        ("m", "      13  layer2 + sample   n_m d1 + n_s t"),
        ("m", "      24  sample + layer2   n_s t + n_m d2"),
        ("m", "      14  the whole gap     n_m d1 + n_s t + n_m d2"),
        ("b", "Each line sits at its pair's optical path, which is what the "
              "coloured stems mark on the chart. The Background panel plays "
              "the same game with one line: the medium etalon at n_medium "
              "times L."),
        ("h", "THE AMPLITUDES"),
        ("f", r"$R_{dm}=\left(\frac{n_d-n_m}{n_d+n_m}\right)^{2}"
              r"\qquad R_{ms}=\left(\frac{n_m-n_s}{n_m+n_s}\right)^{2}$",
         "R_dm = ((n_d - n_m)/(n_d + n_m))^2,   "
         "R_ms = ((n_m - n_s)/(n_m + n_s))^2"),
        ("b", "Light loses a slice at every crossing, so the four interface "
              "intensities cascade:"),
        ("m", "      I1 = R_dm"),
        ("m", "      I2 = (1-R_dm)^2 R_ms"),
        ("m", "      I3 = (1-R_dm)^2 (1-R_ms)^2 R_ms"),
        ("m", "      I4 = (1-R_dm)^2 (1-R_ms)^4 R_dm"),
        ("f", r"$c_{ij} = 2\,s\,\sqrt{I_i\,I_j}$",
         "c_ij = 2 s sqrt(I_i I_j)"),
        ("b", "s is the Fresnel sign. Four pairs cross the middle "
              "reflection an odd number of times: 12, 13, 24 and 34. "
              "Those four flip sign when the sample's index climbs "
              "past layer 2's. The model keeps track of the sign for "
              "you."),
        ("b", "The short dashed stems are Airy harmonics. A real "
              "interference pattern also puts power at 2x and 3x its "
              "own path. The tool draws them at h(h/2) and h(h/2)^2 of "
              "the parent height."),
        ("h", "SOURCES"),
        ("m", "      M. R. Diamond, defringe_dac.py (thin-film model)"),
        ("m", "      github.com/matthewrdiamond/"),
        ("m", "        DAC-Absorption-Fringe-Analysis (MIT, by permission)"),
        ("m", "      diamond n: Phillip & Taft (1964);"),
        ("m", "        Eggert, Goettel & Silvera, EPL 11, 775 (1990);"),
        ("m", "        Eremets et al., Int. J. High Press. Res. 9, 347"),
        ("m", "        (1992); Dewaele et al., PRB 77, 094106 (2008)"),
    ],
    "Detection": [
        ("f", r"$n{\cdot}t \;=\; f/2$", "n*t = f / 2"),
        ("b", "The chart is an FFT taken in WAVENUMBER. The tool lays "
              "the channel out on a uniform 1/lambda grid. It divides "
              "by a smooth 4th-order trend, because the lamp "
              "multiplies. It then mirror-pads and Hann-tapers the "
              "signal. A layer of optical path n*t modulates that "
              "signal as cos(4 pi n*t nu). The layer appears at "
              "frequency f = 2 n*t. The x axis is that frequency "
              "halved, in micron."),
        ("h", "THE TEST"),
        ("f", r"$g \;=\; \max_k P_k \,/\, \sum_k P_k$",
         "g = max(P_k) / sum(P_k)"),
        ("f", r"$p \;=\; \sum_{j=1}^{\lfloor 1/g\rfloor} (-1)^{j-1}"
              r"\binom{n}{j}\,(1-jg)^{n-1}$",
         "p = sum_{j=1..floor(1/g)} (-1)^(j-1) C(n,j) (1-jg)^(n-1)"),
        ("b", "Fisher's exact test asks how big the biggest periodogram peak "
              "is against everything else, under a white-noise null. Small p "
              "means the peak is unlikely under that null. A near-flat "
              "periodogram scores p = 1, and the tool skips it."),
        ("h", "THE VOTE"),
        ("b", "Three FFT windows run the test on their own stretch: narrow, "
              "wide and full. A window detects when its p clears the Fisher "
              "p gate. The tool accepts the fringe when at least TWO windows "
              "detect it. Those windows also agree on n*t within Agree tol, "
              "a relative fraction. The fit then runs in the narrow band."),
        ("h", "SOURCES"),
        ("m", "      Fisher (1929); Wichert et al. (2004),"),
        ("m", "        Bioinformatics 20(1):5-20, eq. (6)"),
        ("m", "      M. R. Diamond, defringe_dac.py (detection pipeline)"),
    ],
    "Notches": [
        ("f", r"$\sigma_f \;=\; 2000 \cdot hw_{\mu m}$",
         "sigma_f = 2000 * halfwidth_um"),
        ("b", "A notch is a Gaussian bite out of the FFT mask. The "
              "tool attenuates each centre, and its mirror twin, by "
              "the Gaussian factor exp(-(f-f_c)^2 / 2 sigma_f^2). The "
              "n*t axis is f/2000, so a half-width of hw micron is "
              "sigma_f = 2000 hw at EVERY centre. That is one absolute "
              "width wherever the fringe sits. It matches real fringe "
              "peaks, whose width barely changes across n*t."),
        ("b", "Before any of that, the tool mirror-pads the signal. It "
              "reflects half the length onto each end. The FFT then sees a "
              "periodic signal, and the notch stays clean at the edges."),
        ("h", "THE LOW-PASS"),
        ("f", r"$M(f) \;=\; \tfrac{1}{2}\left(1-\tanh\frac{f-f_{cut}}{r}"
              r"\right)$",
         "M(f) = (1/2) (1 - tanh((f - f_cut) / r))"),
        ("b", "The dashed line multiplies a soft tanh shoulder into the same "
              "mask. The roll-off is gentle. The tool treats everything past "
              "the cut as noise."),
        ("b", "The right-hand axis reads the fraction of the signal "
              "all the bites remove together. Removing half the signal "
              "to kill one ripple is usually the wrong trade. This is "
              "the number that says so."),
        ("h", "SOURCES"),
        ("m", "      M. R. Diamond, defringe_dac.py"),
        ("m", "        (defringe_fft_notch, band diagnostics)"),
    ],
    "Intensity": [
        ("h", "READING n OFF AN AMPLITUDE"),
        ("f", r"$V \;=\; 2R \qquad R = \left(\frac{n_d-n_s}{n_d+n_s}\\right)^{2}$",
         "V = 2R,   R = ((n_d - n_s)/(n_d + n_s))^2"),
        ("f", r"$n_s \;=\; n_d\,\frac{1-\sqrt{V/2}}{1+\\sqrt{V/2}}$",
         "n_s = n_d (1 - sqrt(V/2)) / (1 + sqrt(V/2))"),
        ("b", "A fringe's amplitude is set by how strongly its two "
              "faces reflect. For a low-finesse etalon between equal "
              "mirrors, that is Fresnel's formula run forward. Compute "
              "fits runs it backward. It fits the fringe's amplitude "
              "V, then inverts for the index that would reflect that "
              "much."),
        ("h", "THE TWO ESTIMATES"),
        ("b", "The cosine fit follows the fringe point by point. It "
              "reads V off the best-fitting cos(4 pi n t / lambda + "
              "phi). The band integral sums the FFT power in a band "
              "around the peak. The band integral is steadier when the "
              "fringe drifts, and it is the blue curves' source. Each "
              "estimator runs over several spectral windows: full, "
              "wide, narrow, fine. fine is the quoted one."),
        ("h", "BAND \u0394 RESOLUTION FLOOR"),
        ("b", "The band integral holds its integration band at the FFT main "
              "lobe or wider, about 2 bins. Only V_band moves when you "
              "toggle it. The notches, the cleaning and the shaded windows "
              "hold."),
        ("h", "SOURCES"),
        ("m", "      M. R. Diamond, defringe_dac.py (fit_signal_*,"),
        ("m", "        band_amp, fresnel_n_from_V)"),
    ],
    "Roles & solve": [
        ("h", "THE THREE PATHS"),
        ("f", r"$A = n_s t \qquad C = n_{l2}(d_1{+}d_2) + n_s t"
              r"\qquad iii = n_m L$",
         "A = n_s t,   C = n_l2 (d1+d2) + n_s t,   iii = n_m L"),
        ("b", "The rectangle is A, light through the sample alone. The "
              "half-filled diamond is C, sample plus the medium above "
              "and below it. The hollow diamond is iii, the whole gap "
              "L = d1 + t + d2 seen through the medium. Three measured "
              "paths and two known indices are enough to solve."),
        ("h", "THE SOLVE"),
        ("f", r"$L = \frac{iii}{n_m} \quad t_{l2} = \frac{C-A}{n_{l2}}"
              r" \quad t_s = L - t_{l2} \quad n_s = \frac{A}{t_s}$",
         "L = iii/n_m,   t_l2 = (C-A)/n_l2,   t_s = L - t_l2,   "
         "n_s = A/t_s"),
        ("b", "Closed form: four lines of algebra, run in that order."),
        ("h", "THE CLAMPS"),
        ("b", "The glyphs can land somewhere unphysical. The solve then "
              "clamps as an A-CONSERVING cascade. t_layer2 below zero is "
              "floored, and t_s is recomputed. t_s below zero is floored. A "
              "zero-thickness sample loses its path. n_s below 1 is floored "
              "with t_s = A/n_s, so the measured sample path A = n_s t_s "
              "survives the clamp. That conservation makes the Series card's "
              "re-solve exact later."),
        ("h", "THE VISIBILITY"),
        ("f", r"$R = \left(\frac{n_d-n_s}{n_d+n_s}\right)^{2}"
              r"\qquad V = 2R$",
         "R = ((n_d - n_s)/(n_d + n_s))^2,   V = 2R"),
        ("f", r"$n_s \;=\; n_d\,\frac{1-\sqrt{V/2}}{1+\sqrt{V/2}}$",
         "n_s = n_d (1 - sqrt(V/2)) / (1 + sqrt(V/2))"),
        ("b", "Fresnel, low-finesse, equal mirrors: V sets the stem "
              "heights, and run backwards it reads a refractive index "
              "straight off a peak's amplitude."),
        ("h", "SOURCES"),
        ("m", "      M. R. Diamond, defringe_dac.py"),
        ("m", "        (fresnel_V, solve_paths and the clamp cascade)"),
    ],
    "Series": [
        ("h", "THE RE-SOLVE"),
        ("b", "A recorded point stores the MEASUREMENT: the three "
              "paths A, C and iii. It also stores the two indices the "
              "solve ran at. The solve conserves A, so feeding the "
              "recorded indices back reproduces the recorded numbers "
              "to the last bit. Feeding another medium's n(P) gives "
              "the answer under that model. It is exact, so any "
              "difference you see is the model."),
        ("h", "EOS CURVES"),
        ("f", r"$t(P) \;=\; t_a\left(\frac{V(P)}{V(P_a)}\right)^{1/3}$",
         "t(P) = t_a * (V(P) / V(P_a))^(1/3)"),
        ("b", "A thickness shrinks as the cube root of the volume "
              "ratio. Each equation of state draws a dashed curve "
              "through one anchor point. The two are Vinet and "
              "3rd-order Birch-Murnaghan. The anchor is the "
              "lowest-pressure point until you right-click another. "
              "The curve is a prediction to compare against."),
        ("h", "ERROR BARS"),
        ("b", "Multiscale variance: the tool tiles the spectrum into "
              "non-overlapping windows at several widths, and fits every "
              "window on its own. The scatter of those per-window answers is "
              "an empirical 1-sigma. The quoted sigma is the LARGEST across "
              "the widths. The widest disagreement sets the error."),
        ("h", "SOURCES"),
        ("m", "      M. R. Diamond, defringe_dac.py (series continuity,"),
        ("m", "        multiscale variance); every EoS constant keeps"),
        ("m", "        its citation in fringe_materials.py"),
    ],
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _deep(o):
    """An independent copy of a JSON-shaped value.

    The series snapshot the memory-vs-disk indicator compares against must
    not share a single nested dict with the live points: a shallow copy
    left every point's 'solved' sub-dict aliased, so editing a solved value
    silently edited the snapshot too and the indicator swore the file was
    up to date.  Deliberately not copy.deepcopy - these payloads are plain
    JSON types, and this keeps the import list honest.
    """
    if isinstance(o, dict):
        return dict((k, _deep(v)) for k, v in o.items())
    if isinstance(o, (list, tuple)):
        return [_deep(v) for v in o]
    return o


def guide_text():
    """The shipped fringe-workbench guide, as tagged lines.

    Read from docs/guide_content through guide_tour -- the same loader the
    Guide / notes dropdown uses, so the panel beside the plot and the entry
    in that dropdown are literally the same words and cannot drift.  Falls
    back to the compiled extract when the content tree is not installed
    (a frozen build run from a stripped folder), exactly as guide_views
    falls back to the compiled REF_VIEWS.

    Tags follow the content's own format contract.  A line indented six
    spaces or more is horizontally meaningful and renders monospaced,
    verbatim.  Everything else is grouped into paragraphs by the blank
    lines, so the text re-wraps to whatever width the pane is dragged to
    instead of keeping the file's 72-column hard breaks.  A paragraph that
    is one line long at column 0 is a heading: ALL-CAPS makes it a section
    head, anything else a sub-head.
    """
    text = None
    try:
        import guide_tour
        text = guide_tour._read_text(os.path.join(guide_tour.GUIDE_DIR,
                                                  GUIDE_FILE))
        if text is not None:
            text = guide_tour._strip_markers(text)
    except Exception:
        text = None
    if not text:
        return list(GUIDE_FALLBACK)
    out, buf, indent = [], [], 0

    def flush():
        if not buf:
            return
        if len(buf) == 1 and indent == 0:
            line = buf[0]
            out.append(("h" if line == line.upper() else "s", line))
        else:
            out.append(("b" if indent == 0 else "i", " ".join(buf)))
        del buf[:]

    for raw in text.rstrip().split("\n"):
        line = raw.rstrip()
        if not line.strip():
            flush()
            if out and out[-1][0] != "gap":
                out.append(("gap", ""))
            continue
        if line.startswith("      "):
            flush()
            out.append(("m", line))
            continue
        if not buf:
            indent = len(line) - len(line.lstrip())
        buf.append(line.strip())
    flush()
    return out


def _ckey(center_nm):
    """Canonical notch-centre key: n*t in um, rounded to 0.01 um.

    Matthew's `_ckey`: the notch list, the removed set and the fundamental pin
    all key off the same rounded micron value, so a peak identified from the
    plot and one read back from state are the same entry.
    """
    return round(float(center_nm) / 1000.0, 2)


def _f(var, fallback):
    """Read a float out of a tk variable, falling back on anything unparsable."""
    try:
        v = float(str(var.get()).strip())
    except (ValueError, tk.TclError, AttributeError):
        return fallback
    return v if np.isfinite(v) else fallback


def _fmt(v, digits=3):
    if v is None or not np.isfinite(v):
        return "–"
    return ("%%.%df" % digits) % v


def defringe_state(settings, panel=None):
    """The FFT-removal parameters EVERYTHING defringe reads.

    v1.4.9 R10 removed the main window's standalone Defringe section, so
    this panel is the only place the numbers live.  The catch is that the
    workbench is built on first use, while the df switch above the plot
    works from a cold start -- so the state has to be readable with no
    widgets in existence:

      * `panel` built  -> the LIVE tk variables, mid-edit values included
      * `panel` absent -> the fr_ settings keys, which carry exactly the
        same defaults (`SETTINGS_DEFAULTS` above) and are rewritten from
        the live variables by `_persist` on every debounced redraw

    The two paths therefore agree by construction, and a user who never
    opens the Fringe tab still gets the auto-detected fundamental at the
    default half-width under the default gates.

    Returns
        nt_min_um / nt_max_um / pvalue_max : the detection gates
        halfwidth_um                       : default notch half-width (+-um)
        channels                           : {'bg_c': {...}, 'samp_c': {...}}
            the PUBLISHED per-channel overrides -- notch centres and that
            channel's low-pass -- or {} when nothing has been published.
            Centres and cutoffs are per-channel and per-spectrum, which is
            why they travel as a snapshot ('Write to defringe') while the
            gates and the half-width are read live.
    """
    s = settings if isinstance(settings, dict) else {}
    live = panel if (panel is not None
                     and getattr(panel, "_built", False)) else None

    def _key(name, dflt):
        try:
            v = float(s.get(name, dflt))
        except (TypeError, ValueError):
            return dflt
        return v if np.isfinite(v) else dflt

    if live is not None:
        nt_lo, nt_hi = _f(live.ntmin_v, 8.0), _f(live.ntmax_v, 300.0)
        pmax = _f(live.pmax_v, 1e-4)
        hw = _f(live.hw_v, 3.0)
    else:
        nt_lo = _key("fr_nt_min_um", 8.0)
        nt_hi = _key("fr_nt_max_um", 300.0)
        pmax = _key("fr_pvalue_max", 1e-4)
        hw = _key("fr_halfwidth_um", 3.0)
    if not 0 < nt_lo < nt_hi:
        nt_lo, nt_hi = 8.0, 300.0
    if not pmax > 0:
        pmax = 1e-4
    if not hw > 0:
        hw = 3.0
    pub = s.get("fr_apply_centers")
    chans = {}
    if isinstance(pub, dict):
        for k, v in pub.items():
            if isinstance(v, dict) and v:
                chans[k] = dict(v)
    return {"nt_min_um": nt_lo, "nt_max_um": nt_hi, "pvalue_max": pmax,
            "halfwidth_um": hw, "channels": chans}


class FringeWorkbench(object):
    """The fringe workbench: an FFT view for the centre canvas plus the right
    panel's five cards, over one shared per-trace state.

    Public API (everything app.py may call):
        build()                 build the cards and the figure (idempotent)
        activate() / deactivate() / toggle()
        is_active()
        on_trace_change(label=None)
        sync_view_switch()      repaint the Plot|Fringe control after a theme
        popout()
        save_state() / load_state(d)
    """

    # -- construction -------------------------------------------------------
    def __init__(self, app, center_parent, sidebar_parent):
        _bind_host(app)
        self.app = app
        self.center_parent = center_parent
        self.sidebar_parent = sidebar_parent
        self.settings = getattr(app, "settings", {})
        for k, v in SETTINGS_DEFAULTS.items():
            self.settings.setdefault(k, v)
        for k, v in C_SETTINGS_DEFAULTS.items():
            self.settings.setdefault(k, (dict(v) if isinstance(v, dict)
                                         else list(v) if isinstance(v, list)
                                         else v))

        self._built = False
        self._active = False
        self._label = None            # current trace's identity label
        self._chan = {}               # (label, channel) -> channel state
        self._trace = {}              # label -> roles / solved / gaussians
        self._disk = {}               # label -> the last COMMITTED state
        self._cache = {}              # (label, channel, sig) -> computed dict
        self._series = []             # recorded points, in memory
        self._drag = None             # active drag descriptor
        self._after = None            # debounce handle
        self._fit_after = None        # centre-split refit debounce handle
        self._pane_w_seen = 0         # last centre-pane width the fitter saw
        # How the guide beside the plot came to be where it is:
        #   "auto"    the fitter decides, which is the normal state
        #   "hidden"  the fitter stood it down to keep the plot usable
        #   "forced"  the reader asked for it anyway on a narrow pane
        self._guide_fit = "auto"
        self._guide_said = False      # the snug-centre note is said once
        self._fit_quiet = False       # the first fit of an activation is
                                      # a layout decision, not news
        self._wr_cache = {}           # folder -> can we write a file there
        self._popout = None
        self._switch_lbls = {}
        self._notch_rows = None
        # the draggable artists of the MAIN canvas; the pop-out's mirror pass
        # swaps its own in and puts these back (see _mirror_popout)
        self._artists = {"roles": {}, "lp": {}, "hover": {}}
        self._peak_xy = {}            # chan -> the peak (x, y) last DRAWN
        self._recs_seen = None        # the trace list the workbench has
        self._nt_labels = {}          # chan -> the boxed stagger labels
        self._schem_labels = {}       # chan -> the cell-schematic header
        self._seed_said = {}          # label -> the last seeding message
        self._cursor_now = None       # the canvas cursor currently set
        self._slots = []              # labels that vanish while empty
        self._guide_boxes = []        # guide Text widgets to repaint on theme
        self._guide_scroll = 0.0      # where the guide was left, this session
        self._suspend = False         # True while load_state rewrites vars
        # ---- series level (Phase C) ------------------------------------
        self._results = None          # the Results-vs-pressure Toplevel
        self._res_ax = {}             # panel key -> axes
        self._res_pick = {}           # panel key -> [(x, y, point), ...]
        self._res_model_v = {}        # medium key -> BooleanVar
        self._res_eos_v = {}          # panel key -> {eos name: BooleanVar}
        self._res_anchor = {}         # (panel, eos) -> recorded point label
        self._msv_cache = {}          # label -> sigma of n*t (um) or None
        self._series_disk = None      # the series payload last read/written
        self._series_path = None      # the file that payload came from
        # ---- R7 workbench-fidelity state ---------------------------
        self._fit_history = []        # Compute fits snapshots, newest first
        self._fits = {}               # (label, chan) -> run_fits=True fit
        self._local = None            # Session-loaded folder + records
        self._parent_nav = None       # parent-folder browse state
        self._prev_thick = None       # Lock In redistribution baseline
        self._lp_last = {}            # per-channel low-pass edit guard
        self._rep = {}                # the Detection card's report labels
        self._fit_btns = []           # the two Fit-peaks glyph buttons
        self._notch_win = None
        self._lines_win = None
        self._detect_win = None
        self._hist_win = None
        self._lines_txt = None
        # ---- theme responsiveness + the [?] boxes ----------------------
        self._info = None             # the singleton [?] window
        self._info_topic = None       # which card it is showing
        self._info_btns = []          # [(label, title)] for theme re-stamps
        self._icon_cache = {}         # (name, colour) -> PhotoImage
        self._theme_seen = None       # last painted theme signature
        self._hook_tint_var()

    # ---- following the theme while windows are open ----------------------
    def _hook_tint_var(self):
        """Repaint the figures when 'Tint plot with theme' flips.

        The app's checkbox redraws the MAIN plot (`command=self._redraw`)
        and knows nothing about the workbench, so the FFT view kept its old
        page until the next unrelated redraw.  The tint variable is an
        existing host attribute (`plot_theme_bg`); tracing it is the same
        read-only host plumbing `_records` uses.  Attached here AND retried
        from build(): the variable is created by the Style tab's builder,
        which may run after _init_fringe.
        """
        if getattr(self, "_tint_hooked", False):
            return
        var = getattr(self.app, "plot_theme_bg", None)
        if var is None:
            return
        try:
            var.trace_add("write", lambda *_a: self._theme_repaint_maybe())
            self._tint_hooked = True
        except (AttributeError, tk.TclError):
            pass

    def _theme_sig(self):
        """Everything the figures and drawn glyphs take their colours from.
        One tuple, so 'did the theme move?' is a single comparison."""
        try:
            br = self.app._brand()
            return (tuple(self._pal()[:3]) + tuple(self._page())
                    + (br["ac1"], br["ac2"], br["ac3"], br["ink"],
                       self._hc()))
        except Exception:
            return None

    def _theme_repaint_maybe(self):
        """Repaint everything colour-carrying if the theme has moved.

        Called from sync_view_switch (the app's theme chain reaches it via
        _recolor_tk -> _sync_tabs -> _render_tabs) and from the tint-var
        trace.  Signature-guarded, so the frequent callers - _render_tabs
        runs on every session-tab repaint - cost one tuple compare."""
        sig = self._theme_sig()
        if sig == self._theme_seen:
            return
        self._theme_seen = sig
        if not self._built:
            return
        # the FFT figure: facecolor, spines, ticks, labels, stems, bands --
        # all re-derived inside _redraw; the pop-out mirror rides along
        self._request_redraw(now=True)
        # the results grid re-derives the same way
        self._res_refresh()
        # the [?] window's mathtext images carry the OLD ink; rebuild
        self._refresh_info()
        # drawn [?] glyphs are regenerated per theme, like the app's icons
        self._restamp_info_btns()
        # Windows caption colours on the open Toplevels
        for w in (self._popout, self._results, self._info):
            if w is not None:
                try:
                    if w.winfo_exists():
                        self.app._apply_titlebar(w)
                except tk.TclError:
                    pass

    # ---- theme-derived colours -------------------------------------------
    def _pal(self):
        return self.app._theme_palette()

    def _page(self):
        """(face, ink) for anything drawn ON the figure -- _mpl_colors is the
        page rule (DESIGN_RULES rule 47), never the UI palette."""
        c = self.app._mpl_colors()
        if isinstance(c, dict):
            return c.get("bg", "#ffffff"), c.get("fg", "#1c2530")
        return c[0], c[1]

    def _hc(self):
        try:
            return self.app.theme_mode.get() == "highcontrast"
        except Exception:
            return False

    def _stem_style(self, i):
        """Colour + dash for model line i.  High Contrast may not carry an
        identity with colour alone (rule 48), so there the ink colour is shared
        and the dash pattern is the carrier."""
        if self._hc():
            return self._page()[1], STEM_DASHES[i % len(STEM_DASHES)]
        return OKABE_ITO[i % len(OKABE_ITO)], "-"

    # ---- host plumbing ----------------------------------------------------
    def _tip(self, widget, text):
        if Tooltip is not None:
            Tooltip(widget, text)

    def _log(self, msg):
        fn = getattr(self.app, "_logline", None)
        if callable(fn):
            fn(msg)

    def _status(self, msg, warn=False, log=True):
        """One status line under Roles & solve, echoed to the hint bar under
        the axes.  `log=False` is for messages a redraw can re-emit (the
        ordering warning), which must not spam the log once per frame.

        The echo matters: every answer a plot click gets is written here, and
        the card is at the opposite side of the window from the mouse.
        """
        lab = getattr(self, "_status_lbl", None)
        if lab is not None:
            try:
                lab.configure(text=msg,
                              foreground=(self._warn_fg() if warn
                                          else self.app._muted_fg()))
            except tk.TclError:
                pass
            self._show_if_text(lab, msg)
        self._hint(msg or None)
        if msg and log:
            self._log("Fringe: " + msg)

    @staticmethod
    def _show_if_text(lab, text):
        """Keep a placeholder label out of the layout while it says nothing.

        An empty label still claims a whole text line, and four of them sat
        at the bottoms of the fringe cards -- which is most of the dead
        space at the end of every group.
        """
        pack = getattr(lab, "_fr_pack", None)
        if pack is None:
            return
        try:
            # winfo_manager, not winfo_ismapped: the cards are sealed while
            # the window is still being built, when nothing is mapped yet
            managed = lab.winfo_manager() == "pack"
            if text and text.strip():
                if not managed:
                    lab.pack(**pack)
            elif managed:
                lab.pack_forget()
        except tk.TclError:
            pass

    def _slot(self, lab, **pack):
        """A label that only occupies a row while it has something to say.

        Packed normally at build time so the card's order is the natural
        one; `_seal_slots` then records the sibling it must go back in
        front of and drops the ones that are still empty.
        """
        lab.pack(**pack)
        self._slots = getattr(self, "_slots", [])
        self._slots.append((lab, dict(pack)))
        return lab

    def _seal_slots(self):
        """Freeze each slot's place in its card, then hide the empty ones."""
        for lab, pack in getattr(self, "_slots", []):
            try:
                sibs = lab.master.pack_slaves()
                i = sibs.index(lab)
                if i + 1 < len(sibs):
                    pack["before"] = sibs[i + 1]
            except (tk.TclError, ValueError):
                pass
            lab._fr_pack = pack
            try:
                self._show_if_text(lab, lab.cget("text"))
            except tk.TclError:
                pass

    def _warn_fg(self):
        """The one warning tone: the brand's signal accent shaded toward
        orange, collapsing to plain ink in High Contrast (rule 48)."""
        if self._hc():
            return self._pal()[1]
        return self.app._blendc("#d97a1f", self._pal()[1], 0.15)

    # ---- window singletons ------------------------------------------------
    def _raise_existing(self, attr):
        """The one way a workbench Toplevel answers a second open request.

        Mainstream behaviour: clicking the button again NEVER spawns a
        twin - the existing window is un-minimised, raised and focused,
        and the caller returns it.  A dead or destroyed window clears the
        attribute and returns None, which tells the caller to build fresh.
        Geometry memory is applied at CREATION only, so raising a window
        the user has moved never yanks it anywhere.
        """
        win = getattr(self, attr, None)
        if win is None:
            return None
        try:
            if win.winfo_exists():
                win.deiconify()
                win.lift()
                win.focus_force()
                return win
        except tk.TclError:
            pass
        setattr(self, attr, None)
        return None

    # ---- how big a workbench window may be --------------------------------
    def _screen_cap(self, frac=DLG_MAX_FRAC):
        """The largest window this screen should be asked to show."""
        try:
            return (int(self.app.root.winfo_screenwidth() * frac),
                    int(self.app.root.winfo_screenheight() * frac))
        except (AttributeError, tk.TclError):
            return 10 ** 5, 10 ** 5

    def _dlg_size(self, w_em, h_em):
        """A window size in em, capped at a share of the screen.

        The same idiom app.py uses for its own dialogs, written out here
        rather than borrowed, so the workbench never leans on a helper it
        does not own.  Without the cap the results grid asked for 1480x840
        and a 1366x768 laptop lost its button bar off the bottom edge.
        """
        em = self.app._em()
        cw, ch = self._screen_cap()
        return min(int(em * w_em), cw), min(int(em * h_em), ch)

    def _clamp_geometry(self, win, geom):
        """Re-apply a remembered "WxH+X+Y", with the SIZE held to the cap.

        A geometry remembered on a big monitor must not put the buttons off
        the bottom of a small one.
        """
        if not geom:
            return
        try:
            size = geom.split("+")[0].split("-")[0]
            w, h = (int(v) for v in size.split("x"))
        except (ValueError, IndexError):
            return
        cw, ch = self._screen_cap()
        try:
            win.geometry("%dx%d%s" % (min(w, cw), min(h, ch),
                                      geom[len(size):]))
        except tk.TclError:
            pass

    # =======================================================================
    # build
    # =======================================================================
    def build(self):
        if self._built:
            return
        self._built = True
        self._hook_tint_var()          # retry: the Style tab may exist now
        self._theme_seen = self._theme_sig()
        self._build_vars()
        self._build_figure()
        self._build_cards()
        self.on_trace_change()

    # ---- tk variables -----------------------------------------------------
    def _build_vars(self):
        s = self.settings
        self.medium_v = tk.StringVar(value=s.get("fr_medium", "Ar"))
        self.medium_n_v = tk.StringVar(
            value="%g" % s.get("fr_medium_n", 1.2))
        self.layer2_on_v = tk.BooleanVar(value=bool(s.get("fr_layer2_on")))
        self.layer2_v = tk.StringVar(value=s.get("fr_layer2", "KCl"))
        self.diamond_v = tk.StringVar(value=s.get("fr_diamond_model",
                                                  "constant"))
        self.ns_v = tk.StringVar(value="%g" % s.get("fr_n_sample", 1.50))
        self.d1_v = tk.StringVar(value="%g" % s.get("fr_d1_um", 0.0))
        self.t_v = tk.StringVar(value="%g" % s.get("fr_t_um", 20.0))
        self.d2_v = tk.StringVar(value="%g" % s.get("fr_d2_um", 0.0))
        self.total_v = tk.StringVar(value="")
        self.lock_v = tk.BooleanVar(value=bool(s.get("fr_lock_total")))
        self.fine_v = tk.BooleanVar(value=bool(s.get("fr_fine_step")))
        self.wlmin_v = tk.StringVar(value="%g" % s.get("fr_wl_min", 600.0))
        self.wlmax_v = tk.StringVar(value="%g" % s.get("fr_wl_max", 800.0))
        self.wlover_v = tk.BooleanVar(value=False)
        self.ntmin_v = tk.StringVar(value="%g" % s.get("fr_nt_min_um", 8.0))
        self.ntmax_v = tk.StringVar(value="%g" % s.get("fr_nt_max_um", 300.0))
        self.pmax_v = tk.StringVar(value="%g" % s.get("fr_pvalue_max", 1e-4))
        self.tol_v = tk.StringVar(value="%g" % s.get("fr_agree_tol", 0.15))
        self.hw_v = tk.StringVar(value="%g" % s.get("fr_halfwidth_um", 3.0))
        # The fringe report the main log writes when df is switched on.
        # Its switch used to sit in the retired Defringe card's
        # "Detection (advanced)"; it lives in the Detection card now,
        # beside the gates it talks about (R14).
        self.suppress_v = tk.BooleanVar(
            value=bool(s.get("fr_suppress_report", False)))
        self.suppress_v.trace_add("write", self._on_suppress)
        # Per-channel low-pass (R7): Matthew keys the cutoff by channel.
        # A pre-R7 settings file seeds both channels from its scalar
        # pair once, so nothing anyone tuned is lost.
        _lg_on = bool(s.get("fr_lowpass_on", True))
        _lg_um = s.get("fr_lp_cutoff_um", 15.0)
        self.lp_on_v = {}
        self.lp_v = {}
        for _chan, _pre in (("Background", "bg"), ("Sample", "s")):
            _on = s.get("fr_lp_%s_on" % _pre)
            _um = s.get("fr_lp_%s_um" % _pre)
            self.lp_on_v[_chan] = tk.BooleanVar(
                value=_lg_on if _on is None else bool(_on))
            self.lp_v[_chan] = tk.StringVar(
                value="%g" % (_lg_um if _um is None else _um))
        # right-column view state (his tiered / clean toggles) and the
        # band-integral resolution floor -- view state, not persisted,
        # exactly as his GUI treats them
        self.tiers_v = tk.BooleanVar(value=False)
        self.hideclean_v = tk.BooleanVar(value=False)
        self.bandfloor_v = tk.BooleanVar(value=True)
        self.fitmode_v = tk.StringVar(value=s.get("fr_fit_mode", "distinct"))
        self.trace_v = tk.StringVar(value="")
        self.msv_v = tk.BooleanVar(value=bool(s.get("fr_msv_errors")))
        # every var that changes the picture asks for a debounced redraw
        for v in (self.medium_v, self.medium_n_v, self.layer2_on_v,
                  self.layer2_v, self.diamond_v, self.ns_v, self.d1_v,
                  self.t_v, self.d2_v, self.hw_v,
                  self.lp_on_v["Background"], self.lp_on_v["Sample"],
                  self.lp_v["Background"], self.lp_v["Sample"]):
            v.trace_add("write", self._on_model_var)
        for v in (self.wlmin_v, self.wlmax_v, self.ntmin_v, self.ntmax_v,
                  self.pmax_v, self.tol_v):
            v.trace_add("write", self._on_detect_var)
        # The half-width redraws this panel through _on_model_var above,
        # and since R10 it is also the main plot's notch width, so it
        # gets its own second trace for the host side.
        self.hw_v.trace_add("write", self._on_hw_var)

    # ---- the figure -------------------------------------------------------
    def _build_figure(self):
        """The centre: the FFT figure, and the guide pane beside it.

        The two live in a horizontal Panedwindow so the split is the user's
        to drag; the figure carries the weight, so growing the window grows
        the plot and the guide keeps the width it was left at.  The pane
        itself is what activate() swaps into the plot area, not the bare
        canvas, so the guide comes and goes with the view.
        """
        face, _ink = self._page()
        self.fig = Figure(figsize=(9.2, 5.2), dpi=100, facecolor=face)
        # Matthew's 2x2: the forward-model FFT panels down the LEFT
        # column, the measured spectra (raw + cleaned) down the RIGHT,
        # Background over Sample in both.  His width ratio, kept.  The
        # gaps are _layout_grid's, measured off the drawn furniture, and
        # a gridspec that carried its own would outrank it.
        gs = self.fig.add_gridspec(2, 2, width_ratios=[1.0, 1.25])
        self.ax_bg = self.fig.add_subplot(gs[0, 0])
        self.ax_s = self.fig.add_subplot(gs[1, 0], sharex=self.ax_bg)
        self.ax_mb = self.fig.add_subplot(gs[0, 1])
        self.ax_ms = self.fig.add_subplot(gs[1, 1], sharex=self.ax_mb)
        self._axes = {"Background": self.ax_bg, "Sample": self.ax_s}
        self._maxes = {"Background": self.ax_mb, "Sample": self.ax_ms}
        self._twins = {}
        self._center_pw = ttk.Panedwindow(self.center_parent,
                                          orient="horizontal")
        self._fig_holder = ttk.Frame(self._center_pw)
        self._center_pw.add(self._fig_holder, weight=5)
        # The hint bar packs FIRST so the canvas is the sacrificial widget
        # when the pane is dragged narrow (rules 13 and 14): the one line
        # that says what the mouse does may never be the thing that goes.
        self._build_hint_bar(self._fig_holder)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self._fig_holder)
        self._tkcanvas = self.canvas.get_tk_widget()
        self._tkcanvas.pack(side="top", fill="both", expand=True)
        self._tkcanvas.configure(background=self._pal()[0],
                                 highlightthickness=0)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("figure_leave_event", self._on_leave)
        self.canvas.mpl_connect("axes_leave_event", self._on_leave)
        self._guide_pane = None
        # The split is re-fitted whenever the centre changes width.  It used
        # to be set once, at activation, and never again -- so a window
        # resized after that kept the sash it was born with, which is how a
        # 1400 px window came to show a 160 px plot.
        self._center_pw.bind("<Configure>", self._on_pane_configure, add="+")
        # a sash the reader dragged is a width they chose: remember it when
        # they let go, not only when the guide is closed
        self._center_pw.bind("<ButtonRelease-1>",
                             lambda e: self._remember_guide_sash(), add="+")
        # The grid's margins are PIXEL amounts turned into fractions for
        # the canvas they were measured on, so a canvas that changes size
        # without a redraw would carry the old pixels, scaled.  A resize
        # re-places the grid and re-fits the labels; it costs no compute
        # and no re-draw of the data, only a new layout.
        self._relayout_job = None
        self._tkcanvas.bind("<Configure>", self._on_canvas_resize, add="+")
        if self.settings.get("fr_guide_open", True):
            self._open_guide_pane()

    def _on_canvas_resize(self, _event=None):
        job, self._relayout_job = getattr(self, "_relayout_job", None), None
        if job is not None:
            try:
                self.app.root.after_cancel(job)
            except (tk.TclError, ValueError):
                pass
        try:
            self._relayout_job = self.app.root.after(120, self._relayout)
        except tk.TclError:
            pass

    def _relayout(self, fig=None, canvas=None):
        """Place the grid and fit the labels again, without recomputing."""
        if fig is None and canvas is None:
            self._relayout_job = None      # the pop-out holds its own
        if not self._built:
            return
        self._layout_grid(fig)
        self._fit_labels(canvas)
        try:
            (canvas or self.canvas).draw_idle()
        except Exception:
            pass

    # ---- the hint bar under the axes --------------------------------------
    HINT_DEFAULT = ("click a peak to notch it.  right-click to pin or assign "
                    "a role.  drag a role glyph along the top of its panel")
    HINT_EMPTY = ("run a folder and the fringes turn up here")

    def _hint_text(self):
        """The standing line under the axes: the mouse grammar once there is
        something to aim at, and an invitation before that."""
        return self.HINT_DEFAULT if self._records() else self.HINT_EMPTY

    def _build_hint_bar(self, parent):
        """One line under the FFT axes saying what the mouse does.

        The gestures are real but invisible: nothing on the figure says a
        peak is clickable, and every answer the workbench gave a click
        ("no FFT peak near the click") landed in the Roles & solve card at
        the far side of the window, where a user with the mouse over the
        plot never looks.  This bar is that answer, next to the mouse, and
        it falls back to the grammar once the message has been read.
        """
        f = ttk.Frame(parent)
        f.pack(side="bottom", fill="x")
        self._hint_lbl = self.app._lbl(f, text=self._hint_text(),
                                       font=self.app._F(-1),
                                       foreground=MUTED)
        self._hint_lbl.pack(side="left", padx=(6, 0), pady=(0, 2))
        self._hint_after = None
        self._tip(self._hint_lbl,
                  "Left-click a peak marker to put a notch there, or to take "
                  "one away. Right-click a peak to pin it as the "
                  "fundamental, or to assign one of the role glyphs to it. "
                  "Drag the dashed low-pass line, or any role glyph along "
                  "the top, with the left button. The pointer turns into a "
                  "hand over a peak and into a resize arrow over anything "
                  "you can drag.")
        return f

    def _hint(self, msg=None):
        """Show `msg` in the hint bar for a few seconds, then the grammar."""
        lab = getattr(self, "_hint_lbl", None)
        if lab is None:
            return
        after = getattr(self, "_hint_after", None)
        if after is not None:
            try:
                self.app.root.after_cancel(after)
            except (AttributeError, tk.TclError, ValueError):
                pass
            self._hint_after = None
        try:
            lab.configure(text=(msg or self._hint_text()),
                          foreground=(self.app._muted_fg() if not msg
                                      else self._pal()[1]))
        except tk.TclError:
            return
        if not msg:
            return
        try:
            self._hint_after = self.app.root.after(HOVER_MS, self._hint)
        except (AttributeError, tk.TclError):
            self._hint_after = None

    # ---- the five cards ---------------------------------------------------
    def _build_cards(self):
        # Matthew's sidebar, top to bottom: the defringe switch, the stack
        # inputs with the solved column and the fit actions, the Session
        # group, the pressure-point navigator, the Detection gates, FFT
        # removal (the main tool), Refractive Index from Intensity, and the
        # Panels launcher with the status lines and CSV folder under it.
        # The cards categorise themselves under the Fringe tab.  app.py's
        # _tabspec still lists the pre-R7 section names until integration;
        # the category map is live state, and registering here is what
        # keeps _reorder_sections and the honesty gate honest meanwhile.
        cat = getattr(self.app, "_section_cat", None)
        if isinstance(cat, dict):
            for t in FRINGE_SECTIONS:
                cat[t] = "Fringe"
        self._claim_section_slot()
        self._install_sec_icons()
        self._defringe_row()
        self._card_stack()
        self._card_session()
        self._card_pressure()
        self._card_detection()
        self._card_removal()
        self._card_intensity()
        self._card_panels()
        self._seal_slots()
        self._tighten_sections()
        for title in FRINGE_SECTIONS:
            if title in INFO_FOR:
                self._add_info_btn(title)

    def _claim_section_slot(self):
        """Give the Detection card its slot in the app's section order.

        `_reorder_sections` walks `App.SECTION_ORDER` and parks anything it
        does not know AFTER everything it does, so a card built between
        Pressure point and FFT removal would be dragged to the foot of the
        tab the first time that pass ran.  The order is claimed on the App
        INSTANCE, which shadows the class tuple for this session only and
        needs no app.py edit; a build where the name is already listed
        changes nothing.
        """
        a = self.app
        order = list(getattr(a, "SECTION_ORDER", ()) or ())
        if "Detection" in order or "FFT removal" not in order:
            return
        order.insert(order.index("FFT removal"), "Detection")
        try:
            a.SECTION_ORDER = tuple(order)
        except AttributeError:
            pass

    def _install_sec_icons(self):
        """Give each Fringe card a marker that says what the card is.

        `App._make_icons` draws one `sec::<title>` glyph per section and
        both theme passes stamp it on that section's head; a title the set
        does not carry keeps the plain square, which is what all seven
        Fringe cards wore.  The glyphs are drawn here and posted into the
        app's OWN icon set, so every pass that already stamps a marker --
        `_apply_brand`, `_sync_section_head` -- finds them and nothing here
        has to chase a theme switch.

        That set is rebuilt from scratch on each switch, so the builder is
        wrapped on the app INSTANCE: the same shadowing `_claim_section_slot`
        uses for SECTION_ORDER, and it needs no app.py edit.  The wrapper
        reads the drawing call off the app each time, so a workbench built
        later owns it and the wrap happens once.
        """
        a = self.app
        a._fr_sec_draw = self._draw_sec_icons
        if not getattr(a, "_fr_sec_wrapped", False):
            base = a._make_icons

            def _remake(*args, **kw):
                out = base(*args, **kw)
                fn = getattr(a, "_fr_sec_draw", None)
                if callable(fn):
                    fn()
                return out
            try:
                a._make_icons = _remake
                a._fr_sec_wrapped = True
            except AttributeError:
                pass
        self._draw_sec_icons()

    def _draw_sec_icons(self):
        """Draw the seven markers into the app's icon set.

        The language is app.py's `sec()` helper, stroke for stroke: a 24 px
        canvas at 3 px, downsampled to 12 px, in the theme's second accent.
        A machine without PIL keeps the plain square.
        """
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return
        a = self.app
        ic = getattr(a, "_icons", None)
        if not isinstance(ic, dict):
            return
        try:
            A = a._brand()["ac2"]
        except (AttributeError, KeyError, tk.TclError):
            return
        pil = getattr(a, "_icon_pil", None)
        W = 3

        def sec(name, fn):
            im = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
            fn(ImageDraw.Draw(im))
            small = im.resize((12, 12), Image.LANCZOS)
            img = ImageTk.PhotoImage(small)
            ic["sec::" + name] = img
            if isinstance(pil, dict):
                pil[img] = small

        # the stack itself, edge on: anvil, sample, anvil
        sec("Stack", lambda d: (d.rectangle([2, 3, 22, 7], fill=A),
                                d.rectangle([6, 10, 18, 14], fill=A),
                                d.rectangle([2, 17, 22, 21], fill=A)))
        # a folder: the series on disk (app.py's own folder glyph)
        sec("Session", lambda d: d.polygon(
            [(2, 5), (9, 5), (11, 8), (22, 8), (22, 19), (2, 19)],
            outline=A, width=W))
        # the diamond of the anvil cell
        sec("Pressure point", lambda d: d.polygon(
            [(12, 2), (22, 11), (12, 22), (2, 11)], outline=A, width=W))
        # a magnifier: the gates that find the peaks
        sec("Detection", lambda d: (d.ellipse([3, 3, 15, 15], outline=A,
                                              width=W),
                                    d.line([14, 14, 21, 21], fill=A,
                                           width=W)))
        # the fringe itself, sampled every pixel so the curve survives the
        # downscale (the Fringe tab's own glyph, at marker size)
        sec("FFT removal", lambda d: d.line(
            [(x, 12.0 - 6.0 * float(np.sin((x - 2) * np.pi / 8.0)))
             for x in range(2, 23)], fill=A, width=W))
        # refraction: a ray bending as it crosses the interface
        sec("Refractive Index from Intensity", lambda d: (
            d.line([2, 12, 22, 12], fill=A, width=W),
            d.line([6, 2, 12, 12], fill=A, width=W),
            d.line([12, 12, 16, 22], fill=A, width=W)))
        # a window with a side panel: what the card opens
        sec("Panels", lambda d: (d.rectangle([2, 4, 22, 20], outline=A,
                                             width=W),
                                 d.line([9, 4, 9, 20], fill=A, width=W),
                                 d.line([9, 12, 22, 12], fill=A, width=W)))

    def _defringe_row(self):
        """The df switch, at the head of the Fringe column.

        ONE variable, two boxes: this checkbox and the `df` box on the
        Quick Access strip hold the same `BooleanVar` and call the same
        command, so they cannot disagree and there is no sync code to fall
        out of step.  It stands above the Stack card rather than inside a
        card of its own because it is the one switch the whole column
        serves.
        """
        a = self.app
        var = getattr(a, "show_notch", None)
        cmd = getattr(a, "_toggle_notch", None)
        if var is None or not callable(cmd):
            return
        f = ttk.Frame(self.sidebar_parent, padding=(12, 6))
        f.pack(fill="x", pady=(2, 0))
        self._df_row = f
        cb = ttk.Checkbutton(f, text="Defringe (df)", variable=var,
                             command=cmd)
        cb.pack(side="left")
        self._df_cb = cb
        self._tip(cb, "The tool notches the anvil fringes out of the "
                      "plotted counts. The df box above the plot is the "
                      "same switch.")
        rule = ttk.Separator(self.sidebar_parent, orient="horizontal")
        rule.pack(fill="x", padx=12, pady=(0, 4))
        self._df_rule = rule

    # ---- the [?] boxes ----------------------------------------------------
    def _add_info_btn(self, title):
        """A small [?] at the right end of a card's title row.

        The affordance for the curious: the card's tooltips say what each
        control does, the [?] window says what the math underneath does.
        Follows the guide pane's own x-close pattern - a bound label on the
        header row - with keyboard access on top.  The glyph is drawn (rule
        31) and re-stamped per theme by _restamp_info_btns.
        """
        rec = next((r for r in getattr(self.app, "_collapsibles", [])
                    if r.get("key") == title), None)
        tl = (rec or {}).get("title_lbl")
        if tl is None:
            return
        try:
            hdr = tl.master
        except AttributeError:
            return
        a = self.app
        lbl = a._lbl(hdr, text="?", font=a._F(0, "bold"),
                     anchor="center", takefocus=1)
        img = self._help_icon()
        if img is not None:
            lbl.configure(image=img, text="")
            lbl.image = img
        # the card bodies are inset 12 px; a [?] 4 px off the panel edge
        # read as though it had been cut in half by the scrollbar
        lbl.pack(side="right", padx=(PAD_X, PAD_X + 4))
        lbl.configure(cursor="hand2")
        for seq in ("<Button-1>", "<Return>", "<Key-space>"):
            lbl.bind(seq, lambda e, t=title: self._open_info(t))
        self._tip(lbl, INFO_TIP)
        self._info_btns.append((lbl, title))

    def _help_icon(self):
        """The [?] glyph: a Bauhaus square holding a drawn question mark,
        in the theme's signal accent (the gear's slot).  Drawn with PIL at
        2x and downsampled, exactly as _make_icons draws the app set; a
        machine without PIL keeps the typed fallback."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return None
        col = self.app._brand()["ac2"]
        if self._hc():
            col = self._pal()[1]
        key = ("help", col)
        if key in self._icon_cache:
            return self._icon_cache[key]
        im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        W = 3
        d.rectangle([3, 3, 29, 29], outline=col, width=W)
        # the question mark: hook, stem, dot
        d.arc([10, 7, 22, 17], start=180, end=90, fill=col, width=W)
        d.line([16, 17, 16, 20], fill=col, width=W)
        d.ellipse([14, 23, 18, 26], fill=col)
        img = ImageTk.PhotoImage(im.resize((16, 16), Image.LANCZOS))
        if len(self._icon_cache) > 8:
            self._icon_cache.clear()
        self._icon_cache[key] = img
        return img

    def _restamp_info_btns(self):
        """Regenerate the [?] glyphs in the new theme's accent (rule 32:
        icons are regenerated per theme, not recoloured)."""
        alive = []
        for lbl, title in self._info_btns:
            try:
                if not lbl.winfo_exists():
                    continue
                img = self._help_icon()
                if img is not None:
                    lbl.configure(image=img, text="")
                    lbl.image = img
                else:
                    lbl.configure(foreground=self.app._brand()["ac2"])
                alive.append((lbl, title))
            except tk.TclError:
                continue
        self._info_btns = alive
        for btn, mode in list(getattr(self, "_fit_btns", [])):
            try:
                if not btn.winfo_exists():
                    continue
                img = self._fit_icon(mode == "shared")
                if img is not None:
                    btn.configure(image=img)
                    btn.image = img
            except tk.TclError:
                continue

    def _open_info(self, topic, _e=None):
        """The singleton math window for one card.

        A second click raises the window it already opened; a click on a
        DIFFERENT card's [?] re-aims the same window rather than opening a
        sibling, so there is never more than one.
        """
        if topic not in INFO_FOR:
            return None
        win = self._raise_existing("_info")
        if win is not None:
            if topic != self._info_topic:
                self._info_topic = topic
                self._fill_info()
            return win
        a = self.app
        win = tk.Toplevel(a.root)
        win.transient(a.root)
        em = a._em()
        a._center_on_root(win, em * 76, em * 60)
        a._apply_titlebar(win)
        win.bind("<Escape>", lambda e: self._close_info())
        win.protocol("WM_DELETE_WINDOW", self._close_info)
        self._info = win
        self._info_topic = topic
        self._fill_info()
        return win

    def _close_info(self):
        win, self._info = self._info, None
        self._info_topic = None
        if win is not None:
            try:
                win.destroy()
            except tk.TclError:
                pass

    def _refresh_info(self):
        """Rebuild the open [?] window's content in the live theme - the
        typeset formulas are IMAGES in the old ink and cannot be retinted."""
        if self._info is None:
            return
        try:
            if not self._info.winfo_exists():
                self._info = None
                return
        except tk.TclError:
            self._info = None
            return
        self._fill_info()

    def _fill_info(self):
        win, topic = self._info, self._info_topic
        if win is None or topic is None:
            return
        try:
            win.title(topic)
            for w in win.winfo_children():
                w.destroy()
        except tk.TclError:
            return
        a = self.app
        card = a._card(win, grow="both")
        card.pack(fill="both", expand=True, padx=10, pady=8)
        card.set_title(a._lf_header(card, topic, icon="book"))
        rows = []
        for _key in INFO_FOR.get(topic, ()):
            if rows:
                rows.append(("gap", ""))
            rows.extend(INFO_CONTENT.get(_key, ()))
        self._info_body(card.body, rows)

    def _info_body(self, parent, lines):
        """The [?] renderer: the guide-box shape plus one extra tag.

        A ("f", mathtext, plain) row asks the host to typeset the formula
        (the same _mathtext_image the formula list renders through, so the
        idiom and the caching are the app's own) and embeds the image in
        the text flow; when mathtext is unavailable - no host renderer, or
        a string its parser rejects - the plain form takes the mono tag
        instead, so the math is never silently missing.
        """
        txtf = ttk.Frame(parent)
        txtf.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(txtf)
        sb.pack(side="right", fill="y")
        txt = tk.Text(txtf, width=50, wrap="word", relief="flat", padx=8,
                      pady=6, highlightthickness=0, bd=0,
                      yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)
        txt._fr_heads = []
        txt._fr_imgs = []              # tk needs the references held
        mt = getattr(self.app, "_mathtext_image", None)
        try:
            ffg = self.app._code_fg()
        except (AttributeError, tk.TclError):
            ffg = self._pal()[1]
        for row in lines:
            kind = row[0]
            if kind == "f":
                img = mt(row[1], fg=ffg) if callable(mt) else None
                if img is not None:
                    txt.insert("end", "   ")
                    txt.image_create("end", image=img, padx=4, pady=6)
                    txt.insert("end", "\n")
                    txt._fr_imgs.append(img)
                else:
                    txt.insert("end", "      " + row[2] + "\n", ("m",))
                continue
            txt.insert("end", row[1] + "\n",
                       () if kind == "gap" else (kind,))
        txt.configure(state="disabled")
        self._guide_boxes = getattr(self, "_guide_boxes", [])
        self._guide_boxes.append(txt)
        self._retint_guide(txt)
        return txt

    def _tighten_sections(self):
        """End each fringe card where its content ends.

        app.py's `_reorder_sections` re-packs every section it knows about at
        the house `pady=(2, 7)`; the workbench's five are not in its order
        list, so they alone kept `_group`'s build-time `(5, 12)` -- five
        pixels more air above and five more below than every other section in
        the program, on top of the empty placeholder labels `_seal_slots`
        has just taken out.  Together that was Nhan's "bunch of dead space at
        the bottom".  Setting the same pady from here needs no app.py edit,
        and if the sections are ever added to that order list it sets exactly
        the same value.
        """
        for rec in getattr(self.app, "_collapsibles", []):
            if rec.get("key") not in FRINGE_SECTIONS:
                continue
            cont = rec.get("cont")
            if cont is None:
                continue
            try:
                if cont.winfo_manager() == "pack":
                    cont.pack_configure(pady=(2, 7))
            except tk.TclError:
                pass

    def _row(self, parent, pady=None):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=(PAD_ROW if pady is None else pady))
        return f

    def _wrap_to_card(self, lab, slack=10):
        """Wrap a running-text label at the card's width, not a guess.

        The status lines were born with `wraplength = 32 em`, about half
        the room the Fringe column actually gives them, so a one-line
        message broke over two or three lines with the right half of the
        card empty.  The width is read from the card body instead, and
        re-read whenever the panel is resized.
        """
        def _set(_e=None):
            try:
                w = int(lab.master.winfo_width()) - slack
                if w > 60 and int(lab.cget("wraplength") or 0) != w:
                    lab.configure(wraplength=w)
            except (tk.TclError, ValueError):
                pass
        lab.master.bind("<Configure>", _set, add="+")
        _set()
        return lab

    def _spin(self, parent, var, lo, hi, width=8):
        sp = ttk.Spinbox(parent, textvariable=var, from_=lo, to=hi,
                         width=width, increment=self._step())
        self._spins = getattr(self, "_spins", [])
        self._spins.append(sp)
        return sp

    def _step(self):
        return 0.1 if self.fine_v.get() else 1.0

    def _sync_steps(self, *_a):
        st = self._step()
        for sp in getattr(self, "_spins", []):
            try:
                sp.configure(increment=st)
            except tk.TclError:
                pass

    # ---- STACK ------------------------------------------------------------
    def _card_stack(self):
        """Matthew's input column: the materials, then the indices and
        thicknesses with the solved readout beside them, the Total row
        with Lock In and fine steps, and the Fit peaks / Plot point /
        Results plot action row.  His order, his defaults, his lock-in
        rules; SPARTA's card grammar and theming."""
        b = self.app._group(self.sidebar_parent, "Stack")
        a = self.app

        r = self._row(b)
        a._lbl(r, text="Anvil", width=STACK_LBL_W).pack(side="left")
        dcb = a._mapped_combo(r, self.diamond_v, DIAMOND_LABELS, width=18)
        dcb.pack(side="left", fill="x", expand=True)
        self._tip(dcb, "Which n(lambda) model stands for the diamond anvil. "
                       "The value it gives sits on the n diamond row below. "
                       "Eremets adds the pressure term, fed from each "
                       "spectrum's own pressure.")

        r = self._row(b, PAD_TIGHT)
        a._lbl(r, text="Medium", width=STACK_LBL_W).pack(side="left")
        mcb = a._mapped_combo(r, self.medium_v, MEDIUM_LABELS, width=18)
        mcb.pack(side="left", fill="x", expand=True)
        self._tip(mcb, "The pressure medium filling the cell. A named medium "
                       "follows pressure through its n(P) model. Other takes "
                       "the index you type on the n medium row.")

        r = self._row(b, PAD_TIGHT)
        l2 = ttk.Checkbutton(r, text="Layer 2", variable=self.layer2_on_v,
                             command=self._on_layer2)
        l2.pack(side="left")
        self._tip(l2, "Turn on when the cell holds a second distinct layer: "
                      "a coating, a second phase, a reaction rim. Off, the "
                      "medium fills the d1/d2 gap.")
        self._l2_cb = a._mapped_combo(
            r, self.layer2_v, {k: k for k in ("KCl", "LiF", "air")}, width=8)
        self._l2_cb.pack(side="left", padx=(PAD_X, 0))

        # ---- indices + thicknesses, with the solved column beside them.
        # His exact row alignment: n_s beside n sample, t_s beside t, the
        # medium total t_m beside d2, and L beside d1.
        self._sol_lbl = {}
        hdr = self._row(b, PAD_GROUP)
        a._lbl(hdr, text="", width=STACK_LBL_W).pack(side="left")
        a._lbl(hdr, text="input", width=10, font=a._F(-1),
               foreground=MUTED).pack(side="left")
        a._lbl(hdr, text="solved (this point)", font=a._F(-1),
               foreground=MUTED).pack(side="left", padx=(PAD_X, 0))

        r = self._row(b, PAD_TIGHT)
        a._lbl(r, text="n diamond", width=STACK_LBL_W).pack(side="left")
        self._nd_lbl = a._lbl(r, text="2.4168", width=10,
                              font=a._F(0, mono=True))
        self._nd_lbl.pack(side="left")
        a._lbl(r, text="Fixed", font=a._F(-1, "bold"),
               foreground=MUTED).pack(side="left", padx=(PAD_X, 0))
        self._tip(self._nd_lbl, "The anvil index the Anvil model gives at "
                                "this spectrum's own pressure. Held fixed "
                                "in the solve.")

        r = self._row(b, PAD_TIGHT)
        a._lbl(r, text="n medium", width=STACK_LBL_W).pack(side="left")
        cell = ttk.Frame(r)
        cell.pack(side="left")
        self._nmed_lbl = a._lbl(cell, text="1.2", width=10,
                                font=a._F(0, mono=True))
        self._nmed_e = ttk.Entry(cell, textvariable=self.medium_n_v,
                                 width=10)
        a._lbl(r, text="Fixed", font=a._F(-1, "bold"),
               foreground=MUTED).pack(side="left", padx=(PAD_X, 0))
        self._tip(self._nmed_e, "Refractive index of the medium: the solve's "
                                "anchor, held fixed. Yours to type while the "
                                "Medium is Other.")
        self._tip(self._nmed_lbl, "The medium index its n(P) model gives "
                                  "at this spectrum's pressure.")

        r = self._row(b, PAD_TIGHT)
        a._lbl(r, text="n sample", width=STACK_LBL_W).pack(side="left")
        ns = ttk.Entry(r, textvariable=self.ns_v, width=10)
        ns.pack(side="left")
        self._tip(ns, "Refractive index the model stems are drawn from. "
                      "Fit peaks writes the solved value back here.")
        self._sol_lbl["n_s"] = self._sol_cell(r, "n_s")

        for key, var, txt, sym, skey, tip in (
                ("d2", self.d2_v, "d2 upper medium (um)", "t_m",
                 "t_layer2",
                 "Thickness of the medium ABOVE the sample. With Lock In "
                 "on, changing it trades against t at a held total. The "
                 "solved value beside it is the medium TOTAL d1+d2."),
                ("t", self.t_v, "t sample (um)", "t_s", "t_s",
                 "Thickness of the sample itself."),
                ("d1", self.d1_v, "d1 lower medium (um)", "L", "L",
                 "Thickness of the medium BELOW the sample. With Lock In "
                 "on, changing it spreads the difference over d2 and t in "
                 "proportion. The solved value beside it is the whole "
                 "gap L = d1+t+d2.")):
            r = self._row(b, PAD_TIGHT)
            a._lbl(r, text=txt, width=STACK_LBL_W).pack(side="left")
            sp = self._spin(r, var, 0.0, 300000.0, width=8)
            sp.configure(command=lambda k=key: self._on_d_edit(k))
            sp.bind("<Return>", lambda e, k=key: self._on_d_edit(k))
            sp.pack(side="left")
            self._tip(sp, tip)
            self._sol_lbl[skey] = self._sol_cell(r, sym)

        r = self._row(b, PAD_GROUP)
        a._lbl(r, text="Total (um)", width=STACK_LBL_W).pack(side="left")
        self._total_sp = ttk.Spinbox(r, textvariable=self.total_v,
                                     from_=0.0, to=300000.0, width=8,
                                     increment=self._step(),
                                     command=self._on_total_edit)
        self._total_sp.bind("<Return>", lambda e: self._on_total_edit())
        self._total_sp.pack(side="left")
        self._spins = getattr(self, "_spins", []) + [self._total_sp]
        self._tip(self._total_sp, "d1 + t + d2. A mirror while unlocked; "
                                  "the driver while Lock In is ticked.")
        lt = ttk.Checkbutton(r, text="Lock In", variable=self.lock_v,
                             command=self._on_lock)
        lt.pack(side="left", padx=(PAD_X, 0))
        self._tip(lt, "Hold the total. d2 and t then trade against each "
                      "other. A d1 change spreads over d2 and t in "
                      "proportion, spilling when one empties. Editing the "
                      "Total itself grows d2, or drains d1, then d2, then t. "
                      "His redistribution rules, verbatim.")
        # The label gutter, the Total spinbox, Lock In and fine steps came
        # to 103 px more than the Fringe column is wide, and pack clips
        # what it cannot fit: "fine steps" showed as "fi" (R14 round 3).
        # It goes on the next line, indented to the same gutter.
        r = self._row(b, PAD_TIGHT)
        a._lbl(r, text="", width=STACK_LBL_W).pack(side="left")
        fs = ttk.Checkbutton(r, text="fine steps (\u00f7 10)",
                             variable=self.fine_v, command=self._sync_steps)
        fs.pack(side="left")
        self._tip(fs, "Step every spinbox at a tenth of the usual pace. It "
                      "covers thicknesses, Total and both low-pass cutoffs.")

        r = self._row(b, PAD_GROUP)
        a._lbl(r, text="Fit peaks:").pack(side="left")
        for mode, name, tip in (
                ("distinct", "Distinct",
                 "Distinct: fit the sample rectangle and sample-diamond as "
                 "SEPARATE peaks, each at its own stem. It then re-detects "
                 "every role and writes the solved n and t into the boxes "
                 "above, in one click."),
                ("shared", "Shared",
                 "Shared: fit the sample rectangle as a shoulder on the "
                 "sample-diamond's hump. It is one joint fit, one width, "
                 "with the offset kept ordered. It then re-detects and "
                 "writes the solved values back.")):
            img = self._fit_icon(mode == "shared")
            btn = ttk.Button(r, command=lambda m=mode:
                             self._fit_peaks_mode(m))
            if img is not None:
                btn.configure(image=img)
                btn.image = img
            else:
                btn.configure(text=name[0], width=3)
            btn.pack(side="left", padx=(PAD_X_TIGHT, 0))
            self._tip(btn, tip)
            self._fit_btns.append((btn, mode))
        # The two glyph buttons, Plot point and Results plot came to
        # 396 px on a 364 px column at text size 10 and Results plot was
        # cut by 35.  The two actions take their own row; they are not
        # "fit peaks" anyway.
        r = self._row(b, PAD_BTNROW)
        rp = a._brand_button(r, "Plot point", self._record_point)
        rp.pack(side="left", fill="x", expand=True)
        self._plot_btn = rp
        self._tip(rp, "Put this pressure point's solved values onto the "
                      "results series. That series is the in-memory record "
                      "Save session writes to disk.")
        rv = ttk.Button(r, text="Results plot",
                        command=self.results_view)
        rv.pack(side="left", fill="x", expand=True, padx=(PAD_X, 0))
        self._results_btn = rv
        self._tip(rv, "Open the recorded series as six panels against "
                      "pressure. A tick on this caption means the loaded "
                      "point is already on it.")

        self._on_layer2()
        self._on_lock()
        self._sync_medium_row()
        self._thick_snapshot()

    def _sol_cell(self, row, sym):
        """One solved-readout cell: 'sym =' then the bold value."""
        a = self.app
        a._lbl(row, text="%s =" % sym,
               foreground=MUTED).pack(side="left", padx=(PAD_X, 0))
        lab = a._lbl(row, text="\u2013", font=a._F(0, "bold", mono=True))
        lab.pack(side="left", padx=(PAD_X_TIGHT, 0))
        return lab

    def _fit_icon(self, shared):
        """The two Fit-peaks glyphs: his icon pair.  Distinct shows the
        rectangle and diamond apart; Shared shows them abutting, because
        the two roles share one fitted hump.  Drawn with PIL at 2x and
        downsampled, like the app's icon set (rule 31)."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return None
        ink = self._pal()[1]
        key = ("fit_shared" if shared else "fit_distinct", ink)
        if key in self._icon_cache:
            return self._icon_cache[key]
        im = Image.new("RGBA", (48, 28), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        W = 3
        if shared:
            d.rectangle([6, 8, 22, 20], outline=ink, width=W)
            pts = [(22, 14), (31, 5), (40, 14), (31, 23), (22, 14)]
        else:
            d.rectangle([2, 8, 18, 20], outline=ink, width=W)
            pts = [(28, 14), (37, 5), (46, 14), (37, 23), (28, 14)]
        d.line(pts, fill=ink, width=W, joint="curve")
        img = ImageTk.PhotoImage(im.resize((24, 14), Image.LANCZOS))
        if len(self._icon_cache) > 12:
            self._icon_cache.clear()
        self._icon_cache[key] = img
        return img

    def _on_layer2(self):
        try:
            self._l2_cb.configure(state=("readonly" if self.layer2_on_v.get()
                                         else "disabled"))
        except tk.TclError:
            pass
        self._request_redraw()

    def _on_lock(self):
        """His _sync_lock: enable the Total with the box, re-snapshot so
        the first edit either way has a fresh baseline, and seed the
        Total display from the current sum."""
        on = self.lock_v.get()
        try:
            self._total_sp.configure(state=("normal" if on else "disabled"))
        except (AttributeError, tk.TclError):
            pass
        self._thick_snapshot()
        pv = self._prev_thick or {}
        try:
            self.total_v.set("%.4g" % ((pv.get("d1") or 0.0)
                                       + (pv.get("t") or 0.0)
                                       + (pv.get("d2") or 0.0)))
        except tk.TclError:
            pass

    def _sync_medium_row(self, *_a):
        manual = self.medium_v.get() == fringe_materials.MEDIUM_MANUAL
        try:
            if manual:
                self._nmed_lbl.pack_forget()
                self._nmed_e.pack(side="left")
            else:
                self._nmed_e.pack_forget()
                self._nmed_lbl.pack(side="left")
        except (AttributeError, tk.TclError):
            pass

    # ---- Lock In: his redistribution rules, verbatim ----------------------
    def _thick_snapshot(self):
        pv = getattr(self, "_prev_thick", None)
        if pv is None:
            pv = self._prev_thick = {"d1": None, "t": None, "d2": None}
        for k, var in (("d1", self.d1_v), ("t", self.t_v),
                       ("d2", self.d2_v)):
            try:
                pv[k] = float(str(var.get()).strip())
            except (ValueError, tk.TclError):
                pass

    def _set_thick(self, key, val):
        var = {"d1": self.d1_v, "t": self.t_v, "d2": self.d2_v}[key]
        var.set("%.4g" % max(0.0, float(val)))

    def _on_d_edit(self, key):
        """A thickness spinbox was edited.  Unlocked: refresh the Total
        mirror and redraw.  Locked: hold the total by redistributing --
        d2 and t trade off (the partner clamped at 0, after which the
        total may grow); d1 splits its change across d2 and t in
        proportion to their current sizes, spilling the remainder when
        one empties.  Matthew's _on_d_edit, line for line."""
        if getattr(self, "_thick_busy", False):
            return
        var = {"d1": self.d1_v, "t": self.t_v, "d2": self.d2_v}[key]
        try:
            new = float(str(var.get()).strip())
        except (ValueError, tk.TclError):
            self._status("that is not a number.", warn=True)
            return
        pv = getattr(self, "_prev_thick", None) or {}
        if self.lock_v.get() and pv.get(key) is not None:
            delta = new - pv[key]
            self._thick_busy = True
            try:
                self._set_thick(key, new)      # honour the edit verbatim
                if key in ("t", "d2"):
                    other = "d2" if key == "t" else "t"
                    self._set_thick(other, (pv.get(other) or 0.0) - delta)
                else:            # d1: split -delta over d2 and t pro rata
                    pool = (pv.get("d2") or 0.0) + (pv.get("t") or 0.0)
                    if pool > 0:
                        d2n = ((pv.get("d2") or 0.0)
                               - delta * ((pv.get("d2") or 0.0) / pool))
                        tn = ((pv.get("t") or 0.0)
                              - delta * ((pv.get("t") or 0.0) / pool))
                    elif delta < 0:      # both empty, d1 shrinking
                        d2n = tn = -delta / 2.0
                    else:                # both empty, d1 growing
                        d2n = tn = 0.0
                    if d2n < 0:          # d2 cannot absorb -> spill to t
                        tn += d2n
                        d2n = 0.0
                    if tn < 0:           # t cannot absorb -> spill back
                        d2n += tn
                        tn = 0.0
                    if d2n < 0:          # both exhausted -> floor
                        d2n = 0.0
                    self._set_thick("d2", d2n)
                    self._set_thick("t", tn)
            finally:
                self._thick_busy = False
        self._thick_snapshot()
        if not self.lock_v.get():
            try:
                self.total_v.set("%.4g" % (_f(self.d1_v, 0.0)
                                           + _f(self.t_v, 0.0)
                                           + _f(self.d2_v, 0.0)))
            except tk.TclError:
                pass
        self._request_redraw()

    def _on_total_edit(self):
        """The Total spinbox was edited (reachable only while locked).
        Increase: all of it goes to d2.  Decrease: drain d1, then d2,
        then t, each floored at zero.  His _on_total_edit, verbatim."""
        if getattr(self, "_thick_busy", False):
            return
        try:
            new_total = float(str(self.total_v.get()).strip())
        except (ValueError, tk.TclError):
            self._status("that is not a number.", warn=True)
            return
        pv = getattr(self, "_prev_thick", None) or {}
        cur = ((pv.get("d1") or 0.0) + (pv.get("t") or 0.0)
               + (pv.get("d2") or 0.0))
        delta = new_total - cur
        self._thick_busy = True
        try:
            if delta >= 0:
                self._set_thick("d2", (pv.get("d2") or 0.0) + delta)
            else:
                rem = -delta
                for k in ("d1", "d2", "t"):
                    have = pv.get(k) or 0.0
                    take = min(have, rem)
                    self._set_thick(k, have - take)
                    rem -= take
                    if rem <= 0:
                        break
        finally:
            self._thick_busy = False
        self._thick_snapshot()
        self._request_redraw()

    def _fit_peaks_mode(self, mode):
        """His one-click peak workflow (_redetect_and_apply): pick the
        Sample fit strategy, hand every role back to auto, re-seed on the
        model stems, Gaussian-refine in that mode, solve, and write the
        solved geometry into the inputs."""
        self.fitmode_v.set(mode)
        tr = self._tr()
        rec = self._record()
        if tr is None or rec is None:
            self._status("load a spectrum first.", warn=True)
            return
        for role in ROLES:
            tr["roles"][role] = None
            tr["gauss"][role] = None
        tr["seeded"] = False
        self._seed_said.pop(self._label, None)
        p = self._stack_params(rec)
        self._seed_roles(p, self._x_upper(p))
        self._fit_peaks()
        self._solve()
        if (tr.get("solved") or {}).get("n_s") is not None:
            self._write_back()
        self._sync_action_marks()

    # ---- SESSION ----------------------------------------------------------
    def _card_session(self):
        b = self.app._group(self.sidebar_parent, "Session")
        a = self.app
        self.series_nav_v = tk.StringVar(value="\u2013 (no parent loaded)")

        r = self._row(b)
        lp = ttk.Button(r, text="Load parent folder...",
                        command=self._load_parent_folder)
        lp.pack(side="left", fill="x", expand=True)
        self._tip(lp, "Pick a folder that CONTAINS series subfolders of "
                      "*_absorbance.csv spectra. The dropdown below then "
                      "jumps between them; each series opens at its "
                      "lowest pressure.")
        lr = ttk.Button(r, text="Load raw spectra...",
                        command=self._load_raw_spectra)
        lr.pack(side="left", fill="x", expand=True, padx=(PAD_X, 0))
        self._tip(lr, "Pick one *_absorbance.csv. Its whole folder loads "
                      "as the working series and the Pressure point "
                      "dropdown fills with its siblings.")

        r = self._row(b, PAD_TIGHT)
        nx = ttk.Button(r, text="\u25b6", width=2,
                        command=lambda: self._step_series(1))
        nx.pack(side="right")
        pv = ttk.Button(r, text="\u25c0", width=2,
                        command=lambda: self._step_series(-1))
        pv.pack(side="left")
        self._series_cb = ttk.Combobox(r, textvariable=self.series_nav_v,
                                       state="readonly", width=16)
        self._series_cb.pack(side="left", fill="x", expand=True,
                             padx=(PAD_X_TIGHT, PAD_X_TIGHT))
        self._series_cb.bind("<<ComboboxSelected>>", self._on_series_pick)
        self._series_nav_btns = (pv, nx)
        self._tip(self._series_cb,
                  "The series subfolders under the loaded parent. Pick one "
                  "to jump straight to it.")
        self._tip(pv, "Previous series folder under the parent.")
        self._tip(nx, "Next series folder under the parent.")

        self._series_lbl = a._lbl(b, text="Series: \u2013",
                                  foreground=MUTED)
        self._series_lbl.pack(fill="x", pady=PAD_BTNROW)
        self._wrap_to_card(self._series_lbl)

        r = self._row(b, PAD_GROUP)
        sv = ttk.Button(r, text="Save session", width=13,
                        command=self.save_series)
        sv.pack(side="left", fill="x", expand=True)
        self._tip(sv, "Write the recorded points out as "
                      "series_continuity.json, plus a timestamped copy. They "
                      "go beside the input data. A data folder inside the "
                      "program, or a read-only one, sends them to your "
                      "output folder. The status line names the path.")
        ld = ttk.Button(r, text="Load session", width=13,
                        command=self.load_series)
        ld.pack(side="left", fill="x", expand=True, padx=(PAD_X, 0))
        self._tip(ld, "Read series_continuity.json back in. The tool looks "
                      "where the last save put it, then beside the input "
                      "data. A file the original program's batch mode left "
                      "with the spectra is found there.")

        self._state_lbl = a._lbl(b, text="", font=a._F(0, mono=True))
        self._slot(self._state_lbl, fill="x", pady=PAD_TIGHT)
        self._tip(self._state_lbl,
                  "%s saved and identical to disk, %s changed in memory, %s "
                  "waiting for the first point." % (IND_SAVED, IND_DIRTY,
                                                IND_NONE))
        self._series_disk_lbl = a._lbl(b, text="", font=a._F(0, mono=True))
        self._slot(self._series_disk_lbl, fill="x", pady=PAD_TIGHT)
        self._tip(self._series_disk_lbl,
                  "%s the saved file holds exactly these points, %s memory "
                  "and file differ, %s waiting for the first save."
                  % (IND_SAVED, IND_DIRTY, IND_NONE))

    # ---- Session loading: spectra straight into the workbench -------------
    @staticmethod
    def _parse_pressure_name(name):
        import re
        m = re.search(r"_(\d+p\d+)[Dd]?_", name)
        return float(m.group(1).replace("p", ".")) if m else None

    @staticmethod
    def _is_decomp_name(name):
        import re
        return bool(re.search(r"_\d+p\d+[Dd]_", name))

    def _load_raw_spectra(self):
        fp = filedialog.askopenfilename(
            title="Select a *_absorbance.csv",
            initialdir=self._input_folder() or os.getcwd(),
            filetypes=[("Absorbance CSV", "*_absorbance.csv"),
                       ("CSV", "*.csv"), ("All files", "*.*")],
            parent=self.app.root)
        if not fp:
            return
        if not self._leave_guard():
            return
        stem = os.path.splitext(os.path.basename(fp))[0]
        self._load_local_folder(os.path.dirname(fp), want_stem=stem)

    def _load_parent_folder(self):
        d = filedialog.askdirectory(
            title="Select the parent folder of the data series",
            initialdir=self._input_folder() or os.getcwd(),
            parent=self.app.root)
        if not d:
            return
        subs = self._scan_series_folders(d)
        if not subs:
            self._status("the workbench looks for a subfolder of "
                         "*_absorbance.csv files under %s."
                         % os.path.basename(d), warn=True)
            return
        if not self._leave_guard():
            return
        self._parent_nav = {"parent": d, "folders": subs, "idx": 0}
        self._load_local_folder(subs[0])

    @staticmethod
    def _scan_series_folders(parent):
        import glob as _glob
        out = []
        try:
            names = sorted(os.listdir(parent), key=lambda s: s.lower())
        except OSError:
            return out
        for name in names:
            p = os.path.join(parent, name)
            if (os.path.isdir(p)
                    and _glob.glob(os.path.join(p, "*_absorbance.csv"))):
                out.append(p)
        return out

    def _load_local_folder(self, folder, want_stem=None):
        """Read one folder of *_absorbance.csv spectra and make them the
        working set, ordered along the experiment's path -- compression
        ascending, then decompression descending (his _pressure_key)."""
        recs = self._read_folder(folder)
        if not recs:
            self._status("reading *_absorbance.csv in %s failed."
                         % os.path.basename(folder), warn=True)
            return
        # a folder switch is a SERIES switch: the in-memory series belongs
        # to the outgoing folder, so offer to save it, then start clean
        # (his _confirm_leave_series + _switch_active_series discipline)
        old = (getattr(self, "_local", None) or {}).get("folder")
        if self._series and old != folder:
            ans = messagebox.askyesnocancel(
                "Fringe workbench",
                "The current series holds %d plotted point(s) from another "
                "folder.\n"
                "\n"
                "Yes: save the continuity file, then switch\n"
                "No: switch and leave it unsaved\n"
                "Cancel: stay where you are" % len(self._series),
                parent=self.app.root)
            if ans is None:
                return
            if ans:
                self.save_series()
            self._series = []
            self._msv_cache.clear()
        app_sig = tuple(r.get("label") for r in
                        (getattr(self.app, "results", None) or []))
        self._local = {"folder": folder, "recs": recs, "app_sig": app_sig}
        self._wr_cache.clear()
        self._series_disk = None
        self._series_path = None
        want = None
        if want_stem:
            for r in recs:
                if r.get("stem") == want_stem:
                    want = r["label"]
                    break
        self._label = None
        self.on_trace_change(want)
        self._sync_series_nav(folder)
        self._status("loaded %d spectra from %s."
                     % (len(recs), os.path.basename(folder)))
        # a continuity file beside the data is an offer, like his
        for cand in self._series_read_paths():
            if os.path.isfile(cand):
                if messagebox.askyesno(
                        "Fringe workbench",
                        "This folder has saved continuity. Yes loads its "
                        "recorded points.", parent=self.app.root):
                    self.load_series()
                break

    def _read_folder(self, folder):
        """Parse every *_absorbance.csv in `folder` (the frozen schema:
        Wavelength_nm ... Background, Sample) into workbench records."""
        import glob as _glob
        paths = _glob.glob(os.path.join(folder, "*_absorbance.csv"))

        def _key(p):
            name = os.path.basename(p)
            pr = self._parse_pressure_name(name)
            tie = (len(name), name.lower())
            if pr is None:
                return (2, 0.0) + tie
            return ((1, -pr) + tie if self._is_decomp_name(name)
                    else (0, pr) + tie)

        recs = []
        for p in sorted(paths, key=_key):
            try:
                arr = np.genfromtxt(p, delimiter=",", names=True)
            except (OSError, ValueError):
                continue
            names = arr.dtype.names or ()

            def _col(want, _names=names, _arr=arr):
                for nm in _names:
                    if want.lower() in nm.lower():
                        return np.asarray(_arr[nm], float)
                return None

            wl = _col("Wavelength")
            bg = _col("Background")
            sm = _col("Sample")
            if wl is None or bg is None or sm is None or wl.size < 8:
                continue
            name = os.path.basename(p)
            stem = os.path.splitext(name)[0]
            pr = self._parse_pressure_name(name)
            dec = self._is_decomp_name(name)
            label = (("%g GPa" % pr) + (" (D)" if dec else "")
                     if pr is not None else stem)
            recs.append({"label": label, "stem": stem, "path": p,
                         "wl": wl, "bg_c": bg, "samp_c": sm,
                         "pressure_val": pr,
                         "pressure_str": (("%g" % pr).replace(".", "p")
                                          if pr is not None else ""),
                         "branch": "D" if dec else "C"})
        # duplicate labels get the stem appended: uniqueness is what the
        # dropdown's routing rides on
        seen = {}
        for r in recs:
            seen.setdefault(r["label"], []).append(r)
        for lab, group in seen.items():
            if len(group) > 1:
                for r in group:
                    r["label"] = "%s (%s)" % (lab, r["stem"])
        return recs

    def _sync_series_nav(self, folder):
        nav = getattr(self, "_parent_nav", None)
        if not nav or folder not in (nav.get("folders") or []):
            parent = os.path.dirname(os.path.normpath(folder))
            subs = self._scan_series_folders(parent)
            if folder not in subs:
                subs = [folder]
            nav = self._parent_nav = {"parent": parent, "folders": subs,
                                      "idx": subs.index(folder)}
        else:
            nav["idx"] = nav["folders"].index(folder)
        self._refresh_series_nav_ui()

    def _refresh_series_nav_ui(self):
        cb = getattr(self, "_series_cb", None)
        nav = getattr(self, "_parent_nav", None)
        if cb is None:
            return
        try:
            if not nav or not nav.get("folders"):
                cb["values"] = []
                self.series_nav_v.set("\u2013 (no parent loaded)")
            else:
                folders = nav["folders"]
                n = len(folders)
                vals = ["%d/%d: %s" % (i + 1, n,
                                       os.path.basename(folders[i]))
                        for i in range(n)]
                cb["values"] = vals
                i = nav.get("idx", -1)
                self.series_nav_v.set(vals[i] if 0 <= i < n else "")
        except tk.TclError:
            return
        btns = getattr(self, "_series_nav_btns", None)
        if btns:
            i = (nav or {}).get("idx", -1)
            n = len((nav or {}).get("folders") or [])
            try:
                btns[0].state(["disabled"] if i <= 0 else ["!disabled"])
                btns[1].state(["disabled"] if (i < 0 or i >= n - 1)
                              else ["!disabled"])
            except tk.TclError:
                pass

    def _step_series(self, d):
        nav = getattr(self, "_parent_nav", None)
        if not nav or not nav.get("folders"):
            self._status("load a parent folder first.", warn=True)
            return
        i = nav.get("idx", -1) + d
        if i < 0 or i >= len(nav["folders"]):
            return
        if not self._leave_guard():
            return
        nav["idx"] = i
        self._load_local_folder(nav["folders"][i])

    def _on_series_pick(self, _e=None):
        nav = getattr(self, "_parent_nav", None)
        cb = getattr(self, "_series_cb", None)
        if not nav or cb is None:
            return
        try:
            i = cb.current()
        except tk.TclError:
            i = -1
        if i is None or i < 0 or i == nav.get("idx"):
            self._refresh_series_nav_ui()
            return
        if not self._leave_guard():
            self._refresh_series_nav_ui()
            return
        nav["idx"] = i
        self._load_local_folder(nav["folders"][i])

    # ---- PRESSURE POINT ---------------------------------------------------
    def _card_pressure(self):
        b = self.app._group(self.sidebar_parent, "Pressure point")
        a = self.app
        r = self._row(b)
        nx = ttk.Button(r, text="\u25b6", width=2,
                        command=lambda: self._step_trace(1))
        nx.pack(side="right")
        pv = ttk.Button(r, text="\u25c0", width=2,
                        command=lambda: self._step_trace(-1))
        pv.pack(side="left")
        self._trace_cb = ttk.Combobox(r, textvariable=self.trace_v,
                                      state="readonly", width=18)
        self._trace_cb.pack(side="left", fill="x", expand=True,
                            padx=(PAD_X_TIGHT, PAD_X_TIGHT))
        self._trace_cb.bind("<<ComboboxSelected>>", self._on_trace_pick)
        self._pressure_btns = (pv, nx)
        self._tip(self._trace_cb,
                  "The pressure points of this series, in the order the "
                  "experiment ran them: up the compression run, then "
                  "back down the decompression leg. This is the only "
                  "picker; the arrows walk the same list.")
        self._tip(pv, "Previous pressure point along the experiment's "
                      "path.")
        self._tip(nx, "Next pressure point along the experiment's path.")

    def _ordered_recs(self):
        """The records along the experiment's path: compression ascending,
        then decompression descending -- his _pressure_key, applied to
        whatever the working set is."""
        def _key(r):
            pr = r.get("pressure_val")
            name = str(r.get("label") or "")
            tie = (len(name), name.lower())
            try:
                pr = None if pr is None else float(pr)
            except (TypeError, ValueError):
                pr = None
            if pr is None:
                return (2, 0.0) + tie
            dec = (r.get("branch") or "C") == "D"
            return ((1, -pr) + tie) if dec else ((0, pr) + tie)
        return sorted(self._records(), key=_key)

    def _refresh_pressure_nav_ui(self):
        btns = getattr(self, "_pressure_btns", None)
        if not btns:
            return
        names = [r["label"] for r in self._ordered_recs()]
        try:
            i = names.index(self._label)
        except ValueError:
            i = -1
        try:
            btns[0].state(["disabled"] if i <= 0 else ["!disabled"])
            btns[1].state(["disabled"] if (i < 0 or i >= len(names) - 1)
                          else ["!disabled"])
        except tk.TclError:
            pass

    # ---- FFT REMOVAL: the main cleaning tool ------------------------------
    def _card_removal(self):
        b = self.app._group(self.sidebar_parent, "FFT removal")
        a = self.app
        for chan in CHANNELS:
            a._subhead(b, chan)
            # The switch, the cutoff and Clear notches came to 411 px on a
            # 364 px column at text size 10: pack DROPPED the unit label
            # and squeezed the spinbox by 25 px.  Clear notches takes the
            # next line, full width, so nothing is cut (rule 14).
            r = self._row(b, PAD_TIGHT)
            cb = ttk.Checkbutton(r, text="Low-pass cutoff",
                                 variable=self.lp_on_v[chan],
                                 command=lambda c=chan:
                                 self._on_lp_toggle(c))
            cb.pack(side="left")
            a._lbl(r, text="um").pack(side="right", padx=(PAD_X_TIGHT, 0))
            sp = self._spin(r, self.lp_v[chan], 1.0, 400.0, width=6)
            sp.configure(command=lambda c=chan: self._on_lp_edit(c))
            sp.bind("<Return>", lambda e, c=chan: self._on_lp_edit(c))
            sp.bind("<FocusOut>",
                    lambda e, c=chan: self._on_lp_edit(c, quiet=True))
            sp.pack(side="right", padx=(PAD_X, 0))
            r = self._row(b, PAD_BTNROW)
            clr = ttk.Button(r, text="Clear notches",
                             command=lambda c=chan:
                             self._clear_notches_for(c))
            clr.pack(side="left", fill="x", expand=True)
            self._tip(cb, "The main cleaning tool: a soft low-pass. It "
                          "removes every ripple above the cutoff in n*t, on "
                          "top of this channel's notches. It is one combined "
                          "mask, applied once. The dashed line on the chart "
                          "is the same control. Drag it.")
            self._tip(sp, "This channel's cutoff, in micron of n*t.")
            self._tip(clr, "Take every notch off this channel, keeping the "
                           "fundamental in the list but unticked, ready to "
                           "re-enable. The saved notches file stays as it is.")
        r = self._row(b, PAD_GROUP)
        ec = ttk.Button(r, text="Export cleaned spectrum",
                        command=self._export_cleaned)
        ec.pack(side="left", fill="x", expand=True)
        self._tip(ec, "Write the cleaned spectrum, the red FFT filtered "
                      "curve, per channel to CSV. The columns are "
                      "Wavenumber_cm, Background_notch, Sample_notch and "
                      "Absorbance_notch, his exactly.")
        nl = ttk.Button(r, text="Notch list", width=11,
                        command=self._open_notch_list)
        nl.pack(side="left", fill="x", expand=True, padx=(PAD_X, 0))
        self._tip(nl, "Open the notch list: every centre, its own "
                      "half-width, the fundamental flag. Click peaks on "
                      "the chart to add or remove them.")
        r = self._row(b, PAD_BTNROW)
        wn = ttk.Button(r, text="Write notches file for batch",
                        command=self.export_notch_overrides)
        wn.pack(side="left", fill="x", expand=True)
        self._tip(wn, "Save notch_overrides.csv. It holds every centre and "
                      "half-width you picked, for every spectrum. The form "
                      "is the one the batch pipeline reads back.")
        dn = ttk.Button(r, text="Delete notches file", width=18,
                        command=self._delete_notches_file)
        dn.pack(side="left", fill="x", expand=True, padx=(PAD_X, 0))
        self._tip(dn, "Remove this spectrum's saved rows from "
                      "notch_overrides.csv; the file goes too once it "
                      "is empty. The live notches on the chart stay.")
        r = self._row(b, PAD_BTNROW)
        wd = ttk.Button(r, text="Write to defringe", width=18,
                        command=self._write_to_defringe)
        wd.pack(side="left", fill="x", expand=True)
        self._tip(wd, "Hand these centres and low-pass cutoffs to the whole "
                      "series. The df box above the plot then cleans at "
                      "these peaks. A Run's defringed CSVs and Export CSV do "
                      "the same.")
        self._notch_file_lbl = a._lbl(b, text="", foreground=MUTED)
        self._slot(self._notch_file_lbl, fill="x", pady=PAD_TIGHT)

    def _on_lp_toggle(self, chan):
        self._lp_last[chan] = self.lp_v[chan].get()
        self._invalidate()

    def _on_lp_edit(self, chan, quiet=False):
        """Live cutoff edits redraw; a FocusOut with nothing changed does
        not (his _make_lp_apply guard)."""
        cur = self.lp_v[chan].get()
        if quiet and cur == self._lp_last.get(chan):
            return
        self._lp_last[chan] = cur
        self._invalidate()

    def _clear_notches_for(self, chan):
        """His Clear notches: drop every harmonic and manual notch on
        this channel but KEEP the fundamental in the list, unticked,
        ready to re-enable.  The saved notches file is not touched
        (that is Delete notches file)."""
        ch = self._ch(chan)
        if ch is None:
            self._status("no %s data loaded." % chan, warn=True)
            return
        defaults = list(ch.get("default_centers") or [])
        fund = defaults[0] if defaults else None
        keys = set(defaults) | set(ch.get("user_centers") or [])
        keys.discard(fund)
        ch["removed"] |= keys
        ch["user_centers"] = [k for k in ch["user_centers"] if k == fund]
        if fund is not None:
            ch["unticked"].add(fund)
        self._notch_sig = None
        self._status("cleared %s notches. the fundamental stays listed, "
                     "unticked." % chan)
        self._invalidate()

    def _delete_notches_file(self):
        """His Delete notches file: remove THIS spectrum's rows from
        notch_overrides.csv, and the file itself once that empties it.
        The live notches on the chart are untouched."""
        import csv
        folder = self._series_folder()
        if not folder:
            self._status("pick a data folder first.", warn=True)
            return
        path = os.path.join(folder, NOTCH_FILE)
        if not os.path.isfile(path):
            self._status("no %s to clear." % NOTCH_FILE)
            return
        stem = self._stem_of(self._label) if self._label else None
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))
        except (OSError, csv.Error) as exc:
            self._status("could not read %s: %s" % (NOTCH_FILE, exc),
                         warn=True)
            return
        if not rows:
            return
        head, body = rows[0], rows[1:]
        kept = [r for r in body if not (r and r[0] == stem)]
        if len(kept) == len(body):
            self._status("no saved rows for %s." % (stem or "this "
                                                    "spectrum"))
            return
        try:
            if not kept:
                os.remove(path)
                self._status("cleared the last override; removed %s."
                             % NOTCH_FILE)
            else:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(head)
                    w.writerows(kept)
                self._status("cleared the saved override for %s." % stem)
        except OSError as exc:
            self._status("could not rewrite %s: %s" % (NOTCH_FILE, exc),
                         warn=True)

    def _export_cleaned(self):
        """His Export cleaned spectrum: the red FFT-filtered curve per
        channel as CSV -- Wavenumber_cm, Background_notch, Sample_notch
        and Absorbance_notch = log10(BG/S), his columns and file name."""
        rec = self._record()
        if rec is None:
            self._status("load a spectrum before exporting.", warn=True)
            return
        cols = {}
        for chan in CHANNELS:
            c = self._compute(chan)
            fi = (c or {}).get("fft_info") or {}
            ic = fi.get("I_notch_1x")
            if ic is not None and np.any(np.isfinite(np.asarray(ic))):
                cols["%s_notch" % chan] = np.asarray(ic, float)
        if not cols:
            self._status("the cleaned spectrum needs a detected fringe.",
                         warn=True)
            return
        folder = self._series_folder()
        if not folder:
            self._status("pick an input or output folder first.", warn=True)
            return
        wl = np.asarray(rec["wl"], float)
        wn = 1e7 / np.maximum(wl, 1e-9)
        out = [("Wavenumber_cm", wn)]
        for k in ("Background_notch", "Sample_notch"):
            if k in cols:
                out.append((k, cols[k]))
        if "Background_notch" in cols and "Sample_notch" in cols:
            with np.errstate(divide="ignore", invalid="ignore"):
                absn = np.log10(cols["Background_notch"]
                                / cols["Sample_notch"])
            absn = np.where(np.isfinite(absn), absn, np.nan)
            out.append(("Absorbance_notch", absn))
        stamp = time.strftime("%Y%m%d_%H%M%S")
        stem = self._stem_of(self._label) or "spectrum"
        path = os.path.join(folder, "cleaned_spectrum_%s_%s.csv"
                            % (stem, stamp))
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(",".join(k for k, _v in out) + "\n")
                for i in range(len(wn)):
                    f.write(",".join((("%.10g" % v[i])
                                      if np.isfinite(v[i]) else "")
                                     for _k, v in out) + "\n")
        except OSError as exc:
            self._status("export failed: %s" % exc, warn=True)
            return
        self._log("Fringe: wrote cleaned spectrum -> %s" % path)
        self._status("exported cleaned spectrum -> %s"
                     % os.path.basename(path))

    def _on_wl_over(self):
        key = self._dataset_key()
        ov = self.settings.setdefault("fr_wl_overrides", {})
        if self.wlover_v.get():
            ov[key] = [_f(self.wlmin_v, 600.0), _f(self.wlmax_v, 800.0)]
            self._status("wavelength window pinned to this dataset "
                         "(%g-%g nm)." % tuple(ov[key]))
        else:
            ov.pop(key, None)
            self._status("wavelength window back to the global default.")
        self._invalidate()

    def _dataset_key(self):
        loc = getattr(self, "_local", None)
        if loc and loc.get("folder"):
            return loc["folder"]
        try:
            return self.app.in_var.get() or "(none)"
        except Exception:
            return "(none)"

    # ---- REFRACTIVE INDEX FROM INTENSITY ----------------------------------
    def _card_intensity(self):
        b = self.app._group(self.sidebar_parent,
                            "Refractive Index from Intensity")
        a = self.app
        r = self._row(b)
        cf = a._brand_button(r, "Compute fits", self._compute_fits)
        cf.pack(side="left", fill="x", expand=True)
        self._tip(cf, "Run the full amplitude fitters on the current notch "
                      "and low-pass settings. They are the constant-n cosine "
                      "fit and the band integral, over every spectral "
                      "window. The right panels switch to the tiered view to "
                      "show the result.")
        hb = ttk.Button(r, text="History \u25be", width=10,
                        command=self._open_history)
        hb.pack(side="left", fill="x", expand=True, padx=(PAD_X, 0))
        self._tip(hb, "Reopen a previous Compute fits run, with its inputs "
                      "and notch settings. The list names each by the fitted "
                      "n.")
        r = self._row(b, PAD_BTNROW)
        self._tiers_btn = ttk.Button(r, text="Show tiered", width=13,
                                     command=self._toggle_tiers)
        self._tiers_btn.pack(side="left", fill="x", expand=True)
        self._tip(self._tiers_btn,
                  "Flat view: the right panels show raw plus the FFT "
                  "filtered spectrum at true intensity. Tiered view: the "
                  "offset diagnostic stack, plus the crimson and blue "
                  "residual FFTs on the left panels. Compute fits "
                  "switches to tiered by itself.")
        self._clean_btn = ttk.Button(r, text="Hide clean spectrum",
                                     width=18,
                                     command=self._toggle_hideclean)
        self._clean_btn.pack(side="left", fill="x", expand=True,
                             padx=(PAD_X, 0))
        self._tip(self._clean_btn,
                  "Hide or show the red FFT filtered curve on the right "
                  "panels. Off leaves raw and the tiers.")
        r = self._row(b, PAD_BTNROW)
        bf = ttk.Checkbutton(r, text="Band \u0394 resolution floor",
                             variable=self.bandfloor_v,
                             command=self._invalidate)
        bf.pack(side="left")
        self._tip(bf, "Applies to the band integral alone: hold its "
                      "integration band at the FFT main lobe or wider. The "
                      "notches, the cleaning and the shaded windows hold. "
                      "Only V_band moves, and mostly on short windows.")

    def _compute_fits(self):
        """His Compute fits: run the full fitters (run_fits=True) on both
        channels under the current notch + low-pass settings, switch the
        right panels to the tiered view, and file a history snapshot."""
        rec = self._record()
        if rec is None:
            self._status("load a spectrum first.", warn=True)
            return
        self._status("computing fits...")
        try:
            self.app.root.update_idletasks()
        except (AttributeError, tk.TclError):
            pass
        cfg = self._cfg_for(rec)
        done = []
        for chan in CHANNELS:
            centers = self._active_centers(chan)
            kw = {}
            if centers:
                kw["notch_centers_nm"] = [k * 1000.0 for k in centers]
                kw["notch_halfwidths_um"] = [self._width_of(chan, k)
                                             for k in centers]
            if self.lp_on_v[chan].get():
                kw["lowpass"] = True
                kw["lp_cutoff_um"] = max(_f(self.lp_v[chan], 15.0), 1e-3)
            try:
                fit, _I, _nt, _d = compute_channel_fit(
                    rec["wl"], rec[CHAN_KEY[chan]], cfg=cfg,
                    label="%s %s" % (rec["label"], chan), run_fits=True,
                    **kw)
            except Exception as exc:
                self._status("%s fit failed: %s" % (chan, exc), warn=True)
                continue
            self._fits[(self._label, chan)] = fit
            n = self._fitted_n(chan)
            done.append("%s n=%s" % (chan[0],
                                     _fmt(n, 3) if n is not None
                                     else "\u2013"))
        self.tiers_v.set(True)      # computing fits shows the tiers, his rule
        self._sync_view_buttons()
        self._record_fit_history()
        self._request_redraw(now=True)
        if done:
            self._status("fits computed (%s)." % ", ".join(done))
        else:
            self._status("the fit needs a detected fringe.",
                         warn=True)

    def _fitted_n(self, chan):
        """The fitted constant-n for a channel: fine window first, then
        narrow, wide, full -- his n_mean preference order."""
        fit = self._fits.get((self._label, chan))
        cn = ((fit or {}).get("models") or {}).get("constant_n") or {}
        for win in ("fine", "narrow", "wide", "full"):
            d = cn.get(win)
            if d and d.get("n_mean") is not None:
                return float(d["n_mean"])
        return None

    def _fine_residual_ffts(self, chan):
        """Post-fit residual FFTs on the measured curve's own grid --
        crimson = direct cosine residual, blue = band-integral residual.
        His _fine_residual_ffts on the vendored core: resid = norm -
        fresnel_V(n) cos(4 pi nt / lambda + phi0), Hann-windowed rfft in
        the measured-FFT V convention."""
        fit = self._fits.get((self._label, chan))
        if not fit:
            return []
        cn = (fit.get("models") or {}).get("constant_n") or {}
        fine = cn.get("fine") or cn.get("narrow")
        if not fine or fine.get("n_mean") is None:
            return []
        fi = fit.get("fft_info") or {}
        wn_u = fi.get("wn_u")
        norm = fi.get("norm_u_detrend")
        if wn_u is None or norm is None or len(np.asarray(norm)) < 16:
            return []
        wn_u = np.asarray(wn_u, float)
        norm = np.asarray(norm, float)
        if wn_u.size != norm.size:
            return []
        wl_u = 1.0 / np.maximum(wn_u, 1e-12)
        w = np.hanning(len(norm))
        wsum = max(float(np.sum(w)), 1e-9)
        dwn = float(np.median(np.diff(wn_u))) or 1e-9
        nt_nm = float(fine["nt_um"]) * 1000.0
        phi0 = float(fine.get("phi0") or 0.0)
        out = []

        def _one(n_val, color, name):
            phi = 4.0 * np.pi * nt_nm / wl_u + phi0
            resid = (norm - fringe_optics.fresnel_V(n_val, wl_u)
                     * np.cos(phi))
            X = np.fft.rfft(resid * w)
            freqs = np.fft.rfftfreq(len(resid), d=abs(dwn))
            out.append((freqs / 2000.0, 2.0 * np.abs(X) / wsum, color,
                        name))

        try:
            _one(float(fine["n_mean"]), "crimson",
                 "direct resid (fine fit)")
            ba = fi.get("band_amp") or {}
            vb = float(ba.get("V_band_fine") or ba.get("V_band") or 0.0)
            if vb > 0:
                cfg = self._cfg_for(self._record() or {})
                wl_c = 0.5 * (cfg.fit_wl_min_nm + cfg.fit_wl_max_nm)
                nb = float(fringe_optics.fresnel_n_from_V(
                    min(vb, 0.9999), wl_c))
                _one(nb, "royalblue", "integral resid (fine fit)")
        except Exception:
            return []
        return out

    def _sync_view_buttons(self):
        try:
            self._tiers_btn.configure(text=("Hide tiered"
                                            if self.tiers_v.get()
                                            else "Show tiered"))
            self._clean_btn.configure(text=("Show clean spectrum"
                                            if self.hideclean_v.get()
                                            else "Hide clean spectrum"))
        except (AttributeError, tk.TclError):
            pass

    def _toggle_tiers(self):
        self.tiers_v.set(not self.tiers_v.get())
        self._sync_view_buttons()
        self._request_redraw(now=True)

    def _toggle_hideclean(self):
        self.hideclean_v.set(not self.hideclean_v.get())
        self._sync_view_buttons()
        self._request_redraw(now=True)

    # ---- fit history ------------------------------------------------------
    def _record_fit_history(self):
        snap = {"stamp": time.strftime("%H:%M:%S"),
                "fitn": {c: self._fitted_n(c) for c in CHANNELS},
                "stack": {"medium": self.medium_v.get(),
                          "medium_n": _f(self.medium_n_v, 1.2),
                          "layer2_on": bool(self.layer2_on_v.get()),
                          "layer2": self.layer2_v.get(),
                          "n_sample": _f(self.ns_v, 1.5),
                          "d1": _f(self.d1_v, 0.0),
                          "t": _f(self.t_v, 20.0),
                          "d2": _f(self.d2_v, 0.0)},
                "lp": {c: [bool(self.lp_on_v[c].get()),
                           _f(self.lp_v[c], 15.0)] for c in CHANNELS},
                "notch": (self._mem_state() or {}).get("chan") or {}}
        same = [s for s in self._fit_history
                if {k: v for k, v in s.items() if k != "stamp"}
                == {k: v for k, v in snap.items() if k != "stamp"}]
        for s in same:
            self._fit_history.remove(s)
        self._fit_history.insert(0, snap)
        del self._fit_history[12:]
        self._fill_history()

    def _open_history(self):
        win = self._raise_existing("_hist_win")
        if win is not None:
            self._fill_history()
            return win
        a = self.app
        win = tk.Toplevel(a.root)
        win.title("Fit history")
        win.transient(a.root)
        a._center_on_root(win, *self._dlg_size(48, 40))
        a._apply_titlebar(win)
        win.bind("<Escape>", lambda e: win.destroy())
        self._hist_win = win
        card = a._card(win, grow="both")
        card.pack(fill="both", expand=True, padx=10, pady=8)
        card.set_title(a._lf_header(card, "Fit history"))
        a._lbl(card.body,
               text="Previous Compute fits runs, newest first, named by "
                    "the fitted Background / Sample n. Click one to "
                    "restore its inputs and notch settings; the cross "
                    "forgets it.",
               wraplength=a._em() * 40, justify="left",
               foreground=MUTED).pack(anchor="w", pady=PAD_ROW)
        self._hist_rows = ttk.Frame(card.body)
        self._hist_rows.pack(fill="both", expand=True)
        self._fill_history()
        return win

    def _fill_history(self):
        f = getattr(self, "_hist_rows", None)
        if f is None:
            return
        try:
            if not f.winfo_exists():
                self._hist_rows = None
                return
            for w in f.winfo_children():
                w.destroy()
        except tk.TclError:
            return
        a = self.app
        if not self._fit_history:
            a._lbl(f, text="(no fits computed yet)",
                   foreground=MUTED).pack(anchor="w")
            return
        for snap in list(self._fit_history):
            r = ttk.Frame(f)
            r.pack(fill="x", pady=1)
            fn = snap.get("fitn") or {}

            def _n(v):
                return ("%.3f" % v) if isinstance(v, float) else "\u2013"
            ttk.Button(r, text="%s   B n=%s   S n=%s"
                       % (snap.get("stamp", ""),
                          _n(fn.get("Background")), _n(fn.get("Sample"))),
                       command=lambda s=snap:
                       self._hist_recall(s)).pack(side="left", fill="x",
                                                  expand=True)
            ttk.Button(r, text="\u00d7", width=2,
                       command=lambda s=snap:
                       self._hist_forget(s)).pack(side="left",
                                                  padx=(4, 0))

    def _hist_forget(self, snap):
        self._fit_history[:] = [s for s in self._fit_history
                                if s is not snap]
        self._fill_history()

    def _hist_recall(self, snap):
        st = snap.get("stack") or {}
        self._suspend = True
        try:
            if st.get("medium") in MEDIUM_CHOICES:
                self.medium_v.set(st["medium"])
            self.medium_n_v.set("%g" % st.get("medium_n", 1.2))
            self.layer2_on_v.set(bool(st.get("layer2_on", False)))
            if st.get("layer2"):
                self.layer2_v.set(st["layer2"])
            self.ns_v.set("%g" % st.get("n_sample", 1.5))
            self.d1_v.set("%g" % st.get("d1", 0.0))
            self.t_v.set("%g" % st.get("t", 20.0))
            self.d2_v.set("%g" % st.get("d2", 0.0))
            for c in CHANNELS:
                pair = (snap.get("lp") or {}).get(c)
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    self.lp_on_v[c].set(bool(pair[0]))
                    self.lp_v[c].set("%g" % float(pair[1]))
        finally:
            self._suspend = False
        if self._label is not None:
            for chan, cd in (snap.get("notch") or {}).items():
                ch = self._ch(chan)
                if ch is None:
                    continue
                ch["user_centers"] = [float(k) for k in
                                      cd.get("user_centers", [])]
                ch["removed"] = set(float(k) for k in
                                    cd.get("removed", []))
                ch["unticked"] = set(float(k) for k in
                                     cd.get("unticked", []))
                ch["user_fundamental"] = cd.get("user_fundamental")
                ch["widths"] = {float(k): float(v) for k, v in
                                (cd.get("widths") or {}).items()}
        self._on_layer2()
        self._sync_medium_row()
        self._thick_snapshot()
        self._notch_sig = None
        self._status("restored a Compute fits run from the history.")
        self._invalidate()

    # ---- PANELS: the pop-out launcher + the bottom readouts ---------------
    def _card_panels(self):
        b = self.app._group(self.sidebar_parent, "Panels")
        a = self.app
        r = self._row(b)
        for txt, cmd, tip in (
                ("Notch list", self._open_notch_list,
                 "The notch list, in its own window."),
                ("Predicted lines", self._open_pred_lines,
                 "The forward-model lines as selectable text: every "
                 "interface pair and its optical path.")):
            btn = ttk.Button(r, text=txt, command=cmd)
            btn.pack(side="left", fill="x", expand=True,
                     padx=(0 if txt == "Notch list" else PAD_X, 0))
            self._tip(btn, tip)
        r = self._row(b, PAD_BTNROW)
        for txt, cmd, tip in (
                ("Results", self.results_view,
                 "The recorded series against pressure. It is the same "
                 "window the Results plot button opens."),
                ("Info", self._open_wb_info,
                 "The marker key, the mouse grammar, and where the "
                 "files go."),
                ("Detection", self._open_detection,
                 "Scroll the Detection card into view. It holds the "
                 "wavelength window, the n*t band, Fisher p, the "
                 "agreement tolerance and the search report.")):
            btn = ttk.Button(r, text=txt, command=cmd)
            btn.pack(side="left", fill="x", expand=True,
                     padx=(0 if txt == "Results" else PAD_X, 0))
            self._tip(btn, tip)
        r = self._row(b, PAD_BTNROW)
        mv = ttk.Checkbutton(r, text="Error bars (multiscale variance)",
                             variable=self.msv_v, command=self._on_msv)
        mv.pack(side="left")
        self._tip(mv, "Estimate each recorded point's uncertainty from the "
                      "spread of the fit across analysis scales. Off by "
                      "default: about 35 ms per point, computed once and "
                      "cached.")

        self._status_lbl = a._lbl(b, text="Load a spectrum to get FFT peaks.",
                                  foreground=MUTED,
                                  wraplength=self.app._em() * 32,
                                  justify="left")
        self._slot(self._status_lbl, fill="x", pady=PAD_ROW)
        self._wrap_to_card(self._status_lbl)
        self._solve_lbl = a._lbl(b, text="",
                                 wraplength=self.app._em() * 32,
                                 justify="left")
        self._slot(self._solve_lbl, fill="x", pady=PAD_TIGHT)
        self._wrap_to_card(self._solve_lbl)
        r = self._row(b, PAD_GROUP)
        a._lbl(r, text="CSV folder:", width=LBL_W).pack(side="left")
        self.csv_dir_v = tk.StringVar(value="\u2013")
        e = ttk.Entry(r, textvariable=self.csv_dir_v, state="readonly")
        e.pack(side="left", fill="x", expand=True)
        self._tip(e, "Where the workbench writes its CSVs: cleaned spectra, "
                     "the notches file, results, the session. Beside your "
                     "data when that folder takes new files, else your "
                     "output folder.")

    def _set_solve_status(self, text):
        """The dedicated solve-status line: solve errors and clamp
        warnings live here so they never overwrite a load or export
        message (his solve_status slot)."""
        lab = getattr(self, "_solve_lbl", None)
        if lab is None:
            return
        try:
            lab.configure(text=text, foreground=self._warn_fg())
        except tk.TclError:
            return
        self._show_if_text(lab, text)

    def _sync_action_marks(self):
        """The green tick on Results plot, his caption grammar: it tracks
        whether THIS pressure point is on the results series."""
        on = any(q.get("label") == self._label for q in self._series)
        try:
            self._results_btn.configure(
                text=("Results plot \u2713" if on else "Results plot"))
        except (AttributeError, tk.TclError):
            pass

    # ---- pop-outs ---------------------------------------------------------
    def _open_notch_list(self):
        win = self._raise_existing("_notch_win")
        if win is not None:
            return win
        a = self.app
        win = tk.Toplevel(a.root)
        win.title("Notch list")
        win.transient(a.root)
        a._center_on_root(win, *self._dlg_size(52, 46))
        a._apply_titlebar(win)
        win.bind("<Escape>", lambda e: win.destroy())
        self._notch_win = win
        card = a._card(win, grow="both")
        card.pack(fill="both", expand=True, padx=10, pady=8)
        card.set_title(a._lf_header(card, "Notch list"))
        b = card.body
        a._lbl(b, text="Click a peak on the chart to add a notch; click "
                       "it again to take it away. Untick a row to keep "
                       "the marker but stop the notch. Widths are "
                       "absolute half-widths, in +/- micron of n*t.",
               wraplength=a._em() * 44, justify="left",
               foreground=MUTED).pack(anchor="w", pady=PAD_ROW)
        r = ttk.Frame(b)
        r.pack(fill="x", pady=PAD_TIGHT)
        a._lbl(r, text="Half-width", width=LBL_W).pack(side="left")
        sp = self._spin(r, self.hw_v, 0.05, 200.0, width=7)
        sp.pack(side="left")
        a._lbl(r, text="+/- um").pack(side="left", padx=PAD_X_TIGHT)
        self._tip(sp, "Default half-width for a NEW notch. Rows keep "
                      "their own widths.")
        rs = ttk.Button(r, text="Reset", width=8,
                        command=self._reset_notches)
        rs.pack(side="right")
        self._tip(rs, "Drop every manual notch on this spectrum and go "
                      "back to the detected fundamental.")
        self._notch_rows = ttk.Frame(b)
        self._notch_rows.pack(fill="both", expand=True)
        self._notch_sig = None
        self._refresh_notch_rows()
        return win

    def _refresh_notch_rows(self):
        """Rebuild the notch list (in its pop-out).  One row per centre:
        micron, half-width, the fundamental flag and a remove cross.
        Signature-guarded: a low-pass drag redraws at 110 ms and
        rebuilding a dozen widgets per frame would stutter."""
        f = self._notch_rows
        if f is None:
            return
        try:
            if not f.winfo_exists():
                self._notch_rows = None
                return
        except tk.TclError:
            return
        sig = []
        for chan in CHANNELS:
            ch = self._ch(chan)
            keys = self._active_centers(chan, include_unticked=True)
            sig.append((chan, tuple(keys), tuple(sorted(ch["unticked"]))
                        if ch else (), self._fund_key(chan),
                        tuple(round(self._width_of(chan, k), 4)
                              for k in keys)))
        sig = tuple(sig)
        if sig == getattr(self, "_notch_sig", None):
            return
        self._notch_sig = sig
        for w in f.winfo_children():
            w.destroy()
        a = self.app
        any_row = False
        for chan in CHANNELS:
            ch = self._ch(chan)
            if ch is None:
                continue
            centers = self._active_centers(chan, include_unticked=True)
            if not centers:
                continue
            a._lbl(f, text=chan, font=a._F(-1, "bold"),
                   foreground=MUTED).pack(anchor="w", pady=PAD_TIGHT)
            fund = self._fund_key(chan)
            for kk in centers:
                any_row = True
                r = ttk.Frame(f)
                r.pack(fill="x", pady=PAD_TIGHT)
                on = tk.BooleanVar(value=kk not in ch["unticked"])
                cb = ttk.Checkbutton(
                    r, variable=on,
                    command=lambda c=chan, k=kk, v=on:
                    self._tick(c, k, v))
                cb.pack(side="left")
                self._tip(cb, "Untick to keep the marker but drop this "
                              "centre from the notch.")
                a._lbl(r, text=("%.2f" % kk), width=7,
                       font=a._F(0, mono=True)).pack(side="left")
                wv = tk.StringVar(value="%g" % self._width_of(chan, kk))
                we = ttk.Entry(r, textvariable=wv, width=5)
                we.pack(side="left", padx=PAD_X_TIGHT)
                we.bind("<Return>",
                        lambda e, c=chan, k=kk, v=wv:
                        self._set_width(c, k, v))
                we.bind("<FocusOut>",
                        lambda e, c=chan, k=kk, v=wv:
                        self._set_width(c, k, v))
                self._tip(we, "Half-width of this notch in +/- micron.")
                if kk == fund:
                    a._lbl(r, text="\u25b2",
                           foreground=a._brand()["ac2"]
                           ).pack(side="left", padx=PAD_X_TIGHT)
                x = ttk.Button(r, text="\u00d7", width=2,
                               command=lambda c=chan, k=kk:
                               self._remove_center(c, k))
                x.pack(side="right")
                self._tip(x, "Remove this centre from the list.")
        if not any_row:
            a._lbl(f, text="no notches yet",
                   foreground=MUTED).pack(anchor="w")

    def _open_pred_lines(self):
        win = self._raise_existing("_lines_win")
        if win is not None:
            self._fill_pred_lines()
            return win
        a = self.app
        win = tk.Toplevel(a.root)
        win.title("Predicted lines")
        win.transient(a.root)
        a._center_on_root(win, *self._dlg_size(46, 38))
        a._apply_titlebar(win)
        win.bind("<Escape>", lambda e: win.destroy())
        self._lines_win = win
        card = a._card(win, grow="both")
        card.pack(fill="both", expand=True, padx=10, pady=8)
        card.set_title(a._lf_header(card, "Predicted lines"))
        a._lbl(card.body, text="Forward-model lines (selectable / "
                               "copyable):",
               foreground=MUTED).pack(anchor="w", pady=PAD_TIGHT)
        pal = self._pal()
        txt = tk.Text(card.body, width=44, height=16, wrap="none",
                      relief="flat", highlightthickness=0, bd=0,
                      background=pal[0], foreground=pal[1],
                      insertbackground=pal[1],
                      font=self.app._F(0, mono=True))
        txt.pack(fill="both", expand=True)
        self._lines_txt = txt
        self._fill_pred_lines()
        return win

    def _fill_pred_lines(self):
        txt = getattr(self, "_lines_txt", None)
        if txt is None:
            return
        try:
            if not txt.winfo_exists():
                self._lines_txt = None
                return
        except tk.TclError:
            return
        rec = self._record()
        rows = []
        if rec is not None:
            try:
                p = self._stack_params(rec)
            except Exception:
                p = None
            if p:
                for name, kind in (("SAMPLE", "sample"),
                                   ("BACKGROUND", "medium")):
                    rows.append(name)
                    try:
                        lines = fringe_stack.stack_lines(p, kind=kind)
                    except Exception:
                        lines = []
                    for ln in lines:
                        ids = "+".join(sorted(ln.get("ids") or []))
                        rows.append("  %s: %s = %.2f um"
                                    % (ids, ln.get("formula") or "",
                                       float(ln["nt"])))
        if not rows:
            rows = ["load a spectrum first"]
        try:
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", "\n".join(rows))
            txt.configure(state="disabled")
        except tk.TclError:
            pass

    def _open_wb_info(self):
        win = self._raise_existing("_wbinfo_win")
        if win is not None:
            return win
        a = self.app
        win = tk.Toplevel(a.root)
        win.title("Info")
        win.transient(a.root)
        a._center_on_root(win, *self._dlg_size(52, 44))
        a._apply_titlebar(win)
        win.bind("<Escape>", lambda e: win.destroy())
        self._wbinfo_win = win
        card = a._card(win, grow="both")
        card.pack(fill="both", expand=True, padx=10, pady=8)
        card.set_title(a._lf_header(card, "Info", icon="book"))
        self._guide_body(card.body, list(WB_INFO), width=52)
        return win

    def _open_detection(self):
        """Bring the Detection card out where it can be read.

        R14 promoted the gates from a pop-out to a card in the Fringe
        column, directly above FFT removal.  Everything that used to open
        the window -- the Panels row, the pop-out's View menu, the guide
        tour -- lands here, and the card expands and scrolls into view.
        """
        return self.reveal_card("Detection")

    def reveal_card(self, title):
        """Show one Fringe card: switch to the tab, expand it, scroll to it.

        The right panel is a notebook of scrolling pages, so a card can be
        on a hidden tab, folded shut, or simply below the fold.  All three
        are undone here, in that order, and the card's header is left at
        the top of the page.
        """
        a = self.app
        rec = next((r for r in getattr(a, "_collapsibles", [])
                    if r.get("key") == title), None)
        if rec is None:
            return None
        cont = rec.get("cont")
        # the tab that holds it
        try:
            nb = a.rnotebook
            for i in range(nb.index("end")):
                if str(nb.tab(i, "text")).strip() == rec.get("cat"):
                    nb.select(i)
                    break
        except (AttributeError, tk.TclError):
            pass
        if rec.get("collapsed"):
            try:
                a._set_collapsed(rec, False)
                a._save_collapsed()
            except (AttributeError, tk.TclError):
                pass
        # Selecting the tab and expanding the card both re-lay the page,
        # and the notebook's own tab-changed handler re-asserts the scroll
        # region after that: a single scroll here would be undone.  The
        # move is made again as the page settles, three times over a fifth
        # of a second, which is under the eye's notice.
        for ms in (0, 70, 220):
            try:
                a.root.after(ms, lambda c=cont: self._scroll_card_into_view(c))
            except (AttributeError, tk.TclError):
                self._scroll_card_into_view(cont)
                break
        return cont

    def _scroll_card_into_view(self, cont):
        """Put `cont`'s header at the top of its scrolling page."""
        if cont is None:
            return
        try:
            page = cont.master               # the canvas' window item
            cv = page.master                 # the tk.Canvas itself
        except AttributeError:
            return
        heal = getattr(self.app, "_heal_tab_scroll", None)
        if callable(heal):
            try:
                heal(cv)
            except Exception:
                pass
        try:
            cv.update_idletasks()
            total = float(page.winfo_height())
            room = float(cv.winfo_height())
            if total <= room or total <= 0:
                return
            y = float(cont.winfo_y()) - 6.0
            top = max(0.0, min(y, total - room))
            cv.yview_moveto(top / total)
        except (AttributeError, tk.TclError, ValueError, ZeroDivisionError):
            pass

    def _card_detection(self):
        """The detection gates, and the live report of what they found.

        Matthew's GUI holds these as fixed constants; SPARTA keeps them
        editable.  They are the ONLY detection gates in the program -- the
        main window's "Detection (advanced)" fold is gone, and the df box
        above the plot reads what is set here.  The fringe-report switch
        sits with them, beside the numbers it talks about.
        """
        b = self.app._group(self.sidebar_parent, "Detection")
        a = self.app
        self._detect_body = b

        def gate(label, pady=PAD_TIGHT):
            r = self._row(b, pady)
            a._lbl(r, text=label, width=LBL_W + 3).pack(side="left")
            return r

        r = gate("Window (nm)", PAD_ROW)
        e1 = ttk.Entry(r, textvariable=self.wlmin_v, width=7)
        e1.pack(side="left", fill="x", expand=True)
        a._lbl(r, text="to", width=3, anchor="center").pack(
            side="left", padx=PAD_X_TIGHT)
        e2 = ttk.Entry(r, textvariable=self.wlmax_v, width=7)
        e2.pack(side="left", fill="x", expand=True)
        for e in (e1, e2):
            self._tip(e, "Wavelength range the FFT and the fits run in.")

        r = self._row(b, PAD_TIGHT)
        ov = ttk.Checkbutton(r, text="This dataset only",
                             variable=self.wlover_v,
                             command=self._on_wl_over)
        ov.pack(side="left")
        self._tip(ov, "Store the window above for the current input folder "
                      "alone, so each dataset keeps its own range.")

        r = gate("n*t band (um)", PAD_ROW)
        e3 = ttk.Entry(r, textvariable=self.ntmin_v, width=7)
        e3.pack(side="left", fill="x", expand=True)
        a._lbl(r, text="to", width=3, anchor="center").pack(
            side="left", padx=PAD_X_TIGHT)
        e4 = ttk.Entry(r, textvariable=self.ntmax_v, width=7)
        e4.pack(side="left", fill="x", expand=True)
        for e in (e3, e4):
            self._tip(e, "The n*t search window. The detector considers the "
                         "peaks inside it.")

        # the two single-value gates keep the FIRST box's column, so all
        # four entries in the card line up on one left and one right edge
        r = gate("Fisher p")
        e5 = ttk.Entry(r, textvariable=self.pmax_v, width=7)
        e5.pack(side="left", fill="x", expand=True)
        self._tip(e5, "The g-test significance gate.")
        a._lbl(r, text="", width=3).pack(side="left", padx=PAD_X_TIGHT)
        ttk.Frame(r).pack(side="left", fill="x", expand=True)

        r = gate("Agree tol")
        e6 = ttk.Entry(r, textvariable=self.tol_v, width=7)
        e6.pack(side="left", fill="x", expand=True)
        self._tip(e6, "How closely two of the three detection windows agree "
                      "on n*t for an accepted answer.")
        a._lbl(r, text="", width=3).pack(side="left", padx=PAD_X_TIGHT)
        ttk.Frame(r).pack(side="left", fill="x", expand=True)

        r = self._row(b, PAD_BTNROW)
        sup = ttk.Checkbutton(r, text="Suppress fringe report",
                              variable=self.suppress_v)
        sup.pack(side="left")
        self._tip(sup, "The fringe report goes to the main log whenever "
                       "defringe is switched on there. It lists which traces "
                       "have a detected fringe. It also gives the fitted n*t "
                       "in um and the detection p-value. Tick this to keep "
                       "it quiet.")

        a._subhead(b, "Report")
        self._rep = {}
        for key, txt2 in (("nt", "n*t"), ("p", "p"), ("corr", "from")):
            r = self._row(b, PAD_TIGHT)
            a._lbl(r, text=txt2, width=LBL_W2).pack(side="left")
            lab = a._lbl(r, text="–", font=a._F(0, mono=True))
            lab.pack(side="left", fill="x", expand=True)
            self._rep[key] = lab
        self._tip(self._rep["corr"],
                  "Which of the three detection windows corroborated the "
                  "fringe. A miss reads here too.")
        return b

    # =======================================================================
    # activation / view switch
    # =======================================================================
    def build_view_switch(self, parent):
        """The Plot | Fringe segmented control on the centre tab-strip row.

        Drawn from plain tk widgets recoloured from the palette on every
        repaint, exactly like the session tab strip above it -- sv_ttk's
        notebook tabs would not sit flush on that row.
        """
        self._switch_parent = parent
        self.sync_view_switch()

    def sync_view_switch(self):
        # This is also the workbench's THEME hook: the app's theme chain runs
        # _recolor_tk -> _sync_tabs -> _render_tabs, and _render_tabs ends by
        # calling this.  Anything of ours that holds colours is repainted
        # here, before the early return, so it follows the theme even while
        # the workbench is not showing.  _theme_repaint_maybe carries the
        # heavier half - the FFT figure, the pop-out mirror, the results
        # grid and the [?] window - behind a signature guard, so the
        # session-tab repaints that also land here cost one tuple compare.
        self._retint_guides()
        self._theme_repaint_maybe()
        self._adopt_new_traces()
        parent = getattr(self, "_switch_parent", None)
        if parent is None or not parent.winfo_exists():
            return
        for w in parent.winfo_children():
            w.destroy()
        uibg, fg = self._pal()[:2]
        muted = self.app._muted_fg()
        accent = self.app._brand()["ac2"]
        # No chrome of its own: the switch is a run of cells ON the tab-strip
        # row, and the only state cue is the accent underline. The row that
        # HOLDS it is a plain tk.Frame nobody had ever coloured, so its Tk
        # default (SystemButtonFace) showed through the 6 px gap beside the
        # switch and the 1 px under it -- the white border round the
        # Plot | Fringe control. Painting the row from the same palette is
        # what makes the switch sit flush.
        parent.configure(bg=uibg, bd=0, highlightthickness=0, relief="flat")
        row = parent.master
        if row is not None and row.winfo_class() == "Frame":
            try:
                row.configure(bg=uibg, bd=0, highlightthickness=0,
                              relief="flat")
            except tk.TclError:
                pass
        self._switch_lbls = {}
        for key, text in (("plot", "Plot"), ("fringe", "Fringe")):
            on = (key == "fringe") == self._active
            cell = tk.Frame(parent, bg=uibg, cursor="hand2", bd=0,
                            highlightthickness=0, relief="flat")
            cell.pack(side="left", padx=(0, 2))
            lab = tk.Label(cell, text=text, bg=uibg,
                           fg=(fg if on else muted),
                           font=self.app._F(0, "bold" if on else "normal"),
                           padx=8, pady=3, bd=0, highlightthickness=0,
                           relief="flat")
            lab.pack(side="top")
            tk.Frame(cell, height=2, bd=0, highlightthickness=0,
                     bg=(accent if on else uibg)).pack(side="top", fill="x")
            for w in (cell, lab):
                w.bind("<Button-1>", lambda e, k=key: self._pick_view(k))
            self._switch_lbls[key] = lab
            self._tip(lab, "Show the %s in the centre. The session tab and "
                           "every plot setting stay exactly as they are."
                      % ("plot" if key == "plot" else "fringe workbench"))
        if self._active:
            # The guide toggle only exists while the workbench is showing:
            # in Plot view it would be a control with nothing to act on.
            # Same cell grammar as the two above, so it takes the theme
            # from the same pass, with the state carried three ways - the
            # accent rule, the weight, and the word itself (rule 25).
            on = bool(self.settings.get("fr_guide_open", True))
            cell = tk.Frame(parent, bg=uibg, cursor="hand2", bd=0,
                            highlightthickness=0, relief="flat")
            cell.pack(side="left", padx=(PAD_X, 2))
            img = getattr(self.app, "_icons", {}).get("hdr::book")
            kw = ({"image": img, "compound": "left"} if img is not None
                  else {})
            lab = tk.Label(cell, text=" Guide", bg=uibg,
                           fg=(fg if on else muted),
                           font=self.app._F(0, "bold" if on else "normal"),
                           padx=8, pady=3, bd=0, highlightthickness=0,
                           relief="flat", **kw)
            lab.image = img            # tk needs the reference held
            lab.pack(side="top")
            tk.Frame(cell, height=2, bd=0, highlightthickness=0,
                     bg=(accent if on else uibg)).pack(side="top", fill="x")
            for w in (cell, lab):
                w.bind("<Button-1>", lambda e: self.toggle_guide())
            self._switch_lbls["guide"] = lab
            self._tip(lab, "Show or hide the workbench guide beside the "
                           "plot. It is the same text the Guide / notes box "
                           "carries under 'Fringe analysis'. The split "
                           "between the two is yours to drag.")

            # The tear-off, in the same cell grammar.  The pop-out was
            # finished and had no way in: no button, no menu entry, no
            # shortcut, nothing.  It reads as a state because it is one --
            # the cell lights up while the second window is open, and a
            # click then raises that window instead of making another.
            try:
                on = bool(self._popout is not None
                          and self._popout.winfo_exists())
            except tk.TclError:
                on = False
            cell = tk.Frame(parent, bg=uibg, cursor="hand2", bd=0,
                            highlightthickness=0, relief="flat")
            cell.pack(side="left", padx=(PAD_X, 2))
            img = getattr(self.app, "_icons", {}).get("copy")
            kw = ({"image": img, "compound": "left"} if img is not None
                  else {})
            lab = tk.Label(cell, text=" Pop out", bg=uibg,
                           fg=(fg if on else muted),
                           font=self.app._F(0, "bold" if on else "normal"),
                           padx=8, pady=3, bd=0, highlightthickness=0,
                           relief="flat", **kw)
            lab.image = img            # tk needs the reference held
            lab.pack(side="top")
            tk.Frame(cell, height=2, bd=0, highlightthickness=0,
                     bg=(accent if on else uibg)).pack(side="top", fill="x")
            for w in (cell, lab):
                w.bind("<Button-1>", lambda e: self.popout())
            self._switch_lbls["popout"] = lab
            self._tip(lab, "Float the FFT view into its own window, for a "
                           "second monitor. It carries the same guide. F11 "
                           "fills the screen, and Escape or the X sends it "
                           "home again.")

    def _adopt_new_traces(self):
        """Pick the trace list up again when the app's results change.

        app.py's workbench touchpoints are the view switch, the Fringe tab
        and the session payload -- and none of them calls on_trace_change,
        so a Run started while the Fringe view was ALREADY showing left the
        workbench on its empty state, "Run a folder to load traces", over a
        window full of freshly loaded traces.  The view switch is repainted
        on that same pass, so this is the honest hook; a signature compare
        keeps it to one tuple for the frequent callers.
        """
        if not self._built:
            return
        sig = tuple(r.get("label") for r in self._records())
        if sig == self._recs_seen:
            return
        self.on_trace_change()

    def _pick_view(self, key):
        if key == "fringe":
            self.activate()
        else:
            self.deactivate()

    # ---- the guide beside the plot ---------------------------------------
    def _guide_body(self, parent, lines, width=38):
        """A read-only guide text box, in the Guide / notes panel's shape.

        One builder for all three places the workbench shows guide copy --
        the pane beside the plot, the pop-out's card and the results
        window's card -- so there is one set of tags and one place a
        rendering rule can be wrong.
        """
        txtf = ttk.Frame(parent)
        txtf.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(txtf)
        sb.pack(side="right", fill="y")
        txt = tk.Text(txtf, width=width, wrap="word", relief="flat", padx=6,
                      pady=4, highlightthickness=0, bd=0,
                      yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)
        # every heading gets a mark, so a jump target is a real place in the
        # text rather than a line number that moves when the copy changes
        heads = []
        for kind, text in lines:
            if kind == "h":
                mark = "sec%d" % len(heads)
                txt.mark_set(mark, "end-1c")
                txt.mark_gravity(mark, "left")
                heads.append((text, mark))
            txt.insert("end", text + "\n",
                       () if kind == "gap" else (kind,))
        txt.configure(state="disabled")
        txt._fr_heads = heads
        self._guide_boxes = getattr(self, "_guide_boxes", [])
        self._guide_boxes.append(txt)
        self._retint_guide(txt)
        return txt

    def _retint_guide(self, txt):
        """Take every colour and font in a guide box from the live palette.

        Called on build AND from `sync_view_switch`, which is the pass the
        theme chain already runs through the tab strip (`_recolor_tk` ->
        `_sync_tabs`).  Without it the box kept the colours it was born in
        and a dark-built pane stayed dark under Standard Light.
        """
        try:
            if not txt.winfo_exists():
                return False
        except tk.TclError:
            return False
        ubg, ufg = self._pal()[:2]
        try:
            txt.configure(background=ubg, foreground=ufg,
                          insertbackground=ufg, font=self.app._F(1),
                          selectbackground=self.app._blendc(
                              ubg, self.app._brand()["ac1"], 0.35),
                          selectforeground=ufg)
            txt.tag_configure("h", font=self.app._F(1, "bold"), spacing1=11,
                              spacing3=3,
                              foreground=self.app._brand()["ac2"])
            txt.tag_configure("s", font=self.app._F(1, "bold"), spacing1=8,
                              spacing3=2, foreground=ufg)
            txt.tag_configure("b", spacing3=4, foreground=ufg)
            txt.tag_configure("i", spacing3=4, lmargin1=10, lmargin2=10,
                              foreground=ufg)
            txt.tag_configure("m", font=self.app._F(0, mono=True),
                              foreground=self.app._code_fg())
        except tk.TclError:
            return False
        return True

    def _retint_guides(self):
        """Repaint every live guide box; forget the ones that have gone."""
        boxes = getattr(self, "_guide_boxes", None)
        if not boxes:
            return
        self._guide_boxes = [t for t in boxes if self._retint_guide(t)]
        lab = getattr(self, "_hint_lbl", None)
        if lab is not None:
            try:
                lab.configure(foreground=(
                    self.app._muted_fg()
                    if lab.cget("text") in (self.HINT_DEFAULT,
                                            self.HINT_EMPTY)
                    else self._pal()[1]))
            except tk.TclError:
                pass

    def _open_guide_pane(self):
        """Build and add the guide pane, once.

        The title row carries the same close affordance the session tabs do
        and a jump list of the page's own headings: the pane is a page, and
        a page you cannot navigate or shut from its own header is a pane
        you stop opening.
        """
        if self._guide_pane is not None:
            return self._guide_pane
        a = self.app
        card = a._card(self._center_pw, grow="both",
                       width=a._em() * GUIDE_DEF_W)
        hdr = a._lf_header(card, "Guide", icon="book")
        x = a._lbl(hdr, text="×", font=a._F(1))
        x.pack(side="left", padx=(PAD_X * 2, 0))
        x.configure(cursor="hand2")
        x.bind("<Button-1>", lambda e: self.toggle_guide(False))
        self._tip(x, "Close the guide. The Guide button on the tab strip "
                     "brings it back at the same width.")
        card.set_title(hdr)

        nav = ttk.Frame(card.body)
        nav.pack(fill="x", pady=(0, 2))
        a._lbl(nav, text="Jump to", width=LBL_W2 + 2).pack(side="left")
        self._guide_jump_v = tk.StringVar(value="")
        self._guide_jump = ttk.Combobox(nav, textvariable=self._guide_jump_v,
                                        state="readonly", width=10)
        self._guide_jump.pack(side="left", fill="x", expand=True)
        self._guide_jump.bind("<<ComboboxSelected>>", self._guide_goto)
        self._tip(self._guide_jump,
                  "Scroll the guide to one of its sections.")

        self._guide_txt = self._guide_body(card.body, guide_text(),
                                           width=GUIDE_MIN_W)
        heads = [h for h, _m in getattr(self._guide_txt, "_fr_heads", [])]
        try:
            self._guide_jump.configure(values=heads)
        except tk.TclError:
            pass
        self._center_pw.add(card, weight=0)
        self._guide_pane = card
        self._restore_guide_scroll()
        return card

    def _guide_goto(self, _e=None):
        """Scroll the pane to the picked heading."""
        txt = getattr(self, "_guide_txt", None)
        if txt is None:
            return
        want = self._guide_jump_v.get()
        for head, mark in getattr(txt, "_fr_heads", []):
            if head == want:
                try:
                    txt.see("%s linestart" % mark)
                    txt.yview("%s linestart" % mark)
                except tk.TclError:
                    pass
                return

    def _remember_guide_scroll(self):
        txt = getattr(self, "_guide_txt", None)
        if txt is None:
            return
        try:
            self._guide_scroll = float(txt.yview()[0])
        except (tk.TclError, ValueError, IndexError):
            pass

    def _restore_guide_scroll(self):
        """Put the reader back where they were, for this run of the program.

        Deliberately in memory and not in settings: where you had scrolled
        to an hour ago in another dataset is not where you want to be on a
        fresh start.
        """
        frac = getattr(self, "_guide_scroll", 0.0)
        txt = getattr(self, "_guide_txt", None)
        if not frac or txt is None:
            return

        def _go():
            try:
                txt.yview_moveto(frac)
            except tk.TclError:
                pass
        try:
            self.app.root.after_idle(_go)
        except (AttributeError, tk.TclError):
            _go()

    def toggle_guide(self, show=None):
        """Show or hide the guide beside the plot.

        The default is "whatever it is not doing now", read off the pane
        itself rather than off the setting: the fitter below can have stood
        the guide down, and a Guide press then has to mean "bring it back",
        not "close the thing that is already closed".

        Hiding remembers the width first, so turning it back on puts the
        split back where it was rather than at the default share.
        """
        self.build()
        showing = self._guide_pane is not None
        want = (not showing) if show is None else bool(show)
        if want:
            snug = not self._guide_fits()
            # asking for prose on a narrow pane gets prose: the reader
            # overrules the fitter, and one more press undoes it
            self._guide_fit = "forced" if snug else "auto"
            self._guide_said = False
            self.settings["fr_guide_open"] = True
            self._open_guide_pane()
            self._restore_guide_sash()
            if snug:
                self._status("the centre is snug, so the guide and the plot "
                             "are sharing it. Press Guide again to give the "
                             "plot the whole width back.")
        else:
            self._remember_guide_sash()
            self._remember_guide_scroll()
            self._drop_guide_pane()
            self.settings["fr_guide_open"] = False
            self._guide_fit = "auto"
            self._guide_said = False
        self.sync_view_switch()
        return want

    def _drop_guide_pane(self):
        """Take the guide out of the split and forget its widgets."""
        if self._guide_pane is None:
            return
        try:
            self._center_pw.forget(self._guide_pane)
        except tk.TclError:
            pass
        txt = getattr(self, "_guide_txt", None)
        boxes = getattr(self, "_guide_boxes", None)
        if boxes and txt is not None:
            self._guide_boxes = [t for t in boxes if t is not txt]
        try:
            self._guide_pane.destroy()
        except tk.TclError:
            pass
        self._guide_pane = None
        self._guide_txt = None

    # ---- how the centre is divided ----------------------------------------
    def _pane_total(self):
        try:
            return int(self._center_pw.winfo_width())
        except (AttributeError, tk.TclError):
            return 0

    def _plot_floor(self):
        """The narrowest FFT canvas worth aiming a click into, in pixels."""
        return int(self.app._em() * PLOT_MIN_W)

    def _guide_floor(self):
        """The width below which the guide's prose stops being prose."""
        return int(self.app._em() * GUIDE_MIN_W)

    def _guide_fits(self, total=None):
        """True when the centre can hold both floors at the same time."""
        total = self._pane_total() if total is None else total
        if total < 120:                 # not laid out yet; assume it fits
            return True
        return total >= self._plot_floor() + self._guide_floor()

    def _guide_w_want(self, total):
        """The guide's width for a pane `total` px wide.

        One place decides it, so the setter and the check that the setter
        worked can never disagree about what "right" was.

        The plot is the protagonist.  Whatever the guide would like, it may
        not push the FFT canvas below PLOT_MIN_W ems -- that clamp is the
        whole of the 160 px bug, where a fixed 276 px of prose took the
        centre first and left the plot half a micron of n*t per pixel.
        Above that floor a width the reader dragged is honoured exactly;
        only a split nobody has ever dragged falls back to the default
        share.  The one case where the guide outranks the plot is "forced":
        the reader pressed Guide on a pane too narrow for both, and asking
        for prose has to give prose.
        """
        em = self.app._em()
        w = int(self.settings.get("fr_guide_w") or 0)
        if w < em * GUIDE_MIN_W:
            w = min(em * GUIDE_DEF_W, int(total * 0.55))
        floor = min(self._guide_floor(), total)
        room = max(0, total - self._plot_floor())
        if self._guide_fit == "forced":
            room = max(room, floor)
        return int(min(max(w, min(floor, room)), room))

    def _remember_guide_sash(self):
        """Record a split the reader chose.

        Bound to the pane's own button release as well as to hide and
        deactivate: fr_guide_w was only ever written on the way out, so a
        drag followed by closing the program was forgotten and the setting
        sat at 0 for good.
        """
        if self._guide_pane is None:
            return
        try:
            w = self._center_pw.winfo_width() - self._center_pw.sashpos(0)
        except (tk.TclError, IndexError):
            return
        # a width at or under the floor is the collapsed state, not a
        # choice; remembering it is how the bug used to persist itself
        if w >= self._guide_floor():
            self.settings["fr_guide_w"] = int(w)

    def _on_pane_configure(self, event=None):
        """Debounced: dragging a window edge fires this per pixel."""
        w = int(getattr(event, "width", 0) or 0) if event is not None else 0
        if w and w == self._pane_w_seen:
            return                      # a height-only change costs nothing
        self._pane_w_seen = w
        if self._fit_after is not None:
            try:
                self.app.root.after_cancel(self._fit_after)
            except (AttributeError, tk.TclError, ValueError):
                pass
            self._fit_after = None
        try:
            self._fit_after = self.app.root.after(80, self._fit_split)
        except (AttributeError, tk.TclError):
            self._fit_split()

    def _fit_split(self):
        """Keep the plot above its floor as the centre changes size.

        Three moves, and only one of them can apply on any one pass: stand
        the guide down when both floors stop fitting, bring it back when
        they fit again, and otherwise take back whatever the guide is
        holding above the plot's floor.  Growing the window still grows the
        PLOT -- the figure holder carries the pane weight -- so this never
        widens the guide behind the reader's back.
        """
        self._fit_after = None
        if not self._built or not self._active:
            return
        total = self._pane_total()
        if total < 120:
            return
        quiet, self._fit_quiet = self._fit_quiet, False
        fits = self._guide_fits(total)
        if (self._guide_pane is not None and not fits
                and self._guide_fit != "forced"):
            self._remember_guide_sash()
            self._remember_guide_scroll()
            self._drop_guide_pane()
            self._guide_fit = "hidden"
            self.sync_view_switch()
            if not self._guide_said and not quiet:
                self._guide_said = True
                self._status("the centre got snug, so the guide stepped "
                             "aside to leave the plot room to work in. "
                             "Widen the window, or press Guide, and it "
                             "comes straight back.")
            return
        if self._guide_pane is None and fits and self._guide_fit == "hidden":
            self._guide_fit = "auto"
            self._guide_said = False
            self._open_guide_pane()
            self.sync_view_switch()
            self._restore_guide_sash()
            if not quiet:
                self._status("room again. the guide sits beside the plot.")
            return
        self._clamp_sash(total)

    def _clamp_sash(self, total=None):
        """Give the plot its floor back, without disturbing a split that is
        already fine."""
        if self._guide_pane is None:
            return
        total = self._pane_total() if total is None else total
        try:
            got = total - self._center_pw.sashpos(0)
        except (tk.TclError, IndexError):
            return
        cap = max(0, total - self._plot_floor())
        if self._guide_fit == "forced":
            cap = max(cap, min(self._guide_floor(), total))
        if got > cap:
            try:
                self._center_pw.sashpos(0, total - cap)
            except (tk.TclError, IndexError):
                pass

    def _restore_guide_sash(self, tries=14):
        """Put the sash back where it was left, and KEEP it there.

        Two failures, one fix.  On the first activation the paned window has
        no width yet, so a single after_idle that finds zero gave up and left
        the guide as a hairline.  And on every re-show the sash was right
        when we set it and wrong a moment later: a re-added ttk pane is
        re-sized by the pane manager on a LATER geometry pass, which handed
        the guide 4 px -- Nhan's "if i click it to hide then show again, it
        doesn't show anymore but is collapsed".  Checking once, however
        carefully, cannot catch that; so this is a short watchdog instead.
        It re-asserts the width whenever the pane is below the width at
        which the text stops being prose, and stops after three consecutive
        clean passes.  Above that floor it never interferes, so dragging the
        split remains entirely the user's.
        """
        if self._guide_pane is None:
            return

        # With nothing remembered the split is OURS to set, not ttk's: left
        # alone it hands the pane the card's requested width, and the first
        # hide then remembers that as if the user had chosen it.
        strict = not int(self.settings.get("fr_guide_w") or 0)

        def _place(n=tries, ok=0):
            if self._guide_pane is None:
                return
            try:
                total = self._center_pw.winfo_width()
                if total >= 120:
                    want = self._guide_w_want(total)
                    floor = min(want, self._guide_floor())
                    got = total - self._center_pw.sashpos(0)
                    # both directions now: too WIDE is the 160 px bug, and
                    # the watchdog is the pass that has to catch it
                    if (got < floor - 4 or got > want + 4
                            or (strict and abs(got - want) > 8)):
                        self._center_pw.sashpos(0, max(0, total - want))
                        ok = 0
                    else:
                        ok += 1
            except (tk.TclError, ValueError, IndexError):
                ok = 0
            if ok >= 3 or n <= 0:
                return
            try:
                self.app.root.after(50, _place, n - 1, ok)
            except (AttributeError, tk.TclError):
                pass
        try:
            self.app.root.after_idle(_place)
        except (AttributeError, tk.TclError):
            _place()

    def is_active(self):
        return self._active

    def toggle(self):
        self.deactivate() if self._active else self.activate()

    def activate(self):
        if self._active:
            return
        self.build()
        try:
            self.app.canvas.get_tk_widget().pack_forget()
        except (AttributeError, tk.TclError):
            pass
        self._center_pw.pack(side="top", fill="both", expand=True)
        self._active = True
        self._restore_guide_sash()
        # The workbench opening on a narrow window is a layout decision, not
        # something that just happened to the reader -- so the first fit
        # says nothing and lets activate's own greeting stand.  A guide that
        # disappears while they watch still explains itself.
        self._fit_quiet = True
        self._sync_view_buttons()
        self._on_pane_configure()     # and re-fit once the pane has a width
        self.settings["fr_view"] = "fringe"
        self.sync_view_switch()
        self.on_trace_change()
        # the mouse grammar is only worth reciting when there is something
        # to aim it at; over an empty plot it reads as a broken promise
        if self._records():
            self._status("workbench open. left-click a peak to notch it, "
                         "right-click to pin the fundamental.")
        else:
            self._status("Run a folder first. The workbench reads fringes "
                         "out of loaded traces.")

    def deactivate(self):
        if not self._active:
            return
        self._remember_guide_sash()
        self._remember_guide_scroll()
        self._set_cursor("")
        try:
            self._center_pw.pack_forget()
        except tk.TclError:
            pass
        try:
            self.app.canvas.get_tk_widget().pack(side="top", fill="both",
                                                 expand=True)
        except (AttributeError, tk.TclError):
            pass
        self._active = False
        self.settings["fr_view"] = "plot"
        self.sync_view_switch()

    # =======================================================================
    # data plumbing
    # =======================================================================
    def _records(self):
        loc = getattr(self, "_local", None)
        if loc and loc.get("recs"):
            app_now = tuple(r.get("label") for r in
                            (getattr(self.app, "results", None) or []))
            if app_now == loc.get("app_sig"):
                return list(loc["recs"])
            # a fresh Run in the main window takes over
            self._local = None
        return list(getattr(self.app, "results", None) or [])

    def _record(self, label=None):
        label = self._label if label is None else label
        for r in self._records():
            if r.get("label") == label:
                return r
        return None

    def on_trace_change(self, label=None):
        """Refresh the trace list and move to `label` (or keep the current
        one).  The app calls this after a Run, a session switch, or a rescan."""
        if not self._built:
            return
        recs = self._records()
        self._recs_seen = tuple(r.get("label") for r in recs)
        # the dropdown walks the experiment's path: compression
        # ascending, then decompression descending (his ordering)
        names = [r["label"] for r in self._ordered_recs()]
        try:
            self._trace_cb.configure(values=names)
        except (AttributeError, tk.TclError):
            pass
        if label is None:
            label = self._label if self._label in names else (names[0]
                                                              if names else None)
        if label != self._label:
            if not self._leave_guard():
                label = self._label
        self._label = label
        self.trace_v.set(label or "")
        self._load_wl_override()
        self._invalidate()
        self._refresh_pressure_nav_ui()

    def _on_trace_pick(self, _e=None):
        want = self.trace_v.get()
        if want == self._label:
            return
        if not self._leave_guard():
            self.trace_v.set(self._label or "")
            return
        self._label = want
        self._load_wl_override()
        self._invalidate()
        self._refresh_pressure_nav_ui()

    def _step_trace(self, d):
        names = [r["label"] for r in self._ordered_recs()]
        if not names:
            return
        try:
            i = names.index(self._label)
        except ValueError:
            i = 0
        j = i + d
        if j < 0 or j >= len(names):
            return                     # his arrows stop at the ends
        self.trace_v.set(names[j])
        self._on_trace_pick()

    def _load_wl_override(self):
        ov = self.settings.get("fr_wl_overrides") or {}
        key = self._dataset_key()
        self._suspend = True
        try:
            if key in ov:
                lo, hi = ov[key]
                self.wlmin_v.set("%g" % lo)
                self.wlmax_v.set("%g" % hi)
                self.wlover_v.set(True)
            else:
                self.wlover_v.set(False)
        finally:
            self._suspend = False

    # ---- per-trace state --------------------------------------------------
    def _tr(self, label=None):
        label = self._label if label is None else label
        if label is None:
            return None
        return self._trace.setdefault(label, {
            "roles": {r: None for r in ROLES},
            "gauss": {r: None for r in ROLES},
            "solved": None})

    def _ch(self, chan, label=None):
        label = self._label if label is None else label
        if label is None:
            return None
        return self._chan.setdefault((label, chan), {
            "default_centers": [], "user_centers": [], "removed": set(),
            "unticked": set(), "user_fundamental": None, "widths": {}})

    def _fund_key(self, chan):
        ch = self._ch(chan)
        if ch is None:
            return None
        if ch["user_fundamental"] is not None:
            return ch["user_fundamental"]
        return ch["default_centers"][0] if ch["default_centers"] else None

    def _active_centers(self, chan, include_unticked=False):
        """Notch centres for `chan`, in micron keys, fundamental first."""
        ch = self._ch(chan)
        if ch is None:
            return []
        keys = []
        for k in list(ch["default_centers"]) + list(ch["user_centers"]):
            if k in ch["removed"] or k in keys:
                continue
            if not include_unticked and k in ch["unticked"]:
                continue
            keys.append(k)
        fund = self._fund_key(chan)
        if fund in keys:
            keys.remove(fund)
            keys.insert(0, fund)
        return keys

    def _width_of(self, chan, kk):
        ch = self._ch(chan)
        return float(ch["widths"].get(kk, _f(self.hw_v, 3.0)))

    # =======================================================================
    # compute
    # =======================================================================
    def _cfg_for(self, rec):
        """A FringeConfig for one trace.

        diamond_pressure_gpa is fed from the trace's OWN parsed pressure
        whenever the Eremets model is picked -- that model is the only one
        that reads it, and a series-wide constant would quietly wrong every
        point but the anchor.
        """
        model = self.diamond_v.get()
        if model not in DIAMOND_MODELS:
            model = "constant"
        pres = 0.0
        if model == "eremets":
            try:
                pres = float(rec.get("pressure_val") or 0.0)
            except (TypeError, ValueError):
                pres = 0.0
        wl_lo, wl_hi = _f(self.wlmin_v, 600.0), _f(self.wlmax_v, 800.0)
        if wl_hi <= wl_lo:
            wl_lo, wl_hi = 600.0, 800.0
        nt_lo, nt_hi = _f(self.ntmin_v, 8.0), _f(self.ntmax_v, 300.0)
        if nt_hi <= nt_lo:
            nt_lo, nt_hi = 8.0, 300.0
        pmax = _f(self.pmax_v, 1e-4)
        if not (0.0 < pmax <= 1.0):
            pmax = 1e-4
        tol = _f(self.tol_v, 0.15)
        hw = _f(self.hw_v, 3.0)
        return FringeConfig(
            diamond_model=model, diamond_pressure_gpa=pres,
            fit_wl_min_nm=wl_lo, fit_wl_max_nm=wl_hi,
            fringe_nt_min_nm=nt_lo * 1000.0, fringe_nt_max_nm=nt_hi * 1000.0,
            fringe_pvalue_max=pmax, nt_agree_tol=(tol if tol > 0 else 0.15),
            notch_halfwidth_um=(hw if hw > 0 else 3.0),
            band_res_floor=bool(self.bandfloor_v.get()),
            lp_cutoff_um=max(_f(self.lp_v["Sample"], 15.0), 1e-3))

    def _sig(self, chan):
        """Cache signature: everything that changes the computed channel."""
        ch = self._ch(chan) or {}
        keys = tuple(self._active_centers(chan))
        return (self.diamond_v.get(), self.wlmin_v.get(), self.wlmax_v.get(),
                self.ntmin_v.get(), self.ntmax_v.get(), self.pmax_v.get(),
                self.tol_v.get(), self.hw_v.get(),
                bool(self.lp_on_v[chan].get()), self.lp_v[chan].get(),
                bool(self.bandfloor_v.get()), keys,
                tuple(round(self._width_of(chan, k), 4) for k in keys),
                ch.get("user_fundamental"))

    def _compute(self, chan):
        """Fast per-channel compute (run_fits=False, ~7 ms), memoised on the
        cache signature so a live drag only pays for what actually changed."""
        rec = self._record()
        if rec is None:
            return None
        key = (self._label, chan, self._sig(chan))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        cfg = self._cfg_for(rec)
        centers = self._active_centers(chan)
        kw = {}
        if centers:
            kw["notch_centers_nm"] = [k * 1000.0 for k in centers]
            kw["notch_halfwidths_um"] = [self._width_of(chan, k)
                                         for k in centers]
        if self.lp_on_v[chan].get():
            kw["lowpass"] = True
            kw["lp_cutoff_um"] = max(_f(self.lp_v[chan], 15.0), 1e-3)
        try:
            fit, _I, nt, defaults = compute_channel_fit(
                rec["wl"], rec[CHAN_KEY[chan]], cfg=cfg,
                label="%s %s" % (rec["label"], chan), run_fits=False, **kw)
        except Exception as exc:                      # a degenerate spectrum
            self._status("%s: %s" % (chan, exc), warn=True)
            return None
        fi = fit.get("fft_info")
        out = {"fit": fit, "nt": nt, "fft_info": fi, "cfg": cfg,
               "defaults": [_ckey(c) for c in defaults]}
        if fi is not None:
            n = len(fi.get("norm_u_detrend", []))
            hann = float(np.sum(np.hanning(n))) if n else 1.0
            out["nt_um"] = np.asarray(fi["freqs"]) / 2000.0
            out["V"] = 2.0 * np.asarray(fi["fft_amp"]) / max(hann, 1e-12)
            ps = fi.get("peaks_sorted")
            out["peaks"] = (np.asarray(ps, dtype=int) if ps is not None
                            else np.array([], dtype=int))
            out["pv"] = fi.get("fisher_pv")
            out["corr"] = fi.get("corroborated_by") or []
            sig_u = fi.get("sig_u_full")
            base = fi.get("notch_baseline")
            out["removed"] = (removed_fraction(sig_u, base)
                              if sig_u is not None and base is not None
                              else 0.0)
        # first sight of this channel seeds the notch list with the detected
        # fundamental, and gives the width migration its centre
        ch = self._ch(chan)
        if ch is not None and out.get("defaults"):
            ch["default_centers"] = list(out["defaults"])
            self._migrate_width(out["defaults"][0])
        self._cache[key] = out
        if len(self._cache) > 64:                     # bounded, cheap to refill
            for k in list(self._cache)[:32]:
                self._cache.pop(k, None)
        return out

    def _invalidate(self):
        self._cache.clear()
        self._request_redraw(now=True)

    # ---- notch width migration -------------------------------------------
    def _migrate_width(self, nt_um):
        """One-time conversion of a legacy FRACTIONAL notch width.

        Before v1.4.9 the width was a fraction of the fringe frequency, so the
        same setting removed a different physical band at every n*t.  A stored
        fractional value is converted ONCE, at the trace's detected centre,
        logged, and the settings marked migrated.
        """
        s = self.settings
        if s.get("fr_width_migrated"):
            return
        frac = None
        for key, scale in (("fr_notch_width_frac", 1.0),
                           ("notch_width", 0.01)):     # the old percent slider
            if key in s:
                try:
                    frac = float(s[key]) * scale
                except (TypeError, ValueError):
                    frac = None
                break
        if frac is None or frac <= 0:
            s["fr_width_migrated"] = True              # nothing legacy stored
            return
        if nt_um is None or not (nt_um > 0):
            return                                     # wait for a centre
        hw = round(frac * float(nt_um), 3)
        s["fr_halfwidth_um"] = hw
        s["fr_width_migrated"] = True
        self._suspend = True
        try:
            self.hw_v.set("%g" % hw)
        finally:
            self._suspend = False
        self._log("Fringe: notch width converted from the old fractional "
                  "convention (%.4g of n*t) to an absolute +/-%.3g um at the "
                  "detected centre %.2f um." % (frac, hw, nt_um))

    # ---- the stack model --------------------------------------------------
    def _index(self, name, P_gpa, wl_nm):
        """Refractive index of a named material at (P, lambda)."""
        if name == fringe_materials.MEDIUM_MANUAL:
            return max(_f(self.medium_n_v, 1.0), 1e-6)
        if name in fringe_materials.MEDIUM_N_OF_P:
            try:
                return fringe_materials.medium_n(name, P_gpa, wl_nm)
            except (ValueError, ZeroDivisionError, FloatingPointError):
                return 1.0
        fn = fringe_materials.AMBIENT_N_FUNC.get(name)
        if fn is not None:
            return float(fn(wl_nm))
        return 1.0

    def _stack_params(self, rec):
        """The dict fringe_stack's line builders take, from the Stack card."""
        cfg = self._cfg_for(rec)
        wl_ref = 0.5 * (cfg.fit_wl_min_nm + cfg.fit_wl_max_nm)
        try:
            P = float(rec.get("pressure_val") or 0.0)
        except (TypeError, ValueError):
            P = 0.0
        med = self.medium_v.get()
        n_med = self._index(med, P, wl_ref)
        n_dia = float(fringe_optics.n_diamond(wl_ref, cfg=cfg))
        try:
            self._nmed_lbl.configure(text="%.4f" % n_med)
            self._nd_lbl.configure(text="%.4f" % n_dia)
        except (AttributeError, tk.TclError):
            pass
        l2_name = self.layer2_v.get() if self.layer2_on_v.get() else med
        n_l2 = (self._index(l2_name, P, wl_ref) if self.layer2_on_v.get()
                else n_med)
        return dict(n_diamond=n_dia,
                    n_layer2=max(n_l2, 1e-6), n_medium=max(n_med, 1e-6),
                    n_sample=max(_f(self.ns_v, 1.6), 1e-6),
                    d1_um=max(_f(self.d1_v, 0.0), 0.0),
                    t_um=max(_f(self.t_v, 0.0), 0.0),
                    d2_um=max(_f(self.d2_v, 0.0), 0.0),
                    layer2_name=(l2_name if self.layer2_on_v.get()
                                 else MEDIUM_LABELS.get(med, med).split(" ")[0]),
                    medium_name=MEDIUM_LABELS.get(med, med).split(" ")[0],
                    sample_name=self.settings.get("fr_sample_name", "sample"),
                    anvil_name="diamond")

    def _schematic(self, p, kind):
        """One-line labelled cell stack, interfaces marked with '|'.

        Matthew draws this across each panel header so the model and the
        picture cannot drift apart in the reader's head.
        """
        A = p.get("anvil_name", "diamond")
        if kind == "sample":
            M, S = p.get("layer2_name", "layer2"), p.get("sample_name",
                                                         "sample")
            return ("lower %s  |  lower %s (d1)  |  %s (t)  |  upper %s (d2)"
                    "  |  upper %s" % (A, M, S, M, A))
        return "lower %s  |  %s (d1+t+d2)  |  upper %s" % (
            A, p.get("medium_name", "medium"), A)

    # =======================================================================
    # drawing
    # =======================================================================
    def _on_model_var(self, *_a):
        if not self._suspend:
            self._request_redraw()

    def _on_detect_var(self, *_a):
        if self._suspend:
            return
        self._cache.clear()
        # detection moved, so a trace that had nothing to seed onto may have
        # peaks now: let the seed speak up again
        self._seed_said.clear()
        self._notify_defringe()
        self._request_redraw()

    def _on_hw_var(self, *_a):
        if not self._suspend:
            self._notify_defringe()

    def _on_suppress(self, *_a):
        self.settings["fr_suppress_report"] = bool(self.suppress_v.get())

    def _notify_defringe(self):
        """Tell the host that a defringe parameter moved.

        These gates and this half-width are not the workbench's private
        business any more (R10): the main plot's df switch, a Run's
        defringed CSVs and Export CSV all read them through
        `defringe_state`, so anything the app cached off them has to go.
        The app's own hook decides whether a redraw is worth it.
        """
        fn = getattr(self.app, "_notch_params_changed", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def _request_redraw(self, now=False):
        if not self._built:
            return
        if self._after is not None:
            try:
                self.app.root.after_cancel(self._after)
            except (tk.TclError, ValueError):
                pass
            self._after = None
        if now:
            self._redraw()
            return
        try:
            self._after = self.app.root.after(DEBOUNCE_MS, self._redraw)
        except tk.TclError:
            self._redraw()

    def _redraw(self):
        self._after = None
        if not self._built:
            return
        face, ink = self._page()
        self.fig.set_facecolor(face)
        for ax in (self.ax_bg, self.ax_s, self.ax_mb, self.ax_ms):
            ax.clear()
            ax.set_facecolor(face)
            for sp in ax.spines.values():
                sp.set_color(ink)
        for tw in self._twins.values():
            try:
                tw.remove()
            except Exception:
                pass
        self._twins = {}
        rec = self._record()
        if rec is None:
            self.ax_bg.text(0.5, 0.5, "Run a folder, or use Session >\n"
                            "Load raw spectra...",
                            transform=self.ax_bg.transAxes, ha="center",
                            va="center", color=ink, fontsize=10)
            self.ax_s.set_axis_off()
            for ax in (self.ax_mb, self.ax_ms):
                ax.text(0.5, 0.5, "no measured data",
                        transform=ax.transAxes, ha="center",
                        va="center", color=self.app._muted_fg(),
                        fontsize=9)
            self._layout_grid()
            self._safe_draw()
            return
        self.ax_s.set_axis_on()
        p = self._stack_params(rec)
        # unlocked, the Total box mirrors d1+t+d2 (his greyed Total)
        if not self.lock_v.get():
            try:
                self.total_v.set("%.4g" % (p["d1_um"] + p["t_um"]
                                           + p["d2_um"]))
            except tk.TclError:
                pass
        upper = self._x_upper(p)
        # the opening guess, before the panels draw: _x_upper has already
        # computed both channels, so the seed reads warm peaks and the glyphs
        # appear in this same pass
        self._seed_roles(p, upper)
        self._artists = {"roles": {}, "lp": {}, "hover": {}}
        self._nt_labels = {}          # rebuilt with the axes, like the rings
        self._schem_labels = {}
        self._hover_key = None
        for chan in CHANNELS:
            self._draw_panel(chan, rec, p, upper)
        for chan in CHANNELS:
            self._draw_measured(chan, rec)
        self._refresh_reports()
        self._refresh_notch_rows()
        self._refresh_roles()
        self._refresh_state_indicators()
        self._layout_grid()
        self._fit_labels()
        self._safe_draw()
        self._persist()
        if self._popout is not None:
            self._mirror_popout()

    def _safe_draw(self):
        try:
            self.canvas.draw_idle()
        except Exception:
            pass

    def _fit_labels(self, canvas=None):
        """Turn any stagger label that overruns its axes around.

        Each boxed label is anchored on its own n*t and grows away from it,
        and the side it grows to is picked from which half of the span the
        line sits in.  That is right until the axes get narrow, where a
        line just short of the middle puts its whole box past the right
        spine.  Measuring after the layout costs one text extent per label
        and settles it exactly; a flip that would only move the overrun to
        the other edge is not made.
        """
        canvas = self.canvas if canvas is None else canvas
        try:
            rend = canvas.get_renderer()
        except Exception:
            return False
        moved = False
        for chan, labs in self._nt_labels.items():
            ax = self._axes.get(chan)
            if ax is None:
                continue
            box = ax.get_window_extent()
            for t in labs:
                try:
                    tb = t.get_window_extent(rend)
                except Exception:
                    continue
                pad = 8.0                  # the rounded box drawn round it
                w = (tb.x1 - tb.x0) + 2 * pad
                if t.get_ha() == "left" and tb.x1 + pad > box.x1:
                    if tb.x0 + pad - w >= box.x0:
                        t.set_ha("right")
                        moved = True
                elif t.get_ha() == "right" and tb.x0 - pad < box.x0:
                    if tb.x1 - pad + w <= box.x1:
                        t.set_ha("left")
                        moved = True
        # The cell schematic across each panel header starts at its axes'
        # left edge and reads rightwards, so it used to run off the end of
        # the figure and cut a word in half ("Argon (d1+t+d2").  Its room
        # is its own COLUMN, not the figure: past the spectra panel's tick
        # labels it collides with them (R14).
        try:
            fw = float(canvas.figure.get_window_extent().width)
        except Exception:
            fw = 0.0
        for chan, t in self._schem_labels.items():
            if fw <= 0:
                break
            if self._fit_schem(chan, t, rend, fw):
                moved = True
            if self._fit_head(chan, getattr(t, "_fr_head", None), rend, fw):
                moved = True
        if self._thin_x_ticks(rend):
            moved = True
        return moved

    TICK_GAP_PX = 5.0            # air a tick label keeps from its neighbour

    def _thin_x_ticks(self, rend):
        """Hide x tick labels until the numbers stop touching.

        A panel is a quarter of the canvas wide and the wavenumber scale
        wants five digits per label, so at 1400 px all four panels ran
        their numbers together into one grey band; the wavelength scale
        along the top is 1/x, so its labels bunch at one end whatever the
        spacing.  Both are settled the same way: sweep left to right and
        keep a label only when it clears the last one kept.  Measured, so
        a wide canvas keeps every label it always had.  The ticks stay;
        only the type goes.
        """
        moved = False
        axes = list((self._axes or {}).values())
        axes += list((getattr(self, "_maxes", None) or {}).values())
        axes += [x for k, x in (getattr(self, "_twins", None) or {}).items()
                 if str(k).startswith("sec_")]
        for ax in axes:
            try:
                labs = [t for t in ax.get_xticklabels() if t.get_text()]
            except Exception:
                continue
            if len(labs) < 3:
                continue
            spans = []
            for t in labs:
                try:
                    bb = t.get_window_extent(rend)
                except Exception:
                    continue
                spans.append((float(bb.x0), float(bb.x1), t))
            spans.sort()
            keep = self._tick_keep(spans)
            for i, (_x0, _x1, t) in enumerate(spans):
                on = i in keep
                t.set_visible(on)
                if not on:
                    moved = True
        return moved

    def _tick_keep(self, spans):
        """Which of these tick labels stay: the widest EVEN stride that
        clears, so the scale still reads as a scale.  A 1/x axis can bunch
        at one end past any stride; that falls back to a left-to-right
        sweep, which always clears."""
        n = len(spans)
        gap = self.TICK_GAP_PX

        def clear(idx):
            edge = None
            for i in idx:
                x0, x1, _t = spans[i]
                if edge is not None and x0 < edge + gap:
                    return False
                edge = x1
            return True
        for k in range(1, n + 1):
            idx = list(range(0, n, k))
            if clear(idx):
                return set(idx)
        keep, edge = set(), None
        for i in range(n):
            x0, x1, _t = spans[i]
            if edge is None or x0 >= edge + gap:
                keep.add(i)
                edge = x1
        return keep

    def _fit_head(self, chan, t, rend, fw):
        """Keep the panel's name line inside its own column.

        "Background   n*t = 27.59 um" is 193 px of bold type; on a
        1400 px window the FFT column is 155 px wide, so the line used to
        run over the spectra panel's tick labels beside it.  It shrinks,
        down to HEAD_PT_MIN.
        """
        if t is None:
            return False
        t.set_fontsize(HEAD_PT)
        try:
            bb = t.get_window_extent(rend)
        except Exception:
            return False
        room = self._schem_limit(chan, rend, fw) - float(bb.x0)
        want = float(bb.x1 - bb.x0)
        if room <= 0 or want <= 0 or want <= room:
            return False
        t.set_fontsize(max(HEAD_PT_MIN, HEAD_PT * room / want))
        return True

    def _schem_limit(self, chan, rend, fw):
        """How far right the FFT panel's header may reach, in figure px.

        Up to the spectra panel beside it, minus that panel's own tick
        labels and a finger of air.  With no spectra panel to the right
        the figure edge is the limit, as it always was.
        """
        mx = (getattr(self, "_maxes", None) or {}).get(chan)
        if mx is None:
            return fw - 3.0
        try:
            return float(mx.get_tightbbox(rend).x0) - 6.0
        except Exception:
            try:
                return float(mx.get_position().x0) * fw - 6.0
            except Exception:
                return fw - 3.0

    @staticmethod
    def _schem_two_lines(full):
        """Break the cell stack at the interface nearest its middle."""
        parts = full.split("|")
        if len(parts) < 2:
            return None
        half, run, cut, best = len(full) / 2.0, 0, 1, None
        for i, seg in enumerate(parts[:-1]):
            run += len(seg) + 1
            d = abs(run - half)
            if best is None or d < best:
                best, cut = d, i + 1
        # the interface the break lands on keeps its bar, at the end of
        # the first line, so the stack still reads as a stack
        return ("|".join(parts[:cut]).rstrip() + "  |\n"
                + "|".join(parts[cut:]).lstrip())

    def _fit_schem(self, chan, t, rend, fw):
        """Fit one cell-schematic header into its column.

        A small shrink keeps it on one line.  Past that the stack is
        broken at the interface nearest its middle and read over two
        lines at full size, because 5 pt of grey text is not reading
        matter.  Both forms carry every word Matthew writes.
        """
        full = getattr(t, "_fr_full", None)
        if full is None:
            full = t.get_text()
            t._fr_full = full
        t.set_text(full)
        t.set_fontsize(SCHEM_PT)

        def span():
            try:
                bb = t.get_window_extent(rend)
                return float(bb.x0), float(bb.x1 - bb.x0)
            except Exception:
                return 0.0, 0.0
        x0, want = span()
        room = self._schem_limit(chan, rend, fw) - x0
        if want <= room or want <= 0 or room <= 0:
            return False
        if room / want >= SCHEM_WRAP_AT:
            t.set_fontsize(SCHEM_PT * room / want)
            return True
        two = self._schem_two_lines(full)
        if two is None:
            t.set_fontsize(max(SCHEM_PT_MIN, SCHEM_PT * room / want))
            return True
        t.set_text(two)
        _x, want = span()
        if 0.0 < room < want:
            t.set_fontsize(max(SCHEM_PT_MIN, SCHEM_PT * room / want))
        return True

    def _layout_grid(self, fig=None):
        """Place the 2x2 grid from measured furniture, in place of
        tight_layout (see GRID_PT for why that cannot do this figure).

        The margins are pixel amounts; matplotlib wants `wspace` and
        `hspace` as fractions of the MEAN cell size, so the gap asked for
        in pixels is inverted back into those two numbers here.  For a
        2 x 2 grid  gap = space * (extent - gap) / 2, which gives
        space = 2 * gap / (extent - gap) whatever the width ratios are.
        """
        fig = self.fig if fig is None else fig
        try:
            ext = fig.get_window_extent()
            W, H = float(ext.width), float(ext.height)
            k = float(fig.dpi) / 72.0
        except Exception:
            return
        if W < 40.0 or H < 40.0:
            return
        m = dict((n, v * k) for n, v in GRID_PT.items())
        cap = 1.0 - GRID_MIN_AXES
        hor = m["left"] + m["right"] + m["wgap"]
        if hor > cap * W:
            s = cap * W / hor
            for n in ("left", "right", "wgap"):
                m[n] *= s
        ver = m["top"] + m["bottom"] + m["hgap"]
        if ver > cap * H:
            s = cap * H / ver
            for n in ("top", "bottom", "hgap"):
                m[n] *= s
        left = m["left"] / W
        right = 1.0 - m["right"] / W
        bottom = m["bottom"] / H
        top = 1.0 - m["top"] / H
        gw, gh = m["wgap"] / W, m["hgap"] / H
        # A GridSpec built with its own wspace / hspace OVERRIDES the
        # figure's, so those two are handed back before the figure is
        # asked to place the grid.
        for ax in fig.axes:
            ss = ax.get_subplotspec() if hasattr(ax, "get_subplotspec") \
                else None
            gs = ss.get_gridspec() if ss is not None else None
            if gs is None:
                continue
            for name in ("left", "right", "bottom", "top", "wspace",
                         "hspace"):
                if getattr(gs, name, None) is not None:
                    setattr(gs, name, None)
        try:
            fig.subplots_adjust(
                left=left, right=right, bottom=bottom, top=top,
                wspace=2.0 * gw / max(right - left - gw, 1e-6),
                hspace=2.0 * gh / max(top - bottom - gh, 1e-6))
        except (ValueError, AttributeError):
            pass

    @staticmethod
    def _tight(fig, **kw):
        """fig.tight_layout, with matplotlib's own complaint kept quiet.

        A pane dragged very narrow, or a results grid on a small screen,
        makes tight_layout give up and say so on stdout once per redraw --
        console noise on a program that is working fine.  The filter is
        around this one call and matches only that message, so a genuine
        warning from anywhere else in the draw still gets through.
        """
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore",
                                        message=".*[Tt]ight.?layout.*",
                                        category=UserWarning)
                fig.tight_layout(**kw)
        except Exception:
            pass

    def _persist(self):
        """Write the card's live values back into the "# b keys" settings.

        Called from the debounced redraw rather than from every trace_add, so
        a spinbox held down costs one write, not thirty.  The app writes the
        settings file itself on close.
        """
        s = self.settings
        s["fr_medium"] = self.medium_v.get()
        s["fr_layer2_on"] = bool(self.layer2_on_v.get())
        s["fr_layer2"] = self.layer2_v.get()
        s["fr_diamond_model"] = self.diamond_v.get()
        s["fr_medium_n"] = _f(self.medium_n_v, 1.2)
        s["fr_n_sample"] = _f(self.ns_v, 1.5)
        s["fr_d1_um"] = _f(self.d1_v, 0.0)
        s["fr_t_um"] = _f(self.t_v, 20.0)
        s["fr_d2_um"] = _f(self.d2_v, 0.0)
        s["fr_lock_total"] = bool(self.lock_v.get())
        s["fr_fine_step"] = bool(self.fine_v.get())
        s["fr_wl_min"] = _f(self.wlmin_v, 600.0)
        s["fr_wl_max"] = _f(self.wlmax_v, 800.0)
        s["fr_nt_min_um"] = _f(self.ntmin_v, 8.0)
        s["fr_nt_max_um"] = _f(self.ntmax_v, 300.0)
        s["fr_pvalue_max"] = _f(self.pmax_v, 1e-4)
        s["fr_agree_tol"] = _f(self.tol_v, 0.15)
        s["fr_halfwidth_um"] = _f(self.hw_v, 3.0)
        s["fr_lp_bg_on"] = bool(self.lp_on_v["Background"].get())
        s["fr_lp_bg_um"] = _f(self.lp_v["Background"], 15.0)
        s["fr_lp_s_on"] = bool(self.lp_on_v["Sample"].get())
        s["fr_lp_s_um"] = _f(self.lp_v["Sample"], 15.0)
        s["fr_fit_mode"] = self.fitmode_v.get()

    def _x_upper(self, p):
        """Upper x limit shared by both panels, so a peak at a given n*t sits
        at the same screen x in Background and Sample.

        Reaches the 2nd Airy harmonic of the strong model modes and at least
        2x the measured fundamental; never past where the measured curve
        actually ends.
        """
        lines = (fringe_stack.stack_lines(p, kind="sample")
                 + fringe_stack.stack_lines(p, kind="medium"))
        mags = [ln["mag"] for ln in lines] or [1.0]
        mmax = max(mags)
        strong = [ln["nt"] for ln in lines if ln["mag"] > 0.1 * mmax] or [1.0]
        reach = 0.0
        nyq = None
        for chan in CHANNELS:
            c = self._compute(chan)
            if not c or "nt_um" not in c:
                continue
            if c.get("nt"):
                reach = max(reach, 2.0 * float(c["nt"]) / 1000.0 * 1.08)
            arr = c["nt_um"]
            if len(arr):
                nyq = float(arr[-1]) if nyq is None else min(nyq,
                                                             float(arr[-1]))
        upper = max(80.0, 2.0 * max(strong) * 1.08, reach)
        step = upper / 8.0
        pw = 10 ** np.floor(np.log10(step)) if step > 0 else 1.0
        nice = next(s for s in (1, 2, 5, 10) if s * pw >= step)
        upper = float(np.ceil(upper / (nice * pw))) * (nice * pw)
        if nyq and np.isfinite(nyq) and nyq > 0:
            upper = min(upper, nyq)
        return float(max(upper, 1.0))

    def _draw_panel(self, chan, rec, p, upper):
        ax = self._axes[chan]
        face, ink = self._page()
        c = self._compute(chan)
        kind = "sample" if chan == "Sample" else "medium"
        lines = fringe_stack.stack_lines(p, kind=kind)

        # measured curve, on the physical V axis
        ref = None
        if c and "V" in c:
            ax.plot(c["nt_um"], c["V"], color=ink, lw=1.0, alpha=0.9,
                    label="measured (%.0f-%.0f nm)" % (c["cfg"].fit_wl_min_nm,
                                                       c["cfg"].fit_wl_max_nm))
            sel = (np.isfinite(c["V"]) & (c["nt_um"] >= 3.0)
                   & (c["nt_um"] <= upper))
            if sel.any():
                ref = float(np.nanmax(c["V"][sel]))
        # tiered view: his crimson/blue post-fit residual FFTs ride on
        # the forward panels (they pair with the right-column tiers)
        if self.tiers_v.get():
            for _rx, _ry, _rc, _rn in self._fine_residual_ffts(chan):
                ax.plot(_rx, _ry, color=_rc, lw=0.8, alpha=0.85,
                        marker=".", ms=3, zorder=3, label=_rn)
        top = max([ln["mag"] for ln in lines] + ([ref] if ref else []) + [1e-9])

        # model stems + staggered boxed labels + m=2,3 Airy harmonics.
        # Four stagger levels, not three: with d1 == d2 the six sample lines
        # collapse onto neighbouring paths and three levels let two boxes
        # overlap (seen on the first screenshot gate).
        xtr = ax.get_xaxis_transform()
        y_levels = (0.92, 0.71, 0.50, 0.29)
        order = sorted(range(len(lines)), key=lambda i: lines[i]["nt"])
        level = {i: y_levels[k % len(y_levels)] for k, i in enumerate(order)}
        for i, ln in enumerate(lines):
            col, ls = self._stem_style(i)
            nt, h = ln["nt"], ln["mag"]
            ax.vlines(nt, 0.0, h, color=col, lw=2.2, ls=ls, zorder=0.5)
            ax.plot([nt], [h], "o", ms=5, color=col, zorder=0.6)
            for m in (2, 3):
                pos = m * nt
                if pos <= 1e-9 or pos > upper:
                    continue
                ax.vlines(pos, 0.0, h * (0.5 * h) ** (m - 1), color=col,
                          lw=1.3, ls="--", alpha=0.9, zorder=0.4)
            if not ln["formula"]:
                continue
            lx = min(max(nt, 0.02 * upper), 0.98 * upper)
            lab = ax.text(lx, level[i], "%s\n= %.1f um"
                          % (ln["formula"], nt),
                          transform=xtr, fontsize=7.5, color=col,
                          ha=("left" if nt < 0.5 * upper else "right"),
                          va="top", clip_on=False, zorder=7,
                          bbox=dict(boxstyle="round,pad=0.3", fc="none",
                                    ec=col, lw=1.0))
            # kept so _fit_labels can turn the ones that overrun around
            self._nt_labels.setdefault(chan, []).append(lab)

        # notch bands
        band = self.app._blendc(ink, face, 0.72)
        for kk in self._active_centers(chan):
            hw = self._width_of(chan, kk)
            ax.axvspan(kk - hw, kk + hw, color=band, alpha=0.35, zorder=0.2,
                       lw=0)

        # peak markers, provenance in the shape.  Their screen positions are
        # kept so hover can answer "is there a peak under the pointer?"
        # without a compute per mouse move (see _hover_peak).
        drawn_pts = []
        if c and "peaks" in c and len(c["peaks"]):
            ch = self._ch(chan)
            fund = self._fund_key(chan)
            act = set(self._active_centers(chan))
            for idx in c["peaks"]:
                x = float(c["nt_um"][idx])
                if x > upper:
                    continue
                kk = round(x, 2)
                y = float(c["V"][idx])
                drawn_pts.append((x, y))
                mk = ("^" if kk == fund else
                      "D" if kk in ch["user_centers"] else "o")
                filled = kk in act
                ax.plot([x], [y], marker=mk, ms=7, ls="none",
                        color=self.app._brand()["ac1"],
                        markerfacecolor=(self.app._brand()["ac1"] if filled
                                         else "none"),
                        markeredgewidth=1.2, zorder=6)
        self._peak_xy = getattr(self, "_peak_xy", {})
        self._peak_xy[chan] = drawn_pts

        # draggable low-pass line.  "drag" is spelled out on the label: the
        # line looked like a plotted limit, and nothing said it was a handle.
        if self.lp_on_v[chan].get():
            lp = _f(self.lp_v[chan], 15.0)
            self._artists["lp"][chan] = ax.axvline(
                lp, color=self.app._brand()["ac3"], lw=1.4, ls="--",
                alpha=0.95, zorder=5)
            ax.text(lp, 0.055, " low-pass (drag)", transform=xtr, fontsize=7,
                    color=self.app._brand()["ac3"], ha="left", va="bottom")

        # the hover ring: one per panel, parked invisible until the pointer
        # is within reach of a peak (see _hover_mark)
        hv, = ax.plot([], [], marker="o", ms=15, ls="none",
                      markerfacecolor="none",
                      markeredgecolor=self.app._brand()["ac3"],
                      markeredgewidth=2.0, zorder=9, visible=False,
                      clip_on=False)
        self._artists.setdefault("hover", {})[chan] = hv

        # role glyphs
        tr = self._tr()
        for role in ROLES:
            if ROLE_PANEL[role] != chan or tr is None:
                continue
            rv = tr["roles"].get(role)
            if not rv:
                continue
            mk, fill = ROLE_MARK[role]
            ln, = ax.plot([float(rv["nt_um"])], [ROLE_Y[role]], marker=mk,
                          ms=13, ls="none", transform=xtr,
                          color=self.app._brand()["ac2"], fillstyle=fill,
                          markerfacecolor=self.app._brand()["ac2"],
                          markeredgewidth=1.4, clip_on=False, zorder=8)
            self._artists["roles"][role] = ln

        ax.set_xlim(0, upper)
        ax.set_ylim(0.0, top * 1.30)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8, steps=[1, 2, 5, 10]))
        ax.xaxis.set_minor_locator(AutoMinorLocator(4))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: "%g" % v))
        yf = ScalarFormatter(useMathText=True)
        yf.set_powerlimits((-2, 3))
        ax.yaxis.set_major_formatter(yf)
        off = ax.yaxis.get_offset_text()
        off.set_ha("right")
        off.set_va("bottom")
        off.set_position((1.0, 1.0))
        ax.set_xlabel(r"Optical path  $n{\cdot}t$  ($\mu$m)", fontsize=9,
                      color=ink)
        ax.set_ylabel(r"Fringe amplitude $V_m$", fontsize=9, color=ink)
        ax.tick_params(labelsize=9, colors=ink)

        # removed-fraction twin axis
        tw = ax.twinx()
        self._twins[chan] = tw
        tw.set_ylim(0.0, 1.0)
        tw.set_ylabel("removed fraction", fontsize=8, color=ink)
        tw.tick_params(labelsize=8, colors=ink)
        tw.set_facecolor("none")
        for sp in tw.spines.values():
            sp.set_color(ink)
        if c and "removed" in c:
            frac = float(c["removed"])
            tw.axhline(frac, color=self.app._brand()["ac2"], lw=1.0, ls=":",
                       alpha=0.9)
            tw.text(0.995, frac, " %.1f%% removed " % (100.0 * frac),
                    transform=tw.get_yaxis_transform(), fontsize=7,
                    color=self.app._brand()["ac2"], ha="right", va="bottom")

        # two-line header: schematic above, channel name below
        from matplotlib.transforms import offset_copy
        ch_tr = offset_copy(ax.transAxes, fig=self.fig, x=0, y=2,
                            units="points")
        sc_tr = offset_copy(ax.transAxes, fig=self.fig, x=0, y=14,
                            units="points")
        head = chan
        if c and c.get("nt"):
            head = "%s   n*t = %.2f um" % (chan, float(c["nt"]) / 1000.0)
        elif c is not None:
            head = "%s   no fringe" % chan
        head_t = ax.text(0.0, 1.0, head, transform=ch_tr, va="bottom",
                         ha="left", fontsize=HEAD_PT, fontweight="bold",
                         color=ink, clip_on=False)
        schem_t = ax.text(
            0.0, 1.0, self._schematic(p, kind), transform=sc_tr,
            va="bottom", ha="left", fontsize=SCHEM_PT,
            color=self.app._muted_fg(), clip_on=False)
        # the two travel together: _fit_labels fits both to this panel's
        # own column, and one registry is one thing for _view to swap
        schem_t._fr_head = head_t
        self._schem_labels[chan] = schem_t

    # ---- the measured column (his Row-0 panels) ---------------------------
    def _draw_measured(self, chan, rec):
        """One measured-spectrum panel: the raw transmitted intensity with
        the FFT-filtered clean curve over it, at true intensity -- his
        Row-0 flat view.  Show tiered stacks the diagnostic tiers
        instead: the cosine-fit residual, the clean curve, each fitted
        window's defringed curve, and raw on top, offset apart."""
        ax = self._maxes[chan]
        face, ink = self._page()
        muted = self.app._muted_fg()
        c = self._compute(chan)
        if not c:
            ax.text(0.5, 0.5, "no measured data", transform=ax.transAxes,
                    ha="center", va="center", color=muted, fontsize=9)
            ax.set_title(chan, fontsize=9, color=ink)
            ax.tick_params(labelleft=False, labelbottom=False, colors=ink)
            return
        wl = np.asarray(rec["wl"], float)
        raw = np.asarray(rec[CHAN_KEY[chan]], float)
        wn_cm = 1e7 / np.maximum(wl, 1e-9)
        fi = c.get("fft_info") or {}
        ic = fi.get("I_notch_1x")
        if ic is not None:
            ic = np.asarray(ic, float)
            if not np.any(np.isfinite(ic)):
                ic = None
        # the clean curve only means something while SOMETHING is being
        # filtered -- at least one live notch, or this channel's low-pass
        have_mask = (bool(self._active_centers(chan))
                     or bool(self.lp_on_v[chan].get()))
        show_clean = (ic is not None and have_mask
                      and not self.hideclean_v.get())
        fin = np.isfinite(raw)
        ptp = float(np.ptp(raw[fin])) if fin.any() else 1.0
        ptp = ptp or 1.0
        inner = 0.10 * ptp
        outer = 0.35 * ptp
        if not self.tiers_v.get():
            # flat view: raw then the clean curve ON TOP, true intensity
            ax.plot(wn_cm, raw, color=ink, lw=0.5, label="raw", zorder=4)
            if show_clean:
                ax.plot(wn_cm, ic, color="#FF2020", lw=0.6,
                        label="FFT filtered", zorder=5)
        else:
            y = 0.0
            nt = fi.get("notch_refined_nt") or c.get("nt")
            amp = fi.get("notch_refined_amp")
            phase = fi.get("notch_refined_phase") or 0.0
            if nt and amp:
                sine = (float(amp) * np.cos(4.0 * np.pi * float(nt) / wl
                                            + float(phase)))
                ax.plot(wn_cm, raw - sine + y, color="tab:blue", lw=0.4,
                        label="$\\Delta$(raw, cosine fit)  "
                              "n*t=%.1f um" % (float(nt) / 1000.0))
                y += inner
            if show_clean:
                ax.plot(wn_cm, ic + y, color="#FF2020", lw=0.5,
                        label="FFT filtered")
                y += inner
            fit = self._fits.get((self._label, chan)) or {}
            cn = (fit.get("models") or {}).get("constant_n") or {}
            drew_tier = False
            for win, alpha in (("fine", 1.0), ("narrow", 0.55),
                               ("wide", 0.4), ("full", 0.25)):
                d = cn.get(win)
                if not d or d.get("n_mean") is None:
                    continue
                # the window's defringed curve: divide the fitted fringe
                # factor 1 + V cos(4 pi nt / lambda + phi0) out of raw.
                # First-order in his airy_factor -- noted in the guide.
                V = fringe_optics.fresnel_V(float(d["n_mean"]), wl)
                phi = (4.0 * np.pi * float(d["nt_um"]) * 1000.0 / wl
                       + float(d.get("phi0") or 0.0))
                den = np.clip(1.0 + V * np.cos(phi), 0.1, None)
                y += outer if not drew_tier else inner
                drew_tier = True
                ax.plot(wn_cm, raw / den + y, color="darkred", lw=0.4,
                        alpha=alpha, label="ConstantN %s  n*t=%.1f um"
                        % (win, float(d["nt_um"])))
            y += outer
            ax.plot(wn_cm, raw + y, color=ink, lw=0.3, label="raw")
        # ---- axis furniture: his Row-0 grammar --------------------------
        if fin.any():
            ax.set_xlim(float(np.nanmin(wn_cm[fin])),
                        float(np.nanmax(wn_cm[fin])))
        ax.tick_params(labelsize=7, colors=ink)
        ax.set_xlabel("Wavenumber (cm$^{-1}$)", fontsize=8, color=ink)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p:
                                                   "%g" % v))
        try:
            sec = ax.secondary_xaxis(
                "top", functions=(lambda v: 1e7 / np.maximum(v, 1e-9),
                                  lambda v: 1e7 / np.maximum(v, 1e-9)))
            sec.set_xlabel("Wavelength (nm)", fontsize=7, color=ink)
            sec.tick_params(labelsize=6, colors=ink)
            for sp in sec.spines.values():
                sp.set_color(ink)
            self._twins["sec_" + chan] = sec
        except Exception:
            pass
        # mantissa ticks + a x10^n header, his hand-rolled offset text
        ylo, yhi = ax.get_ylim()
        ymax = max(abs(ylo), abs(yhi))
        exp = int(np.floor(np.log10(ymax))) if ymax > 0 else 0
        sc = 10.0 ** exp
        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda v, _p, _s=sc: "%g" % (v / _s)))
        if exp:
            ax.text(0.005, 0.97, "$\\times 10^{%d}$" % exp,
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=7, color=ink, clip_on=False)
        title = chan
        n_fit = self._fitted_n(chan)
        if n_fit is not None:
            title = "%s   fit n = %.4f" % (chan, n_fit)
        ax.set_title(title, fontsize=9, color=ink, pad=16)
        try:
            lg = ax.legend(fontsize=6, loc="upper right", framealpha=0.7)
            if lg is not None:
                lg.set_zorder(100)
                lg.get_frame().set_facecolor(face)
                lg.get_frame().set_edgecolor(muted)
                for t in lg.get_texts():
                    t.set_color(ink)
        except Exception:
            pass

    # ---- readouts ---------------------------------------------------------
    def _refresh_reports(self):
        rep = getattr(self, "_rep", None) or {}
        if rep:
            c = self._compute("Sample") or self._compute("Background")
            try:
                if not c:
                    for lab in rep.values():
                        lab.configure(text="–")
                else:
                    nt = c.get("nt")
                    rep["nt"].configure(
                        text=("%.3f um" % (float(nt) / 1000.0))
                        if nt else "no fringe")
                    pv = c.get("pv")
                    rep["p"].configure(
                        text=("%.2g" % pv) if pv is not None
                        else "–")
                    corr = c.get("corr") or []
                    rep["corr"].configure(
                        text=(" + ".join(corr) if corr
                              else "not corroborated"))
            except tk.TclError:
                self._rep = {}
        self._fill_pred_lines()

    def _refresh_roles(self):
        # R7: the role paths live on the chart itself (glyphs and the
        # panel legend), as in his GUI -- only the ordering check stays
        self._check_ordering()

    def _check_ordering(self):
        """A dropped glyph lands where it was dropped; if that ordering cannot
        be inverted the workbench says so rather than silently clamping."""
        tr = self._tr()
        if tr is None:
            return
        r = tr["roles"]
        if not (r.get("sample") and r.get("sampledia")):
            return
        A, C = r["sample"]["nt_um"], r["sampledia"]["nt_um"]
        if C < A:
            self._status("sample-diamond sits left of the sample: the "
                         "layer-2 thickness would be negative. Solve will "
                         "floor it.", warn=True, log=False)

    # ---- the opening guess: role glyphs seeded onto the peaks -------------
    def _pred_paths(self, p):
        """Where the stack model expects the three roles, in n*t micron.

        The very three paths solve_paths inverts, read straight off the
        forward lines the panels already draw as stems: A = n_s t (the '23'
        pair), C = n_layer2 (d1+d2) + n_s t (the whole-cell '14' pair) and
        iii = n_medium L (the bare etalon).  An empty dict means the model
        could not be built, and the seed falls back on raw peak strength.
        """
        try:
            sample = fringe_stack.stack_lines(p, kind="sample")
            medium = fringe_stack.stack_lines(p, kind="medium")
        except (KeyError, ValueError, ZeroDivisionError, FloatingPointError):
            return {}
        out = {}
        for ln in sample:
            if "23" in ln["ids"]:
                out["sample"] = float(ln["nt"])
            if "14" in ln["ids"]:
                out["sampledia"] = float(ln["nt"])
        if medium:
            out["mediumdia"] = float(medium[0]["nt"])
        return {k: v for k, v in out.items() if np.isfinite(v) and v > 0.0}

    def _seed_cands(self, chan, upper):
        """Peaks a seed may land on: strongest first, on screen, positive."""
        c = self._compute(chan)
        if not c or "peaks" not in c or not len(c["peaks"]):
            return []
        out = []
        for idx in c["peaks"]:
            x = float(c["nt_um"][idx])
            if not np.isfinite(x) or x <= 0.0 or x > upper:
                continue
            out.append(x)
            if len(out) >= SEED_MAX_CAND:
                break
        return out

    @staticmethod
    def _seed_tol(pred):
        return max(SEED_TOL_UM, SEED_TOL_FRAC * float(pred))

    def _seed_near(self, cands, pred):
        """The peak closest to `pred`, or None if none is close enough."""
        best = None
        tol = self._seed_tol(pred)
        for x in cands:
            d = abs(x - pred)
            if d <= tol and (best is None or d < best[0]):
                best = (d, x)
        return best[1] if best else None

    def _seed_pair(self, cands, pa, pc):
        """The best ORDERED pair of peaks for the two Sample roles.

        Scored jointly, not one role at a time: when the Stack's t is
        over-guessed the peak nearest A is the whole-cell bump, and taking
        each role's nearest peak on its own then puts the rectangle on the
        wrong hump.  Minimising the total miss over the pairs that keep C
        above A does not, and it cannot hand the solve an inverted ordering.
        """
        best = None
        for xa in cands:
            for xc in cands:
                if xc <= xa:
                    continue
                if (abs(xa - pa) > self._seed_tol(pa)
                        or abs(xc - pc) > self._seed_tol(pc)):
                    continue
                score = abs(xa - pa) + abs(xc - pc)
                if best is None or score < best[0]:
                    best = (score, xa, xc)
        return (best[1], best[2]) if best else None

    def _seed_roles(self, p, upper):
        """Park the role glyphs on the workbench's best opening guess.

        Matthew's original kept the three glyphs on screen at all times, and
        a fresh trace with nothing to drag is a workbench with no way in.
        This runs once per trace and only while every role is still empty, so
        a glyph you placed -- or one that arrived with a saved session -- is
        never overwritten.  Seeded glyphs are ordinary glyphs: drag them, fit
        them, clear them.
        """
        tr = self._tr()
        if tr is None or tr.get("seeded"):
            return
        if any(tr["roles"].get(r) for r in ROLES):
            tr["seeded"] = True            # yours, or a session's: hands off
            return
        pred = self._pred_paths(p)
        placed = {}
        s_cand = self._seed_cands("Sample", upper)
        if s_cand:
            pair = None
            if len(s_cand) > 1 and "sample" in pred and "sampledia" in pred:
                pair = self._seed_pair(s_cand, pred["sample"],
                                       pred["sampledia"])
            if pair is None:               # no trustworthy prediction: the
                pair = sorted(s_cand[:2])  # strongest peaks, in n*t order
            placed["sample"] = pair[0]
            if len(pair) > 1:
                placed["sampledia"] = pair[1]
        b_cand = self._seed_cands("Background", upper)
        if b_cand:
            x = (self._seed_near(b_cand, pred["mediumdia"])
                 if "mediumdia" in pred else None)
            placed["mediumdia"] = b_cand[0] if x is None else x
        if not placed:
            self._seed_status(
                "none", "the detector missed this trace, so the role glyphs "
                        "stay parked. Loosen Detection, or right-click a "
                        "peak to place a role by hand.")
            return
        for role, x in placed.items():
            # "seed" marks a glyph nobody has touched yet: it draws and drags
            # exactly like a placed one, but it is not unsaved work (see
            # _dirty_items), so a seeded trace never triggers a leave guard.
            tr["roles"][role] = {"nt_um": float(x), "auto": True, "seed": True}
            tr["gauss"][role] = None
        tr["seeded"] = True
        missing = [ROLE_DISP[r] for r in ROLES if r not in placed]
        if missing:
            self._seed_status(
                "part", "parked %d of the 3 role glyphs on our best guess; "
                "%s still needs a home. Right-click a peak to assign it."
                % (len(placed), " and ".join(missing)))
        else:
            self._seed_status(
                "all", "role glyphs parked on our best guess from your stack. "
                "Drag them, or right-click a peak, to move them.")

    def _seed_status(self, kind, msg):
        """Say it once per trace: a redraw must not re-announce the seed."""
        if self._seed_said.get(self._label) == kind:
            return
        self._seed_said[self._label] = kind
        self._status(msg, log=False)

    def _refresh_state_indicators(self):
        """Two-level model: what is in memory vs what was committed."""
        items = self._dirty_items()
        if self._label is None:
            self._state_lbl.configure(text="")
            self._show_if_text(self._state_lbl, "")
            return
        if self._label not in self._disk:
            mark, txt = IND_NONE, "this trace is waiting for its first record"
        elif items:
            mark, txt = IND_DIRTY, "%d change(s) in memory" % len(items)
        else:
            mark, txt = IND_SAVED, "saved, identical to disk"
        self._state_lbl.configure(text="%s  %s" % (mark, txt))
        self._show_if_text(self._state_lbl, txt)
        n = len(self._series)
        try:
            self._series_lbl.configure(
                text="Series: %s   %s"
                     % (self._series_label() or "–",
                        ("no points plotted" if not n else
                         "%d point%s plotted"
                         % (n, "" if n == 1 else "s"))))
        except (AttributeError, tk.TclError):
            pass
        try:
            self.csv_dir_v.set(self._series_folder() or "–")
        except (AttributeError, tk.TclError):
            pass
        self._sync_action_marks()
        self._refresh_series_disk()

    # =======================================================================
    # interactions
    # =======================================================================
    def _panel_of(self, ax):
        for chan, a in self._axes.items():
            if a is ax or self._twins.get(chan) is ax:
                return chan
        return None

    def _toolbar_busy(self):
        tb = getattr(self.canvas, "toolbar", None)
        return bool(tb is not None and getattr(tb, "mode", ""))

    # ---- hit radii, in screen pixels --------------------------------------
    def _um_per_px(self, ax):
        """How many micron of n*t one screen pixel is worth on `ax`."""
        try:
            x0, x1 = ax.get_xlim()
            w = float(ax.get_window_extent().width)
        except Exception:
            return None
        if not (w > 1.0) or not np.isfinite(x1 - x0):
            return None
        return abs(float(x1 - x0)) / w

    def _tol(self, ax, px, floor_um):
        """`px` screen pixels in micron: never below `floor_um`, never more
        than `frac` of the visible span.

        The cap earns its place on a narrow canvas.  With the guide pane
        open the axes can be 200 px wide, where 15 px is 7.5 um of n*t --
        wide enough that the low-pass line would claim a peak six micron
        away and every click near it turned into a drag.  Capping on the
        span keeps the reach proportionate at any size.
        """
        upp = self._um_per_px(ax)
        if upp is None:
            return floor_um
        try:
            x0, x1 = ax.get_xlim()
            span = abs(float(x1 - x0))
        except Exception:
            span = 0.0
        tol = max(floor_um, px * upp)
        cap = TOL_CAP_FRAC * span
        if cap > floor_um:
            tol = min(tol, cap)
        return tol

    def _ax_of(self, chan):
        return self._axes.get(chan)

    def _on_press(self, event):
        if event.inaxes is None or event.xdata is None or self._toolbar_busy():
            return
        chan = self._panel_of(event.inaxes)
        if chan is None:
            return
        if event.button == 3:
            self._rclick(chan, float(event.xdata), event)
            return
        if event.button != 1:
            return
        # a draggable handle first, then the notch toggle
        kind, role = self._grab_at(chan, float(event.xdata), event)
        if kind == "role":
            self._drag = {"kind": "role", "role": role, "chan": chan}
            self._hint("dragging %s. release to drop it, then Fit peaks to "
                       "snap it onto the peak." % ROLE_DISP[role].lower())
            return
        if kind == "lp":
            self._drag = {"kind": "lp", "chan": chan}
            return
        self._toggle_notch_at(chan, float(event.xdata), ax=event.inaxes)

    def _grab_at(self, chan, x, event):
        """The draggable handle under `x`, if one really is the nearest thing.

        Matthew's order is role glyph, then low-pass line, then the notch
        click.  Order alone is not enough once the reaches are measured in
        pixels: on a narrow canvas the low-pass line's reach overlaps peaks
        several micron away and swallowed every click near it, so the
        low-pass line only wins when it is at least as close as the peak.

        A role glyph is not in that argument.  It sits ON its peak by
        construction, so the nearer-peak test threw the grab away for the
        sake of the very marker the glyph is standing on, and the press
        fell through to the notch toggle -- a notch nobody asked for, three
        times in a row for one reader.  A glyph within reach now wins
        outright, which is also what the pointer has been promising: hover
        and press both read this method, so the resize arrow means the same
        thing every time it appears.
        """
        ax = event.inaxes if event.inaxes is not None else self._ax_of(chan)
        role = self._grab_role(chan, x, event)
        if role is not None:
            rv = (self._tr() or {"roles": {}})["roles"].get(role)
            if rv:
                return "role", role
        peak = self._hover_peak(chan, x, ax)
        d_peak = None if peak is None else abs(float(peak[0]) - x)
        if self.lp_on_v[chan].get():
            d = abs(x - _f(self.lp_v[chan], 15.0))
            if (d <= self._tol(ax, GRAB_PX, GRAB_TOL_UM)
                    and (d_peak is None or d_peak >= d)):
                return "lp", None
        return None, None

    # ---- hover: the affordance the gestures never had ---------------------
    def _on_leave(self, _event=None):
        self._hover_clear()

    def _hover_clear(self):
        self._set_cursor("")
        self._hover_mark(None, None)

    def _set_cursor(self, name):
        if getattr(self, "_cursor_now", None) == name:
            return
        self._cursor_now = name
        try:
            self._tkcanvas.configure(cursor=name)
        except (AttributeError, tk.TclError):
            pass

    def _hover(self, event):
        """Cursor and peak highlight under the pointer.

        Three states, and each one is the answer to "can I click this?":
        a resize arrow over anything draggable (a role glyph, the low-pass
        line), a hand plus a ring around the peak that a click would act
        on, and the plain pointer over bare plot.
        """
        chan = self._panel_of(event.inaxes) if event.inaxes else None
        if chan is None or event.xdata is None or self._toolbar_busy():
            self._hover_clear()
            return
        ax, x = event.inaxes, float(event.xdata)
        if self._grab_at(chan, x, event)[0] is not None:
            self._hover_mark(None, None)
            self._set_cursor("sb_h_double_arrow")
            return
        xy = self._hover_peak(chan, x, ax)
        self._set_cursor("hand2" if xy is not None else "")
        self._hover_mark(chan, xy)

    def _hover_peak(self, chan, x, ax):
        """The drawn peak under the pointer, from what is ON the axes.

        Motion fires per pixel, so this reads the markers the last draw put
        down (`_peak_xy`) instead of asking `_compute` -- a cache miss there
        would cost an FFT per mouse move.  The click path still goes through
        `_nearest_peak`, which is exact.
        """
        pts = getattr(self, "_peak_xy", {}).get(chan) or []
        if not pts:
            return None
        best = min(pts, key=lambda p: abs(p[0] - x))
        if abs(best[0] - x) > self._tol(ax, PICK_PX, CLICK_TOL_UM):
            return None
        return best

    def _hover_mark(self, chan, xy):
        """Ring the peak a click would take, and only that one.

        Guarded on the ring's identity, not on the pointer: motion fires per
        pixel and every repaint is a full figure draw, so moving ACROSS one
        peak must cost one draw, not forty.
        """
        key = None if xy is None else (chan, round(float(xy[0]), 3))
        if key == getattr(self, "_hover_key", None):
            return
        self._hover_key = key
        for ch, ln in self._artists.get("hover", {}).items():
            want = xy is not None and ch == chan
            if want:
                ln.set_data([xy[0]], [xy[1]])
            ln.set_visible(want)
        self._safe_draw()

    def _on_motion(self, event):
        if self._drag is None:
            self._hover(event)
            return
        if event.xdata is None:
            return
        x = max(float(event.xdata), 0.0)
        if self._drag["kind"] == "lp":
            chan = self._drag["chan"]
            self._suspend = True
            try:
                self.lp_v[chan].set("%.2f" % x)
            finally:
                self._suspend = False
            ln = self._artists.get("lp", {}).get(chan)
            if ln is not None:
                ln.set_xdata([x, x])
            self._safe_draw()
            self._status("low-pass cutoff %.2f um" % x, log=False)
            self._request_redraw()
        elif self._drag["kind"] == "role":
            role = self._drag["role"]
            tr = self._tr()
            if tr is not None:
                tr["roles"][role] = {"nt_um": x, "auto": False}
                tr["gauss"][role] = None
            ln = self._artists.get("roles", {}).get(role)
            if ln is not None:
                ln.set_xdata([x])
                self._safe_draw()

    def _on_release(self, _event):
        if self._drag is None:
            return
        kind = self._drag["kind"]
        self._drag = None
        if kind == "lp":
            self._invalidate()      # per-channel keys persist in redraw
        else:
            self._refresh_roles()
            self._request_redraw()

    def _grab_role(self, chan, x, event):
        best = None
        tr = self._tr()
        if tr is None:
            return None
        try:
            yf = event.inaxes.transAxes.inverted().transform(
                (event.x, event.y))[1]
        except Exception:
            yf = None
        tol = self._tol(event.inaxes if event.inaxes is not None
                        else self._ax_of(chan), GRAB_PX, GRAB_TOL_UM)
        for role in ROLES:
            if ROLE_PANEL[role] != chan:
                continue
            rv = tr["roles"].get(role)
            if not rv:
                continue
            dx = abs(float(rv["nt_um"]) - x)
            if dx > tol:
                continue
            dy = abs(ROLE_Y[role] - yf) if yf is not None else 0.0
            if dy > ROLE_GRAB_DY:
                continue
            if best is None or (dy, dx) < best[0]:
                best = ((dy, dx), role)
        return best[1] if best else None

    def _candidates(self, chan):
        c = self._compute(chan)
        if not c or "peaks" not in c or not len(c["peaks"]):
            return np.array([])
        return c["nt_um"][c["peaks"]]

    def _nearest_peak(self, chan, x, ax=None):
        cand = self._candidates(chan)
        if not len(cand):
            return None
        j = int(np.argmin(np.abs(cand - x)))
        tol = self._tol(self._ax_of(chan) if ax is None else ax,
                        PICK_PX, CLICK_TOL_UM)
        if abs(float(cand[j]) - x) > tol:
            return None
        return round(float(cand[j]), 2)

    def _toggle_notch_at(self, chan, x, ax=None):
        """Left-click within reach of a peak: a peak in the list is removed, a
        bare peak is added.  Unticking (keep the marker, drop it from the
        notch) is the list's checkbox, not a plot click -- Matthew's
        grammar."""
        kk = self._nearest_peak(chan, x, ax=ax)
        if kk is None:
            self._status("aim at a marker to pick its FFT peak.")
            return
        ch = self._ch(chan)
        listed = ((kk in ch["default_centers"] or kk in ch["user_centers"])
                  and kk not in ch["removed"])
        if listed:
            ch["removed"].add(kk)
            ch["user_centers"] = [k for k in ch["user_centers"] if k != kk]
            self._status("removed the notch at %.2f um." % kk)
        else:
            ch["removed"].discard(kk)
            if kk not in ch["default_centers"] and kk not in ch["user_centers"]:
                ch["user_centers"].append(kk)
            self._status("added a notch at %.2f um." % kk)
        self._invalidate()

    def _rclick(self, chan, x, event):
        kk = self._nearest_peak(chan, x, ax=event.inaxes)
        if kk is None:
            self._status("aim at a marker to pick its FFT peak.")
            return
        ch = self._ch(chan)
        menu = tk.Menu(self.app.root, tearoff=0)
        is_fund = (self._fund_key(chan) == kk)
        menu.add_command(
            label=("%.2f um is the fundamental" % kk if is_fund
                   else "Pin %.2f um as the fundamental" % kk),
            state=("disabled" if is_fund else "normal"),
            command=lambda: self._pin_fundamental(chan, kk))
        if ch["user_fundamental"] is not None:
            menu.add_command(label="Reset the fundamental to auto",
                             command=lambda: self._pin_fundamental(chan, None))
        # ...and the roles this panel carries, so a glyph can always be put
        # somewhere without hunting for it first
        roles = [r for r in ROLES if ROLE_PANEL[r] == chan]
        if roles:
            menu.add_separator()
            for role in roles:
                menu.add_command(
                    label="Assign %.2f um as %s" % (kk, ROLE_DISP[role]),
                    command=lambda r=role, k=kk: self._assign_role_here(r, k))
        ge = getattr(event, "guiEvent", None)
        try:
            if ge is not None:
                menu.tk_popup(ge.x_root, ge.y_root)
            else:
                menu.tk_popup(self.app.root.winfo_pointerx(),
                              self.app.root.winfo_pointery())
        finally:
            menu.grab_release()

    def _pin_fundamental(self, chan, kk):
        ch = self._ch(chan)
        ch["user_fundamental"] = kk
        if kk is not None:
            ch["removed"].discard(kk)
            if kk not in ch["default_centers"] and kk not in ch["user_centers"]:
                ch["user_centers"].append(kk)
            self._status("%s fundamental pinned at %.2f um." % (chan, kk))
        else:
            self._status("%s fundamental back to the detected peak." % chan)
        self._invalidate()

    # ---- notch list actions ----------------------------------------------
    def _tick(self, chan, kk, var):
        ch = self._ch(chan)
        if var.get():
            ch["unticked"].discard(kk)
        else:
            ch["unticked"].add(kk)
        self._invalidate()

    def _set_width(self, chan, kk, var):
        hw = _f(var, self._width_of(chan, kk))
        if hw <= 0:
            var.set("%g" % self._width_of(chan, kk))
            return
        self._ch(chan)["widths"][kk] = hw
        self._invalidate()

    def _remove_center(self, chan, kk):
        ch = self._ch(chan)
        ch["removed"].add(kk)
        ch["user_centers"] = [k for k in ch["user_centers"] if k != kk]
        self._invalidate()

    def _reset_notches(self):
        for chan in CHANNELS:
            ch = self._ch(chan)
            if ch is None:
                continue
            ch["user_centers"] = []
            ch["removed"] = set()
            ch["unticked"] = set()
            ch["user_fundamental"] = None
            ch["widths"] = {}
        self._status("notches reset to the detected fundamental.")
        self._invalidate()

    def _write_to_defringe(self):
        """Hand this spectrum's cleaning to the whole series.

        The centres picked on the chart and each channel's low-pass
        cutoff are per-CHANNEL and per-SPECTRUM, so they travel as a
        published snapshot in `fr_apply_centers`: from here on the main
        plot's df box, a Run's defringed CSVs and Export CSV all clean at
        exactly these peaks.  The detection gates and the default
        half-width need no snapshot -- `defringe_state` reads those live
        off this panel.

        Publishing nothing is a real answer, and it is the shipped one:
        with no snapshot the app notches the auto-detected fundamental,
        which is what df does for someone who never opens this tab.
        """
        pub = {}
        for chan in CHANNELS:
            entry = {}
            keys = self._active_centers(chan)
            if keys:
                entry["notch_centers_nm"] = [k * 1000.0 for k in keys]
                entry["notch_halfwidths_um"] = [self._width_of(chan, k)
                                                for k in keys]
            if self.lp_on_v[chan].get():
                entry["lowpass"] = True
                entry["lp_cutoff_um"] = max(_f(self.lp_v[chan], 15.0), 1e-3)
            if entry:
                pub[CHAN_KEY[chan]] = entry
        self.settings["fr_apply_centers"] = pub
        self._notify_defringe()
        n = sum(len(v.get("notch_centers_nm") or ()) for v in pub.values())
        lp = sum(1 for v in pub.values() if v.get("lowpass"))
        self._status("published %d notch centre(s) and %d low-pass cutoff(s) "
                     "to the main plot." % (n, lp))

    # ---- Fit peaks --------------------------------------------------------
    def _fit_peaks(self):
        """Auto-snap every assigned glyph onto its local peak.

        Distinct fits each role independently.  Shared ties the two Sample
        roles to ONE hump: a joint two-Gaussian fit with a shared sigma and an
        offset constrained to delta >= 0, so the pair can never come back in
        an order the solve cannot invert.
        """
        tr = self._tr()
        if tr is None:
            return
        mode = self.fitmode_v.get()
        moved = []
        if mode == "shared":
            pair = self._fit_shared()
            if pair:
                for role, mu in pair.items():
                    tr["roles"][role] = {"nt_um": mu, "auto": True}
                    moved.append("%s -> %.2f" % (ROLE_DISP[role], mu))
            targets = ("mediumdia",)
        else:
            targets = ROLES
        for role in targets:
            rv = tr["roles"].get(role)
            if not rv:
                continue
            mu = self._refine(ROLE_PANEL[role], float(rv["nt_um"]))
            if mu is None:
                continue
            tr["roles"][role] = {"nt_um": mu, "auto": True}
            moved.append("%s -> %.2f" % (ROLE_DISP[role], mu))
        self.settings["fr_fit_mode"] = mode
        if moved:
            self._status("fit peaks (%s): %s" % (mode, "; ".join(moved)))
        else:
            self._status("fit peaks: every glyph kept its position.")
        self._refresh_roles()
        self._request_redraw(now=True)

    def _window(self, chan, x0, half=None):
        c = self._compute(chan)
        if not c or "V" not in c:
            return None
        half = half if half is not None else max(2.5 * _f(self.hw_v, 3.0), 3.0)
        x, y = c["nt_um"], c["V"]
        m = np.isfinite(y) & (x >= x0 - half) & (x <= x0 + half)
        if int(m.sum()) < 5:
            return None
        return x[m], y[m]

    def _refine(self, chan, x0):
        """Gaussian refine of one peak: A exp(-((x-mu)/sig)^2/2) + c."""
        w = self._window(chan, x0)
        if w is None:
            return None
        x, y = w
        try:
            from scipy.optimize import least_squares
        except ImportError:
            return None
        c0 = float(np.min(y))
        a0 = max(float(np.max(y)) - c0, 1e-12)
        s0 = max(0.5 * _f(self.hw_v, 3.0), 0.2)
        lo = [0.0, float(x[0]), 0.05, -abs(c0) - a0]
        hi = [10.0 * a0, float(x[-1]), 5.0 * s0 + 1.0, abs(c0) + a0]

        def resid(q):
            A, mu, sig, c = q
            return A * np.exp(-0.5 * ((x - mu) / max(sig, 1e-9)) ** 2) + c - y
        try:
            r = least_squares(resid, [a0, x0, s0, c0], bounds=(lo, hi),
                              max_nfev=400)
        except (ValueError, RuntimeError):
            return None
        mu = float(r.x[1])
        return mu if np.isfinite(mu) else None

    def _fit_shared(self):
        """Joint two-Gaussian fit of the Sample panel's pair: shared sigma,
        offset ordered delta >= 0 (the sample-diamond peak never lands left of
        the sample peak)."""
        tr = self._tr()
        rs, rd = tr["roles"].get("sample"), tr["roles"].get("sampledia")
        if not (rs and rd):
            return None
        lo_x = min(float(rs["nt_um"]), float(rd["nt_um"]))
        hi_x = max(float(rs["nt_um"]), float(rd["nt_um"]))
        w = self._window("Sample", 0.5 * (lo_x + hi_x),
                         half=max(0.75 * (hi_x - lo_x) + 3.0, 4.0))
        if w is None:
            return None
        x, y = w
        try:
            from scipy.optimize import least_squares
        except ImportError:
            return None
        c0 = float(np.min(y))
        a0 = max(float(np.max(y)) - c0, 1e-12)
        s0 = max(0.5 * _f(self.hw_v, 3.0), 0.2)
        d0 = max(hi_x - lo_x, 0.0)

        def resid(q):
            A1, mu1, A2, delta, sig, c = q
            g1 = A1 * np.exp(-0.5 * ((x - mu1) / max(sig, 1e-9)) ** 2)
            g2 = A2 * np.exp(-0.5 * ((x - (mu1 + delta))
                                     / max(sig, 1e-9)) ** 2)
            return g1 + g2 + c - y
        lo = [0.0, float(x[0]), 0.0, 0.0, 0.05, -abs(c0) - a0]
        hi = [10.0 * a0, float(x[-1]), 10.0 * a0, float(x[-1] - x[0]),
              5.0 * s0 + 1.0, abs(c0) + a0]
        try:
            r = least_squares(resid, [a0, lo_x, 0.6 * a0, d0, s0, c0],
                              bounds=(lo, hi), max_nfev=800)
        except (ValueError, RuntimeError):
            return None
        mu1 = float(r.x[1])
        mu2 = mu1 + float(r.x[3])
        if not (np.isfinite(mu1) and np.isfinite(mu2)):
            return None
        # the LOWER centre is the sample path; the higher one carries the
        # loaded sample-diamond path (delta >= 0 by construction)
        return {"sample": mu1, "sampledia": mu2}

    def _clear_role(self, role):
        tr = self._tr()
        if tr is None:
            return
        tr["roles"][role] = None
        tr["gauss"][role] = None
        tr["seeded"] = True           # deliberate: the seed does not undo it
        self._status("%s unassigned. Right-click a peak to put the glyph "
                     "back." % ROLE_DISP[role])
        self._refresh_roles()
        self._request_redraw(now=True)

    def _assign_role_here(self, role, x):
        """Put one role at `x` outright -- the right-click menu's answer, and
        the same result a drag would leave: yours, unsnapped, refinable."""
        tr = self._tr()
        if tr is None:
            return
        tr["roles"][role] = {"nt_um": float(x), "auto": False}
        tr["gauss"][role] = None
        tr["seeded"] = True           # you have taken over from the guess
        self._status("%s assigned at %.2f um. Fit peaks will settle it onto "
                     "the local bump." % (ROLE_DISP[role], float(x)))
        self._refresh_roles()
        self._request_redraw(now=True)

    # ---- Solve ------------------------------------------------------------
    def _solve(self):
        tr = self._tr()
        rec = self._record()
        if tr is None or rec is None:
            return
        r = tr["roles"]
        missing = [ROLE_DISP[k] for k in ROLES if not r.get(k)]
        if missing:
            self._status("assign %s before solving." % ", ".join(missing),
                         warn=True)
            return
        p = self._stack_params(rec)
        sol = fringe_optics.solve_paths(
            float(r["sample"]["nt_um"]), float(r["sampledia"]["nt_um"]),
            float(r["mediumdia"]["nt_um"]), p["n_layer2"], p["n_medium"])
        if sol is None:
            self._status("a refractive index came out at or below zero; the "
                         "solve needs a positive index.", warn=True)
            return
        tr["solved"] = dict(sol)
        for key in ("n_s", "t_s", "t_layer2", "L"):
            lab = self._sol_lbl.get(key)
            if lab is None:
                continue
            try:
                lab.configure(text=_fmt(sol[key], 3))
            except tk.TclError:
                pass
        warns = sol.get("warns") or []
        self._set_solve_status("; ".join(warns) if warns else "")
        if warns:
            self._status("solved with clamps: " + "; ".join(warns), warn=True)
        else:
            self._status("solved: n_s = %s, t_s = %s um, L = %s um."
                         % (_fmt(sol["n_s"]), _fmt(sol["t_s"], 2),
                            _fmt(sol["L"], 2)))
        self._refresh_state_indicators()

    def _write_back(self):
        tr = self._tr()
        sol = (tr or {}).get("solved")
        if not sol:
            self._status("solve first, then adopt.", warn=True)
            return
        self._suspend = True
        try:
            self.ns_v.set("%.4f" % sol["n_s"])
            self.t_v.set("%.3f" % sol["t_s"])
            # his _apply_solved: d1 is yours and stays put; d2 takes
            # the remainder of the solved medium total, floored at 0
            _d1 = max(_f(self.d1_v, 0.0), 0.0)
            _d2 = max(float(sol["t_layer2"]) - _d1, 0.0)
            self.d2_v.set("%.3f" % _d2)
            if self.lock_v.get():
                self.total_v.set("%.3f" % sol["L"])
        finally:
            self._suspend = False
        self._thick_snapshot()
        for k, v in (("fr_n_sample", sol["n_s"]), ("fr_t_um", sol["t_s"]),
                     ("fr_d2_um", _d2)):
            self.settings[k] = float(v)
        self._status("adopted into the stack. the model stems have moved.")
        self._request_redraw(now=True)

    # ---- Series -----------------------------------------------------------
    def _branch(self, rec):
        fn = getattr(self.app, "_branch_of", None)
        if callable(fn):
            try:
                return fn(rec)
            except Exception:
                pass
        return rec.get("branch") or "C"

    def _record_point(self):
        tr = self._tr()
        rec = self._record()
        if rec is None:
            return
        if not (tr and tr.get("solved")):
            self._status("solve first. a point records the solved values.",
                         warn=True)
            return
        r = tr["roles"]
        p = self._stack_params(rec)
        # The two indices the solve was run AT travel with the point. That is
        # what makes the Results view's re-solve exact rather than
        # approximate: (A, C, iii) are the measurement, and solve_paths
        # conserves A, so feeding the recorded indices back reproduces the
        # recorded numbers bit for bit, and feeding a different medium's n(P)
        # gives the honest answer under that model.
        pt = {"label": rec["label"],
              "pressure": float(rec.get("pressure_val") or 0.0),
              "branch": self._branch(rec),
              "A": float(r["sample"]["nt_um"]),
              "C": float(r["sampledia"]["nt_um"]),
              "iii": float(r["mediumdia"]["nt_um"]),
              "medium": self.medium_v.get(),
              "layer2": bool(self.layer2_on_v.get()),
              "layer2_name": (self.layer2_v.get()
                              if self.layer2_on_v.get() else
                              self.medium_v.get()),
              "n_medium": float(p["n_medium"]),
              "n_layer2": float(p["n_layer2"]),
              "diamond": self.diamond_v.get(),
              "solved": {k: float(v) for k, v in tr["solved"].items()
                         if k != "warns"}}
        self._series = [q for q in self._series if q["label"] != pt["label"]]
        self._series.append(pt)
        self._series.sort(key=lambda q: (q["branch"], q["pressure"]))
        self._commit()
        self._status("recorded %s on the %s branch."
                     % (pt["label"], pt["branch"]))
        self._refresh_state_indicators()

    def _drop_point(self):
        n0 = len(self._series)
        self._series = [q for q in self._series if q["label"] != self._label]
        if len(self._series) == n0:
            self._status("drop point acts on a recorded trace.")
            return
        self._status("dropped the recorded point for this trace.")
        self._refresh_state_indicators()

    # =======================================================================
    # state discipline: memory vs disk
    # =======================================================================
    def _mem_state(self, label=None):
        """The committable state of one trace, as plain JSON types."""
        label = self._label if label is None else label
        if label is None:
            return {}
        out = {"chan": {}, "roles": {}, "solved": None}
        for chan in CHANNELS:
            ch = self._chan.get((label, chan))
            if ch is None:
                continue
            out["chan"][chan] = {
                "user_centers": sorted(ch["user_centers"]),
                "removed": sorted(ch["removed"]),
                "unticked": sorted(ch["unticked"]),
                "user_fundamental": ch["user_fundamental"],
                "widths": {("%.2f" % k): v for k, v in ch["widths"].items()}}
        tr = self._trace.get(label)
        if tr:
            out["roles"] = {k: (dict(v) if v else None)
                            for k, v in tr["roles"].items()}
            out["solved"] = (dict(tr["solved"]) if tr.get("solved") else None)
            out["solved"] = ({k: v for k, v in out["solved"].items()
                              if k != "warns"} if out["solved"] else None)
        return out

    @staticmethod
    def _owned_role(rv):
        """A role as the guard sees it: a glyph still sitting where the seed
        parked it is the workbench's opening guess, not work you would be
        sorry to lose, so it must not raise a leave prompt on its own.  One
        drag, fit or assign drops the mark and it counts from then on."""
        rv = rv or {}
        return {} if rv.get("seed") else rv

    def _dirty_items(self, label=None):
        """Itemised differences between memory and disk, in plain words."""
        label = self._label if label is None else label
        if label is None:
            return []
        mem = self._mem_state(label)
        disk = self._disk.get(label)
        if disk is None:
            empty = (not any(v.get("user_centers") or v.get("removed")
                             or v.get("unticked") or v.get("user_fundamental")
                             or v.get("widths")
                             for v in mem["chan"].values())
                     and not any(self._owned_role(v)
                                 for v in mem["roles"].values())
                     and not mem["solved"])
            return [] if empty else ["this trace is waiting for its first "
                                     "save"]
        items = []
        for chan in CHANNELS:
            m = mem["chan"].get(chan, {})
            d = (disk.get("chan") or {}).get(chan, {})
            for key, word in (("user_centers", "manual notch centres"),
                              ("removed", "removed centres"),
                              ("unticked", "unticked centres"),
                              ("widths", "notch widths")):
                if m.get(key) != d.get(key):
                    items.append("%s: %s changed" % (chan, word))
            if m.get("user_fundamental") != d.get("user_fundamental"):
                items.append("%s: the pinned fundamental changed" % chan)
        for role in ROLES:
            if (self._owned_role(mem["roles"].get(role))
                    != self._owned_role((disk.get("roles") or {}).get(role))):
                items.append("%s moved" % ROLE_DISP[role])
        if mem.get("solved") != disk.get("solved"):
            items.append("the solved values changed")
        return items

    def _commit(self, label=None):
        label = self._label if label is None else label
        if label is None:
            return
        self._disk[label] = self._mem_state(label)

    def _restore(self, label):
        d = self._disk.get(label)
        if d is None:
            return
        self._apply_trace_state(label, d)

    def _apply_trace_state(self, label, d):
        for chan, cd in (d.get("chan") or {}).items():
            ch = self._ch(chan, label)
            ch["user_centers"] = [float(k) for k in cd.get("user_centers", [])]
            ch["removed"] = set(float(k) for k in cd.get("removed", []))
            ch["unticked"] = set(float(k) for k in cd.get("unticked", []))
            ch["user_fundamental"] = cd.get("user_fundamental")
            ch["widths"] = {float(k): float(v)
                            for k, v in (cd.get("widths") or {}).items()}
        tr = self._tr(label)
        for role in ROLES:
            rv = (d.get("roles") or {}).get(role)
            tr["roles"][role] = (dict(rv) if rv else None)
        tr["solved"] = (dict(d["solved"]) if d.get("solved") else None)

    def _leave_guard(self):
        """Three-way guard before leaving a trace with unsaved changes.

        Returns True when it is safe to leave (saved or discarded), False when
        the answer was Stay.  The changes are itemised so the answer is never
        a guess; long lists are capped.
        """
        label = self._label
        if label is None:
            return True
        items = self._dirty_items(label)
        if not items:
            return True
        shown = items[:DIRTY_CAP]
        more = len(items) - len(shown)
        body = "\n".join("  • " + s for s in shown)
        if more > 0:
            body += "\n  …and %d more" % more
        ans = messagebox.askyesnocancel(
            "Fringe workbench",
            "%s holds unsaved changes:\n"
            "\n"
            "%s\n"
            "\n"
            "Yes: save, then leave\n"
            "No: leave them unsaved\n"
            "Cancel: stay here" % (label, body),
            parent=self.app.root)
        if ans is None:
            return False
        if ans:
            self._commit(label)
            self._log("Fringe: saved %d change(s) on %s." % (len(items),
                                                             label))
        else:
            self._restore(label)
            self._log("Fringe: discarded %d change(s) on %s." % (len(items),
                                                                 label))
        return True

    # ---- save / load ------------------------------------------------------
    def save_state(self):
        """The workbench's whole session payload.  Additive: app.py stores it
        under one new key and never touches the existing schema."""
        # Reading the payload means reading the control variables, so an
        # unbuilt workbench has to build first (idempotent). app.py skips
        # calling this at all when the panel was never opened, so the
        # common path still never pays for the build.
        self.build()
        self._commit()
        return {
            "version": 1,
            "view": "fringe" if self._active else "plot",
            "label": self._label,
            "stack": {"medium": self.medium_v.get(),
                      "medium_n": self.medium_n_v.get(),
                      "layer2_on": bool(self.layer2_on_v.get()),
                      "layer2": self.layer2_v.get(),
                      "diamond": self.diamond_v.get(),
                      "n_sample": _f(self.ns_v, 1.6),
                      "d1": _f(self.d1_v, 0.0), "t": _f(self.t_v, 0.0),
                      "d2": _f(self.d2_v, 0.0),
                      "lock_total": bool(self.lock_v.get()),
                      "total": _f(self.total_v, 0.0),
                      "fine_step": bool(self.fine_v.get())},
            "detect": {"wl_min": _f(self.wlmin_v, 600.0),
                       "wl_max": _f(self.wlmax_v, 800.0),
                       "nt_min": _f(self.ntmin_v, 8.0),
                       "nt_max": _f(self.ntmax_v, 300.0),
                       "pmax": _f(self.pmax_v, 1e-4),
                       "tol": _f(self.tol_v, 0.15)},
            "notch": {"halfwidth": _f(self.hw_v, 3.0),
                      # R7: per channel.  A pre-R7 payload holds a bool
                      # here instead; load_state migrates it.
                      "lowpass": dict((c, [bool(self.lp_on_v[c].get()),
                                           _f(self.lp_v[c], 15.0)])
                                      for c in CHANNELS)},
            "fit_mode": self.fitmode_v.get(),
            "traces": dict(self._disk),
            "series": list(self._series),
            # c keys -- the series level. Additive: a payload written by a
            # build without them still loads, and these are all defaulted.
            "msv_errors": bool(self.msv_v.get()),
            "res_models": [k for k, v in self._res_model_v.items()
                           if v.get()] or list(
                               self.settings.get("fr_res_models") or []),
            "eos": {"selections": self._eos_selections(),
                    "anchors": [{"panel": p, "eos": e, "dk": v}
                                for (p, e), v in sorted(
                                    self._res_anchor.items())]}}

    def load_state(self, d):
        if not isinstance(d, dict):
            return
        self.build()
        self._suspend = True
        try:
            st = d.get("stack") or {}
            for var, key, dflt in (
                    (self.medium_v, "medium", "Other"),
                    (self.medium_n_v, "medium_n", "1.2"),
                    (self.layer2_v, "layer2", "KCl"),
                    (self.diamond_v, "diamond", "constant")):
                var.set(st.get(key, dflt))
            self.layer2_on_v.set(bool(st.get("layer2_on", False)))
            self.lock_v.set(bool(st.get("lock_total", False)))
            self.fine_v.set(bool(st.get("fine_step", False)))
            for var, key, dflt in ((self.ns_v, "n_sample", 1.5),
                                   (self.d1_v, "d1", 0.0),
                                   (self.t_v, "t", 20.0),
                                   (self.d2_v, "d2", 0.0),
                                   (self.total_v, "total", 0.0)):
                var.set("%g" % float(st.get(key, dflt)))
            dt = d.get("detect") or {}
            for var, key, dflt in ((self.wlmin_v, "wl_min", 600.0),
                                   (self.wlmax_v, "wl_max", 800.0),
                                   (self.ntmin_v, "nt_min", 8.0),
                                   (self.ntmax_v, "nt_max", 300.0),
                                   (self.pmax_v, "pmax", 1e-4),
                                   (self.tol_v, "tol", 0.15)):
                var.set("%g" % float(dt.get(key, dflt)))
            nc = d.get("notch") or {}
            self.hw_v.set("%g" % float(nc.get("halfwidth", 3.0)))
            _lpd = nc.get("lowpass")
            if isinstance(_lpd, dict):        # R7 payload: per channel
                for c in CHANNELS:
                    _pair = _lpd.get(c)
                    if (isinstance(_pair, (list, tuple))
                            and len(_pair) == 2):
                        self.lp_on_v[c].set(bool(_pair[0]))
                        self.lp_v[c].set("%g" % float(_pair[1]))
            else:                             # pre-R7 scalar payload
                for c in CHANNELS:
                    self.lp_on_v[c].set(bool(True if _lpd is None
                                             else _lpd))
                    self.lp_v[c].set(
                        "%g" % float(nc.get("lp_cutoff", 15.0)))
            self.fitmode_v.set(d.get("fit_mode", "distinct"))
            self._disk = dict(d.get("traces") or {})
            for label, td in self._disk.items():
                self._apply_trace_state(label, td)
            self._series = list(d.get("series") or [])
            # c keys
            self.msv_v.set(bool(d.get("msv_errors", False)))
            self.settings["fr_msv_errors"] = bool(self.msv_v.get())
            if d.get("res_models") is not None:
                self.settings["fr_res_models"] = list(d["res_models"])
            self._msv_cache.clear()
        except (TypeError, ValueError) as exc:
            self._log("Fringe: session payload partly unreadable (%s)." % exc)
        finally:
            self._suspend = False
        self._apply_eos_state(d.get("eos") or {})
        self._sync_steps()
        self._on_layer2()
        self._on_lock()
        self._sync_medium_row()
        want = d.get("label")
        self.on_trace_change(want if want else None)
        if d.get("view") == "fringe":
            self.activate()

    # =======================================================================
    # series continuity on disk
    # =======================================================================
    def _program_roots(self):
        """Every folder that counts as "inside the program".

        A frozen build unpacks its data under sys._MEIPASS and a onedir
        build keeps a copy beside the executable, so all three are checked
        rather than betting on one packaging layout.
        """
        out = [os.path.dirname(os.path.abspath(__file__))]
        mei = getattr(sys, "_MEIPASS", None)
        if mei:
            out.append(mei)
        if getattr(sys, "frozen", False):
            out.append(os.path.dirname(os.path.abspath(sys.executable)))
        return out

    def _under_program(self, path):
        """True when `path` sits inside the program's own folder.

        The bundled demo data does, and so does everything else a packaged
        install ships.  Writing a reader's results in there pollutes the
        installation, and under Program Files it is simply refused.
        """
        try:
            p = os.path.normcase(os.path.abspath(path))
        except (TypeError, ValueError):
            return False
        for root in self._program_roots():
            r = os.path.normcase(os.path.abspath(root))
            if p == r or p.startswith(r + os.sep):
                return True
        return False

    def _writable(self, folder):
        """Can a file actually be created here?  Remembered per folder.

        os.access is not to be trusted on Windows shares, so the only
        honest test is to write something and take it away again; the
        answer is cached so the disk indicator does not touch the disk on
        every redraw.
        """
        try:
            key = os.path.normcase(os.path.abspath(folder))
        except (TypeError, ValueError):
            return False
        if key in self._wr_cache:
            return self._wr_cache[key]
        probe = os.path.join(folder, ".sparta-write-test-%d" % os.getpid())
        ok = True
        try:
            with open(probe, "w") as f:
                f.write("")
        except OSError:
            ok = False
        else:
            try:
                os.remove(probe)
            except OSError:
                pass
        self._wr_cache[key] = ok
        return ok

    def _input_folder(self):
        loc = getattr(self, "_local", None)
        if loc and os.path.isdir(loc.get("folder") or ""):
            return loc["folder"]
        var = getattr(self.app, "in_var", None)
        try:
            p = (var.get() or "").strip() if var is not None else ""
        except tk.TclError:
            p = ""
        return p if p and os.path.isdir(p) else None

    def _series_dest(self):
        """(folder, why) for series_continuity.json.

        Matthew writes it beside the spectra and so do we -- that shared
        convention is what lets either program pick the other's file up.
        Two folders cannot take it: the bundled demo data, which lives
        inside the program (and on a packaged install that is Program
        Files), and any read-only beamline share.  Both hand the job to the
        run's output folder, which the reader chose and which is writable
        by definition.  `why` is the sentence the status line owes them
        when that happens.
        """
        src = self._input_folder()
        var = getattr(self.app, "out_var", None)
        try:
            out = (var.get() or "").strip() if var is not None else ""
        except tk.TclError:
            out = ""
        out = out if out and os.path.isdir(out) else None
        if src is None:
            return out, None
        why = None
        if self._under_program(src):
            why = ("the data folder lives inside the program, so this went "
                   "to your output folder")
        elif not self._writable(src):
            why = ("the data folder is read-only, so this went to your "
                   "output folder")
        if (why and out and self._writable(out)
                and os.path.normcase(out) != os.path.normcase(src)):
            return out, why
        return src, None

    def _series_folder(self):
        """Where series_continuity.json is written."""
        return self._series_dest()[0]

    def _series_read_paths(self):
        """Every series_continuity.json worth looking in, best first.

        The destination is where we write; the input folder is where
        Matthew's program writes.  A file his batch mode left beside the
        data still loads even when our own saves are going elsewhere.
        """
        out, seen = [], set()
        for folder in (self._series_folder(), self._input_folder()):
            if not folder:
                continue
            key = os.path.normcase(os.path.abspath(folder))
            if key in seen:
                continue
            seen.add(key)
            out.append(os.path.join(folder, SERIES_FILE))
        return out

    def series_path(self):
        folder = self._series_folder()
        return os.path.join(folder, SERIES_FILE) if folder else None

    def _series_label(self):
        # a Session-loaded folder IS the series: name it after the folder,
        # never after wherever the continuity file happens to be written
        loc = getattr(self, "_local", None)
        if loc and loc.get("folder"):
            return os.path.basename(os.path.normpath(loc["folder"]))
        rec = self._record() or (self._records() or [{}])[0]
        dac, samp = rec.get("dac"), rec.get("sample")
        if dac and samp:
            return "%s_%s" % (dac, samp)
        folder = self._series_folder()
        return os.path.basename(os.path.normpath(folder)) if folder else ""

    def _series_payload(self):
        """The series as Matthew's fft_gui_series/v2 writer shapes it.

        Same top-level fields, same meanings: a schema string, the series
        label, the series-wide materials SEED, the EoS overlay state, the
        recorded points keyed by their identity, and the per-point inputs
        with the material keys stripped (two copies of the seed could
        disagree).  SPARTA's own point rows travel verbatim inside 'points',
        which is what makes a round trip lossless.
        """
        points, inputs = {}, {}
        for pt in self._series:
            key = pt["label"]
            points[key] = _deep(pt)
            inputs[key] = {"nt_min_um": _f(self.ntmin_v, 8.0),
                           "nt_max_um": _f(self.ntmax_v, 300.0),
                           "wl_min_nm": _f(self.wlmin_v, 600.0),
                           "wl_max_nm": _f(self.wlmax_v, 800.0),
                           "halfwidth_um": _f(self.hw_v, 3.0),
                           "lowpass": dict(
                               (c, bool(self.lp_on_v[c].get()))
                               for c in CHANNELS),
                           "lp_cutoff_um": dict(
                               (c, _f(self.lp_v[c], 15.0))
                               for c in CHANNELS),
                           "fit_mode": self.fitmode_v.get()}
        anchors = [{"panel": p, "eos": e, "dk": v}
                   for (p, e), v in sorted(self._res_anchor.items())]
        return {"schema": SERIES_SCHEMA,
                "series_label": self._series_label(),
                "written_by": "SPARTA fringe workbench",
                "materials": {"names": {"sample": self.settings.get(
                                            "fr_sample_name", "sample"),
                                        "anvil": "diamond"},
                              "layer2_model": self.layer2_v.get(),
                              "layer2": bool(self.layer2_on_v.get()),
                              "medium_model": self.medium_v.get(),
                              "diamond_model": self.diamond_v.get()},
                "eos": {"selections": self._eos_selections(),
                        "anchors": anchors},
                "points": points,
                "inputs": inputs}

    def save_series(self):
        """Write series_continuity.json where it can actually go, plus a
        stamped copy.

        The stamped copy is the cheap insurance the state discipline asks
        for: the canonical file is overwritten every save, so without it a
        mistaken save over a good series is unrecoverable.  Both names and
        the folder they landed in go in the status line and the log -- a
        file written without saying where is a file the reader has to go
        hunting for, and the timestamped copy used not to be mentioned at
        all.
        """
        folder, why = self._series_dest()
        if folder is None:
            self._status("pick an input or output folder first.", warn=True)
            return None
        if not self._series:
            self._status("record a point first.", warn=True)
            return None
        path = os.path.join(folder, SERIES_FILE)
        payload = self._series_payload()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        copy = os.path.join(folder, SERIES_STAMP % stamp)
        try:
            for target in (path, copy):
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
        except OSError as exc:
            self._status("writing the series failed: %s" % exc, warn=True)
            return None
        self._series_disk = payload
        self._series_path = path
        self._log("Fringe: wrote %d series point(s) -> %s"
                  % (len(self._series), path))
        self._log("  . timestamped copy: " + copy)
        if why:
            self._log("  . " + why + ".")
        fn = getattr(self.app, "_provenance", None)
        if callable(fn):
            try:
                fn(path, "series_continuity",
                   {"schema": SERIES_SCHEMA, "n_points": len(self._series),
                    "series_label": payload["series_label"]},
                   files=[path, copy])
            except Exception:
                pass
        self._status("series saved: %d point(s) in %s, with the timestamped "
                     "copy %s beside it%s."
                     % (len(self._series), path, os.path.basename(copy),
                        (" (%s)" % why) if why else ""))
        self._refresh_series_disk()
        return path

    def load_series(self):
        """Read series_continuity.json back in.

        Best-effort, exactly like Matthew's reader: unknown keys are kept,
        missing ones tolerated, and a bad file logs and changes nothing.  A
        point whose trace is already recorded in memory is REPLACED, so the
        file is the authority for what it carries and memory keeps the rest.
        """
        # The workbench is built on first use (app.py's _init_fringe leaves
        # it unbuilt), and this method ends by writing the stack rows and
        # the medium row, so it has to make sure they exist -- the same
        # thing load_state() does, for the same reason. build() is
        # idempotent.
        self.build()
        path = None
        for cand in self._series_read_paths():
            if os.path.isfile(cand):
                path = cand
                break
        if path is None:
            self._status("Save series writes the first %s."
                         % SERIES_FILE, warn=True)
            return 0
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            self._status("could not read %s (%s)." % (SERIES_FILE, exc),
                         warn=True)
            return 0
        pts = data.get("points") or {}
        if not isinstance(pts, dict):
            self._status("reading points from %s failed." % SERIES_FILE,
                         warn=True)
            return 0
        incoming = []
        for key, row in pts.items():
            if not isinstance(row, dict):
                continue
            row = _deep(row)          # never share a nested dict with `data`
            row.setdefault("label", key)
            incoming.append(row)
        keep = {p["label"] for p in incoming}
        self._series = [q for q in self._series if q["label"] not in keep]
        self._series.extend(incoming)
        self._series.sort(key=lambda q: (q.get("branch") or "C",
                                         q.get("pressure") or 0.0))
        mats = data.get("materials") or {}
        self._suspend = True
        try:
            if mats.get("medium_model") in MEDIUM_CHOICES:
                self.medium_v.set(mats["medium_model"])
            if mats.get("layer2_model"):
                self.layer2_v.set(mats["layer2_model"])
            if "layer2" in mats:
                self.layer2_on_v.set(bool(mats["layer2"]))
            if mats.get("diamond_model") in DIAMOND_MODELS:
                self.diamond_v.set(mats["diamond_model"])
        finally:
            self._suspend = False
        self._apply_eos_state(data.get("eos") or {})
        self._series_disk = data
        self._series_path = path
        self._msv_cache.clear()
        self._log("Fringe: read %d series point(s) <- %s"
                  % (len(incoming), path))
        self._status("loaded %d point(s) from %s." % (len(incoming), path))
        self._on_layer2()
        self._sync_medium_row()
        self._refresh_state_indicators()
        self._res_refresh()
        return len(incoming)

    def _series_state(self):
        """(indicator, words) for the series against its file on disk."""
        path = self.series_path()
        if path is None or not os.path.isfile(path):
            return (IND_NONE, "not written out yet")
        disk = self._series_disk
        if disk is None or self._series_path != path:
            return (IND_DIRTY, "a file exists here, unread this session")
        mine = self._series_payload()["points"]
        theirs = disk.get("points") or {}
        if mine == theirs:
            return (IND_SAVED, "%s holds these %d point(s)"
                    % (SERIES_FILE, len(mine)))
        n = len(set(mine) ^ set(theirs)) or sum(
            1 for k in mine if mine[k] != theirs.get(k))
        return (IND_DIRTY, "%d point(s) differ from the file" % n)

    def _refresh_series_disk(self):
        lab = getattr(self, "_series_disk_lbl", None)
        if lab is None:
            return
        mark, txt = self._series_state()
        try:
            lab.configure(text="%s  %s" % (mark, txt))
        except tk.TclError:
            pass
        self._show_if_text(lab, txt)

    # ---- notch_overrides.csv ---------------------------------------------
    def _stem_of(self, label):
        """The batch pipeline's file stem for one trace.

        {DAC}_{sample}_{value}, lower case -- the same stem
        engine.write_absorbance_csv builds its file name from (minus the
        branch letter and the _absorbance suffix), so a batch run over
        SPARTA's own output matches these rows.
        """
        rec = self._record(label)
        if rec is None:
            return str(label)
        if rec.get("stem"):          # Session-loaded: the file's own stem
            return rec["stem"]
        return ("%s_%s_%s" % (rec.get("dac", ""), rec.get("sample", ""),
                              rec.get("pressure_str", ""))).lower()

    def notch_override_rows(self):
        """[(stem, channel, nt_um, is_fundamental, halfwidth_um)] for every
        trace that has notches, fundamental first within each group.

        Pure: the writer below and the tests share it."""
        # reads hw_v for the default half-width, so the controls have to
        # exist (the workbench builds on first use); build() is idempotent
        self.build()
        rows = []
        for label in sorted(set(list(self._trace) + [k[0] for k
                                                     in self._chan])):
            stem = self._stem_of(label)
            for chan in CHANNELS:
                ch = self._chan.get((label, chan))
                if not ch:
                    continue
                fund = (ch["user_fundamental"] if ch["user_fundamental"]
                        is not None else (ch["default_centers"][0]
                                          if ch["default_centers"] else None))
                keys = []
                for k in list(ch["default_centers"]) + list(ch["user_centers"]):
                    if k in ch["removed"] or k in ch["unticked"] or k in keys:
                        continue
                    keys.append(k)
                if fund in keys:
                    keys.remove(fund)
                    keys.insert(0, fund)
                for k in keys:
                    rows.append((stem, chan, round(float(k), 4),
                                 int(k == fund),
                                 round(float(ch["widths"].get(
                                     k, _f(self.hw_v, 3.0))), 2)))
        return rows

    def export_notch_overrides(self, path=None):
        """Write notch_overrides.csv in the batch pipeline's exact format.

        Columns, in order: stem, channel, nt_um, is_fundamental,
        halfwidth_um.  load_notch_overrides reads that verbatim, so a batch
        re-run notches every spectrum where this session did.
        """
        rows = self.notch_override_rows()
        if not rows:
            self._status("pick a notch first.",
                         warn=True)
            return None
        if path is None:
            folder = self._series_folder()
            path = filedialog.asksaveasfilename(
                title="Write the notch overrides the batch pipeline reads",
                defaultextension=".csv", initialfile=NOTCH_FILE,
                initialdir=folder or None,
                filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
                parent=self.app.root)
            if not path:
                return None
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write("stem,channel,nt_um,is_fundamental,halfwidth_um\n")
                for stem, chan, nt, fund, hw in rows:
                    f.write("%s,%s,%.4f,%d,%.2f\n" % (stem, chan, nt, fund,
                                                      hw))
        except OSError as exc:
            self._status("writing the notches file failed: %s" % exc,
                         warn=True)
            return None
        lab = getattr(self, "_notch_file_lbl", None)
        if lab is not None:
            try:
                lab.configure(text="%d row(s) -> %s"
                                   % (len(rows), os.path.basename(path)))
            except tk.TclError:
                pass
            self._show_if_text(lab, "x")
        self._log("Fringe: wrote %d notch override row(s) -> %s"
                  % (len(rows), path))
        fn = getattr(self.app, "_provenance", None)
        if callable(fn):
            try:
                fn(path, "notch_overrides",
                   {"n_rows": len(rows),
                    "n_traces": len({r[0] for r in rows}),
                    "halfwidth_convention": "absolute +/- um of n*t"},
                   files=[path])
            except Exception:
                pass
        self._status("wrote %d notch override row(s)." % len(rows))
        return path

    # =======================================================================
    # multiscale-variance error bars
    # =======================================================================
    def _on_msv(self):
        self.settings["fr_msv_errors"] = bool(self.msv_v.get())
        if not self.msv_v.get():
            self._status("error bars off.")
        self._res_refresh()

    def _msv_sigma(self, label):
        """1 sigma on the sample channel's n*t (um) for one recorded point.

        Computed lazily -- it costs about 35 ms a point -- and cached per
        trace.  NOTE for constant_n the n*t variance lives in
        param_variance['nt'], NOT in derived_variance; msv_trend_summary
        already looks in the right place for each name, which is why the
        summary is used here rather than the raw dict.  The reported sigma
        is the LARGEST across the swept window widths: the multiscale point
        is that an estimate you cannot reproduce at some scale is not a
        number you may quote a tighter error on.
        """
        if label in self._msv_cache:
            return self._msv_cache[label]
        self._msv_cache[label] = None
        keep, self._label = self._label, label
        try:
            c = self._compute("Sample")
        finally:
            self._label = keep
        fi = (c or {}).get("fft_info")
        if not fi or "wn_u" not in fi or "norm_u_detrend" not in fi:
            return None
        try:
            import fringe_msv
            res = fringe_msv.multiscale_variance_analysis(
                fi["wn_u"], fi["norm_u_detrend"], fi, "constant_n",
                cfg=c["cfg"], label=str(label))
            stds = [row["nt_std"] for row in fringe_msv.msv_trend_summary(res)
                    if row.get("nt_std") is not None
                    and np.isfinite(row["nt_std"])]
        except Exception as exc:
            self._log("Fringe: multiscale variance unavailable for %s (%s)."
                      % (label, exc))
            return None
        if not stds:
            return None
        self._msv_cache[label] = float(max(stds))
        return self._msv_cache[label]

    # =======================================================================
    # results vs pressure
    # =======================================================================
    def _pt_branch(self, pt):
        """The point's branch, read LIVE from the main window.

        Recorded points keep the branch they were filed under, but the app's
        C/D state is the authority: ticking a D box, or loading a
        decompression list, must move the marker here without asking for the
        point to be recorded again.
        """
        rec = self._record(pt.get("label"))
        if rec is not None:
            return self._branch(rec)
        return pt.get("branch") or "C"

    def _pt_indices(self, pt):
        """(n_layer2, n_medium) the point was recorded at.

        Stored on the row since v1.4.9; a point written before that is
        reconstructed from its medium name at its own pressure, which is
        what the solve used at the time.
        """
        n_med = pt.get("n_medium")
        n_l2 = pt.get("n_layer2")
        if n_med and n_l2:
            return float(n_l2), float(n_med)
        wl = 0.5 * (_f(self.wlmin_v, 600.0) + _f(self.wlmax_v, 800.0))
        p = float(pt.get("pressure") or 0.0)
        med = pt.get("medium") or self.medium_v.get()
        n_med = float(n_med or self._index(med, p, wl))
        l2 = pt.get("layer2_name") or med
        n_l2 = float(n_l2 or self._index(l2, p, wl))
        return n_l2, n_med

    def _resolve_point(self, pt, medium=None):
        """Re-solve one recorded point, optionally under another medium.

        `medium` None keeps the recorded indices, and then the answer is the
        recorded one EXACTLY: (A, C, iii) are the measurement and
        solve_paths conserves A, so the stored solved tuple is a lossless
        encoding of the three paths at those indices.
        """
        try:
            A = float(pt["A"])
            C = float(pt["C"])
            iii = float(pt["iii"])
        except (KeyError, TypeError, ValueError):
            return None
        n_l2, n_med = self._pt_indices(pt)
        if medium is not None:
            wl = 0.5 * (_f(self.wlmin_v, 600.0) + _f(self.wlmax_v, 800.0))
            p = float(pt.get("pressure") or 0.0)
            n_med = self._index(medium, p, wl)
            n_l2 = (self._index(pt.get("layer2_name"), p, wl)
                    if pt.get("layer2") else n_med)
        sol = fringe_optics.solve_paths(A, C, iii, n_l2, n_med)
        if sol is None:
            return None
        return {"n_s": sol["n_s"], "n_medium": n_med, "n_layer2": n_l2,
                "t_s": sol["t_s"], "L": sol["L"],
                "t_layer2": sol["t_layer2"]}

    def _eos_selections(self):
        out = {}
        for panel in RES_EOS_PANELS:
            names = [n for n, v in (self._res_eos_v.get(panel) or {}).items()
                     if v.get()]
            if names:
                out[panel] = sorted(names)
        if not self._res_eos_v:          # window never opened: settings win
            stored = self.settings.get("fr_res_eos") or {}
            return {k: list(v) for k, v in stored.items() if v}
        return out

    def _apply_eos_state(self, eos):
        sel = eos.get("selections") or {}
        if isinstance(sel, dict):
            self.settings["fr_res_eos"] = {k: list(v) for k, v in sel.items()}
            for panel, names in sel.items():
                for name, var in (self._res_eos_v.get(panel) or {}).items():
                    var.set(name in names)
        self._res_anchor = {}
        for a in (eos.get("anchors") or []):
            if a.get("panel") and a.get("eos") and a.get("dk"):
                self._res_anchor[(a["panel"], a["eos"])] = a["dk"]
        self.settings["fr_res_anchors"] = {
            "%s|%s" % k: v for k, v in self._res_anchor.items()}

    def _res_color(self, pt):
        """Colour of a recorded point: its medium's slot in Okabe-Ito, so the
        identity a colour carries here is 'which n(P) model produced this'."""
        med = pt.get("medium") or "Other"
        try:
            i = MEDIUM_CHOICES.index(med)
        except ValueError:
            i = len(MEDIUM_CHOICES)
        if self._hc():
            return self._page()[1]
        return OKABE_ITO[i % len(OKABE_ITO)]

    def results_view(self):
        """The recorded series as Matthew's 2x3 grid against pressure.

        Same pop-out shape as the FFT view (rule 21): the work on the left,
        a Guide card on the right, a button bar along the bottom.
        """
        win = self._raise_existing("_results")
        if win is not None:
            self._res_refresh()
            return win
        win = tk.Toplevel(self.app.root)
        win.title("Results vs pressure")
        win.transient(self.app.root)
        self.app._center_on_root(win, *self._dlg_size(148, 84))
        self.app._apply_titlebar(win)
        win.bind("<Escape>", lambda e: self._close_results())
        win.protocol("WM_DELETE_WINDOW", self._close_results)
        self._results = win

        bar = ttk.Frame(win, padding=(10, 8))
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="Close",
                   command=self._close_results).pack(side="right")
        ttk.Button(bar, text="Save figure…",
                   command=self._res_save).pack(side="right",
                                                padx=(0, PAD_X))
        self._res_count = self.app._lbl(bar, text="", foreground=MUTED)
        self._res_count.pack(side="left")

        self._build_results_guide(win)
        main = ttk.Frame(win, padding=(12, 10))
        main.pack(side="left", fill="both", expand=True)

        opts = ttk.Frame(main)
        opts.pack(side="top", fill="x", pady=PAD_ROW)
        self.app._lbl(opts, text="Re-solve under", width=14).pack(side="left")
        stored = set(self.settings.get("fr_res_models") or [])
        for key in RES_MODEL_CHOICES:
            v = tk.BooleanVar(value=key in stored)
            self._res_model_v[key] = v
            # The FULL label, never a shortened one: three of the four media
            # are argon, and clipping at the bracket gave three boxes all
            # reading "Argon" -- a display map has to stay injective over
            # the canonical set (rule 53).
            cb = ttk.Checkbutton(opts, text=MEDIUM_LABELS.get(key, key),
                                 variable=v, command=self._res_refresh)
            cb.pack(side="left", padx=(0, PAD_X))
            self._tip(cb, "Solve every recorded point again under %s at its "
                          "own pressure and draw the answer beside the "
                          "recorded one." % MEDIUM_LABELS.get(key, key))
        eosr = ttk.Frame(main)
        eosr.pack(side="top", fill="x", pady=PAD_TIGHT)
        self.app._lbl(eosr, text="EoS curves", width=14).pack(side="left")
        stored_eos = self.settings.get("fr_res_eos") or {}
        for name in sorted(fringe_materials.EOS_MODELS):
            v = tk.BooleanVar(value=any(name in (stored_eos.get(p) or [])
                                        for p in RES_EOS_PANELS))
            for panel in RES_EOS_PANELS:
                self._res_eos_v.setdefault(panel, {})[name] = v
            cb = ttk.Checkbutton(eosr, text=name, variable=v,
                                 command=self._res_refresh)
            cb.pack(side="left", padx=(0, PAD_X))
            self._tip(cb, "Draw %s as a dashed thickness curve on the three "
                          "thickness panels. It scales as the cube root of "
                          "the volume ratio. It anchors on the "
                          "lowest-pressure point, or on the one you "
                          "right-click." % name)

        self._res_fig = Figure(figsize=(9.0, 5.6), dpi=100,
                               facecolor=self._page()[0])
        self._res_canvas = FigureCanvasTkAgg(self._res_fig, master=main)
        self._res_canvas.get_tk_widget().pack(fill="both", expand=True)
        self._res_canvas.mpl_connect("button_press_event", self._on_res_press)
        self.app._iconize_buttons(win)
        self._clamp_geometry(win, self.settings.get("fr_res_geom"))
        self._res_refresh()
        return win

    def _close_results(self):
        win, self._results = self._results, None
        if win is not None:
            try:
                self.settings["fr_res_geom"] = win.geometry()
                win.destroy()
            except tk.TclError:
                pass
        self.settings["fr_res_models"] = [k for k, v
                                          in self._res_model_v.items()
                                          if v.get()]
        self.settings["fr_res_eos"] = self._eos_selections()

    def _res_save(self):
        fig = getattr(self, "_res_fig", None)
        if fig is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save the results figure", defaultextension=".png",
            initialfile="results_vs_pressure.png",
            initialdir=self._series_folder() or None,
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")],
            parent=self._results or self.app.root)
        if not path:
            return
        try:
            fig.savefig(path, dpi=200, facecolor=fig.get_facecolor())
        except Exception as exc:
            self._status("saving the figure failed: %s" % exc, warn=True)
            return
        self._log("Fringe: wrote the results figure -> " + path)
        self._status("results figure saved.")

    def _res_build_axes(self):
        fig = self._res_fig
        fig.clear()
        gs = fig.add_gridspec(2, 3, hspace=0.42, wspace=0.38)
        self._res_ax = {}
        for key, (row, col), _lab, _eos in RES_PANELS:
            self._res_ax[key] = fig.add_subplot(gs[row, col])

    def _res_refresh(self):
        """Redraw the six panels.  Cheap enough to run on every toggle."""
        win = self._results
        if win is None or not win.winfo_exists():
            return
        face, ink = self._page()
        self._res_fig.set_facecolor(face)
        self._res_build_axes()
        self._res_pick = {}
        pts = sorted([p for p in self._series
                      if p.get("pressure") is not None],
                     key=lambda q: q["pressure"])
        models = [k for k, v in self._res_model_v.items() if v.get()]
        series = {m: [(p, self._resolve_point(p, medium=m)) for p in pts]
                  for m in models}
        for key, _pos, ylab, is_eos in RES_PANELS:
            ax = self._res_ax[key]
            ax.set_facecolor(face)
            for sp in ax.spines.values():
                sp.set_color(ink)
            ax.tick_params(colors=ink, labelsize=8)
            ax.tick_params(which="minor", length=3, colors=ink)
            drew = self._res_draw_panel(ax, key, pts, series, ink)
            if is_eos and drew:
                self._res_draw_eos(ax, key, pts)
            if not drew:
                ax.text(0.5, 0.5, "no points", transform=ax.transAxes,
                        ha="center", va="center", color=ink, alpha=0.55,
                        fontsize=9)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
            ax.set_xlabel("Pressure (GPa)", fontsize=9, color=ink)
            ax.set_ylabel(ylab, fontsize=9, color=ink)
            ax.grid(alpha=0.28, which="major")
            ax.grid(alpha=0.12, which="minor")
            ax.xaxis.set_minor_locator(AutoMinorLocator(4))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
            ax.yaxis.set_minor_locator(AutoMinorLocator(2))
            ax.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
        n_d = sum(1 for p in pts if self._pt_branch(p) == "D")
        lab = getattr(self, "_res_count", None)
        if lab is not None:
            try:
                lab.configure(text="%d point(s):  %d compression, %d "
                                   "decompression" % (len(pts),
                                                      len(pts) - n_d, n_d))
            except tk.TclError:
                pass
        # the key's height is what the panels have to make room for, so the
        # reserved strip is computed from how many rows it actually took
        rows = self._res_legend(pts, models, ink)
        self._tight(self._res_fig, pad=1.3, h_pad=2.0, w_pad=1.8,
                    rect=(0.0, 0.02 + 0.035 * rows, 1.0, 1.0))
        try:
            self._res_canvas.draw_idle()
        except Exception:
            pass

    def _res_legend(self, pts, models, ink):
        """One key for the whole grid, along the bottom.

        Six panels would carry six copies of the same key, and a per-panel
        legend on a plot this small lands on the data. The entries are built
        from proxies rather than scraped off one axis, because the EoS names
        differ between panels and the marker shapes belong to the branch,
        not to any single line.
        """
        from matplotlib.lines import Line2D
        h, lab = [], []
        media = []
        for p in pts:
            m = p.get("medium") or "Other"
            if m not in media:
                media.append(m)
        for m in media:
            col = self._res_color({"medium": m})
            h.append(Line2D([], [], ls="none", marker="o", ms=5.5,
                            color=col))
            lab.append("recorded, %s" % MEDIUM_LABELS.get(m, m))
        h.append(Line2D([], [], ls="none", marker="x", ms=6.0, mew=1.5,
                        color=(self._res_color({"medium": media[0]})
                               if media else ink)))
        lab.append("decompression")
        for m in sorted(models):
            h.append(Line2D([], [], ls="-", marker="o", ms=3.0, lw=1.1,
                            color=self._res_color({"medium": m})))
            lab.append("re-solved, %s" % MEDIUM_LABELS.get(m, m))
        seen = []
        for panel in RES_EOS_PANELS:
            for i, name in enumerate(sorted(fringe_materials.EOS_MODELS)):
                if name in seen:
                    continue
                if (self._res_eos_v.get(panel) or {}).get(name) is not None \
                        and self._res_eos_v[panel][name].get():
                    seen.append(name)
                    col = (ink if self._hc() else
                           OKABE_ITO[(len(MEDIUM_CHOICES) + i)
                                     % len(OKABE_ITO)])
                    h.append(Line2D([], [], ls="--", lw=1.2, color=col))
                    lab.append("EoS: " + name)
        if self.msv_v.get():
            h.append(Line2D([], [], ls="-", lw=0.9, color=ink,
                            marker="_", ms=6))
            lab.append("multiscale-variance 1 sigma")
        if not h:
            return 0
        ncol = min(4, len(h))
        leg = self._res_fig.legend(h, lab, loc="lower center", ncol=ncol,
                                   fontsize=7.5, frameon=False,
                                   handlelength=2.2, columnspacing=1.6,
                                   borderaxespad=0.2)
        for t in leg.get_texts():
            t.set_color(ink)
        return int(np.ceil(len(h) / float(ncol)))

    def _res_draw_panel(self, ax, key, pts, series, ink):
        """Model curves, then the recorded points on top.  Returns True when
        anything was drawn."""
        drew = False
        for i, (name, rows) in enumerate(sorted(series.items())):
            xy = [(p["pressure"], sol[key]) for p, sol in rows
                  if sol is not None and np.isfinite(sol[key])]
            if not xy:
                continue
            # A model curve takes the colour of the MEDIUM it stands for,
            # the same slot a point recorded under that medium would get.
            # Colouring it by draw order put an argon-Chen curve in the same
            # blue as argon-Dewaele points and made the two unreadable.
            col = self._res_color({"medium": name})
            dash = STEM_DASHES[(i + 1) % len(STEM_DASHES)] if self._hc() else "-"
            ax.plot([q[0] for q in xy], [q[1] for q in xy], ls=dash,
                    marker="o", ms=3.0, lw=1.1, color=col, zorder=2,
                    label=MEDIUM_LABELS.get(name, name))
            drew = True
        rows = [(p, self._resolve_point(p)) for p in pts]
        rows = [(p, s) for p, s in rows
                if s is not None and np.isfinite(s[key])]
        if not rows:
            return drew
        ax.plot([p["pressure"] for p, _s in rows], [s[key] for _p, s in rows],
                "-", color=self.app._muted_fg(), lw=1.0, zorder=3)
        comp = [(p, s) for p, s in rows if self._pt_branch(p) != "D"]
        deco = [(p, s) for p, s in rows if self._pt_branch(p) == "D"]
        if comp:
            ax.scatter([p["pressure"] for p, _s in comp],
                       [s[key] for _p, s in comp],
                       c=[self._res_color(p) for p, _s in comp],
                       s=RES_MS, zorder=5, edgecolors="none",
                       label="compression")
        if deco:
            ax.scatter([p["pressure"] for p, _s in deco],
                       [s[key] for _p, s in deco],
                       c=[self._res_color(p) for p, _s in deco],
                       s=RES_MS_D, zorder=5, marker="x", linewidths=1.5,
                       label="decompression")
        if self.msv_v.get() and key in ("t_s", "n_s"):
            self._res_error_bars(ax, key, rows, ink)
        self._res_pick[key] = [(p["pressure"], s[key], p) for p, s in rows]
        return True

    def _res_error_bars(self, ax, key, rows, ink):
        """Multiscale-variance bars on the sample panels.

        The measurement the variance is on is the sample optical path
        A = n_s * t_s, so it propagates onto t_s at fixed n_s and onto n_s at
        fixed t_s.  Both are one division; neither pretends to know a
        covariance the measurement never gave.
        """
        xs, ys, es = [], [], []
        for p, s in rows:
            sig = self._msv_sigma(p.get("label"))
            if sig is None or not np.isfinite(sig):
                continue
            n_s, t_s = float(s["n_s"]), float(s["t_s"])
            if key == "t_s":
                err = sig / n_s if n_s > 0 else None
            else:
                err = sig / t_s if t_s > 0 else None
            if err is None or not np.isfinite(err):
                continue
            xs.append(p["pressure"])
            ys.append(s[key])
            es.append(err)
        if xs:
            ax.errorbar(xs, ys, yerr=es, fmt="none", ecolor=ink, elinewidth=0.9,
                        capsize=2.5, alpha=0.75, zorder=4)

    def _res_draw_eos(self, ax, key, pts):
        """One dashed EoS curve per checked model, anchored on the lowest-
        pressure recorded point unless a right-click set another."""
        names = [n for n, v in (self._res_eos_v.get(key) or {}).items()
                 if v.get()]
        if not names:
            return
        cand = []
        for p in pts:
            sol = self._resolve_point(p)
            if sol is not None and np.isfinite(sol[key]):
                cand.append((float(p["pressure"]), float(sol[key]),
                             p.get("label")))
        if len(cand) < 2:
            return
        p_lo = min(c[0] for c in cand)
        p_hi = max(c[0] for c in cand)
        for i, name in enumerate(sorted(fringe_materials.EOS_MODELS)):
            if name not in names:
                continue
            meta = fringe_materials.EOS_MODELS.get(name)
            if meta is None:
                continue
            floor = meta["p_floor"]
            on = [c for c in cand if c[0] >= floor]
            if not on:
                continue
            over = self._res_anchor.get((key, name))
            hit = next((c for c in on if c[2] == over), None)
            if over is not None and hit is None:
                self._res_anchor.pop((key, name), None)     # stale -> auto
            pa, ya, _dk = hit if hit is not None else min(on,
                                                          key=lambda c: c[0])
            px = np.linspace(max(p_lo, floor), p_hi, 200)
            try:
                py = fringe_materials.thickness_from_volume_ratio(
                    ya, [fringe_materials.eos_volume_ratio(name, float(v), pa)
                         for v in px])
            except (ValueError, ZeroDivisionError, FloatingPointError):
                continue
            # EoS colours start past the media slots so a dashed curve never
            # takes the colour of a point it is drawn beside.
            col = (self._page()[1] if self._hc()
                   else OKABE_ITO[(len(MEDIUM_CHOICES) + i) % len(OKABE_ITO)])
            ax.plot(px, py, "--", color=col, lw=1.2, zorder=1,
                    label="%s (anchor %g GPa%s)"
                          % (name, pa, ", set" if hit is not None else ""))

    def _on_res_press(self, event):
        """Right-click a recorded point: make it that panel's EoS anchor.

        Right-clicking the anchor again releases it back to automatic, so the
        gesture is its own undo.
        """
        if event.button != 3 or event.inaxes is None:
            return
        panel = next((k for k, a in self._res_ax.items()
                      if a is event.inaxes), None)
        if panel is None or panel not in RES_EOS_PANELS:
            return
        pick = self._res_pick.get(panel) or []
        if not pick or event.xdata is None or event.ydata is None:
            return
        x0, x1 = event.inaxes.get_xlim()
        y0, y1 = event.inaxes.get_ylim()
        sx = abs(x1 - x0) or 1.0
        sy = abs(y1 - y0) or 1.0
        best = min(pick, key=lambda t: ((t[0] - event.xdata) / sx) ** 2
                   + ((t[1] - event.ydata) / sy) ** 2)
        if (((best[0] - event.xdata) / sx) ** 2
                + ((best[1] - event.ydata) / sy) ** 2) > 0.01:
            return                                   # not near enough a point
        label = best[2].get("label")
        names = [n for n, v in (self._res_eos_v.get(panel) or {}).items()
                 if v.get()]
        if not names:
            self._status("tick an equation of state before anchoring one.",
                         warn=True)
            return
        for name in names:
            if self._res_anchor.get((panel, name)) == label:
                self._res_anchor.pop((panel, name), None)
            else:
                self._res_anchor[(panel, name)] = label
        self.settings["fr_res_anchors"] = {"%s|%s" % k: v for k, v
                                           in self._res_anchor.items()}
        self._status("EoS anchor on %s: %s." % (panel, label))
        self._res_refresh()

    def _build_results_guide(self, win):
        """The results window's helper card, same shape as the pop-out's."""
        card = self.app._card(win, grow="both", width=self.app._em() * 38)
        card.pack(side="right", fill="both", expand=True, padx=(0, 10), pady=8)
        card.set_title(self.app._lf_header(card, "Guide", icon="book"))
        self._guide_body(card.body, RESULTS_GUIDE, width=38)
        return card

    # =======================================================================
    # pop-out
    # =======================================================================
    def popout(self):
        """Open Matthew's window: his layout and controls, SPARTA's paint.

        R11: the tear-off is no longer a second copy of the FFT figure, it
        is the original GUI -- his sidebar on the left in his order, his
        2x2 figure and navigation toolbar on the right, his View / Window /
        Settings menubar.  fringe_popout builds and owns every widget of
        it.

        ONE MODEL, TWO VIEWS.  The replica binds to THIS workbench: the
        same tk variables, the same methods, the same compute.  An edit in
        either view is an edit in the model, and both follow it.

        The contract this method has always had is unchanged -- the
        singleton guard above, the window remembered in `_popout` (so
        `_close_popout`, `sync_view_switch` and the theme chain reach it),
        the geometry memory in `fr_popout_geom`, and Escape or the X
        sending it home.
        """
        if self._raise_existing("_popout") is not None:
            return
        self.build()
        return fringe_popout.open_popout(self)

    def _close_popout(self):
        win, self._popout = self._popout, None
        # A window closed while it fills the screen must not save the
        # screen as its size: the view keeps the windowed geometry.
        view = getattr(self, "_po_view", None)
        geom = None
        if view is not None:
            try:
                geom = view.normal_geometry()
            except (AttributeError, tk.TclError):
                geom = None
        if win is not None:
            try:
                self.settings["fr_popout_geom"] = geom or win.geometry()
                win.destroy()
            except tk.TclError:
                pass
        self.sync_view_switch()

    def _mirror_popout(self):
        """Re-render the same panels into the pop-out's own figure.

        Mirroring by redraw rather than by sharing the Figure keeps each
        canvas at its own size; the compute is cached, so the second render
        costs only the drawing.
        """
        if self._popout is None or not self._popout.winfo_exists():
            return
        main_fig, main_axes = self.fig, self._axes
        main_twins, main_art = self._twins, self._artists
        main_labs = (self._nt_labels, self._schem_labels)
        try:
            self._po_fig.clear()
            # the main canvas keeps its own artists (restored in `finally`)
            self._artists = {"roles": {}, "lp": {}, "hover": {}}
            self._nt_labels = {}
            self._schem_labels = {}
            self.fig = self._po_fig
            self.ax_bg = self._po_fig.add_subplot(211)
            self.ax_s = self._po_fig.add_subplot(212)
            self._axes = {"Background": self.ax_bg, "Sample": self.ax_s}
            self._twins = {}
            # fresh subplots are born on matplotlib's white; the mirror has
            # to give them the page, exactly as _redraw's clear loop does,
            # or a tinted theme shows dark chrome around white panels
            face, ink = self._page()
            for ax in (self.ax_bg, self.ax_s):
                ax.set_facecolor(face)
                for sp in ax.spines.values():
                    sp.set_color(ink)
            rec = self._record()
            if rec is not None:
                p = self._stack_params(rec)
                upper = self._x_upper(p)
                for chan in CHANNELS:
                    self._draw_panel(chan, rec, p, upper)
            self._po_fig.set_facecolor(self._page()[0])
            self._tight(self._po_fig, pad=1.4, h_pad=2.4)
            self._fit_labels(self._po_canvas)
            self._po_canvas.draw_idle()
        finally:
            self.fig, self._axes = main_fig, main_axes
            self._twins, self._artists = main_twins, main_art
            self._nt_labels, self._schem_labels = main_labs
            self.ax_bg = main_axes["Background"]
            self.ax_s = main_axes["Sample"]

    def _build_popout_guide(self, win):
        """The pop-out's helper card.

        Same card shape as the formula editor's Guide, and the SAME content
        as the pane beside the plot -- one loader, one renderer, so the
        pop-out cannot end up documenting an older grammar than the window
        it was torn off.
        """
        card = self.app._card(win, grow="both", width=self.app._em() * 38)
        card.pack(side="right", fill="both", expand=True, padx=(0, 10), pady=8)
        card.set_title(self.app._lf_header(card, "Guide", icon="book"))
        self._guide_body(card.body, guide_text(), width=38)
        return card
