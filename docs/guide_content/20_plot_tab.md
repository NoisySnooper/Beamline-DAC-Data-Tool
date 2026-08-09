PLOT TAB

This tab sets what is drawn and how the traces are arranged. It has
four sections, each folding shut by its title. Type a control's name
into 'Find a setting' at the top of the panel. The right section then
opens itself.


PLOT > PLOT MODE

  Series variable: what the number in each file name means. Pick one
    of the presets: Pressure GPa, Temperature K, Dose Gy, Time min.
    Pick Custom... to type your own name and unit. The colorbar
    label, legend entries, 3D depth axis, inspect title and the data
    table header all follow the choice. Only the labels change. The
    parsed values, the CSV columns, the output file names and the
    provenance keys stay as they are. Older outputs and scripts keep
    working.
    The star beside the custom boxes saves that name and unit pair
    into the dropdown. A field run or a pH run is then one pick next
    time. Click the lit star to remove it. Leave the unit blank for a
    unitless variable, and values print as bare numbers.

  Auto rescan plus every N s: the unattended top-up. It is one timer
    for the whole program. The interval runs from 5 to 3600 s,
    default 30, remembered between launches. It waits for the first
    Run. It fires while the tool sits idle, and it re-runs the
    folder when new files appeared.
    While it is armed, the status line under the plot reads
    'auto-rescan: N s'. A tick that finds new files says so in a
    brief toast. Changing the interval while it is on restarts the
    timer. Rescan and F5 keep working by hand.

  Overlay all traces: every shown trace on one set of axes. This is
    the publication view. The Y axis row in AXES > AXIS picks what it
    plots on Y.

  Inspect one trace: one measurement, diagnostically. Sample,
    Background and Dark counts draw on the left axis, and its
    Absorbance draws on the right. It shows the signal behind an
    absorbance curve. In a healthy measurement the background sits
    above the sample across the range. Both channels sit under the
    detector ceiling.
    Inspect picks the trace. Channels S / B / D / Abs picks which of
    the four curves are drawn. The right-hand absorbance axis takes
    the theme styling the main axis takes.

  Thickness (fringe n*t): the third radio, and the one mode that
    draws one point per shown trace in place of a spectrum. The
    point is the optical thickness n*t against the Series variable.
    The value is the fringe frequency the defringe detector finds
    in the raw counts. It runs on the loaded data alone. The tool
    marks a trace where the detector missed. Sample points are
    filled, background points are open, and D traces keep their own
    style.
    The Thickness row below picks the channels drawn (S / B). 'mark
    misses' puts a small open triangle above the axis wherever the
    detector searched and missed. 'join points' unticked
    leaves a plain scatter. 'Thickness table...' lists the numbers
    behind the points, n*t and p-value per trace. The Thickness plots
    view holds the full story.

  Absorbance readout at...: type a wavelength in nm. You get a table
    of the absorbance at that point for every shown trace. It is the
    quick way to track a band across a series. 'on click' does the
    same from a left-click anywhere on a 2D plot.


PLOT > STACKED & 3D

  Mode
    off         every trace on a shared baseline.
    2D stacked  each trace shifted up by Offset/step.
    3D ridge    x = wavelength, depth = series value, height =
                absorbance. A filled joyplot.
    3D shape    the same 3D scene with the ridges joined into one
                continuous surface, orbited live. It is the
                'surface' 3D look promoted to a mode of its own.
                Every 3D plot option still applies: camera,
                stretch, label gaps, axis ranges. Graphics in
                PLOT > 3D PLOT OPTIONS sets how finely it draws.
    Keys 1 / 2 / 3 / 4 switch between them. The tool ignores those
    keys while you type in a box.

  Offset/step: in 2D stacked, the vertical gap added between
    successive curves. In 3D ridge with 'Even rank spacing' on, how
    far apart the ridges sit along the series axis. Default 0.2.

  Auto: picks a step that spreads the shown ridges evenly. It turns
    'Even rank spacing' on to hold that spacing. In 2D stacked it does
    a different job. There it measures the gap the shown curves need
    and writes that gap into Offset/step.

  Auto separation (2D stacked): the tool sets the 2D stacked gap from
    the shown traces. The tool compares each curve with the next one.
    The gap it picks clears the largest overlap between them by 6
    percent. Every pair of curves then stays apart. The tool prints
    the gap it used beside the box. Clear this box to use your own
    Offset/step value. It is on by default.

  Label each ridge with its value: writes the series value beside
    each ridge.


PLOT > 2D PLOT OPTIONS

  Line style: solid / dashed / dotted / dash-dot for the 2D curves.

  Decompression traces is a sub-heading inside this section. It
    holds the same style controls as the compression curves, applied
    to D traces alone. The default look is dashed, at the compression
    width. That default makes a compression and decompression pair
    readable in one panel.
      Style D traces apart  the master switch. Untick it and a D
                            trace looks like a C one.
      Line style            solid / dashed / dotted / dashdot /
                            custom / bicolor.
      Pattern               the dash sequence in points, on/off
                            alternating ('6, 3'), used while Line
                            style is 'custom'.
      Second color          the stripe's second ink. This row
                            appears only while Line style is
                            'bicolor'. 'auto' takes the
                            high-contrast ink for the plot page:
                            white on a dark page, near-black on a
                            white one. You can also name a color or
                            paste a hex code.
      Width                 points; blank follows Curve line above.
      opacity               0 to 1, on the same row as Width.
      Marker                a point marker on every D trace, so the
                            branch survives grayscale and small
                            print. Its size box sits beside it, in
                            points.
    Bicolor keeps the trace's own color and dashes a second color
    over it, half and half along the curve. A decompression run then
    stands out in a crowded overlay before you read the legend. The
    stripe length follows the line width. It draws in overlay, 2D
    stacked, the 3D trace lines and the Thickness plot. On a FILLED
    3D ridge, which shows only its edge, bicolor draws dashed.
    These controls apply in overlay, stacked and 3D. The legend
    keys reflect them, and a bicolor trace gets a hatched two-color
    swatch. The tool remembers every one between launches. The
    defaults reproduce the old look exactly: dashed, same width,
    opaque, plain line.

  Inset zoom: magnify an X range in a corner panel, for an
    absorption-edge close-up. Type the two wavelengths, then pick the
    corner and the size fraction (0.15 to 0.5). The tool outlines the
    zoomed region on the main plot. 2D overlay and stacked.

  Defringe compare (selected trace): with df ticked, click a curve
    to select it. The tool draws its pre-defringe absorbance behind
    it, as a gray dashed line. You then see what the notch removed.

  Curve line: Line width for the 2D curves, in points. Type an exact
    value or drag. Right-click resets it.

  Aspect ratio: the shape of the plot box. Pick Auto (fill the
    area), 1:1, 4:3, 3:2, 16:9, or custom W:H.

  View: a pan pad with Fit in the middle. Hold a button to repeat.
    Fit X / Fit Y refit one axis. Zoom +/- acts about the view
    center, on X, Y or both.
    Keyboard: arrows pan, the +/- keys zoom, and 0 fits. The tool
    ignores those keys while you type in a box. Drag a box on the
    plot to
    zoom into it. The wheel zooms at the cursor.


PLOT > 3D PLOT OPTIONS

  Camera
    Elevation (0-90 degrees above the horizon), Azimuth (-180 to
    180), Zoom (0.5 to 2.0, camera distance).
    View presets Iso / Front / Side / Top snap the camera. Fine-tune
    with the sliders. Reset returns to the default.
    Arrow keys orbit three degrees a step. The +/- keys zoom and 0
    resets. The mouse wheel drives the camera.

  Box & panes
    Box frame picks which of the twelve box edges draw:
      open front  the corner facing you stays open
      3 axes      the classic matplotlib look: the x, y and z tick
                  axes facing you. The default. It draws on top at
                  every camera angle, so ridge walls cannot hide it
      closed      all twelve edges
      floor only  the four bottom edges
      no top      everything but the top rim
      none        no edges at all
      custom      unlocks the Edges checkboxes
    Edges (active only in 'custom'): 3 axes / floor / posts / top /
      open front. '3 axes' can be forced on top of any mix.
    Frame shade: edge color. 'auto' follows the theme's axis color.
      Lighter shades recede into the page.
    Frame width: edge thickness.
    Panes: the three back walls. Pick grid / white / theme / light
      gray / off, with their own opacity. 'white' is the clean print
      look, and dark themes keep dark panes. Gridline styling itself
      lives in AXES > FRAME & GRID.

  Ridges
    3D look: walls + traces (filled ridges with outlines), walls only
      (filled, no outline), traces only (outlines, no fill, the clean
      line joyplot), surface (one continuous sheet).
    Surface joins adjacent traces into a single gradient sheet:
      wavelength across, the series value into the page, the plotted
      channel as height. The height between two measured values is a
      straight line. The sheet passes through every trace you loaded
      and claims nothing between them. The tool trims wavelengths
      that any shown trace is missing off both ends first. It bridges
      a dropout inside a trace from that trace's own neighbours, so
      the sheet has no holes.
      The sheet takes its colour from the colormap the way the ridges
      do, by series value, so the colorbar still reads correctly.
      The Z limits, Log Z, Clip Z spikes, Even rank spacing, Project
      and 3D detail all still apply. The outline controls and Fill
      opacity have no effect here. A sheet has no outline, and a
      see-through sheet shows only its own far side.
      Three shown traces are the minimum. Below three, the tool draws
      the ridge outlines and the log says why.
      For speed the tool draws the sheet at a coarser cell size than
      the grid behind it. The STL export in EXPORT > 3D PRINTING
      always uses the full grid.
      Picking '3D shape' in the Mode box draws the same
      sheet without changing the 3D look, so you can flip between the
      ridges and the surface with keys 3 and 4.
    Color traces by colormap: outline each ridge in its trace color
      in place of flat black or white. It pairs well with 'traces
      only'.
    Fill opacity: transparency of each filled wall.
    3D line width / 3D line color / 3D line opacity: the outlines.
      'auto' color is white on dark themes and black on light.
    Project: drop a faint shadow of every trace onto the back wall,
      which reads as a 2D overlay, onto the floor, or onto both.
    Log Z (absorbance) scale: the tool log10-transforms the values
      and relabels the ticks as powers of ten. It drops values at
      or below zero.
    Clip Z spikes (99th pct): cap the automatic Z range at the 99th
      percentile. It holds the ridge scale steady under a saturated
      spike. Typed Z limits always win.
    Even rank spacing: place ridges at 1, 2, 3 and so on, whatever
      the real gaps between series values are, so crowded runs stay
      readable. Uncheck it to place each ridge at its true value.

  3D shape
    Everything the continuous sheet needs, in one place. Reach it
    either by picking 'surface' as the 3D look above or '3D shape' in
    the Mode box. It has its own controls, listed here.
    Graphics: one control for quality against speed. It has five
      notches: potato, low, medium, high and best. potato draws the
      fewest polygons and orbits the fastest. best draws every
      polygon in the grid. medium is the default. The dial moves
      two things together. It sets how finely the tool draws the
      sheet, and how finely it draws the stand-in you orbit.
      Performance mode holds the dial at low, and the panel says so
      under the box. The exported solid always uses the full grid.
    Smooth polygon edges (antialias): antialias each polygon of the
      sheet on its own. On softens every polygon outline and opens
      hairline seams between neighbours. Off draws the sheet solid,
      and off is the default.
    Draft quality while rotating: draw a coarser sheet for the
      length of a drag. The full sheet returns on release. The
      draft follows the relief, mesh, underside and antialias
      settings, at a lower resolution. It is on by default.
    Interpolation: how the sheet crosses the gap between two
      measured traces. Straight takes the shortest line, so every
      drawn height is one your data supports. Smooth rounds every
      crease with a monotone cubic, which stays between the two
      measurements it sits between. The same choice feeds the
      exported STL grid, so the object you print is the surface you
      saw. The provenance sidecar records which one ran. The [?]
      beside it opens the formulas.
    Mark measured traces: draw every measured trace on the sheet. Each
      line sits at its own series value. The lines show the heights
      the tool measured. The sheet between two lines is interpolation.
      The 3D line color, 3D line width and 3D line opacity in Ridges
      style these lines. 'auto' picks black or white per trace. The
      tool picks whichever ink carries more contrast against the sheet
      colour under that trace. It is on by default.
    Relief shading: light the sheet from the north-west like a relief
      map, so ridges and valleys read as shape. The color still means
      what the colorbar says. The shading only lifts and drops its
      brightness. It tracks the box aspect, so stretching an axis
      relights the shape you are looking at. It is on by default.
    Relief strength: how far that shading lifts and drops the
      brightness, from 0 to 1. 0 leaves the colors flat and 1 is
      the full modulation. 0.6 is the default, which holds the
      color spread inside one row under the color step between two
      measured traces.
    Show mesh: draw the edge of every polygon in the sheet, in the
      theme's own text color. The line count follows the Graphics
      notch. It is off by default.
    Fill underside: close the sheet into a solid, with walls down all
      four sides and a flat base. The surface then reads as the
      object the STL export prints. It is on by default. Untick it
      for the open sheet alone. Every wall draws at every angle, so
      orbiting the figure never opens a face.
    Fill color: what those walls and that base are painted. 'auto'
      takes the sheet's own edge colors and dims them, so the sides
      read as the sides of this data. 'theme bg' sinks them into the
      page and leaves the silhouette. Any other entry paints all five
      faces one flat color, exactly as picked.

  Layout & speed
    Stretch X / Y / Z: fan the box out along the spectral, series or
      height axis. The data keeps its spacing. Each has its own
      reset.
    Label gap X / Y / Z: distance from each axis's numbers to its
      title. Raise it when an axis name overlaps the tick numbers.
    3D detail (points/ridge): points kept per ridge while rendering
      3D, 200 to 3000. Lower is much faster to rotate on big spectra.
      2D plots and every export always use the full data.
    Performance mode (faster 3D): decimates harder and skips the raw
      ghost. It is off by default. 2D and exports keep the full
      data. The app-wide Performance mode, in the top bar's
      Settings panel, is a different control.
    Reduce motion (no UI animation): turns off the small one-shot
      interface animations.


PLOT AREA > SESSION TABS

  The browser-style tabs above the plot. Each is an independent
    session with its own data, folders, settings and undo history.
    '+' opens a blank tab. Running or loading data names the tab
    after the folder. Double-click renames. The x or a middle-click
    closes. Ctrl+T opens a new tab, Ctrl+W closes, and Ctrl+Tab /
    Ctrl+Shift+Tab cycle.
    A blank tab lists your recent runs for one-click reopening. NUKE
    clears every tab back to one.


PLOT AREA > DATA TABLE

  The Data table button at the bottom right opens a spreadsheet
    drawer under the plot, for the selected trace. Ctrl+D does the
    same. The columns are Wavelength_nm, Wavenumber_cm-1,
    Absorbance, Dark, Background and Sample. Absorbance_defringed and
    Absorbance_smoothed join them when those toggles are on. Drag the
    top edge to resize.
    'Copy all (TSV)' pastes straight into Excel. 'Open in Excel'
    writes a CSV and opens it. Ctrl+C copies the selected rows.

  The status line on the same bar reads the active tab, the plot
    mode and the preset. It also reads the shown trace count. While
    the poll timer is armed it reads 'auto-rescan: N s' too.
