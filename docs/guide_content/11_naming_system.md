NAMING SYSTEM

How a filename becomes a measurement. Everything downstream is
decided here: grouping, absorbance, legends, and output file names.
Ten minutes with this view covers every folder you will meet.

To reduce a folder, Run has to know five things about every file.
Which DAC it came from. Which sample. What the value of the
experiment variable was. Which channel it is (sample / background /
dark). Which grating segment it is. Those five are the whole job.


TOKENS

  The tool reads a filename as a list of pieces. A piece, or token,
    is whatever sits between two separators.

      vis_Y04_Arch29_26p0_s.003
      \_/ \_/ \____/ \__/ \/ \_/
       1   2    3      4   5  segment suffix

    Token 1 is a fixed prefix. Tokens 2 and 3 are the DAC id and the
    sample id. Token 4 is the value and token 5 is the channel
    keyword. The '.003' at the end is the segment suffix. The tool
    splits it off the end of the name BEFORE it tokenizes anything.

  The tool drops empty tokens, so a doubled separator reads as one.

  A profile assigns a MEANING to each token position, in order. The
    meanings available are:

      dac       the cell id. Required, unless a default supplies it.
      sample    the sample id. Required, unless a default supplies it.
      pressure  the value of the Series variable. Optional.
      role      the channel keyword (sample / background / dark).
      branch    the compression / decompression tag.
      rep       the retake number.
      ignore    a piece that carries nothing the pipeline needs.

    'pressure' is the internal name of the field, whatever the Series
    variable is called. The dialog shows the variable's own name on
    the label and the preview column.


THE TWO KINDS OF PROFILE

  22-IR-1 default (built-in). A fixed, hand-written grammar. It
    ships read-only, and its behavior holds across releases.

      vis_{DAC}_{Sample}[_{Pressure}][_bg|_s][_C|_D][_rep][.{seq}]

    - the name starts with 'vis' and carries at least three
      underscore-separated tokens
    - a bare name = dark, _bg = background, _s = sample
    - _C / _D is the branch tag; _2 / _3 is a retake. They may appear
      in either order
    - the value uses 'p' for the decimal: 1p39 = 1.39. 0 is allowed.
      The tool reads a missing value token as 0 and notes it in the
      log
    - the segment suffix is a dot plus digits (.001 .. .00N). Any
      number of segments is fine. Omit it for a single-stitch file
      and the segment is 1
    - a trailing '.csv' twin is tolerated and deduplicated

    Worked example:

      vis_Y04_Arch29_26p0_s.003
        DAC       Y04
        sample    Arch29
        value     26.0
        channel   sample
        branch    none
        retake    1
        segment   3

    Rejections this grammar produces:

      vis_Y04_Arch29_26p0_s_r.003
        'unrecognized trailing token'. _r is not a known suffix. The
        built-in accepts bg / s / C / D / a digit retake.
      vis_Y04_Arch29_26p0_sA.003
        The same reason. 'sA' is not the sample keyword.
      vis_Y04_Arch29_bg.001.002
        'malformed (extra extension)'. The base still holds a dot
        after the tool split the segment off.
      vis_Y04_Arch29_26p0_s.abc
        'segment is not numeric'.
      Y04_Arch29_26p0_s.003
        'does not match vis_DAC_SAMPLE[_PRESSURE]'. There is no 'vis'
        prefix.

    Each of these has a fix that leaves your file names alone.
    Teach a custom profile, or fix the individual files by hand.
    Both are below.

  Custom profiles. Everything above becomes editable. The tool saves
    a custom profile under a name, lists it in the Profile dropdown,
    and keeps it across restarts.


THE PROFILE FIELDS

  Prefix
    A fixed first token at the start of every filename. The tool
    compares it case-insensitively and then consumes it. The
    classic names use 'vis'. Blank suits names that open on a
    field. A name that starts with something else is skipped with
    "missing prefix '<x>'".

  Separator
    The text between tokens. It is usually _ or -. Comma-separate
    alternatives to accept several: '_,-' splits on either. The tool
    tries alternatives longest-first, so a multi-character
    alternative wins over a single character inside it. A bare ','
    means the comma itself is the separator.

  Value decimal (labelled with the Series variable's name)
    The character that stands for the decimal point inside the value
    token. 'p' reads 12p5 as 12.5. '.' reads 12.5 directly. ',' reads
    12,5. The tool also accepts '.' and ',' whatever you pick, so a
    folder that mixes 12p5 and 12.5 still parses.

  Strip units
    Unit text the tool removes from the END of the value token before
    it reads the number, comma-separated. With 'gpa,kbar', the token
    '15.3GPa' reads as 15.3. Matching is case-insensitive and the
    first match wins.

  Segment sep
    The text immediately before the grating-segment number at the
    very end of the name. It may be several characters: '_seg' reads
    name_seg003. The RIGHTMOST occurrence splits base from segment.
    Blank suits a convention of plain names, where every file is a
    single stitch.

  Numbering
    digits  - any all-digit run, read with int(), so any padding
              works: .001, .01 and .1 all mean segment 1.
    letters - a = 1, b = 2 ... z = 26, then aa = 27 (spreadsheet
              style), case-insensitive. Capped at two letters, so a
              plain data extension (.txt, .dat, .asc) stays an
              extension.

  No number =
    What a bare name means. Give a segment index, normally 1, which
    means one stitch called segment 1. Give the word 'reject' to
    skip such files with the reason
    "no segment suffix ('<sep><segment>' required)". Use 'reject'
    when every real file in the convention is numbered, so a bare
    name is something else: a log, a note, a stray export. 'reject'
    needs a segment separator, and the validator says so when the
    separator box is blank.

  Background / Sample / Dark keyword(s)
    The token that marks each channel. Comma-separate alternatives
    (bg,ref). Matching is case-insensitive. Dark is the default
    role, so the Dark box can stay empty. Fill it when your names
    say 'dark' explicitly.

  Compression / Decompression keyword(s)
    The branch tag, shown as C and D on the plot. D draws dashed.
    Classic names use c and d. Comma-separate alternatives. Leave
    both blank and the tool uses the classic c / d.

  Default DAC Name / Default Sample Name
    For single-cell folders whose names omit that piece. Put the
    value here AND drop that label from the token order. Set the
    chip to 'ignore', or leave the field chipless. dac and sample
    are the two required fields, and a token or a default supplies
    each.

  Token order
    The chips under 'Teach by example' set it. It is the list of
    meanings, in the order the pieces appear.


HOW A NAME IS PARSED, STEP BY STEP

  1. The tool removes a single trailing '.csv'.

  2. The tool splits the segment suffix off. When the segment
     separator appears in the name, the tool decodes the text after
     its rightmost occurrence under the numbering scheme. It counts
     as a segment only when it decodes AND something is left in front
     of it. Otherwise the 'No number =' policy applies.

     This step runs first and is permissive. It leaves a dotted
     value like '1.5' alone when the segment separator is '.'.

  3. The tool tokenizes the rest on the separator.

  4. The prefix, if any, matches the first token. The tool
     consumes it.

  5. The tool walks the token order left to right against the
     remaining tokens. The optional fields behave like this:

       dac, sample   consume the token unconditionally. A missing
                     token is an error ("missing dac token").
       ignore        consume a token if one is there.
       pressure      consume the token ONLY if it reads as a number,
                     after unit-stripping and decimal substitution.
                     Otherwise the value stays at its default and the
                     token goes to the NEXT field.
       role          consume the token ONLY if it is a known channel
                     keyword.
       branch        consume the token ONLY if it is a known branch
                     keyword.
       rep           consume the token ONLY if it is all digits.

     That conditional consumption lets one profile read
     vis_Y04_Arch29_bg.001 and vis_Y04_Arch29_26p0_bg_C_2.001 with
     one token order. An absent piece leaves its token to the
     next field.

  6. Any token left over is an error: "unrecognized trailing token".

  7. The resolved channel reads as dark, background or sample.

  Defaults fill anything the name omits: value 0, channel dark,
  retake 1, plus the DAC and sample defaults you set.


TEACH BY EXAMPLE

  Open 'Name format' from the left panel. The window holds the
  grammar boxes on top and the chip strip in the middle. The live
  whole-folder preview sits below them. A Guide card sits on the
  right.

  1. Pick a profile, or press 'Save as...' and name a new one. The
     built-in opens read-only. Saving under a new name starts you
     from an editable copy of it.

  2. Set the grammar boxes: separator first, then prefix, decimal,
     unit stripping, keywords, segment convention.

  3. Under 'Teach by example', pick a real filename from the folder.
     Pick one that shows EVERY piece your scheme can produce, so each
     piece gets a chip to label.

     The tool decomposes the name in place. Each token gets a bold
     chip with a dropdown under it. Set the dropdown to what that
     piece means. The gray pieces between chips are the literal
     separators found in that name. Click one to jump to the
     Separator box. A matched prefix gets its own chip, whose
     dropdown reads 'prefix'. Change that dropdown to a field to
     label the piece like any other. The segment suffix sits at the
     end with a caption saying how the tool read it.

     A tail can look like a segment number while the current
     settings skip it. The tool still shows it separately, with a
     caption naming the box to change ("segment tail: set Segment
     sep: '-'"). Click it to jump to that box.

  4. Watch the Preview. The tool parses every file in the folder with
     the grammar as it stands. Green rows parsed. Red rows skipped,
     with the reason in the note column. Blue rows fixed by hand. The
     counter under the list reads "matched N / M files". You can drag
     the columns. Hover a clipped cell to see it in full.

     The preview reads at most the first 500 files in the folder. It
     says so when it stops there.

  5. When the match count satisfies you, press 'Use this profile'.
     The tool saves the profile and Run uses it. The tool processes
     the folder when you press Run.

     A grammar with a problem makes the button refuse, and the tool
     lists the problem. The problems are:

       an empty separator
       an unknown field
       a role keyword that maps to no channel
       dac or sample supplied by neither a token nor a default
       an unusable segment scheme
       a bad missing-segment value


GUESS FORMAT

  'Guess format' reads the folder and proposes the whole grammar. It
  is a starting point. The preview is the real check.

  What it does:
    Segment convention first. It scores candidate separators
      (. - _ _seg -seg) against both numbering schemes. It looks for
      the same base recurring with SEVERAL different segment values
      (x.001 and x.002), which is the strong signal. Coverage alone
      is weak, because dotted values look the same. If every file it
      examined is numbered, it sets 'No number =' to 'reject'. If
      only some are, it sets 1.
    Then the token separator, chosen for the most consistent token
      count across the folder.
    Then a shared literal first token becomes the prefix. It skips
      that step when absorbing the token would leave fewer than two
      id columns. That happens in a single-cell folder where the
      shared token IS the DAC id. It then retries with no prefix.
    Then it classifies columns: a value column (a token that parses
      as a number, where bare integers alone are a weak signal), a
      channel-keyword column, a branch column, a retake column. It
      knows the usual words: bg / ref / back / background, s / sam /
      samp / sample / sig, dark / dk / drk, c / comp / up,
      d / dec / decomp / down.
    The first two unclaimed columns become dac and sample.

  It reports "matched N / M files" as a toast and in the log. It
  hands back a plain default in two cases. One is a folder with
  fewer than two id columns. The other is a profile the validator
  rejects.


WORKED EXAMPLES

  Every piece present, dash-separated:

    vis-D42-fo90-15.3GPa-s-c-2.003

      Prefix          vis
      Separator       -
      Value decimal   .
      Strip units     gpa
      Sample keyword  s
      Compression     c
      Segment sep     .
      Numbering       digits
      Order           dac, sample, pressure, role, branch, rep

    That reads as DAC D42, sample fo90, 15.3, sample channel,
    compression, retake 2, segment 3.

  Letter segments (a/b/c):

    ol_run7_4p2_bg_b

      Segment sep  _
      Numbering    letters
      No number =  1

    The rightmost '_' splits 'b' off, which decodes as segment 2.
    Here the segment separator and the token separator are the same
    character. That works. It also means the tool reads any name
    ending in a one-letter or two-letter token as a segment. See the
    traps below.

    Give segments their own separator when you can, such as '-b' or
    '_segb'. The two conventions then stay apart.

  Zero-padded to two digits (.01):

    Numbering 'digits' reads .01, .1 and .001 identically, because
    the tool parses the suffix with int().

  Dash-numbered segments (-1, -2, -3) with underscore tokens:

    quartz_C3_8p1_s-2

      Separator    _
      Segment sep  -
      Numbering    digits

    The two conventions stay apart, because '-' serves the segment
    alone here.

  Single-cell folder, with DAC and sample outside the names:

    12p5_bg.001

      Prefix               (blank)
      Separator            _
      Default DAC Name     Y04
      Default Sample Name  Arch29
      Order                pressure, role

    The dac and sample chips are absent from the order. The defaults
    supply both. The output CSVs are still named
    Y04_Arch29_12p5_absorbance.csv.

  Names with a spare piece:

    vis_20260731_Y04_Arch29_26p0_s.003

    Label the date chip 'ignore'. The tool consumes and discards it.


EDGE CASES AND TRAPS

  Decimal character equal to the segment separator.
    Take decimal '.' with segment sep '.'. A name ending in a dotted
    value ('..._2.5') has its '5' read as a segment. The segment
    split runs first, on the character alone. The preview makes it
    visible at once: the value column reads 2 and the segment column
    reads 5. Give segments a different separator, or use 'p' for the
    decimal.

  Token separator equal to the segment separator.
    This is legal, and sometimes unavoidable. The cost is that any
    trailing token that decodes under the numbering scheme becomes
    the segment. Under 'digits' the tool eats a trailing retake
    number. Under 'letters' it eats a trailing one-letter or
    two-letter keyword. Check the preview's segment column against a
    name you know.

  A value of 0.
    It is allowed and meaningful. The tool also reads a MISSING
    value token as 0. For that group the log records "no pressure
    in filename, assumed 0 GPa", so the two cases stay apart.

  Negative or non-finite values.
    The tool takes a finite value at or above 0, and rejects the
    rest.

  Case.
    The tool matches prefix, channel keywords, branch keywords, unit
    suffixes and letter segments case-insensitively. It keeps DAC and
    sample ids exactly as written, because they become file names.

  Raw/.csv twins.
    The tool recognises a file and its .csv copy as one logical
    segment and counts it once. It logs a skipped name once as well.

  Data extensions.
    Under 'letters', a segment runs to two letters, so .txt / .dat
    / .asc survive as extensions. Under 'digits' the same holds,
    because those suffixes carry letters.

  Two profiles, one folder.
    One profile is active at a time. When a folder mixes two
    conventions, run the majority convention and fix the minority by
    hand, below. You can also split the folder.


FIXING STUBBORN FILES

  A few files earn a hand fix of their own: the one hand-labelled
  retake, the stray export with a date in the middle. Double-click
  any row in the preview to type its fields by hand. Selecting it and
  pressing 'Fix selected...' does the same.

    Channel role   dark / background / sample
    DAC
    Sample
    <Series variable>
    Replicate
    Segment

  Leave a field blank to keep what the parser produced. A fix beats
  any pattern. A fix that supplies a channel role can even
  resurrect a file the parser rejected outright. A fix on a
  rejected file needs that role, and the tool ignores a fix that
  leaves it blank.

  'Exclude selected' leaves the file out of the run entirely. The
  preview note then reads "excluded by user". 'Remove fix' inside the
  fix dialog undoes one file. 'Clear all fixes' forgets every fix and
  exclusion for the folder.

  The tool stores fixes per folder and keeps them across restarts. It
  applies them after parsing, on every Run, Rescan and preview.


WHERE THE PARSED VALUES GO

  dac, sample and the value become the output file name stem:
    {DAC}_{SAMPLE}_{VALUE}[_C|_D]_absorbance.csv, with 'p' as the
    decimal.

  The trace's identity label is "{DAC} {SAMPLE} {VALUE} GPa", plus a
    branch tag and a retake note. The interface relabels it to the
    active Series variable's unit for display. The identity label
    itself holds. It is the key that presets, sessions and exports
    resolve through.

  The channel decides which of Sample / Background / Dark the file
    contributes to. The segment decides concatenation order. The
    retake decides which measurement wins, which is the highest
    index.
