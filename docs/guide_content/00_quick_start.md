QUICK START

This is the ten-minute path from raw segment files to a finished
figure. Every step is reversible. The tool writes to disk when you
press Run or Save.

For a first look, point the Input folder at demo_data,
which ships beside the program. It holds a small synthetic series: 5
series points, 3 channels, 2 grating segments. It uses the classic
22-IR-1 naming convention, so every step below works on it
unchanged, fringes and all. One of the five points carries a _D tag.
Both the compression branch and the decompression branch are
present. Every file in demo_data is synthetic.

About > 'Welcome & tour...' loads that folder and walks this path in
the window itself. The program dims around the control it explains.
Esc leaves the tour at any point.


1. POINT AT THE DATA

  Left panel, Input folder: press Browse, or drag a folder from
    Explorer onto the window, or paste a path and press Enter. Enter
    also rescans and remembers the folder.
  The small arrow beside Browse drops down your last 5 input folders
    plus 'Open in Explorer'. A right-click inside the box does the
    same.
  The scan reads one folder. Point at the folder that holds the
    segment files themselves. If you pick a parent folder, the log
    says so and lists the subfolders it found.

  Output folder: press Browse and pick anywhere you can write. A Run
    creates <output>/<inputname>_absorbance/ and puts the CSVs there.
    If that subfolder already exists and holds files, the tool
    appends a timestamp (<inputname>_absorbance_YYYYMMDD_HHMM). An
    earlier run keeps its own folder.


2. CHECK HOW THE NAMES ARE READ

  The button under the Input box shows the active profile. The
    default profile is '22-IR-1 default'. That profile reads

      vis_{DAC}_{Sample}[_{Pressure}][_bg|_s][_C|_D][_rep][.{seq}]

    For example, vis_Y04_Arch29_26p0_s.003 is DAC Y04, sample
    Arch29, 26.0 GPa, the sample channel, grating segment 3.

  If your filenames look like that, go to step 3.

  For any other scheme, open the button. Press 'Guess format'. Check
    the Preview: green means parsed, red means skipped with the
    reason. Correct anything wrong, then press 'Use this profile'.
    The Naming system view holds the full walkthrough.


3. RUN

  Press Run. The tool concatenates the grating segments of each
    measurement and computes

      A = -log10[(Sample - Dark) / (Background - Dark)]

    The tool writes one CSV per measurement into the output
    subfolder. It also writes a _reduction.provenance.json sidecar,
    which records the tool version, the parameters and every curve.

  Watch the Progress log. Each line is one measurement. OK lines
    carry the point count and the file written. SKIP lines carry the
    filename and the reason. Run turns into Cancel while a run is in
    flight.

  Absorbance needs all three channels. A measurement with only some
    of them loads as raw counts. The tool tags the trace name
    ([S only], [S+B]).


4. LOOK AT THE DATA BEFORE YOU TRUST IT

  Every trace plots at once. Do two checks first.

  Inspect one trace (Plot tab > Plot mode). Pick a measurement. The
    left axis shows Sample, Background and Dark counts. The right
    axis shows its Absorbance. In a healthy point the background
    sits comfortably above the sample, and both channels sit under
    the detector ceiling.

  Traces (Data tab). One row per loaded point. A colored dot beside
    a row means a quick quality check fired. Hover the dot for the
    reason (saturation, negative absorbance, missing channels).

  Click a curve on the plot to select it. Double-click to solo it.
    Click a legend entry to hide it. Right-click a curve for the
    quick-actions menu (inspect, solo, hide, toggle D, defringe
    compare, show in data table).

  Ctrl+D opens the data table under the plot. It holds the numbers
    for the selected trace, with 'Copy all (TSV)' and 'Open in
    Excel'.


5. MAKE IT A FIGURE

  Export tab > Figure: pick a Journal preset. One pick sets the
    column width and the house style: typeface, text sizes, line
    weight, thin spines, ticks in, DPI. Tick 'Preview at export size
    (WYSIWYG)' in Export tab > Export to see the true printed
    proportions on screen.

  Style tab > Legend: above about ten traces, turn on 'Direct labels
    at curves' or use Style tab > Colorbar. A legend box that size
    covers the data.

  Export tab > Export: 'Save plot...' writes PNG / PDF / SVG / EPS /
    TIFF. PDF and SVG are vector. Leave 'Editable text' on to keep
    the labels editable in Illustrator or Inkscape.


WHAT ELSE IS WORTH KNOWING ON DAY ONE

  Session tabs sit above the plot. Each tab is an independent
    session with its own data, folders, settings and undo history.
    Ctrl+T opens a blank one, Ctrl+W closes, Ctrl+Tab cycles,
    double-click renames. Use them to compare two loads side by
    side.

  'Load previous run' reopens a finished output folder at once. The
    tool re-imports the CSVs for plotting, straight off disk. A
    blank tab also lists recent runs.

  Rescan (or F5) re-runs the folder when new files appeared since
    the last Run. It is the between-measurements top-up. The Auto
    rescan pill in Plot tab > Plot mode does it unattended every N
    seconds.

  Hover any control for a tip. Helper tips, in the top bar's
    Settings panel, is the master switch. F1 lists the keyboard
    shortcuts.

  Theme sits on the top bar. The six themes above the divider are
    the working ones. They include High Contrast, Colorblind Safe
    and Colorblind Safe Dark. The rest of the list changes colors
    only.

  The gear beside Theme opens the Settings panel. It holds Font,
    Text size, Helper tips, Performance mode, Tutorial and About.
    Font sets the typeface of every control. Pick OpenDyslexic
    there for the dyslexia-friendly face.

  The Quick Access strip above the tabs is yours to furnish. The
    gear in its corner opens a two-column checklist. CONTROLS on the
    left are settings the strip can carry a second copy of.
    ESSENTIAL FUNCTIONS on the right are one-press actions: Run,
    Rescan, Open output, Data table, Save plot, Copy figure and
    more. They arrive as small labelled buttons under a rule. The
    strip starts empty. With 'Collapse all' pressed, section headers
    become handles: drag one up or down to rearrange its tab.

  The tool remembers folders, theme, window size, default colormap,
    notes and presets between launches.

  NUKE (top bar, center) is the hard reset. It clears the session:
    data, plot, folders, log, every control. It leaves your files on
    disk untouched. Saved presets and your default colormap survive.
    It asks first.
