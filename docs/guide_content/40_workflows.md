WORKFLOWS

Recipes by goal. Start from the thing you need and work down. Each
recipe assumes a folder is loaded. To rehearse a recipe first, point
the Input folder at the bundled demo dataset and follow it through
there.


A PUBLICATION OVERLAY FIGURE

  1. Run the folder. Confirm the trace count in the Progress log
     matches what you measured.
  2. DATA > TRACES: tick the traces for the figure. Leave 'Lock
     colors to all datasets' on in STYLE > COLORS & COLORMAP. The
     colors then hold as you untick.
  3. EXPORT > FIGURE: pick the journal preset for the column you are
     filling. That sets width, typeface, sizes, line weight, spines
     and DPI in one action.
  4. EXPORT > EXPORT: tick 'Preview at export size (WYSIWYG)'. Judge
     the figure at that size. 7 pt type at 89 mm is smaller than it
     looks in a full window.
  5. Decide the key. Up to about ten traces, use STYLE > LEGEND with
     Location 'outside right'. Above that, use STYLE > COLORBAR, or
     'Direct labels at curves' in STYLE > LEGEND. Direct labels
     usually read best.
  6. AXES > LIMITS & SCALE: set the X range you want to show. A zoom
     on the plot fills these boxes for you.
  7. STYLE > TITLE & AXIS LABELS: the axis labels default sensibly.
     Override them when the journal has a house form. Mathtext works:
     $\lambda$ (nm), Fe$^{2+}$.
  8. Save the plot as PDF with 'Editable text' on. Tick 'Also save'
     PNG for slides. Add 'Grayscale copy' when the journal prints
     some figures in mono.
  9. The export may auto-fit the legend. The tool writes the columns
     and font size it used back into the panel. Copy them to make
     that layout permanent.
 10. Left panel > Progress > 'Export settings' prints the whole
     configuration into the log for the methods section.


DEFRINGED CSVs FOR IGOR OR ANOTHER TOOL

  1. Tick df on the strip beside the plot. That is the whole first
     pass. The tool finds the strongest ripple in each channel and
     takes it out.
  2. Read the fringe report in the log. It names the traces with a
     detected fringe, the fitted n*t in micron, and the p-value. An
     absent trace is one the detector missed, and it passes through
     unchanged.
  3. Sanity-check one trace. In PLOT > 2D PLOT OPTIONS, tick
     'Defringe compare (selected trace)', then click a curve. The
     gray dashed line behind it is the pre-defringe absorbance. If
     the notch took out structure you care about, narrow the
     half-width in FRINGE > FFT REMOVAL > Notch list. If fringes
     survive, widen it, or loosen 'Fisher p' under FRINGE > PANELS >
     Detection. Press 'Write to defringe' to send your settings to
     the export.
  4. EXPORT > EXPORT: pick 'Export CSV...' > 'Defringed CSV
     (FFT-notch absorbance)'. Tick Crop and give a wavelength range
     first to export part of the spectrum.
  5. Pick a destination folder. You get one
     {stem}_absorbance_notch.csv per trace. The columns are
     Wavelength, Dark, Background, Sample, Absorbance. A channel the
     tool notched adds Background_notch, Sample_notch and
     Absorbance_notch. An un-notched channel leaves its notch column
     blank, so a reader can tell what the tool touched.

  Leave df ticked and every Run writes the notch files beside the
  absorbance CSVs.


SMOOTHED CSVs

  Take the same path with 'Export CSV...' > 'Smoothed CSV (raw +
  smoothed columns)'. You get wavelength, wavenumber, eV, the raw
  columns and the smoothed ones side by side. Tune the filter first
  in DATA > SMOOTHING > 'Smoothing settings...', with live preview
  on. The split at 600 nm gives the two grating regions their own
  windows.


THICKNESS VERSUS PRESSURE

  1. Tick df beside the plot. The detection supplies n*t.
  2. Check the fringe report. A thickness point needs a confident
     detection. The 'mark misses' triangles show the rest.
  3. PLOT > PLOT MODE: switch to Thickness (fringe n*t). Sample
     points are filled circles and background points are open
     squares. The S / B boxes pick the channels.
  4. For solved physical thickness, take the traces through the
     fringe workbench: describe the stack, assign roles, Solve,
     Record point. 'Results vs pressure...' in FRINGE > SESSION plots
     the solved values. Turn on 'Error bars (multiscale variance)'
     before you quote a number.
  5. 'Thickness table...' in PLOT > PLOT MODE lists n*t and its
     p-value per trace. The plot exports through the normal Save plot
     path.
  <!-- v149: PLAN Phase C also promises solved values replacing n*t
       on this plot and a thickness CSV export; neither is in code
       yet. -->


COMPARING COMPRESSION AND DECOMPRESSION

  1. Set the branches. An explicit _C / _D tag in the
     filename wins. The tool recognises ten historical experiments
     automatically. Otherwise tick the D box per trace in DATA >
     TRACES, or load a list.
  2. 'Decompression list...' in DATA > TRACES reads a CSV or text
     file of decompression values. It takes a pressure_GPa column or
     plain numbers, allows 'p' as the decimal, and ignores headers.
     Each value takes the nearest loaded trace within 0.05. The tool
     remembers the list per cell and sample.
  3. Read one branch at a time with 'Only C' and 'Only D' before you
     overlay them.
  4. Overlay both. The Decompression traces controls in PLOT > 2D
     PLOT OPTIONS draw the D branch dashed under 'Style D traces
     apart'. Give it its own width, opacity and markers when dashing
     alone separates the branches too little.
  5. STYLE > LEGEND: rename 'C' and 'D' in the two small boxes.
     Other words may fit your experiment better, such as 'heat' /
     'cool' or 'inc' / 'dec'. That rename is display only. The file
     names and the D list keep C and D.
  6. 'Export D list (CSV) by selection' writes the branch assignment
     back out, so the next person has it.
  7. 'Save C/D-tagged CSVs...' writes the whole set with the branch
     letter in every file name.


A CUSTOM QUANTITY, PLOTTED AND EXPORTED

  1. DATA > FORMULAS: press New...
  2. Name it and give it a unit. The name labels the Y axis and names
     the CSV column.
  3. Write the expression over the loaded columns. The tool derives
     the typeset preview under the box from what you typed, so the
     two always agree. The problems list and a live min / max / NaN
     preview update as you type. Save stays disabled until the
     formula is clean.
  4. Tick df first when the formula uses Sf, Bf or Af. Turn 'Show
     smoothed' on when it uses As. The tool reports a missing
     column and leaves a gap.
  5. Save, then click the dot beside the row. The formula becomes the
     Y axis ('formula: <name>'). The row tints and goes bold.
  6. Style and export the figure as you would for absorbance.
  7. 'Save formula CSVs...' writes one two-column file per trace:
     wavelength plus the formula, with the expression in the header
     comments. One provenance sidecar covers the batch. The
     absorbance CSVs stay untouched.

  Worked example, what the smoother removed:
    expression  A - As
    unit        (blank)
    needs       Show smoothed on
    Plot it and you get the residual. The residual is what decides
    whether a smoothing setting is defensible.


LIVE ACQUISITION AT THE BEAMLINE

  1. Run once as soon as there are a few measurements. The tool then
     has a baseline file list.
  2. PLOT > PLOT MODE: turn on Auto rescan. Set the interval to
     roughly your measurement cadence.
  3. Leave it. The status line under the plot reads 'auto-rescan: N
     s' while the timer is armed. A tick that finds new files
     re-reduces the folder and says so in a brief toast. The timer
     fires while the tool sits idle.
  4. Rescan and F5 still work by hand, mid-run included.
  5. Use Inspect one trace on each new point as it appears. That is
     the moment to notice a saturated channel or a drifting lamp.


COMPARING TWO DATASETS SIDE BY SIDE

  1. Press Ctrl+T for a new session tab. Each tab has its own data,
     folders, settings and undo history.
  2. Load or Run the second dataset there. The tab names itself after
     the folder.
  3. Ctrl+Tab cycles. Style each tab on its own. You can also style
     one tab and save it as a preset (EXPORT > PRESETS & PROJECTS).
     Load that preset in the other tab for identical styling.
  4. Double-click a tab to rename it something you will recognise in
     an hour.


COMING BACK TO A SESSION LATER

  Three levels. Pick by how much you need back.

  The curves alone: 'Load previous run...' on the left panel. Pick the
    output subfolder a Run wrote. The tool re-imports its
    *_absorbance.csv files for plotting, straight off disk.
    Smoothing and defringe still apply live on top.
    A blank session tab also lists recent runs for one click.

  The styling: EXPORT > PRESETS & PROJECTS, pick the preset and
    Load. A preset carries the plot controls alone, so one preset
    styles many datasets.

  Everything: 'Open project...'. A project is every setting plus the
    input and output folders, in one .json. It reopens an analysis
    exactly where you left it.

  The tool remembers the rest between launches: folders, theme,
    window size, the default colormap, your notes, and your presets.
