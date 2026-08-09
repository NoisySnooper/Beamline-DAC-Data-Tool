EXPORT TAB

This tab gets the figure and the numbers out. It sizes them for a
journal. It records how the tool made them.


EXPORT > PRESETS & PROJECTS

  A preset saves the whole control state under a name. Pick it in the
    dropdown and click Load. 'Save as...' names a new one. Delete
    removes it. A preset stores styling only.

  A project stores the same state plus the input and output folders.
    It is a .json you can reopen exactly where you left off. Use
    'Save project...' and 'Open project...'.

  Use a preset for a house style you apply to many datasets. Use a
    project to put one analysis back on screen months later.

  'Reset all' on the control bar at the top of the panel resets every
    plot control. It asks first. It keeps your loaded data and
    folders.


EXPORT > FIGURE

  Journal preset: sets a publisher's current column width and its
    whole house style in one pick. The style covers the typeface and
    the title, label and tick sizes. It also covers line weight, grid
    off, thin spines, ticks in, minor ticks on, and DPI.

      Nature single / double        89 mm / 183 mm, Arial
      Science 1 / 2 / 3-col         5.7 / 12.1 / 18.4 cm, Arial
      RSI / AIP 1 / 2-col           3.37 / 6.69 in, Arial
      APS 1 / 2-col                 3.4 / 7.0 in, serif
      Elsevier 1 / 2-col            90 mm / 190 mm, Arial
      Nature 3D single / double     as above, plus the 3D scene
      Science 3D 2-col              as above, plus the 3D scene
      APS 3D 2-col                  as above, plus the 3D scene
      Clean style                   grid off, thin spines - the
                                    font-agnostic tidy-up; leaves
                                    your size and fonts alone
      Square (5 in), Wide (10x4 in) size only

    The presets marked 3D also style the whole 3D scene the way those
    journals print it. That style uses the minimal 3-axes frame,
    with the background panes and the grid off. It uses a colorbar
    in place of a many-entry legend, and a standard camera.

  Set as default: remembers the preset and applies it at every
    launch. Every session then opens sized for the journal you
    publish in. The star marks the preset that is saved.

  W x H in plus Apply: a custom figure size. Type in either box and
    press Return to apply it.

  Transparent background: save with a transparent page (PNG / SVG /
    PDF). It overrides the face color.

  Tight bounding box: trim the surrounding whitespace on export.

  Pad (in): the margin kept around a tight box.

  Face: the page background on export. Pick auto (the current
    theme), white, black, or 'none' for a transparent page.

  The typeface and the per-item text sizes live in STYLE > FONTS and
    beside each text item.


EXPORT > EXPORT

  Preview at export size (WYSIWYG): render the on-screen figure at
    the exact export width and height. You then see the true printed
    proportions and text size before saving. Off means the figure
    fills the window, which hides how small 7 pt type looks at 89 mm.

  DPI: 72 to 600, used by Save plot and Copy figure. Journal presets
    set 300.

  Save plot...: PNG, PDF, SVG, EPS or TIFF. The tool offers the
    format you saved last. PDF and SVG are vector.

  Also save PNG / PDF / SVG / TIF: one Save writes every ticked extra
    format next to the file you named, with the same base name. TIF
    is the high-resolution raster some submission systems demand.

  Editable text: vector exports embed real TrueType text (fonttype
    42). Journals accept it, and Illustrator or Inkscape can edit it.
    Off outlines the text as paths, at exact shapes. It is on by
    default.

  Grayscale copy: also writes <name>_grayscale.png. Use it as the
    print-survival check on whether the curves still separate.

  Open after: open the saved file in its default viewer.

  Name: the suggested file name for Save plot. The tokens are {tab}
    {mode} {wf} {preset} {cmap} {date}. The default is
    {tab}_{mode}_{date}.

  PNG, PDF and SVG carry the tool version in their file metadata.

  Copy figure: put the figure on the clipboard as an image, at the
    Figure size and this DPI. Paste it into Word, PowerPoint or an
    email. Ctrl+Shift+C.

  Batch export (one per shown trace)...: solo each shown trace on the
    figure as it is styled right now. The tool saves one file per
    trace. The styling covers mode, labels, fonts and journal size.
    The formats are png, pdf, svg and tif. This is how you get a
    consistent set of single-trace panels.

  Crop plus min / max nm: limit the CSV exports below to a wavelength
    range.

  Export CSV...: a menu with two writers.
      Smoothed CSV (raw + smoothed columns): wavelength, cm-1, eV,
        the raw columns and the smoothed ones.
      Defringed CSV (FFT-notch absorbance): the
        {stem}_absorbance_notch.csv files, notched at the fringe
        workbench's settings.
    Both writers work whatever the matching display toggle is set to.
    Both write one file per trace into a folder you choose.

    Press 'Write to defringe' in FRINGE > FFT REMOVAL and the
      defringed export uses that notch set: your centres, each at its
      own absolute half-width, plus each channel's low-pass cutoff.
      Until then it uses the single automatic fundamental. Reset in
      the notch list puts the automatic behaviour back. The
      parameters actually used land in the provenance sidecar, so an
      export is always traceable to the notch decisions behind it.

  The branch-tagged CSVs live elsewhere. 'Save C/D-tagged CSVs...' is
    in DATA > TRACES, under 'Export D list'.

  Provenance sidecars
    Every reduction and every batch export writes a JSON sidecar
    beside its output. The reduction sidecar is
    _reduction.provenance.json. It records:
      tool name and version
      the timestamp it was written
      the input folder and the output subfolder
      the absorbance definition, spelled out
      the Series variable's name and unit
      how many curves were written
      whether defringe was on, and with exactly which parameters
      every curve's identity label and value
    Export sidecars record the same shape for the batch they cover.
    A sidecar traces a figure or a CSV back to the settings behind
    it. The parameters copy straight into a methods section.

  'Export settings' sits in the left panel's Progress card. It
    prints the current plot configuration into the log, in a
    paste-ready form.


EXPORT > 3D PRINTING

  This section writes your data as a solid object you can 3D print.
  The Shape box picks which object the tool builds. The tool
  rebuilds the geometry for the export, from the data itself.

  Shape: 'Surface cube' builds the surface the 3D Surface look draws.
    The data becomes the top face. Four walls drop from its rim to a
    flat base. This shape needs three or more shown traces.
    'Folder divider' builds a thin upright plate from ONE trace. The
    top edge of the plate is that trace. The plate stands on a wider
    foot, so it holds itself up on a shelf. This shape needs one
    shown trace.

  What gets exported: the shown traces, on the Y channel you are
    plotting, at the X unit on screen. The Y channel can be
    absorbance, a raw channel, or an active formula. The tool applies
    the same smoothing and defringe the plot uses. What you see is
    the shape you print.

  Size X/Y (mm): the footprint. X runs along the spectral axis. Y
    runs along the series axis. The tool stretches the data to fill
    it, so any ratio works. 80 x 80 is a comfortable desk object.

  Height Z (mm): the total height at exaggeration 1. It covers the
    base plus the data relief standing on it.

  Base (mm): how thick the slab under the surface is. It gives the
    print something to stand on. It also keeps the lowest parts of
    the data from printing as foil. 6 mm is a safe floor for most
    printers.

  Z exaggeration: multiplies the relief above the base. 2 makes every
    feature twice as tall and the print taller with them. The base
    keeps its thickness. Use it when the structure you care about is
    small next to the full range of the data.

  Plate (mm): the thickness of the divider plate. 2 mm prints solid
    on a standard nozzle. This row appears for the folder divider.

  Foot (mm): the depth of the foot the divider stands on. The foot
    runs wider than the plate. 14 mm holds an 80 mm plate upright.
    This row appears for the folder divider.

  One file per trace: the tool writes one divider for every shown
    trace. The tool asks for a folder. Each file is named after its
    own trace. Leave this box clear for a single file. The single
    file uses the trace you selected on the plot.

  For the folder divider, Size X is the width of the plate and Height
    Z is its total height. Base is the height of the foot. Z
    exaggeration works the same way. Size Y belongs to the cube.
    The lowest point of the trace still gets 1 mm of plate above the
    foot. The thinnest part of the silhouette then prints.

  Export STL...: names the file and writes it. It writes binary STL
    in millimetres, which every slicer expects. The divider passes
    the same closed-mesh proof as the cube.

  Watertight, And Checked
    A slicer takes a closed model. The tool proves the mesh closed
    before it writes a single byte. Every edge carries exactly two
    triangles. Those two triangles run the edge in opposite
    directions, which makes the surface normals consistent. The
    Euler characteristic comes to 2.

      V - E + F = 2

    The enclosed volume comes out positive. A failed check stops
    the write, and the log names the failure. The numbers go to the
    log and into the sidecar, so you can check the claim yourself.

  The status line under the button reports the triangle count, the
    watertight result and the file size. The log carries the full
    report. It names the grid size, the traces it came from and the
    proof numbers. It also names the physical dimensions, and how
    many millimetres one unit of the plotted quantity became.

  The tool writes a <name>.stl.provenance.json sidecar beside the
    file. It has the same shape as every other export sidecar. It
    holds the tool and version, the timestamp, the input folder and
    the series variable. It holds the grid recipe: interpolation,
    columns, rows, every series value. It holds the physical mapping
    and the watertightness numbers.

  Printing Notes
    Fringes and noise print too. A spectrum full of etalon fringes
    becomes a field of thin fins. Those fins sit under the
    resolution of most printers, and a printed fin snaps off. Turn
    on Smoothing, or
    tick df, before exporting. The solid then follows the cleaned
    curve.
    A big Z exaggeration on a thin base tips over. Raise the base
    when you raise the relief.
    The lowest value in the data sits on the base. The slab stays
    solid under a negative baseline.

  Size on disk is about 50 bytes per triangle. The default grid is
  roughly 90 000 triangles, or 4 MB.
