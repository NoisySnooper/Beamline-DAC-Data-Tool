TROUBLESHOOTING

Symptom first, then the cause and the fix. For anything to do with a
Run, look first at the Progress log on the left panel. 'Copy log'
takes the whole log to the clipboard.


NO TRACES AFTER A RUN

  The log says "Found 0 measurement group(s)".

  The log may also print a HINT that lists subfolders. You then
    pointed at a parent folder. The scan reads one folder. Pick the
    folder that holds the segment files themselves.

  Every file may be on a SKIP line. Another naming profile then
    fits. Open 'Name format', press 'Guess format', check the
    preview, and press 'Use this profile'. The Naming system view has
    the full walkthrough.

  The folder may hold this tool's own *_absorbance.csv output in
    place of raw segments. Run then falls back to viewer mode, loads
    them, and says so in the log. 'Load previous run...' is the
    direct route to the same result.


FILES WERE SKIPPED - WHAT THE REASONS MEAN

  Every skipped file gets one SKIP line with its own reason. The
  preview inside 'Name format' shows the same reasons live, in red,
  before you commit to anything.

  does not match vis_DAC_SAMPLE[_PRESSURE]
    The built-in grammar needs a 'vis' first token and at least three
    underscore-separated pieces. Your files use another scheme.
    Teach a custom profile.

  missing prefix '<x>'
    Custom profile. The first token differs from the prefix you
    set. Correct the Prefix box, or clear it.

  unrecognized trailing token '<x>'
    Every field in the token order was satisfied and a piece is left
    over. It is usually one of two things. It can be a date or
    operator initials outside the profile, so label that chip
    'ignore'. It can be a suffix outside the built-in grammar: the
    built-in takes bg / s, C / D and a digit retake, so it rejects
    _r and _sA.

  missing dac token / missing sample token
    The name ran out of pieces before the tool filled those fields.
    The order may have one field too many. This file may also be
    shorter than the rest. For single-cell folders, drop the chip and
    use Default DAC Name / Default Sample Name.

  segment is not numeric
    Built-in grammar. The text after the final dot holds something
    other than digits.

  no segment suffix ('<sep><segment>' required)
    Custom profile with 'No number =' set to reject. This file may be
    off-convention. The policy may also be too strict, so set it back
    to 1.

  malformed (extra extension)
    Built-in grammar. The base still holds a dot after the tool split
    the segment off. An example is ..._bg.001.002. Fix the file, or
    fix that one file by hand in the preview.

  pressure '<x>' not numeric / pressure not finite / < 0
    The value token reads as a finite number at or above 0. Check
    the Value decimal box ('p' against '.') and Strip units.

  role '<x>' is not a valid channel
    A role map entry points at something other than dark, background
    or sample. Correct the keyword boxes.

  excluded by user
    You excluded that file in the preview. 'Clear all fixes' undoes
    every exclusion and hand fix for the folder.

  Two escape hatches always work, whatever the reason.
    Double-click the row in the preview and type the fields by hand.
    Select it and press 'Exclude selected'. The tool remembers fixes
    per folder.


A PROFILE WILL NOT COMMIT

  'Use this profile' refuses and lists the problems. The common ones:

    separator is empty
      The Separator box has to hold something.

    '<dac|sample>' missing from token order
      Add a chip for it, or give it a default in Default DAC Name /
      Default Sample Name.

    role is in the order but the role map is empty
      You labelled a chip 'role' and gave no channel keywords.

    'reject' needs a segment separator
      With a blank segment separator, no file ever has a segment
      number. 'reject' would then skip everything.

    missing-segment value must be a whole number >= 1 or 'reject'
      The 'No number =' box takes a whole number at or above 1, or
      the literal word 'reject'.


THE VALUE AND SEGMENT COLUMNS LOOK SWAPPED

  A name ends in a dotted value, and '.' is both the value decimal
  and the segment separator. In '..._2.5' the tool reads the 5 as a
  segment. It splits the segment off before it parses anything else.
  Use 'p' for the decimal, or give segments their own separator.

  The same trap has a milder form. The token separator and the
  segment separator can be the same character. Any trailing token
  that decodes under the numbering scheme then becomes the segment.
  Check the preview's segment column against a name you know the
  answer for.


A TRACE HAS NO ABSORBANCE

  Absorbance needs sample plus background plus dark. A group that
  misses one loads as raw counts. Its name carries a channel tag
  ([S only], [S+B]) and the log carries a line.

  In a load of raw channels alone, the overlay Y axis switches to
    the best available raw channel. It says so in the log.

  A load can mix complete groups with incomplete ones. A banner then
    offers a one-click switch to the channel the incomplete ones
    have.

  Either way, use Inspect one trace to see which channels arrived.
    Then check the file names for the missing one.

  "no shared segments -- skipped" means the channels of that group
    share zero segment numbers. Take a sample numbered .001 to
    .002. A background numbered .001 to .004 shares .001 and .002
    with it. A background numbered .005 onward starts past both.
    Check the segment numbering on that measurement.

  "channel grids differ ... aligned by wavelength" is a warning. The
    tool interpolated the channels onto the anchor channel's grid.
    Points outside a channel's own range become NaN.


A TRACE IS FLAGGED IN DATA > TRACES

  The colored dot means a quick quality check fired. Hover it.

  "N point(s) at A >= 4: likely saturated or blocked beam"
    The sample channel is at or near the detector floor over part of
    the range. The ratio is meaningless there. Use Inspect one trace
    and look at the raw counts. A sample channel pinned near
    the dark level does this. A background that has drifted down
    toward it does this too. The fix is at the beamline: more light
    or a shorter path. You can hide the affected range with the
    saturation cutoff in the smoother, and say so in the methods.

  "negative absorbance over N point(s): check channel pairing / lamp
   drift"
    The sample channel is coming out brighter than the background.
    That usually means the background was taken at a different lamp
    state, or the two channels are mismatched. Check that the right
    background is paired. The group uses the latest retake of the
    anchor channel and matches the others by replicate.

  "no absorbance (raw channels: ...)" names the channels that did
    arrive. See above.


DEFRINGE FINDS NO FRINGE

  This is a normal outcome. The tool notches a channel on a
  confident detection alone, and passes the rest through as they
  are.

  Read the fringe report in the log. It lists the traces with a
    detection, their fitted n*t in micron, and the p-value. An
    absent trace is one the detector missed.

  Everything you need sits in the Fringe tab, in the Detection
  card.
    Widen the search window. 'n*t band (um)' defaults to 8 to 300 um.
      A very thin or very thick sample falls outside that band.
    Loosen the significance gate. 'Fisher p' defaults to 1e-4.
      Raising it catches weaker fringes, at the cost of notching
      noise now and then. The box accepts scientific notation.
    Check the trace has enough finite points. Detection runs at 16
      finite points or more.
    Look at the raw counts. Detection operates on the raw Sample and
      Background channels independently, before the ratio. The fringe
      lives there.

  Detection may succeed and still give a wrong result. The usual
    cause is a harmonic: the FFT latched onto 2 n*t or 3 n*t in place
    of the fundamental. The fringe workbench shows the harmonics
    explicitly. Right-click the bump you believe in to pin the
    fundamental by hand.

  The same pop-out carries 'Suppress fringe report'. Tick it to keep
    the log quiet about all this.


THE NOTCH REMOVED SOMETHING I WANTED

  Turn on 'Defringe compare (selected trace)' in PLOT > 2D PLOT
  OPTIONS and click the curve. The tool draws the pre-defringe
  absorbance behind it in gray dashed, so you can see the
  difference.

  Then narrow the notch. Open FRINGE > FFT REMOVAL > Notch list and
  drop the half-width. Every centre can carry its own half-width.
  Untick df beside the plot to switch the whole thing off.


TEXT IS UNREADABLE, OR A CONTROL LOOKS WRONG AFTER A THEME SWITCH

  The tool derives field text from the active theme and re-pins it on
  every theme change. If it ever goes stale, the tool heals it on the
  next redraw and logs "field styles were stale". If you see that
  line, the fix has already happened. Switching theme once more
  forces it immediately.

  On some Tk builds, checkboxes, radio buttons and switches keep a
  fixed blue accent. It is known, accepted and cosmetic.

  For interface text that is too small or too large, use Text size
  in the top bar's Settings panel. It runs from 3 to 15, and 'auto'
  takes the size from the screen. It applies live and the tool
  remembers it.

  For maximum legibility use the High Contrast theme. For
  color-vision safety use Colorblind Safe (Okabe-Ito). Both themes
  carry state in shape as well as color. The active-row cues are a
  tint, a bold name and a text tag.

  The interface theme stops at the interface. 'Tint plot with
  theme' in STYLE > COLORS & COLORMAP carries it into the figure.


ITALIC DOES NOTHING

  The bundled Jost typeface draws upright at every weight. Pick
  Arial or Segoe UI in STYLE > FONTS for an italic face. Journal
  presets already set Arial, or a serif for APS.


THE LEGEND CHANGED SIZE ON EXPORT

  'Auto-fit oversized legend' reflowed it to fit the page. It adds
  columns first, then it lowers the font size. The tool writes the
  values it used back into STYLE > LEGEND. You can see what happened
  there, and keep those values. Turn it off to have your settings
  honored
  exactly as typed. An oversized legend then overflows.


A RUN WROTE TO A FOLDER I DID NOT EXPECT

  A Run creates <output>/<input folder name>_absorbance/ and writes
  there. The tool appends a timestamp when that folder exists and
  holds files. An earlier run then keeps its own folder. 'Open
  output' opens the folder the tool actually used.


AUTO RESCAN IS NOT FIRING

  It waits for the first Run, which gives it a baseline file list
    to compare against.
  It fires while the tool sits idle.
  It re-runs the folder when new files appeared.
  It is one timer for the whole program.
  The status line under the plot reads 'auto-rescan: N s' whenever
    the timer is armed. Any other reading means the timer is off.


WINDOWS 7 AND OTHER OLDER MACHINES

  A separate Windows 7 package is built for Python 3.8.10. Each
  release is checked for parity with the current build.

  What you may notice on such a machine:
    Some keyboard shortcuts depend on newer key symbols and stay
      unbound. Ctrl+Shift+Tab still cycles tabs backwards.
    The interface animations cost more than they are worth. Turn on
      'Reduce motion' in PLOT > 3D PLOT OPTIONS.
    3D rotation is the expensive operation. Lower '3D detail
      (points/ridge)' and turn on 'Performance mode (faster 3D)'.
      Both controls act on the 3D view alone. 2D plots and every
      export use the full data.
    Pane dragging can feel heavy. Turn on the app-wide Performance
      mode, in the top bar's Settings panel. The dividers then show
      a guide line and resize once, on release.

  A program that stays shut on an old machine may be unpacked
  wrong. Check that you unpacked the whole distribution folder. It
  is a directory build, and the launcher runs from inside it.


NOTHING ELSE WORKS

  NUKE, on the top bar, clears the session and keeps your files.
  Loaded data, the plot, the folders, the log and every control go
  back to a fresh start. Your files on disk stay as they are, and
  your saved presets and default colormap survive. It asks first.

  'Reset all' on the right panel's control bar is the gentler
  version. It puts every plot control back to default and keeps your
  data and folders.
