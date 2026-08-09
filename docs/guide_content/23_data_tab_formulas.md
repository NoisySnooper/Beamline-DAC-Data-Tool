DATA TAB

Three sections act on the numbers: the smoothing pipeline, which
traces are shown and which branch they belong to, and your own
formulas. Fringe removal now heads the Fringe tab, next door, beside
the workbench that reads the same transform by hand.

Three things in this program are called data. The DATA TAB is this
fourth tab of the right panel. The DATA TABLE is the spreadsheet
drawer under the plot. A SESSION TAB is one of the browser-style
tabs above the plot.


DATA > SMOOTHING

  Show smoothed: draw the smoothed curve over the raw one in 2D, or
    smooth each ridge in 3D. The raw trace stays visible underneath,
    at the opacity below.

  Raw opacity: how much of the raw trace shows through, 0 to 1.
    Right-click resets it.

  No raw background: hide the raw trace (sets Raw opacity to 0).
    Unticking restores the previous opacity.

  Smoothing settings...: the whole filter. The tool runs five steps
    top to bottom on the raw absorbance. Removed points become gaps
    (NaN).

    1. Saturation cutoff
       The tool drops any point with A above the ceiling. The path
       there is opaque and the signal is in the noise.
         drop where A > Max absorbance
       Max absorbance: default 4.0. Higher keeps more.

    2. Density filter
       The tool blanks stretches where too few real points survive.
         in each Window: if (#finite) < Min valid -> blank the window
       Window (pts): default 50, the span checked at once.
       Min valid pts: default 10.
       The tool clamps the window to the length of the trace. An
       over-large window on a short trace still runs.

    3. Hampel despike
       The tool kills isolated spikes such as cosmic rays and
       single-pixel glitches. It keeps the shape of real peaks.
         replace where |A - med| > Sigma * 1.4826 * MAD
       Window (pts): default 5, half-width of the local median.
       Sigma threshold: default 3.0. Lower is more aggressive.

    4. Savitzky-Golay (split)
       The main smoother. The tool least-squares fits a low-order
       polynomial to a sliding window and keeps the fitted center
       point. This preserves peak shape better than a moving
       average. The tool splits the spectrum at a wavelength, so
       each side gets its own window and order.
       Split at (nm): default 600, the boundary between the two
         grating / detector regimes. The split always uses
         wavelength, whatever the display axis shows.
       Left window / Left poly: default 101 / 2 (below the split).
       Right window / Right poly: default 51 / 2 (above it).
       Steps 1, 2, 3 and 5 are the Igor values verbatim.
       This step always runs. Steps 1, 2, 3 and 5 have Enable boxes.

    5. Jump filter
       Final cleanup for step discontinuities. They appear where
       segments meet, and where a filter blanked a run.
         drop where |dA| > Max jump within Step dist (+/- Buffer)
       Max jump (abs): default 0.2.
       Step dist (pts): default 1.
       Buffer (pts): default 2, trimmed each side.

    The tool clamps point-count fields to sane bounds when it
    parses them. The filters then always see a legal value. The
    live preview redraws as you type. Cancel and Escape both revert
    to the values you opened with.

  Reset sits beside 'Smoothing settings...'. It restores the
    defaults and clears the smoothing cache.

  Smoothing is a display and export filter. The absorbance CSVs a
    Run writes stay as they are. 'Export CSV... > Smoothed CSV'
    writes the smoothed columns.


DATA > TRACES

  One row per loaded point. The check shows the trace. The D box
    marks the trace decompression. A D trace takes the Decompression
    traces style. It also sits after the compression branch in the
    legend.

  A colored dot before a row means a quick quality check fired.
    Hover it for the reason. The checks are cheap and conservative.
    They flag a trace for a second look.
      no absorbance at all, naming which raw channels did arrive
      points at or above A = 4: likely saturated or a blocked beam
      negative absorbance over more than 5% of the trace: check the
        channel pairing or lamp drift

  Double-click a row to solo that trace. Double-click again to
    restore the others.

  All / None show or hide everything. Only C hides every D trace.
    Only D hides every C trace. Use them to read one branch's trend
    alone.

  Decompression list... reads a .csv or .txt of decompression
    values. The file can carry a pressure_GPa column, or numbers
    separated by commas, spaces, tabs or newlines. 'p' may stand for
    the decimal (1p39 = 1.39). The tool ignores header lines and
    stray words. Each value takes the nearest loaded trace within
    0.05. Each trace takes one value. A value outside the tolerance
    is reported. The list is remembered per {DAC}_{Sample}, so a
    re-run or a reopened project applies it again by itself. The ?
    button spells the format out.

  Export D list (CSV) by selection writes the values currently
    flagged D back out. It uses the same format Decompression list
    reads.

  Save C/D-tagged CSVs... writes the CSVs a Run writes: one per
    loaded point, same columns. It puts the branch letter in every
    file name ({DAC}_{sample}_{value}_C_absorbance.csv, or
    ..._D_...). C and D come from the state on screen: the
    auto-detected branches plus any D boxes you ticked. One
    provenance sidecar covers the batch.

  A branch letter comes from three places, in this order. An
    explicit _C / _D tag in the filename wins. The tool then
    recognises ten historical experiments from a built-in list. The
    D box is yours to tick.


DATA > FORMULAS

  Your own quantities, written as ordinary arithmetic over the
  loaded columns and shown as real typeset formulas.

  The columns
    S    Sample counts, raw, dark not subtracted
    B    Background / reference counts, raw
    D    Dark counts, the detector baseline
    wl   Wavelength in nm - the grid every column shares
    A    Absorbance as the pipeline computes it,
         -log10[(S - D)/(B - D)]
    Sf   Sample counts, FFT-defringed        (needs Defringe on)
    Bf   Background counts, FFT-defringed    (needs Defringe on)
    Af   Absorbance from the defringed channels (needs Defringe on)
    As   Absorbance after the smoothing filter (needs Show smoothed)
    t    Optical thickness n*t of the SAMPLE channel, in um, from the
         fringe detection. NaN wherever the detector missed. NaN
         propagates and draws as a gap.

    Long spellings resolve too: sample, background, dark, wavelength,
    absorbance, and thickness or nt_um for t. Any case works.

    t is one value per TRACE. It enters a formula as a constant over
    that trace's wavelength grid. It scales a spectrum uniformly. t
    is the sample channel's n*t. The background channel's fringe is
    a different quantity, and it keeps its own name.

    A variant whose processing is switched off is absent. A formula
    that needs it says so on the status line under the list. The
    tool skips those traces and leaves a gap.

  Writing one
    Use numbers, parentheses, and these operators:

      + - * / **

    The functions are log10, log, exp, sqrt, abs, minimum and
    maximum. Click any symbol under the Expression box to insert it
    at the cursor. Exponents are capped at 8, because a typo there
    turns into an unbounded computation.

    Examples:
      100 * (S - D) / (B - D)     transmittance in %, from raw counts
      log((B - D) / (S - D))      optical density in base e
      A - As                      what the smoother removed
      A - Af                      what the notch removed
      A / t                       absorbance per unit thickness

  The builtins
    Absorbance and Transmittance ship read-only. Both are spelled out
    in formula form, so you can read exactly what the pipeline
    computes. Open one and press Duplicate to start a new formula
    from it.

    Absorption coefficient: alpha = ln(10) * A / t, in cm^-1. The um
      to cm conversion is inside the builtin, which is written
      log(10) * A / (t * 1e-4). Hand it t in um, as the column always
      is, and read cm^-1 off the axis. A hand-written version goes
      wrong on that factor of 10^4.
    A/t: absorbance per unit thickness, in um^-1. It gives the raw
      ratio, at the units the columns carry.

    Both need t. Both are NaN for any trace the detector missed.
    The status line under the list says so.

  The row dot is the one control that matters. It plots that
    formula: the Y axis list gains 'formula: <name>', labelled with
    its name and unit. It is also what View / Edit, Delete and Save
    formula CSVs act on. One picker drives them all. Pick
    'absorbance' in the Y axis list to go back. The row on the plot
    right now is tinted. Its name is bold. It carries an 'on plot'
    tag.

  New / Edit opens the two-panel editor. The left panel holds the
    name, unit, expression and an optional LaTeX override. The right
    panel holds a Guide with worked examples and the live column
    table. Leave the LaTeX on 'auto'. The tool then derives the
    picture from the expression itself, so the two always agree. The
    problems
    list and a live min / max / NaN preview of the first shown trace
    update as you type. Save stays off until the formula is clean.

  Name and unit: the name labels the Y axis and names the CSV
    column. The unit is free text printed after the name. Leave it
    empty for a bare ratio.

  Safety. A formula is arithmetic. The tool parses the text and
    checks it against a whitelist before anything runs. The
    whitelist holds the columns, the listed functions and the
    arithmetic operators. The tool rejects everything else at that
    check. Division by zero, log of a negative and overflow return
    NaN, which the plotting and export layers expect.

  Save formula CSVs... writes the picked formula for every loaded
    trace as separate two-column files, {trace}_{key}.csv. Each file
    holds Wavelength_nm and the formula, with the expression in the
    header comments. The absorbance CSVs a Run writes stay untouched.
    One provenance sidecar covers the batch.
