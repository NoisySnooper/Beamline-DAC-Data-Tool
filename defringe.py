"""
defringe.py  --  FFT-notch defringe for DAC raw spectra.

Thin compatibility shim over SPARTA's vendored fringe core
(`fringe_detect` + `fringe_notch`).  The public API, the defaults and the
numerical results are UNCHANGED from the v1.2.x-v1.4.8 implementation: notch
the dominant diamond-anvil interference fringe out of a raw intensity channel
(Sample or Background) and, for export, recompute absorbance from the two
defringed channels.

Numeric core vendored from `defringe_dac.py` (DAC Absorption Fringe Analysis).
    Source module : defringe_dac.py
    Author        : Matthew R. Diamond
    Repository    : github.com/matthewrdiamond/DAC-Absorption-Fringe-Analysis
    License       : vendored under MIT by permission of the author.

Faithful to `defringe_dac.py` (operates on RAW counts, per channel, then forms
the absorbance ratio):
  - wavenumber = 1 / lambda_nm           (nm^-1)
  - fringe frequency f_center = 2 * n*t   (n*t in nm)
  - peak search restricted to n*t in [FRINGE_NT_MIN_NM, FRINGE_NT_MAX_NM]
  - Fisher g-test gate: a channel with no confident fringe is left UNCHANGED.

NaN-safe: invalid points are dropped for the FFT (the uniform-wavenumber
resample bridges the gaps) and restored as NaN in the output, so results align
1:1 with the input. Uses only numpy + scipy + stdlib csv (no pandas).

WIDTH CONVENTION.  The legacy default is a FRACTIONAL notch half-width:
sigma_f = width_frac * f_center, i.e. the notch widens with the fringe
frequency.  That is what `width_frac` still means, and it stays the default so
every existing caller and settings file behaves identically.  The vendored core
works in ABSOLUTE n*t half-widths (sigma_f = 2000 * halfwidth_um, the same
+-reach at every peak, which is what real FFT fringe peaks look like); pass the
NEW `halfwidth_um` keyword to select that mode.  The two are related at a given
centre by  halfwidth_um = width_frac * nt_um.

New optional capabilities, all opt-in (defaults reproduce the legacy path):
    halfwidth_um        absolute +-reach in n*t um, overrides width_frac
    notch_centers_nm    notch several n*t centres at once
    notch_halfwidths_um per-centre absolute half-widths
    lowpass / lp_cutoff_um / lp_rolloff_um   soft high-cut on top of the notches
    corroborate         require 2-of-3 window agreement before notching
    log                 status callback for detection diagnostics
    cfg                 a fringe_config.FringeConfig to override the detector

NQT / Lee Lab port -- Jun 2026; re-cut onto the vendored core Aug 2026.
"""

import csv
import os

import numpy as np

from fringe_config import DEFAULT_CONFIG
from fringe_detect import (corroborate_nt, fft_initial_guess,
                           fft_peak_on_uniform_grid)
from fringe_detect import fisher_g_pvalue as _fisher_g_pvalue
from fringe_notch import defringe_fft_notch

# -- Constants (verbatim from defringe_dac.py) -------------------------------
NOTCH_WIDTH_FRAC  = 0.15      # default Gaussian-notch half-width / centre freq
FRINGE_NT_MIN_NM  = 15_000    # min n*t for FFT peak search (nm) ~ 15 um
FRINGE_NT_MAX_NM  = 100_000   # max n*t for FFT peak search (nm) ~ 100 um
FRINGE_PVALUE_MAX = 1e-4      # Fisher g-test p-value above which "no fringe"

_NM_TO_UM = 1.0e-3

#: Detector configuration reproducing this module's historical defaults.
#: (The vendored core's own defaults are the wider defringe_dac.py search band;
#: SPARTA's quick-look band has always been 15-100 um.)
LEGACY_CONFIG = DEFAULT_CONFIG.evolve(
    fringe_nt_min_nm=float(FRINGE_NT_MIN_NM),
    fringe_nt_max_nm=float(FRINGE_NT_MAX_NM),
    fringe_pvalue_max=float(FRINGE_PVALUE_MAX),
    min_detect_points=16,
)


def fisher_g_pvalue(periodogram):
    """Fisher's exact test for periodicity in a periodogram.

    Returns (g, pvalue). Small p-value => significant periodicity.
    Delegates to `fringe_detect.fisher_g_pvalue`, which carries the same
    overflow guard this module has always applied (p_terms capped at 30: the
    exact alternating sum is only stable for a strong fringe, and a near-flat
    periodogram is by definition not significant, so it scores p = 1).
    """
    return _fisher_g_pvalue(periodogram, cfg=LEGACY_CONFIG)


def _cfg_for(cfg, nt_min_nm, nt_max_nm, pvalue_max):
    """Detector config from the legacy keyword overrides (None = the default)."""
    base = LEGACY_CONFIG if cfg is None else cfg
    kw = {}
    if nt_min_nm is not None:
        kw['fringe_nt_min_nm'] = float(nt_min_nm)
    if nt_max_nm is not None:
        kw['fringe_nt_max_nm'] = float(nt_max_nm)
    if pvalue_max is not None:
        kw['fringe_pvalue_max'] = float(pvalue_max)
    return base.evolve(**kw) if kw else base


def detect_fringe_nt(wn_u, sig_u, nt_min_nm=None, nt_max_nm=None, cfg=None,
                     log=None, label=''):
    """Locate the dominant fringe frequency on a uniform-wavenumber signal.

    Core of `fft_initial_guess` (defringe_dac.py:1458). Divisive detrend
    `sig_u/trend - 1` (correct for raw counts with a multiplicative lamp
    envelope), Hann window, FFT, strongest prominent peak in the physical n*t
    range, Fisher g-test.

    Returns (nt_nm, pvalue): nt_nm is n*t in nm (fringe freq = 2*nt), or None
    when there is no frequency in range. pvalue small => confident periodicity.

    `wn_u` must already be a uniform ascending wavenumber grid; this calls the
    vendored detector's uniform-grid entry point directly, so the arithmetic is
    identical to the pre-v1.4.9 implementation (no 1/wn round-trip).
    """
    cfg = _cfg_for(cfg, nt_min_nm, nt_max_nm, None)
    _nt, info = fft_peak_on_uniform_grid(wn_u, sig_u, cfg=cfg, log=log,
                                         label=label)
    if info is None:
        return None, 1.0
    return float(info['nt_est']), float(info['fisher_pv'])


def _notch(wn_u, sig_u, wl, raw, nt_nm, width_frac):
    """Subtract the Gaussian-notched fringe band, mapped back to the wl grid.

    Legacy FRACTIONAL width: sigma_f = width_frac * f_center.  The vendored
    `defringe_fft_notch` normally takes an ABSOLUTE half-width in n*t um
    (sigma_f = 2000 * halfwidth_um); its `width_frac` keyword selects this
    legacy convention exactly, so the arithmetic is bit-identical rather than
    merely equal in real arithmetic (2000*(frac*nt/1000) != frac*2*nt in
    IEEE754).
    """
    clean, _nt_est, _filtered = defringe_fft_notch(
        wn_u, sig_u, wl, raw, nt_nm, width_frac=float(width_frac),
        cfg=LEGACY_CONFIG)
    return clean


def defringe_channel(wl_nm, counts, width_frac=NOTCH_WIDTH_FRAC,
                     nt_min_nm=None, nt_max_nm=None, pvalue_max=None,
                     halfwidth_um=None, notch_centers_nm=None,
                     notch_halfwidths_um=None, lowpass=False,
                     lp_cutoff_um=None, lp_rolloff_um=None,
                     corroborate=False, cfg=None, log=None, label=''):
    """FFT-notch defringe one raw intensity channel.

    nt_min_nm / nt_max_nm / pvalue_max override the module constants when
    given (None = the defringe_dac.py defaults, identical behavior).

    Returns a dict: {'clean', 'applied', 'nt_um', 'pvalue'}.
      clean   : defringed counts (same shape as input; a copy of `counts` when
                no fringe is removed). NaNs in the input are preserved.
      applied : True iff a confident fringe was found and notched.
      nt_um   : detected n*t in micron (None if not applied).
      pvalue  : Fisher g-test p-value of the detection (1.0 if not applied).

    This is the single source of truth for both the GUI and the CSV writer.

    Optional (new in v1.4.9; every default reproduces the legacy result):
      halfwidth_um        : absolute +-reach in n*t um.  Overrides width_frac.
      notch_centers_nm    : list of n*t centres (nm) to notch instead of just
                            the detected fundamental.
      notch_halfwidths_um : per-centre absolute half-widths, parallel to
                            notch_centers_nm.
      lowpass, lp_cutoff_um, lp_rolloff_um : soft high-cut on top of the notches.
      corroborate         : require 2-of-3 agreement between the narrow / wide /
                            full FFT windows before accepting the fringe.
      cfg / log / label   : detector config, status callback, log prefix.

    The returned dict also carries 'corroborated_by' (window names) when
    `corroborate` is on.
    """
    cfg = _cfg_for(cfg, nt_min_nm, nt_max_nm, pvalue_max)
    wl_nm = np.asarray(wl_nm, float)
    y = np.asarray(counts, float)
    if wl_nm.shape != y.shape:
        raise ValueError("defringe_channel: wl_nm and counts must have the same "
                         "shape (got %s, %s)" % (wl_nm.shape, y.shape))
    out = y.copy()
    result = {"clean": out, "applied": False, "nt_um": None, "pvalue": 1.0}
    if width_frac <= 0 and halfwidth_um is None:
        return result

    finite = np.isfinite(y) & np.isfinite(wl_nm) & (wl_nm > 0)
    if finite.sum() < cfg.min_detect_points:
        return result

    wl_f = wl_nm[finite]
    y_f = y[finite]

    # Uniform wavenumber grid (nm^-1), ascending; interpolation bridges any gaps
    # left by the dropped non-finite points.
    wn = 1.0 / wl_f
    sidx = np.argsort(wn)
    wn_s, sig_s = wn[sidx], y_f[sidx]
    wn_u = np.linspace(wn_s[0], wn_s[-1], len(wn_s))
    sig_u = np.interp(wn_u, wn_s, sig_s)

    _nt, info = fft_initial_guess(wl_f, y_f, cfg=cfg, log=log, label=label)
    if info is None:
        return result
    nt_nm = float(info['nt_est'])
    pvalue = float(info['fisher_pv'])
    result["pvalue"] = pvalue

    if corroborate:
        wide = (wl_f >= 1.0 / cfg.wide_hi) & (wl_f <= 1.0 / cfg.wide_lo)
        _w, info_w = (fft_initial_guess(wl_f[wide], y_f[wide], cfg=cfg, log=log,
                                        label=label)
                      if int(wide.sum()) >= cfg.min_detect_points else (None, None))
        narrow = ((wl_f >= cfg.fit_wl_min_nm) & (wl_f <= cfg.fit_wl_max_nm))
        _n, info_n = (fft_initial_guess(wl_f[narrow], y_f[narrow], cfg=cfg,
                                        log=log, label=label)
                      if int(narrow.sum()) >= cfg.min_detect_points else (None, None))
        corr = corroborate_nt([('narrow', info_n if info_n is not None else info),
                               ('wide', info_w), ('full', info)],
                              cfg=cfg, log=log, label=label)
        result['corroborated_by'] = list(corr['names'])
        if not corr['accepted']:
            return result
        nt_nm = float(corr['nt'])
    elif nt_nm <= 0 or pvalue > cfg.fringe_pvalue_max:
        return result

    if nt_nm <= 0:
        return result

    legacy_width = (halfwidth_um is None and notch_halfwidths_um is None
                    and notch_centers_nm is None)
    hw_um = (cfg.notch_halfwidth_um if halfwidth_um is None
             else float(halfwidth_um))

    clean_f, _nt_est, _filtered = defringe_fft_notch(
        wn_u, sig_u, wl_f, y_f, nt_nm, halfwidth_um=hw_um,
        notch_centers_nm=notch_centers_nm,
        notch_halfwidths_um=notch_halfwidths_um,
        lowpass=lowpass, lp_cutoff_um=lp_cutoff_um,
        lp_rolloff_um=lp_rolloff_um, cfg=cfg,
        width_frac=(float(width_frac) if legacy_width else None))

    out[finite] = clean_f
    result["applied"] = True
    result["nt_um"] = nt_nm * _NM_TO_UM
    return result


def defringe_curve(wl_nm, y, width_frac=NOTCH_WIDTH_FRAC, **kw):
    """Thin wrapper returning just the defringed array (for simple call sites)."""
    return defringe_channel(wl_nm, y, width_frac, **kw)["clean"]


# ---------------------------------------------------------------------------
# CSV export  (reduced schema -- no noise-floor / best-case / dispersion cols)
# ---------------------------------------------------------------------------
_NOTCH_CSV_BASE = ["Wavelength", "Dark", "Background", "Sample", "Absorbance"]
_NOTCH_CSV_NOTCH = ["Background_notch", "Sample_notch", "Absorbance_notch"]


def _result_stem(result):
    stem = "%s_%s_%s" % (result["dac"], result["sample"], result["pressure_str"])
    if result.get("branch_tag"):
        stem += "_" + result["branch_tag"]
    return stem


def write_notch_csv(result, out_dir, width_frac=NOTCH_WIDTH_FRAC,
                    nt_min_nm=None, nt_max_nm=None, pvalue_max=None,
                    bg_kw=None, s_kw=None, **kw):
    """Write one defringed CSV for an engine result dict.

    Notches the raw Sample and Background counts independently, then recomputes
    absorbance from the defringed (or, per channel, original) counts. The three
    `_notch` columns are written only when at least one channel had a confident
    fringe; an un-notched channel's column is left blank.

    Columns: Wavelength, Dark, Background, Sample, Absorbance
             [, Background_notch, Sample_notch, Absorbance_notch]
    Returns the path written.

    Any extra keyword is forwarded to `defringe_channel`, so the new
    absolute-width / multi-centre / low-pass / corroboration options are
    available here too.

    `bg_kw` / `s_kw` are optional PER-CHANNEL overrides layered on top of
    `kw` for the Background and Sample calls respectively.  The two
    channels carry different fringes and are cleaned independently, so a
    caller that picked notch centres or a low-pass cutoff per channel can
    say so here.  Both default to None, i.e. the two channels get the same
    keywords and the result is unchanged.
    """
    wl = np.asarray(result["wl"], float)
    dark = np.asarray(result["dark_c"], float)
    bg = np.asarray(result["bg_c"], float)
    s = np.asarray(result["samp_c"], float)
    bg_ds = bg - dark
    s_ds = s - dark

    with np.errstate(divide="ignore", invalid="ignore"):
        abs_straight = np.log10(bg_ds / s_ds)           # = +absorbance
    abs_straight[~np.isfinite(abs_straight)] = np.nan

    bg_ch = defringe_channel(wl, bg, width_frac, nt_min_nm, nt_max_nm,
                             pvalue_max, **dict(kw, **(bg_kw or {})))
    s_ch = defringe_channel(wl, s, width_frac, nt_min_nm, nt_max_nm,
                            pvalue_max, **dict(kw, **(s_kw or {})))
    has_notch = bg_ch["applied"] or s_ch["applied"]

    bg_for_abs = (bg_ch["clean"] - dark) if bg_ch["applied"] else bg_ds
    s_for_abs = (s_ch["clean"] - dark) if s_ch["applied"] else s_ds
    with np.errstate(divide="ignore", invalid="ignore"):
        abs_notch = np.log10(bg_for_abs / s_for_abs)
    abs_notch[~np.isfinite(abs_notch)] = np.nan

    # Un-notched channels write a blank column (all-NaN -> "").
    bg_notch_col = bg_ch["clean"] if bg_ch["applied"] else np.full_like(wl, np.nan)
    s_notch_col = s_ch["clean"] if s_ch["applied"] else np.full_like(wl, np.nan)

    header = list(_NOTCH_CSV_BASE)
    cols = [wl, dark, bg, s, abs_straight]
    if has_notch:
        header += _NOTCH_CSV_NOTCH
        cols += [bg_notch_col, s_notch_col, abs_notch]

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, _result_stem(result) + "_absorbance_notch.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for row in zip(*cols):
            w.writerow(["" if (isinstance(v, float) and np.isnan(v)) else v
                        for v in row])
    return path
