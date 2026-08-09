STYLE TAB

This tab decides how the figure looks. It holds the color, the type,
the labels, the key, and the reference lines drawn over the data.


STYLE > COLORS & COLORMAP

  Filter: type to narrow the colormap list (try 'blu', 'div',
    'gray'). Clear the box to show all maps.

  Colormap: the color scale spread across the traces, with a live
    swatch under it. The Crameri maps (batlow, roma, hawaii, lajolla)
    are perceptually uniform and color-blind safe. batlow is the
    default. The two arrow buttons on the same row step back and
    forward through the list. The keys [ and ] do the same from
    anywhere.

  Set as default: remembers this map and applies it at every launch.
    The star marks the map that is the saved default. Click the star
    again to clear it.

  Reverse colormap: flip which end of the scale the highest value
    takes.

  Shades: how the tool applies the map. 'continuous' gives each trace
    the exact color of its value. 'discrete' cuts the map into Levels
    steps and puts each trace on a step. 'auto' uses discrete for
    eight traces or fewer. Above eight traces 'auto' uses continuous.
    The colorbar shows the same steps. The default is 'auto'.

  Levels: the number of steps the discrete mode cuts the map into.
    The range is 2 to 24 steps. The default is 6. This row works with
    Shades on 'discrete'.

  Trace colors...: opens a list of the shown traces. Click a swatch
    to set that trace's color by hand. A set color wins over the
    colormap in every 2D and 3D view. The legend, the direct labels
    and the 3D ridges all follow it. 'Clear all' returns every trace
    to the map.

  The 3D Surface look (PLOT > 3D PLOT OPTIONS) reads this same map.
    It colors the sheet by series value. A band of the sheet takes
    the color of the ridge at that pressure. The colorbar then reads
    correctly. A categorical map colors the sheet in bands by rank.
    Pick a continuous map for a surface.

  Lock colors to all datasets: color each dataset from the full
    loaded set. A curve then keeps its color when you toggle others
    off. It is on by default. Leave it on while you make a figure
    series.

  Tint plot with theme: accent themes keep the plot page neutral, so
    the figure is publication-ready in any theme. Turn this on to
    tint the plot background to match the theme. It is a display
    choice. The export face color is set in EXPORT > FIGURE.

  Text color: the tick numbers and axis labels, 2D and 3D. 'auto'
    follows the theme.


STYLE > FONTS

  The typeface for every text element in the figure. The default is
    the interface face. Journal presets override it with Arial, or
    with a serif for APS.

  Bold and Italic, per element: Title, Labels, Ticks, Legend, Bar
    (the colorbar label and its tick numbers). 2D and 3D.

  Italic needs a font that has an italic face. The bundled Jost
    draws upright at every weight. Pick Arial or Segoe UI. Journal
    presets already set Arial.

  Mathtext works in any label box: $\lambda$, Fe$^{2+}$, $\mu$m.
    matplotlib renders it, so what you see on screen is what
    exports.

  The per-item text sizes sit beside the item each one governs.
    Title size sits next to Title, tick size in AXES > TICKS, legend
    size in STYLE > LEGEND.


STYLE > TITLE & AXIS LABELS

  Title, X label, Y label and Z label, each with its own size box. X
    and Y labels share one size, because matplotlib applies a single
    label size to both. Right-click a box to restore the automatic
    text.

  Title pos: left / center / right. pad is the gap above the axes in
    points (blank = default).

  Title X / Title Y: the title position in axes fractions. A y above
    1 is above the axes. The boxes always show the position actually
    drawn. Type both values to pin a custom spot. Blank one value, or
    change Title pos, to follow the automatic placement again.

  X pos / Y pos: slide the axis labels along their own axes (left /
    center / right, bottom / center / top). 2D and 3D.

  Footnote: a small note stamped at the bottom-left of the page.
    Use it for sample notes, a run ID, or the word 'preliminary'. It
    has its own size box and it exports with the figure. 2D and 3D.


STYLE > LEGEND

  Show legend: a per-trace key.

  Branch tags: the ' - C' / ' - D' suffix on every legend entry.
    Switch it off for the value alone. You can also rename the two
    branches in the small C and D boxes (heat / cool, inc / dec).
    Blank falls back to C and D. This control is display only. The D
    list, the C/D-tagged CSV export and every file name keep the
    letters C and D.
    What the two branches look like is set in PLOT > 2D PLOT
    OPTIONS, under the Decompression traces sub-heading. That block
    holds line style, pattern, width, opacity and markers. The
    legend keys follow it.

  Location: the usual matplotlib positions, plus outside right,
    left, top and bottom. 'outside right' keeps a legend off the
    data.

  X / Y: the legend box center in axes fractions. The boxes always
    show the position actually drawn. Type both values to pin a
    custom spot. Blank one value, or change Location, to follow
    automatically again.

  Auto-fit oversized legend: reflow an oversized legend to fit the
    page. It applies on export and in the WYSIWYG preview. The tool
    adds columns first, then it lowers the font size. It writes the
    values it used back into this panel. Off means the tool uses your
    settings exactly as typed.

  Swatch: the key style. 'color box' draws a thick color block per
    trace, and the 3D legend uses it. 'line' shows the artist
    itself.

  Direct labels at curves: write each trace's value at its curve end.
    It works in 2D overlay, 2D stacked and 3D ridge. For a dense
    series this reads better than a legend or a colorbar. Five rows
    style the labels.

    Size: the label text size in points. The default is 9.

    Color: 'trace' colors each label like its own curve. You can also
      pick black, white or gray, or type any hex code.

    Distance: the gap from the curve end to its label, in points.
      The range is 0 to 40. The default is 4.

    Bold: thickens the label text.

    Backing: what sits behind each label. 'none' draws the text
      alone. 'box' draws a rounded box in the page color. 'halo'
      draws an outline in the page color around the glyphs. Both
      keep the label readable over a crowded plot.

  Columns (up to 16), Font size, and an optional Title above the
    entries.

  Frame (shared with colorbar)
    Border box on/off, Background opacity and Border width. Border
    opacity is independent of the background. Edge color paints the
    border. These same controls style the colorbar frame.


STYLE > COLORBAR

  Show colorbar (continuous maps): a continuous scale across the
    Series variable. For a dense series, one smooth ramp reads better
    than twenty legend entries.

  The legend and the colorbar draw together. The bar reads the scale
    and the legend names the traces, so ticking both boxes draws
    both. The tool builds the bar first and then steps an outside
    legend past it. A right-hand bar moves a right-hand legend
    further right. A pinned X / Y stays where you pinned it.

  Auto: colorbar for many traces: off by default. When it is on, a
    continuous colormap with more than about ten traces switches
    itself to a colorbar. This is the one case that drops the legend,
    because a legend that large hides the data. A categorical
    colormap always keeps a discrete legend. Off means the tool
    honors the Legend and colorbar checkboxes literally.

  Bar label: defaults to the Series variable ('Pressure (GPa)').
    Type here to override it.

  Location: right / left (vertical) or top / bottom (flat). It also
    decides which side the ticks sit on.

  X / Y: the bar center in figure fractions. Axes fractions are a
    different measure. Type both values to pin a custom spot. Blank
    one value, or change Location, to follow automatically again.

  Label font, Tick font, Thickness (as a fraction of the axes) and
    # ticks (0 = automatic).

  The frame styling is shared with the legend and set there.


STYLE > REFERENCE LINES

  Vertical lines: wavelength (nm)
    Type a list of wavelengths, separated by commas or spaces. For
    example: 450, 620, 700. Each set has its own color, pattern,
    width and opacity. 'Auto every N nm' plus Fill lays down a regular
    comb. Clear empties the box.

  Horizontal lines: absorbance
    The same controls, at given Y values: 1.0, 2.5. Use them for a
    baseline or a threshold. 'Auto every N abs' plus Fill, and
    Clear.

  Reference lines draw on 2D plots. In 3D the tool draws them as
  faint planes through the box.


TOP BAR > THEME

  The six entries above the divider are the working themes:
    Standard Light, Kinda Dark, Black Hole, and three accessibility
    themes. The accessibility three are High Contrast, Colorblind
    Safe and Colorblind Safe Dark. Everything below the line
    changes interface colors only.

  Colorblind Safe and Colorblind Safe Dark use the Okabe-Ito
    palette. One sits on a white ground and one on a dark ground.
    Every color in both clears the 4.5:1 contrast floor.

  The dyslexia-friendly typeface is a font. Pick OpenDyslexic in
    the Font box, in the top bar's Settings panel. It applies to
    every control, and it works with any theme.

  The plot itself stays neutral in every theme. 'Tint plot with
    theme' in STYLE > COLORS & COLORMAP is what changes that. The
    interface can be as dark as you like, and the figure still
    exports on a white page.


TOP BAR > SETTINGS

  The gear beside Theme opens the Settings panel. Esc shuts it, and
    a click outside shuts it too.

  Font sets the typeface of every button, label and control. Jost
    is the standard face. OpenDyslexic is the dyslexia-friendly
    face.

  Text size sets the size of every button, label and control. The
    range is 3 to 15. 'auto' takes the size from the screen
    resolution and the display scale. The figure's text sizes are
    separate, and they sit in STYLE > FONTS.

  Helper tips is the master switch for the hover tips.

  Performance mode, Tutorial and About share the panel. Every
    setting here applies live, and the tool remembers it.
