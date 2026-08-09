FRINGE WORKBENCH

The regular ripple on your spectrum is light that bounced inside the
cell. It carries the thickness of the layer it bounced in. This page
takes that ripple out of the absorbance, or reads it as a
measurement.


Two ways in

  The df box beside the plot is the quick one. Tick it. The tool
  then finds the strongest ripple in every trace, removes it, and
  computes absorbance again. That covers most spectra. The same
  switch heads the Fringe panel's own column.

  The workbench is the same physics with every step exposed. It has
  four charts, a low-pass filter you can drag, and notches you place
  by clicking. Its solve turns ripples into thickness and refractive
  index. Press Write to defringe and the df box uses your settings
  from then on.


Opening it

  Click Fringe at the right-hand end of the session-tab row above
    the plot. Click Plot to go back. The rest of the session holds.

  Guide, next to those words, opens and closes this page beside the
    chart. Pop out floats the chart into its own window. F11 fills
    the screen, and Escape sends it home.

  The controls sit in the right-hand panel, in the Fringe tab:
    Stack, Session, Pressure point, FFT removal, Refractive Index
    from Intensity, and Panels.


The four charts

  Left column: the ripple spectrum, Background on top and Sample
    below. Left to right is n*t in micron, which is thickness times
    index. A bump means a layer of about that thickness is in the
    light path. Up and down is the ripple's real amplitude.

  The tall coloured lines are the model's predictions. They mark
    where the stack you described puts a ripple. A coloured line
    under a measured bump means your model matches your data. Thin
    dashed lines at two and three times a line's position are its
    harmonics. Harmonics confirm a real interference pattern.

  Shaded bands show where a notch removes signal. The scale on the
    right edge reads the fraction removed. The dashed vertical line
    is the low-pass cut. Drag it.

  Right column: the measured spectrum itself, Background on top and
    Sample below. The raw curve draws in ink and the cleaned result
    draws in red. The left column plans the cleaning and the right
    column shows it done. Before a spectrum loads, this column
    reads "no measured data".

  Peak markers on the bumps:

      filled triangle   the main ripple
      filled circle     found automatically
      filled diamond    you put it there
      hollow            still listed, switched off

  Along the top of each left chart your cell is written out in
    order: anvil, medium, sample, medium, anvil. The picture and the
    numbers stay in step.


Using the mouse

  Point at a bump. The arrow becomes a HAND, and a ring marks what a
    click will act on. Left-click adds a notch there. Click again to
    take it away.

  Right-click a bump to pin it as the main ripple. The same menu
    hands the bump to one of the three role shapes.

  Point at the dashed low-pass line, or at a shape along the top.
    The arrow becomes a LEFT-RIGHT ARROW. Drag it.

  The three shapes arrive parked on the workbench's best guess. Drag
    them, or right-click a bump, to move them. Fit peaks then
    settles them onto the bumps properly.

      rectangle    through the sample
      half-filled  through the sample AND the diamonds
      diamond      through the medium only


FRINGE > STACK

  Describe what the light goes through, and read the answers back.

  Anvil: which formula stands for the diamond's index. Eremets
    follows pressure, and the tool feeds it each spectrum's own
    value. The result shows on the n diamond row, marked Fixed.

  Medium: what fills the cell. A named medium follows pressure
    through its n(P) model. Other means you type the index on the n
    medium row. The default is Other with n = 1.2. It is Fixed too,
    and the solve is anchored on it.

  Layer 2: switch it on when a second distinct layer is in the cell,
    then pick what it is.

  n sample: the index the prediction lines are drawn from, 1.5 to
    start. Fit peaks writes the solved value back here.

  d2 upper medium (um), t sample (um), d1 lower medium (um): the
    stack top to bottom, defaults 0 / 20 / 0. Beside each box is the
    solved value for that row. n_s sits beside n sample and t_s sits
    beside t. The medium total t_m sits beside d2. The whole gap L
    sits beside d1.

  Total (um) plus Lock In: unlocked, Total mirrors d1+t+d2. Locked,
    Total holds. d2 and t then trade against each other. A d1 change
    spreads over both in proportion. Editing the Total itself grows
    d2, or drains d1, then d2, then t.

  fine steps (/ 10): every spinbox moves in tenths.

  Fit peaks: the two small glyph buttons are the one-click workflow.
    Both re-detect all three peaks, solve, and write the answers into
    the boxes above. Distinct fits the rectangle and sample-diamond
    as separate peaks. Shared fits the rectangle as a shoulder on the
    sample-diamond's hump.

  Plot point: put this pressure point's solved values onto the
    results series. Results plot opens the series. A tick on its
    caption means this point is already on the series.

  The [?] on the card title opens the six interface pairs, the
    Fresnel amplitudes, the solve and its clamps.


FRINGE > SESSION

  Load parent folder...: pick a folder that CONTAINS series
    subfolders of *_absorbance.csv spectra. The dropdown between the
    arrows jumps between them. Each series opens at its lowest
    pressure.

  Load raw spectra...: pick one *_absorbance.csv. Its whole folder
    loads, and the Pressure point dropdown fills with its siblings.
    Both loaders read the files a Run writes. The bundled demo data
    and a beamline Processed CSVs folder load alike.

  Series:: names the working series.

  Save session: write the recorded points as
    series_continuity.json, plus a timestamped copy. They go beside
    the input data. A read-only folder sends them to your output
    folder. The status line names the path.

  Load session: read the file back, from wherever the last save put
    it. It is the format Matthew Diamond's program reads and writes.
    A folder saved by either program opens in the other.

  The small marks under the buttons: a tick when file and memory
    match, a dot when they differ, a circle while the first write is
    still to come.


FRINGE > PRESSURE POINT

  The dropdown picks which spectrum the workbench shows. The arrows
  walk the same list in the order the experiment ran: up the
  compression run, then back down the decompression leg. They stop
  at the ends.

  Leaving a point with unsaved changes asks first. The tool lists
  exactly what differs.


FRINGE > FFT REMOVAL

  The main cleaning tool, and the only one. This card is what the df
  box beside the plot cleans with. The defringed CSVs a Run writes
  and Export CSV clean with it too. It holds one sub-block per
  channel, Background and Sample, so the tool cleans the two
  independently. A channel the detector missed stays as it is.

  Low-pass cutoff: the tool treats everything above the cutoff as
    noise and removes it. The cutoff is in micron of n*t, default
    15. The dashed line on the chart is the same control. Drag
    either one and the other follows. The edge is soft, so the
    result stays smooth.

  Clear notches: take every notch off that channel. The fundamental
    stays in the list, unticked and ready to re-enable.

  Export cleaned spectrum: write the red FFT filtered curve per
    channel to CSV. The columns are Wavenumber_cm, Background_notch,
    Sample_notch, Absorbance_notch.

  Notch list: the notch table in its own window. It holds every
    centre with its own half-width. It also holds the fundamental
    flag, a remove cross, and the default width for new notches.

  Write notches file for batch: save notch_overrides.csv, with every
    centre and width you picked. The batch pipeline reads that form
    back.

  Delete notches file: remove this spectrum's saved rows from that
    file. The live notches on the chart stay.

  Write to defringe: hand your centres and low-pass cutoffs to the
    whole series. From then on the df box cleans at exactly the peaks
    you picked. A Run's defringed CSVs and Export CSV do the same.
    Press it
    again after you change your mind. Until you press it at all, df
    notches the auto-detected ripple on its own.

  With df ticked, a Run also writes {stem}_absorbance_notch.csv
    beside each absorbance CSV.

  The Detection card holds the search gates that decide what counts
    as a ripple. It also holds the switch that keeps the fringe
    report out of the log.

  The [?] on the card title shows the mask as a formula: the
    Gaussian notch, the mirror padding, the tanh low-pass edge.


FRINGE > REFRACTIVE INDEX FROM INTENSITY

  A fringe's amplitude also carries an index. How strongly the faces
  reflect sets how deep the ripple is.

  Compute fits: run the full amplitude fitters on the current notch
    and low-pass settings. The fitters are the cosine fit and the
    band integral, over every spectral window. The right panels
    switch to the tiered view, and the fitted n appears in each panel
    title.

  History: reopen a previous Compute fits run, with its inputs and
    notch settings, named by the fitted n.

  Show tiered / Hide tiered: the flat view shows raw plus the
    cleaned curve at true intensity. Tiered stacks the diagnostics
    apart: the cosine-fit residual, the cleaned curve, each fitted
    window's defringed curve, and raw on top. The left panels gain
    the crimson and blue residual FFTs.

  Hide clean spectrum / Show clean spectrum: the red curve, on and
    off.

  Band D resolution floor: the band integral holds its integration
    band at the FFT main lobe or wider. Only the band values move.
    The cleaning stays as it is.

  The [?] on the card title holds the two estimators and the Fresnel
    inversion, written out.


FRINGE > DETECTION

  The search gates: wavelength window, n*t band, Fisher p, and
  agreement tolerance. The card also holds the live report of what
  the search found. These are the program's detection gates, and
  the df box reads them too.

  This dataset only keeps a window for one input folder alone.

  Suppress fringe report keeps the per-trace summary out of the
    main log.


FRINGE > PANELS

  The pop-out windows, one click each: Notch list, Predicted lines,
  Results and Info. Predicted lines holds the forward-model lines
  as copyable text. Info holds the marker key and the mouse
  grammar. Detection scrolls the Detection card into view.

  Error bars (multiscale variance): uncertainty for the results
    plot, from the spread of the fit across analysis scales. The
    tool computes it once per point and caches it.

  Below the buttons sit the status line, the solve line, and the CSV
  folder every export writes to. Clamp warnings appear on the solve
  line.


Results vs pressure

  Six charts against pressure: the three indices n_s, n_medium and
  n_layer2 over the three thicknesses t_s, L and t_layer2.

  Compression points are filled circles. Decompression points are
  open crosses. Point colour is the medium the point was solved
  under.

  Re-solve under runs every recorded point through another medium's
  pressure curve. The result is exact, because each point stores the
  measured paths themselves. EoS curves adds dashed
  equation-of-state lines to the thickness charts. Right-click a
  point to anchor a curve there. One key along the bottom names
  every mark. Save figure... writes the grid at print quality.


State, and keeping work

  The workbench tracks what you changed and what it has written:

      check   written down, same as the file
      dot     changed here, still to write
      circle  waiting for the first record

  Moving away from unsaved changes offers save, discard, or stay,
  with the differences listed. Long lists stop at eight lines and
  count the rest.


Credit

  The fringe analysis is a port of Matthew R. Diamond's
  defringe_dac.py, used with permission under the MIT license. The
  numbers are checked against the original on real spectra, and his
  citations are kept in the source.
