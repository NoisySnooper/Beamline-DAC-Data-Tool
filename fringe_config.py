"""
fringe_config.py -- frozen configuration object for the vendored fringe core.

Vendored from `defringe_dac.py` (DAC Absorption Fringe Analysis).
    Source module : defringe_dac.py
    Author        : Matthew R. Diamond
    Repository    : github.com/matthewrdiamond/DAC-Absorption-Fringe-Analysis
    License       : vendored under MIT by permission of the author.

This module has no counterpart in the source: it replaces the source module's
mutable globals (DIAMOND_MODEL, FIT_PHI0, FINE_WN_LO/HI, BAND_RES_FLOOR,
NOTCH_HALFWIDTH_UM, MSV_MODELS_TO_RUN, ...) with one immutable value object
that every vendored function takes explicitly.  Default values are the source
module's defaults, verbatim, with the source's inline comments preserved.

SPARTA adaptations
  * No module-level mutable state; no import side effects (the source module
    calls `matplotlib.use('Agg')` and `warnings.filterwarnings('ignore')` at
    import time -- neither is reproduced here).
  * The "lamp regime" that the source derives from a parsed folder date
    (FINE_CUTOVER_YEAR_MONTH) is an EXPLICIT value here: `fine_center_cm`,
    selectable via `FringeConfig.for_lamp_regime()`.
  * Python 3.8 compatible (no dict `|`, no `str.removeprefix/removesuffix`,
    no 3.9+ typing generics).

Unit zones (rule inherited from the source module: a value that multiplies
wn[1/nm] or divides wl[nm] is in nm; anything stored, exported or shown to a
human is in um).  Config fields carry their unit in the field name.
"""

from dataclasses import dataclass, replace

try:                                    # typing-only; keeps py3.8 happy
    from typing import Optional, Tuple
except ImportError:                     # pragma: no cover
    Optional = Tuple = None


# cm^-1 -> nm^-1.  The source spells this out at every use site
# (e.g. `WIDE_LO = 11000.0e-7`); named here so the conversion is one idiom.
_CM_TO_NM_INV = 1e-7

# Wavelength/thickness boundary factor: values that pair with wn[1/nm] live in
# nm, values stored/exported/displayed live in um (source module header).
NM_TO_UM = 1e-3

# Fine-window centre per lamp regime.  In the source these are picked by
# `_fine_window_for_date()` from a parsed folder date against
# FINE_CUTOVER_YEAR_MONTH = (2025, 11); SPARTA makes the choice explicit
# because SPARTA sessions are not organised by acquisition-date folders.
LAMP_REGIMES = {
    'pre_nov2025':   13500.0,   # May/Jun 2025 datasets  (FINE_CENTER_PRE_NOV2025_CM)
    'nov2025_plus':  11200.0,   # Nov 2025 onward        (FINE_CENTER_NOV2025_PLUS_CM)
}
DEFAULT_LAMP_REGIME = 'pre_nov2025'

DIAMOND_MODELS = ('constant', 'cauchy', 'oscillator', 'eremets')
DISPERSION_MODELS = ('constant_n', 'cauchy', 'linear_n', 'sellmeier',
                     'band_integral')


@dataclass(frozen=True)
class FringeConfig:
    """Immutable settings bundle for the vendored fringe core.

    Every vendored function that needs a tunable takes either this object or
    the individual value as an explicit argument.  Instances are frozen; make
    a variant with :meth:`evolve` (a thin ``dataclasses.replace``).
    """

    # -- Diamond refractive-index model (source: DIAMOND_MODEL / DIAMOND_PRESSURE_GPA)
    diamond_model: str = 'constant'          # 'constant'|'cauchy'|'oscillator'|'eremets'
    diamond_pressure_gpa: float = 0.0        # set per-spectrum from the parsed pressure

    # -- Fitting (source: FIT_PHI0, T_BOUNDS_NM)
    fit_phi0: bool = True                    # fit phi0 as a free parameter, else fix 0
    t_min_nm: float = 1000.0                 # thickness bounds: 1-200 um, in nm
    t_max_nm: float = 200000.0

    # -- FFT / fit wavelength range (source: FIT_WL_MIN_NM / FIT_WL_MAX_NM)
    fit_wl_min_nm: float = 600.0             # narrow window used for FFT + optimizer
    fit_wl_max_nm: float = 800.0

    # -- Corroboration windows (source: WIDE_LO / WIDE_HI / FULL_WN_LO / FULL_WN_CAP)
    wide_lo_cm: float = 11000.0
    wide_hi_cm: float = 18000.0
    full_wn_lo_cm: float = None              # None -> no lower cap on the full window
    full_wn_cap_cm: float = 21500.0

    # -- Fine window: `fine_width_cm` wide, centre picked by lamp regime
    fine_width_cm: float = 2000.0
    fine_center_cm: float = 13500.0

    # -- Fringe detection (source: FRINGE_NT_MIN_NM / MAX / FRINGE_PVALUE_MAX / NT_AGREE_TOL)
    fringe_nt_min_nm: float = 8000.0         # minimum n*t for the FFT peak search (nm)
    fringe_nt_max_nm: float = 300000.0       # maximum n*t for the FFT peak search (nm)
    fringe_pvalue_max: float = 1e-4          # Fisher g-test p above which "no fringe"
    nt_agree_tol: float = 0.15               # 2-of-3 cross-validation RELATIVE tolerance
    fisher_p_terms_max: int = 30             # SPARTA overflow guard, see fringe_detect
    peak_prominence_frac: float = 0.005      # find_peaks prominence / in-band max
    detrend_poly_deg: int = 4                # divisive polynomial detrend degree
    min_detect_points: int = 16              # refuse to detect on fewer finite points

    # -- Notch (source: NOTCH_HALFWIDTH_UM / LP_CUTOFF_UM_DEFAULT / LP_ROLLOFF_UM)
    notch_halfwidth_um: float = 3.0          # HALF-width (+-reach) in n*t um, ABSOLUTE:
                                             # sigma_f = 2000*halfwidth_um at every centre
    lp_cutoff_um: float = 15.0               # default low-pass cutoff in n*t um
    lp_rolloff_um: float = 2.0               # low-pass tanh roll-off width in n*t um

    # -- Band-integrated amplitude (source: BAND_RES_FLOOR)
    band_res_floor: bool = True              # floor the band half-width at the Hann
                                             # main-lobe width (anti-clipping)

    # -- Multi-scale variance (source: MSV_MODELS_TO_RUN / MULTISCALE_WIDTHS_CM)
    msv_models: tuple = ('constant_n', 'cauchy', 'linear_n')
    multiscale_widths_cm: tuple = (1000.0, 1500.0, 2000.0, 2500.0, 3000.0,
                                   4000.0, 5000.0)
    msv_min_window_points: int = 20          # per-window point floor
    fit_min_points: int = 20                 # window point floor for the tiered fits

    # ---- validation -----------------------------------------------------
    def __post_init__(self):
        """Reject impossible settings at construction time.

        SPARTA addition: the source module has no validation, so a typo in a
        CLI flag surfaces much later as a confusing ValueError or a silently
        wrong window.  Failing here names the offending field.
        """
        if self.diamond_model not in DIAMOND_MODELS:
            raise ValueError(
                "FringeConfig.diamond_model must be one of %s (got %r)"
                % (', '.join(DIAMOND_MODELS), self.diamond_model))
        if not (self.fit_wl_min_nm > 0 and self.fit_wl_max_nm > self.fit_wl_min_nm):
            raise ValueError(
                "FringeConfig: need 0 < fit_wl_min_nm < fit_wl_max_nm (got %r, %r)"
                % (self.fit_wl_min_nm, self.fit_wl_max_nm))
        if not (0 < self.fringe_nt_min_nm < self.fringe_nt_max_nm):
            raise ValueError(
                "FringeConfig: need 0 < fringe_nt_min_nm < fringe_nt_max_nm "
                "(got %r, %r)" % (self.fringe_nt_min_nm, self.fringe_nt_max_nm))
        if not (0.0 < self.fringe_pvalue_max <= 1.0):
            raise ValueError("FringeConfig.fringe_pvalue_max must be in (0, 1] "
                             "(got %r)" % (self.fringe_pvalue_max,))
        if self.nt_agree_tol <= 0:
            raise ValueError("FringeConfig.nt_agree_tol must be > 0 (got %r)"
                             % (self.nt_agree_tol,))
        if self.notch_halfwidth_um <= 0:
            raise ValueError("FringeConfig.notch_halfwidth_um must be > 0 (got %r)"
                             % (self.notch_halfwidth_um,))
        if not (0 < self.t_min_nm < self.t_max_nm):
            raise ValueError("FringeConfig: need 0 < t_min_nm < t_max_nm "
                             "(got %r, %r)" % (self.t_min_nm, self.t_max_nm))
        if self.fisher_p_terms_max < 1:
            raise ValueError("FringeConfig.fisher_p_terms_max must be >= 1 "
                             "(got %r)" % (self.fisher_p_terms_max,))
        if self.fine_width_cm <= 0 or self.fine_center_cm <= 0:
            raise ValueError("FringeConfig: fine_width_cm and fine_center_cm "
                             "must be > 0 (got %r, %r)"
                             % (self.fine_width_cm, self.fine_center_cm))
        for name in ('msv_models', 'multiscale_widths_cm'):
            val = getattr(self, name)
            if not isinstance(val, tuple):
                # frozen != deeply immutable; a list here would be shared state.
                object.__setattr__(self, name, tuple(val))
        for m in self.msv_models:
            if m not in DISPERSION_MODELS:
                raise ValueError(
                    "FringeConfig.msv_models: unknown model %r (known: %s)"
                    % (m, ', '.join(DISPERSION_MODELS)))

    # ---- derived views (nm^-1 wavenumber zone) --------------------------
    @property
    def t_bounds_nm(self):
        """(t_min_nm, t_max_nm) -- the source module's T_BOUNDS_NM tuple."""
        return (self.t_min_nm, self.t_max_nm)

    @property
    def wide_lo(self):
        """Wide-window lower bound in nm^-1 (source WIDE_LO)."""
        return self.wide_lo_cm * _CM_TO_NM_INV

    @property
    def wide_hi(self):
        """Wide-window upper bound in nm^-1 (source WIDE_HI)."""
        return self.wide_hi_cm * _CM_TO_NM_INV

    @property
    def full_wn_lo(self):
        """Full-window lower cap in nm^-1, or None (source FULL_WN_LO)."""
        return None if self.full_wn_lo_cm is None else self.full_wn_lo_cm * _CM_TO_NM_INV

    @property
    def full_wn_cap(self):
        """Full-window upper cap in nm^-1 (source FULL_WN_CAP)."""
        return self.full_wn_cap_cm * _CM_TO_NM_INV

    @property
    def fine_wn_lo(self):
        """Fine-window lower bound in nm^-1 (source FINE_WN_LO)."""
        return (self.fine_center_cm - self.fine_width_cm / 2.0) * _CM_TO_NM_INV

    @property
    def fine_wn_hi(self):
        """Fine-window upper bound in nm^-1 (source FINE_WN_HI)."""
        return (self.fine_center_cm + self.fine_width_cm / 2.0) * _CM_TO_NM_INV

    @property
    def freq_min(self):
        """FFT peak-search lower frequency bound: fringe freq = 2*n*t."""
        return 2.0 * self.fringe_nt_min_nm

    @property
    def freq_max(self):
        """FFT peak-search upper frequency bound: fringe freq = 2*n*t."""
        return 2.0 * self.fringe_nt_max_nm

    # ---- variants -------------------------------------------------------
    def evolve(self, **kw):
        """Return a copy with `kw` overridden (``dataclasses.replace``)."""
        return replace(self, **kw)

    def for_lamp_regime(self, regime):
        """Return a copy whose fine window is centred for `regime`.

        `regime` is a key of :data:`LAMP_REGIMES`.  This replaces the source
        module's date-magic (`_fine_window_for_date`, which reads a folder
        name / xlsx sidecar and compares against FINE_CUTOVER_YEAR_MONTH).
        """
        if regime not in LAMP_REGIMES:
            raise ValueError("unknown lamp regime %r (known: %s)"
                             % (regime, ', '.join(sorted(LAMP_REGIMES))))
        return self.evolve(fine_center_cm=LAMP_REGIMES[regime])


#: Module-level convenience instance.  Frozen, so sharing it is safe; use
#: ``DEFAULT_CONFIG.evolve(...)`` rather than mutating anything.
DEFAULT_CONFIG = FringeConfig()


def make_logger(log):
    """Normalise an optional `log` callable into a no-argument-safe sink.

    The source module prints diagnostics with bare ``print()``.  Vendored
    functions instead call ``log(message)``; passing ``log=None`` (the
    default everywhere) discards them.  SPARTA passes the session status
    callback.  A non-callable `log` raises rather than silently swallowing
    every diagnostic.
    """
    if log is None:
        def _sink(_msg):
            return None
        return _sink
    if not callable(log):
        raise TypeError("log must be callable or None (got %r)" % (type(log).__name__,))
    return log
