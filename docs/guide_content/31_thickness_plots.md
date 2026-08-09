THICKNESS PLOTS

<!-- v149: the mode, its detection n*t points, the decompression
     list and the separate C/D polylines are live in code. Two
     claims below remain PLAN-derived (Phase C) and are fenced in
     their own comments: solved t/n replacing n*t on this plot, and
     the thickness CSV export with its sidecar.
     R12: the pointer to the error-bar switch reads FRINGE > SESSION.
     The live card is Session (fringe_panel FRINGE_SECTIONS); the old
     text said FRINGE > SERIES, a section that no longer exists. -->

The sample changes thickness across a compression run. Much of the
absorption spectroscopy in a diamond cell depends on knowing how it
changed. The interference fringes already carry that information,
and the tool plots it directly.


WHERE IT LIVES

  Thickness (fringe n*t) is the third radio in PLOT > PLOT MODE,
  beside Overlay all traces and Inspect one trace. It draws one point
  per shown trace against the Series variable. The Thickness row
  under the radios picks the channels (S / B). 'mark misses' flags
  the traces the detector came back empty from. 'join points'
  unticked leaves a plain scatter. 'Thickness table...' lists the
  numbers behind the points.


WHAT IS PLOTTED

  Stage one plots n*t per channel. The fringe detection already
    produces that quantity, ahead of any stack model. n*t is the
    optical path: refractive index times physical thickness. The
    FFT measures it directly, from the raw counts alone.

  <!-- v149: PLAN Phase C, not yet in code - the shipped mode plots
       detected n*t only, and the axis label is fixed. Solved values
       live in the workbench's 'Results vs pressure...' view today.
  Once the fringe workbench has solved a trace, the solved physical
    thickness t and index n are used instead, and the axis label says
    which quantity is on screen.
  -->
  A point needs a detection or a solve. Every point here is
    measured.

  Point styles carry their own meaning:
      filled circle   sample channel
      open square     background channel
      decompression   drawn with the decompression line and marker
                      controls under 2D plot options


Compression and decompression are separate lines

  The tool draws each channel as two independent polylines. One
    polyline is the compression branch, one is the decompression
    branch. The two branches stay apart. The last compression point
    and the first decompression point keep the gap between them.
    That gap in the middle of a hysteresis loop is data.

  The tool draws four lines when both branches are present and both
    channels are shown: sample C, sample D, background C, background
    D. The legend names each one with its branch letter. The two
    decompression lines take the line style, width, opacity and
    marker from the Decompression traces controls. What makes a D
    curve recognisable on the overlay makes it recognisable here.

  The tool marks every trace where the detector missed. The mark is
    a small open down-triangle above the axis. 'mark misses' in
    PLOT > PLOT MODE turns the marks off. Those markers span both
    branches.


Marking the decompression branch

  A branch letter comes from three places, in this order. The _D tag
    in a file name wins, when the naming profile carries one. The
    built-in list for known experiments comes next. The D box beside
    each trace in DATA > TRACES comes last and always wins. A
    decompression list writes to that box.

  Decompression list... in DATA > TRACES reads a .csv or .txt of the
    decompression values. The file can carry a pressure_GPa column,
    or a plain column of numbers. The tool flags the matching traces
    D. It suits a dataset whose file names leave the _D tag out,
    which is most of them.

  The tool matches by value. Each listed value takes the nearest
    loaded trace within 0.05, and each trace takes one value. A
    list containing 18.8 takes the 18p8 point, and it leaves the
    18p7 point beside it alone. A value outside the tolerance is
    reported, in the log and in a dialog.

  A trace the list leaves out keeps the branch it already had.

  The tool remembers the list against {DAC}_{Sample}. A re-run, a
    rescan, a session switch or a reopened project applies it again
    by itself. The list travels inside saved projects. A list loaded
    for one cell leaves another cell's list alone.

  Everything downstream reads that one flag. It drives the overlay's
    legend tags, Only C / Only D, and the C/D-tagged CSV export. It
    drives the two polylines here. It drives the compression and
    decompression markers in the fringe workbench's results view.

  Multiscale-variance error bars turn on in FRINGE > SESSION. They
    estimate the spread of the thickness estimate across analysis
    scales. The tool draws them on the solved thickness and index
    panels of the results view. They are off by default, because each
    point costs about 35 ms to estimate.


READING IT

  A compression run drops n*t monotonically as the gasket thins. A
    point that jumps out of that trend usually means one of three
    things. The detection latched onto a harmonic in place of the
    fundamental. The sample moved out of the beam. The fringe faded
    and the number is noise. The fringe report in the log tells you
    which. The report in the Detection card tells you the same.
    Both carry the p-value and the corroboration count for that
    trace.

  Sample and background n*t differ. The background passes through the
    medium and the anvils, and it misses the sample. The difference
    between the two channels is the sample's own contribution. The
    solve inverts that quantity.

  A decompression branch that departs from the compression branch is
    a real result. The tool draws the two as separate lines for that
    reason. Use Only C / Only D in DATA > TRACES to read either
    branch alone.


EXPORT

  The plot exports through the normal EXPORT > EXPORT path, journal
    presets and WYSIWYG preview included. 'Thickness table...' in
    PLOT > PLOT MODE lists the numbers behind the points: n*t and its
    Fisher p-value per trace and per channel, in plot order.

  <!-- v149: PLAN Phase C, not yet in code:
  The thickness points export as their own CSV, additive to the
    existing outputs: nothing about the absorbance CSVs changes.
  A provenance sidecar records which quantity was plotted (detected
    n*t or solved t), the detection parameters in force, and the
    stack model when one was used.
  -->



USING THICKNESS IN A FORMULA

  The formula editor reads each trace's thickness as the column t.
  It is the sample channel's n*t, in micron, one value per trace. An
  absorption coefficient is one formula away:

      alpha = ln(10) * A / t

  It ships as the builtin 'Absorption coefficient' in cm^-1, with the
  um to cm conversion inside it. The plain ratio ships as 'A/t' in
  um^-1. See DATA > FORMULAS. t is NaN for any trace the detector
  missed. A formula that needs t says so on the status line.
