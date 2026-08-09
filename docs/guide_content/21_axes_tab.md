AXES TAB

This tab sets the coordinate system. It picks the unit on each axis,
the range, the ticks, and the box around the plot. The controls here
leave your data as it is.


AXES > AXIS

  Four dropdowns, one per axis, and the two flips.

  X axis: the spectral unit of the bottom axis. The tool converts
    the same data on the fly, at every redraw.

      wavenumber [cm-1] = 1e7 / wavelength [nm]
      photon energy [eV] = 1239.84 / wavelength [nm]

  Y axis: what overlay mode plots on the left axis. Pick absorbance,
    one of the raw counts channels (sample / background / dark), or
    'formula: <name>'. The formula entry appears once you pick a
    formula in DATA > FORMULAS. Pick 'absorbance' to go back.
    Absorbance is the default.
    The Quick Access strip can carry a second copy of this control.
    Both copies drive the same variable. The strip's gear picks which
    controls the strip carries.

  Top axis: mirror a second unit across the top of the plot.
    Wavenumber and energy are reciprocal in wavelength. Keep X min
    above 0 when you use them.

  Right axis: none, mirror the left Y, or % transmittance
    (T = 100 x 10^-A, absorbance mode only). 2D plots.

  Flip X / Flip Y: reverse either axis. Flip X is the usual move when
    you plot against wavenumber and think in wavelength.

  Label gap: distance in points from the X and Y axes to their
    labels. The 3D label gaps are separate, in PLOT > 3D PLOT
    OPTIONS.


AXES > LIMITS & SCALE

  X / Y / Z min and max. Leave a pair blank to fit the data. The Z
    row applies to 3D only.

  These boxes and the plot are two views of one state. A zoom fills
    the boxes with the range you zoomed to, so the zoom holds across
    redraws. You can zoom with a drag box, the wheel, the toolbar or
    the View pad. Typing a limit and pressing Return does the same as
    'Apply limits'. Right-click a box to clear it.

  Reset axes clears all six boxes. It turns auto-fit back on for
    every redraw. It is the way back after any zoom.

  Scale: linear or log, independently for X and Y. Log on absorbance
    drops non-positive points. Log on the spectral axis needs X min
    above 0.


AXES > TICKS

  Major / minor spacing per axis, in axis units. Blank means
    automatic. Z is 3D only. Return, or leaving a box, redraws.
    Right-click a box to clear it.

  Auto fills the spacing boxes with the values matplotlib uses right
    now. You can then nudge those values.

  Marks: out (ticks point outward), in (inward, the journal
    convention), or inout (both sides of the axis line).

  Minor ticks: draw them at all. The tool picks automatic positions
    when the minor spacing box is blank.

  Ticks on all sides (2D): mirror ticks onto the top and right
    spines.

  Tick length major / minor and Tick width, in points. Label font is
    the tick-number size.

  X format / Y format: fixed decimals (0 = integers, 0.00 = two
    places) or scientific notation. 'auto' leaves matplotlib's choice
    alone. 2D linear axes.

  Rotate X: rotate the X tick labels 0 to 90 degrees in 15-degree
    steps. Use it for dense wavenumber ticks.


AXES > FRAME & GRID

  The tool styles Major grid and Minor grid independently. Each has
    its own color, pattern, width and opacity. 'auto' color follows
    the theme. The minor grid needs minor ticks on to have something
    to draw against.

  Spines: the three controls that style the box around the plot, in
    one place.
      Axis line   thickness in points
      Axis color  outer spine color in 2D, box edge color in 3D;
                  'auto' follows the theme
      Hide top/right spines  the two-spine journal look

  Journal presets set grid off, spines hidden, ticks in and minor
  ticks on. 'Clean style (no grid, thin spines)' in EXPORT > FIGURE
  does the same tidy-up. It leaves your fonts and sizes alone.
