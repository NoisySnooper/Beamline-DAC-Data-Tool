DATA INPUT

The left panel is where data enters the program. This view walks it
top to bottom: the folders, the file names, what a Run writes, and
how to reopen a finished run.


LEFT PANEL > FOLDERS

  Input folder: the folder that holds the raw spectrometer segment
    files. There are four ways to set it.
      Press Browse for the usual picker.
      Type or paste a path and press Enter. Enter also rescans and
        files that folder in the recent list.
      Press the small arrow beside Browse, or right-click in the
        box. Both drop down your last 5 input folders plus 'Open in
        Explorer'.
      Drag a folder from Explorer onto the window (Windows). Drop a
        file and the tool uses its containing folder.
    Hover the box to read a long path in full.

  The scan reads the folder you pick. The tool prints a HINT in the
    log when a folder holds other content. The HINT names the
    subfolders it found.

  Output folder: anywhere you can write. A Run creates

      <output>/<input folder name>_absorbance/

    and writes there. If that subfolder exists and holds files, the
    destination becomes

      <output>/<input folder name>_absorbance_YYYYMMDD_HHMM/

    A second Run keeps the first folder as it is.

  Both folder cards fold shut by their title. A path you have set
    then costs one row.

  Run: the reduction. For each measurement group the tool
    concatenates the grating segments in ascending segment order,
    sorts by wavelength, and computes

      A = -log10[(Sample - Dark) / (Background - Dark)]

    The tool writes one CSV per group. Run turns into Cancel while it
    works. Cancel stops after the current group and keeps what the
    tool already wrote.

  Open output: opens the destination subfolder in Explorer.


WHAT A RUN WRITES

  {DAC}_{SAMPLE}_{VALUE}[_C|_D]_absorbance.csv, one per measurement
    group, with the frozen column set

      Wavelength_nm, Wavenumber_cm-1, Absorbance, Dark, Background,
      Sample

    Blank cells are NaN. The value token uses 'p' for the decimal
    (26p0), as the input convention does.

  _reduction.provenance.json: one sidecar per run. It records the
    tool name and version, the timestamp, and the two folders. It
    records the absorbance definition and the Series variable name
    and unit. It records the defringe state with its parameters. It
    records the label and value of every curve written.

  {stem}_absorbance_notch.csv: written only when df is ticked at Run
    time. The columns are Wavelength, Dark, Background, Sample,
    Absorbance. A channel with a confident fringe adds
    Background_notch, Sample_notch and Absorbance_notch. A channel
    the detector missed leaves its notch column blank.

  A user-defined formula always gets its own two-column CSVs. See
    the Formulas view.


HOW MEASUREMENTS ARE GROUPED

  The tool groups files by (DAC, sample, value, branch). Inside a
    group, each channel (dark / background / sample) can have several
    replicates. Each replicate can have several grating segments.

  The group anchors on the sample channel when it is present, else
    on background, else on dark. The tool uses the latest retake of
    the anchor, which is the highest replicate index. It pairs the
    other channels by matching replicate when one exists, else by
    their own latest.

  The tool concatenates only the segments the channels share. A
    group whose channels share zero segment numbers is skipped,
    with a note in the log.

  Channels normally sit on the same wavelength grid. A truncated or
    differently binned segment breaks that. The tool then
    interpolates every channel onto the anchor's grid and says so in
    the log. Points outside a channel's own range become NaN.

  The tool deduplicates raw/.csv twins. An old batch tool that
    copied each raw file to a .csv is counted once.

  The tool computes absorbance only when sample, background and dark
    all exist. Otherwise the available channels load as raw counts.
    The absorbance column is then all-NaN. The trace label then
    carries a channel tag ([S only], [S+B], ...). In a load of raw
    channels alone, the overlay Y axis switches to the best
    available raw channel. The log says so.


LEFT PANEL > NAME FORMAT

  The button under the Input box names the profile in force. It is
    the door to the whole naming system: teach-by-example, Guess
    format, the live whole-folder preview, and per-file fixes. The
    Naming system view holds the deep dive.

  The tool saves profiles with the program, and they survive
    restarts. It remembers per-file fixes per folder.


LEFT PANEL > RESCAN

  Rescan sits beside 'Load previous run'. It compares the input
    folder against the file list captured at the last Run. New files
    re-reduce the whole folder. This is the between-measurements
    top-up.

  F5 does the same from anywhere. Enter in the input-folder box
    rescans and files that folder in the recent list.

  The unattended version is the Auto rescan pill in Plot tab > Plot
    mode. It is one timer for the whole program. The interval runs
    from 5 to 3600 s, default 30. It waits for the first Run. It
    fires while the tool sits idle, and it re-runs the folder when
    new files appeared.


LOAD PREVIOUS RUN (VIEWER MODE)

  'Load previous run...' asks for a folder of *_absorbance.csv
    files, which is the output subfolder a Run wrote. The tool
    re-imports them as plottable traces, straight off disk.

  The importer reads the writer's own schema. It ignores files that
    end in _absorbance_notch.csv, because they are companions. It
    skips every other file silently.

  Smoothing and defringe still apply live on top of imported data.
    Both are display-time filters over the loaded columns.

  Run itself falls back to viewer mode. A folder of this tool's own
    *_absorbance.csv output, with the raw segments elsewhere, loads
    straight off disk. The log says so.

  A blank session tab lists your recent runs, so reopening one takes
    a single click.


LEFT PANEL > PROGRESS AND GUIDE / NOTES

  Progress logs every run, rescan and action. It includes the reason
    for every skipped file. 'Copy log' takes the whole log to the
    clipboard. 'Export settings' prints the current plot
    configuration into the log. That printed form pastes into a
    methods section.

  Guide / notes is this box. The View dropdown switches between the
    guide views and 'My notes', which is a free-text scratchpad saved
    between launches. The gear beside it holds this box's font and
    size.

  Both cards fold shut by their title.


TOP BAR > SETTINGS

  The gear beside Theme opens the Settings panel. Esc shuts it, and
    a click outside shuts it too. Every setting here applies live
    and is remembered between launches.

  Font sets the typeface of every button, label and control. Jost
    is the standard face. OpenDyslexic is the dyslexia-friendly
    face. The list shows the faces this computer has.

  Text size sets the size of every button, label and control, from
    3 to 15. 'auto' takes it from the screen and the Windows
    display scale.

  Helper tips is the master switch for the hover tips.

  Performance mode suits a slower machine. A pane-divider drag then
    shows a thin guide line and resizes the panes once, on release.
    Off is the default.

  Tutorial starts the guided tour. About names the build, the
    license and the people behind it.

  'Performance mode (faster 3D)' in Plot tab > 3D plot options is a
    different control. That one decimates ridges for smoother
    rotation.
