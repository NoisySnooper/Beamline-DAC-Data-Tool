r"""
formulas.py  --  SPARTA: user-defined computed quantities (formula editor).

The pipeline's absorbance A = -log10[(Sample - Dark)/(Background - Dark)] is
fixed: engine.py owns it and its CSV schema is frozen. This module is the
OTHER lane -- it lets a user define extra quantities over the same channels
(transmittance, a raw ratio, an optical-density variant, anything expressible
as arithmetic over the loaded columns), written in ordinary Python/numpy
syntax and displayed as matplotlib mathtext.

Three pieces, all pure:
  1. COLUMNS -- the registry of names an expression may use, each with the
     description the editor's legend shows and the symbol it prints as. New
     columns (Phase F2: defringed / smoothed variants) are added with
     add_column(); the evaluator and the renderer read the table at call
     time, so nothing else changes.
  2. A whitelist evaluator. Text is parsed with ast.parse(mode="eval") and
     walked against an explicit node/name/function whitelist BEFORE any
     arithmetic happens; expressions are then evaluated node by node with
     numpy. Nothing ever reaches eval()/exec(), so a rejected expression is
     not merely blocked, it is never executed. Validation returns a list of
     human-readable problems ([] = usable), same shape as
     engine.validate_profile.
  3. A renderer that turns the SAME ast into mathtext ('/' -> \frac{}{},
     '**' -> ^{}, log10 -> \log_{10}, wl -> \lambda ...), so the picture
     always matches the arithmetic. Rendering from the tree (not from the
     text) is what makes the parentheses come out right.

Quantities are plain JSON-able dicts, so settings / sessions / provenance
store them as they are. The two builtins (Absorbance, Transmittance) are
flagged read-only; the GUI shows them but never edits them.

No GUI imports, and deliberately no engine import: this module is unit-
testable on its own, and its CSV writer copies engine's conventions instead
of borrowing its code.

NQT / Lee Lab -- Jul 2026
"""

import ast
import csv
import math
import re
import unicodedata

import numpy as np

# Largest literal exponent a formula may use. '**' with a bigger constant is
# rejected outright: nothing in this domain needs it, and it is the one
# operator where a typo turns into an unbounded computation.
POW_LIMIT = 8


class FormulaError(ValueError):
    """A formula that cannot be parsed, is not allowed, or has no data.

    Carries the same human-readable text validate_expr() puts in its list, so
    the GUI can show either without translating.
    """


# ---------------------------------------------------------------------------
# Column registry
# ---------------------------------------------------------------------------
# Canonical short names are what the evaluator and the renderer speak; the
# long aliases (and the engine result-dict keys) are resolved at parse time,
# so a user may type either. Matching is case-insensitive.

COLUMNS = {}


def add_column(name, desc, tex, aliases=()):
    """Register an input column and return its spec.

    name    canonical short name used inside expressions (S, B, D, wl, A)
    desc    one line for the editor's legend
    tex     mathtext symbol WITHOUT the $ delimiters (e.g. r'\\lambda')
    aliases other spellings that resolve to this column (long names, and the
            engine result-dict keys so the GUI can hand its dict straight in)

    Phase F2 registers the defringed / smoothed variants here; no other part
    of the module needs to know about them.
    """
    spec = {"name": name, "desc": desc, "tex": tex, "aliases": tuple(aliases)}
    COLUMNS[name] = spec
    return spec


add_column("S", "Sample counts (raw, dark not subtracted)", "S",
           ("sample", "samp_c"))
add_column("B", "Background / reference counts (raw)", "B",
           ("background", "bg", "bg_c"))
add_column("D", "Dark counts (detector baseline)", "D",
           ("dark", "dark_c"))
add_column("wl", "Wavelength in nm (the grid every column shares)",
           r"\lambda", ("wavelength", "wavelength_nm", "nm"))
add_column("A", "Absorbance as the pipeline computes it, "
                "-log10[(S - D)/(B - D)]", "A", ("absorbance",))
# Optical thickness. Per TRACE, not per point: the caller hands it in as a
# constant column over the same wavelength grid, so it divides an absorbance
# spectrum without any shape rules of its own. NaN wherever the fringe
# detector found nothing confident, which propagates to NaN and is drawn as
# a gap -- the honest answer, not a guessed thickness.
add_column("t", "Optical thickness n*t of the sample channel in um, from "
                "the fringe detection (NaN when no fringe was found)", "t",
           ("thickness", "nt_um"))


def column_names():
    """Canonical column names, in registration order."""
    return tuple(COLUMNS)


def canonical(name):
    """Resolve a column name or alias to its canonical short name (None if it
    is not a known column). Case-insensitive."""
    if name in COLUMNS:
        return name
    low = str(name).strip().lower()
    for cn, spec in COLUMNS.items():
        if low == cn.lower():
            return cn
        if low in tuple(a.lower() for a in spec["aliases"]):
            return cn
    return None


def column_legend():
    """Rows for the editor's legend: [{name, desc, tex, aliases}, ...]."""
    return [dict(COLUMNS[n]) for n in COLUMNS]


# ---------------------------------------------------------------------------
# Function whitelist
# ---------------------------------------------------------------------------
# nargs is exact (no optional arguments -- there is nothing to be gained and
# it keeps the arity error unambiguous). tex is a %-template over the already
# rendered arguments; prec is the rendered form's precedence (see _tex).

FUNCS = {
    "log10":   {"nargs": 1, "fn": np.log10, "prec": 5,
                "tex": r"\log_{10}\left(%s\right)",
                "desc": "base-10 logarithm"},
    "log":     {"nargs": 1, "fn": np.log, "prec": 5,
                "tex": r"\ln\left(%s\right)",
                "desc": "natural logarithm"},
    "exp":     {"nargs": 1, "fn": np.exp, "prec": 4,
                "tex": r"e^{%s}",
                "desc": "e to the power of"},
    "sqrt":    {"nargs": 1, "fn": np.sqrt, "prec": 5,
                "tex": r"\sqrt{%s}",
                "desc": "square root"},
    "abs":     {"nargs": 1, "fn": np.abs, "prec": 5,
                "tex": r"\left|%s\right|",
                "desc": "absolute value"},
    "minimum": {"nargs": 2, "fn": np.minimum, "prec": 5,
                "tex": r"\min\left(%s,\,%s\right)",
                "desc": "smaller of two, point by point"},
    "maximum": {"nargs": 2, "fn": np.maximum, "prec": 5,
                "tex": r"\max\left(%s,\,%s\right)",
                "desc": "larger of two, point by point"},
}


def function_names():
    """Whitelisted function names, sorted (for messages and the legend)."""
    return tuple(sorted(FUNCS))


def _func_list():
    return ", ".join(function_names())


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
# Whitelist by node type. Anything not on this list is rejected without
# recursing into it, so the reported problem is the outermost one the user
# actually typed rather than a pile of consequences.

ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call,
                 ast.Name, ast.Constant, ast.Load)
ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
ALLOWED_UNARYOPS = (ast.USub, ast.UAdd)

# Operators that parse but are not part of the formula language.
_OP_TEXT = {ast.Mod: "%", ast.FloorDiv: "//", ast.MatMult: "@",
            ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^",
            ast.LShift: "<<", ast.RShift: ">>",
            ast.Invert: "~", ast.Not: "not"}

# Node kinds worth naming explicitly; everything else falls back to the
# generic message in _reject().
_NODE_TEXT = {
    ast.Lambda: "lambda expressions are not allowed",
    ast.IfExp: "conditional expressions (a if b else c) are not allowed",
    ast.Compare: "comparisons are not allowed",
    ast.BoolOp: "'and' / 'or' are not allowed",
    ast.ListComp: "comprehensions are not allowed",
    ast.SetComp: "comprehensions are not allowed",
    ast.DictComp: "comprehensions are not allowed",
    ast.GeneratorExp: "comprehensions are not allowed",
    ast.List: "lists are not allowed",
    ast.Tuple: "tuples are not allowed",
    ast.Set: "sets are not allowed",
    ast.Dict: "dicts are not allowed",
    ast.Starred: "* / ** unpacking is not allowed",
    ast.NamedExpr: "':=' assignment is not allowed",
    ast.JoinedStr: "text (f-strings) is not allowed",
    ast.Slice: "slicing is not allowed",
    ast.Await: "await is not allowed",
    ast.Yield: "yield is not allowed",
}


def _opname(op):
    return _OP_TEXT.get(type(op), type(op).__name__)


def _reject(node):
    """The human-readable problem for a node that is not on the whitelist."""
    if isinstance(node, ast.Attribute):
        return "attributes are not allowed ('.%s')" % node.attr
    if isinstance(node, ast.Subscript):
        base = node.value.id if isinstance(node.value, ast.Name) else "..."
        return "indexing / slicing is not allowed ('%s[...]')" % base
    for kind, msg in _NODE_TEXT.items():
        if isinstance(node, kind):
            return msg
    return "'%s' is not allowed in a formula" % type(node).__name__


def _const_number(node):
    """The numeric value of a literal (or of -literal), else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _const_number(node.operand)
        return None if v is None else -v
    return None


def _check(node, probs):
    """Walk one node, appending problems. Rejected nodes stop the descent."""
    if isinstance(node, ast.Expression):
        _check(node.body, probs)
        return

    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, ALLOWED_BINOPS):
            probs.append("operator '%s' is not allowed (use + - * / **)"
                         % _opname(node.op))
        elif isinstance(node.op, ast.Pow):
            e = _const_number(node.right)
            if e is not None and abs(e) > POW_LIMIT:
                probs.append("exponent %g is too large (limit %d)"
                             % (e, POW_LIMIT))
        _check(node.left, probs)
        _check(node.right, probs)
        return

    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ALLOWED_UNARYOPS):
            probs.append("'%s' is not allowed" % _opname(node.op))
            return
        _check(node.operand, probs)
        return

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            probs.append("method calls are not allowed ('.%s(...)')"
                         % node.func.attr)
            return
        if not isinstance(node.func, ast.Name):
            probs.append("only the built-in functions may be called "
                         "(allowed: %s)" % _func_list())
            return
        fname = node.func.id
        spec = FUNCS.get(fname)
        if spec is None:
            if canonical(fname):
                probs.append("'%s' is a column, not a function" % fname)
            else:
                probs.append("unknown function '%s' (allowed: %s)"
                             % (fname, _func_list()))
        elif len(node.args) != spec["nargs"]:
            probs.append("%s() takes %d argument%s, got %d"
                         % (fname, spec["nargs"],
                            "" if spec["nargs"] == 1 else "s", len(node.args)))
        if node.keywords:
            probs.append("keyword arguments are not allowed")
        for a in node.args:
            _check(a, probs)
        return

    if isinstance(node, ast.Name):
        if canonical(node.id) is None:
            if node.id in FUNCS:
                probs.append("'%s' is a function -- write %s(...)"
                             % (node.id, node.id))
            else:
                probs.append("unknown name '%s' (columns: %s)"
                             % (node.id, ", ".join(column_names())))
        return

    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, (str, bytes)):
            s = v if isinstance(v, str) else v.decode("utf-8", "replace")
            probs.append("text is not allowed ('%s')" % s[:20])
        elif isinstance(v, bool) or v is None or v is Ellipsis:
            probs.append("%r is not allowed; formulas take numbers only" % v)
        elif isinstance(v, complex):
            probs.append("complex numbers are not allowed")
        elif not isinstance(v, (int, float)):
            probs.append("only numbers are allowed as constants")
        elif not math.isfinite(v):
            probs.append("'%s' is not a finite number" % v)
        return

    probs.append(_reject(node))


def validate_expr(text):
    """Return a list of human-readable problems with an expression
    ([] = usable). Nothing is evaluated: this is pure inspection of the
    parsed tree."""
    probs = []
    s = (text or "").strip()
    if not s:
        return ["expression is empty"]
    try:
        tree = ast.parse(s, mode="eval")
    except SyntaxError as e:
        return ["syntax error: %s" % (e.msg or "invalid syntax")]
    except (ValueError, MemoryError, RecursionError) as e:
        return ["cannot read the expression: %s" % e]
    _check(tree, probs)
    # keep the first occurrence of each message (a repeated mistake reads as
    # one problem, not five)
    seen, out = set(), []
    for p in probs:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def parse_expr(text):
    """Parse and validate an expression, returning the ast.Expression.

    Raises FormulaError listing every problem. The returned tree is known to
    contain only whitelisted nodes, so evaluate() and expr_to_mathtext() can
    walk it without re-checking.
    """
    probs = validate_expr(text)
    if probs:
        raise FormulaError("; ".join(probs))
    return ast.parse(text.strip(), mode="eval")


def _inputs(tree):
    return sorted({canonical(n.id) for n in ast.walk(tree)
                   if isinstance(n, ast.Name) and canonical(n.id)})


def inputs_of(text):
    """Sorted canonical names of the columns an expression uses."""
    return _inputs(parse_expr(text))


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def _as_array(v):
    """v as a float array, or None if it is not numeric at all."""
    try:
        return np.asarray(v, float)
    except (TypeError, ValueError):
        return None


def _resolve_columns(columns):
    """Map a caller's dict to canonical name -> float array.

    Keys may be canonical names, aliases, or a whole engine result dict --
    unknown and non-numeric keys are ignored. Lookup runs per column in a
    fixed order (canonical name, then the aliases as registered) rather than
    in the caller's dict order, and a real array beats a stray scalar: an
    engine result dict carries 'sample' as the sample's NAME and 'samp_c' as
    its counts, and the counts must win even when the name happens to parse
    as a number.
    """
    src = {}
    for k, v in (columns or {}).items():
        src.setdefault(str(k).strip().lower(), v)
    out = {}
    for cn, spec in COLUMNS.items():
        found = None
        for cand in (cn,) + spec["aliases"]:
            if cand.lower() not in src:
                continue
            arr = _as_array(src[cand.lower()])
            if arr is None:
                continue
            if arr.ndim:
                found = arr
                break
            if found is None:
                found = arr
        if found is not None:
            out[cn] = found
    return out


def _eval(node, vals):
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, vals), _eval(node.right, vals)
        op = node.op
        if isinstance(op, ast.Add):
            return a + b
        if isinstance(op, ast.Sub):
            return a - b
        if isinstance(op, ast.Mult):
            return a * b
        if isinstance(op, ast.Div):
            return a / b
        return a ** b                      # Pow (the only one left)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, vals)
        return -v if isinstance(node.op, ast.USub) else +v
    if isinstance(node, ast.Call):
        spec = FUNCS[node.func.id]
        return spec["fn"](*[_eval(a, vals) for a in node.args])
    if isinstance(node, ast.Name):
        return vals[canonical(node.id)]
    # Constant. Floats only: an integer literal in a '**' chain could
    # otherwise build an arbitrarily long int instead of overflowing to inf.
    return float(node.value)


def evaluate(text, columns):
    """Evaluate an expression over a dict of column arrays; returns a float
    ndarray.

    columns keys may be canonical names, aliases, or an engine result dict
    (extra keys are ignored). Arithmetic runs under np.errstate(all='ignore'):
    divide-by-zero, log of a negative, and overflow do not warn and do not
    raise -- every non-finite result comes back as NaN, which is what the
    plotting and export layers already expect.

    Raises FormulaError for a bad expression, a missing column, or columns of
    different lengths.
    """
    tree = parse_expr(text)
    vals = _resolve_columns(columns)
    used = {}
    for cn in _inputs(tree):
        if cn not in vals:
            raise FormulaError("no data for column '%s' (%s)"
                               % (cn, COLUMNS[cn]["desc"]))
        used[cn] = vals[cn]
    lens = {cn: v.shape[0] for cn, v in used.items() if v.ndim}
    if len(set(lens.values())) > 1:
        raise FormulaError("column lengths differ (%s)"
                           % ", ".join("%s=%d" % kv
                                       for kv in sorted(lens.items())))
    with np.errstate(all="ignore"):
        out = _eval(tree.body, used)
    out = np.asarray(out, float)
    return np.where(np.isfinite(out), out, np.nan)


# ---------------------------------------------------------------------------
# Mathtext rendering
# ---------------------------------------------------------------------------
# Precedence of a RENDERED fragment, used only to decide parentheses:
#   1 = a +- b, 2 = a*b and -a, 4 = a^{b} and e^{x},
#   5 = self-delimiting but wide (\frac{}{}, \sqrt{}, |...|, f(...)),
#   6 = a bare symbol or number.
# A child is wrapped in \left(...\right) when its precedence is below what
# its slot needs; the tree gives the grouping, so no string surgery is
# involved. The base of a power needs 6, which is why (a/b)**2 keeps its
# parentheses while S**2 does not.

def _num(v):
    """A number as mathtext ('%g', with an exponent turned into 10^{n})."""
    s = "%g" % v
    if "e" in s:
        mant, exp = s.split("e")
        return r"%s{\times}10^{%d}" % (mant, int(exp))
    return s


def _tex(node, need=0):
    s, prec = _tex_body(node)
    if prec < need:
        s = r"\left(" + s + r"\right)"
    return s


def _tex_body(node):
    """Render one node; returns (mathtext, precedence)."""
    if isinstance(node, ast.BinOp):
        op = node.op
        if isinstance(op, ast.Div):
            return (r"\frac{%s}{%s}" % (_tex(node.left), _tex(node.right)), 5)
        if isinstance(op, ast.Pow):
            return ("%s^{%s}" % (_tex(node.left, 6), _tex(node.right)), 4)
        if isinstance(op, ast.Mult):
            # a bare number next to a symbol needs a real dot; symbol next to
            # symbol reads better with a thin space
            numeric = any(isinstance(x, ast.Constant)
                          for x in (node.left, node.right))
            sym = r" \cdot " if numeric else r"\,"
            return ("%s%s%s" % (_tex(node.left, 2), sym,
                                _tex(node.right, 3)), 2)
        sym = "+" if isinstance(op, ast.Add) else "-"
        # 'a - (b - c)' keeps its parentheses; 'a + (b + c)' does not need any
        right_need = 1 if isinstance(op, ast.Add) else 2
        return ("%s %s %s" % (_tex(node.left, 1), sym,
                              _tex(node.right, right_need)), 1)

    if isinstance(node, ast.UnaryOp):
        sym = "-" if isinstance(node.op, ast.USub) else "+"
        return ("%s%s" % (sym, _tex(node.operand, 2)), 2)

    if isinstance(node, ast.Call):
        spec = FUNCS[node.func.id]
        return (spec["tex"] % tuple(_tex(a) for a in node.args), spec["prec"])

    if isinstance(node, ast.Name):
        return (COLUMNS[canonical(node.id)]["tex"], 6)

    # Constant. A number that renders in scientific form is already a power,
    # so it takes the same precedence as one (mathtext refuses a double
    # superscript, and (1e-5)**2 would produce exactly that).
    s = _num(node.value)
    return (s, 4 if "^" in s else 6)


def expr_to_mathtext(text):
    """Render an expression as a matplotlib mathtext string, '$...$'.

    Raises FormulaError if the expression does not validate.
    """
    tree = parse_expr(text)
    return "$" + _tex(tree.body) + "$"


def mathtext_problems(tex):
    """Problems rendering `tex` with matplotlib mathtext ([] = it draws).

    matplotlib is imported lazily and only its parser is touched (no figure,
    no backend, no GUI). If matplotlib is not installed the check is skipped
    rather than failing the quantity.
    """
    s = (tex or "").strip()
    if not s:
        return ["LaTeX is empty"]
    if s.count("$") % 2:
        return ["unbalanced '$' in the LaTeX"]
    try:
        from matplotlib.mathtext import MathTextParser
    except Exception:
        return []
    try:
        MathTextParser("path").parse(s)
    except Exception as e:
        first = str(e).strip().splitlines()
        return ["LaTeX does not render: %s" % (first[-1] if first else e)]
    return []


# ---------------------------------------------------------------------------
# Quantities
# ---------------------------------------------------------------------------
def quantity_key(name, taken=()):
    """A filesystem- and CSV-safe slug for a quantity name.

    Accents are folded to ASCII, every other run of non-alphanumerics becomes
    one underscore, and a name that leaves nothing behind (all-symbol or
    non-Latin) falls back to 'quantity'. `taken` is the keys already in use;
    a collision gets _2, _3, ... so two different quantities can never write
    the same CSV column or filename.
    """
    folded = unicodedata.normalize("NFKD", str(name))
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_only).strip("_")
    if not slug:
        slug = "quantity"
    if slug[0].isdigit():
        slug = "q" + slug
    taken = set(taken or ())
    if slug not in taken:
        return slug
    n = 2
    while "%s_%d" % (slug, n) in taken:
        n += 1
    return "%s_%d" % (slug, n)


def make_quantity(name, expr, unit="", latex="", taken=()):
    """Build a quantity dict (plain JSON-able types, no numpy, no objects).

    {name, expr, unit, latex, key, builtin}

    latex is auto-derived from expr when left empty; an explicit string is
    kept verbatim (that is the manual override, and it wins). An expr that
    does not validate simply leaves latex empty -- validate_quantity() is
    what reports the problem, so a half-typed formula can still be stored
    while the editor is open.
    """
    tex = (latex or "").strip()
    if not tex:
        try:
            tex = expr_to_mathtext(expr)
        except FormulaError:
            tex = ""
    return {"name": str(name).strip(),
            "expr": str(expr).strip(),
            "unit": str(unit).strip(),
            "latex": tex,
            "key": quantity_key(name, taken),
            "builtin": False}


def validate_quantity(q, taken=()):
    """Return a list of human-readable problems with a quantity ([] = usable).

    `taken` is the names of the OTHER quantities, for the uniqueness check
    (the caller owns the collection, so it owns that list). unit is free text
    and is never validated.
    """
    probs = []
    q = q or {}
    name = str(q.get("name") or "").strip()
    if not name:
        probs.append("name is empty")
    elif name in set(taken or ()):
        probs.append("another quantity is already called '%s'" % name)
    if not str(q.get("key") or "").strip():
        probs.append("key is empty (use quantity_key)")
    probs.extend(validate_expr(q.get("expr")))
    tex = str(q.get("latex") or "").strip()
    if tex:
        probs.extend(mathtext_problems(tex))
    return probs


def evaluate_quantity(q, columns):
    """Evaluate a quantity dict over a column dict; returns a float ndarray."""
    return evaluate((q or {}).get("expr"), columns)


def is_builtin(q):
    """True for the shipped read-only quantities (the GUI shows but never
    edits them)."""
    return bool((q or {}).get("builtin"))


def _builtin(name, expr, unit=""):
    q = make_quantity(name, expr, unit)
    q["builtin"] = True
    return q


# Absorbance is the pipeline's own definition, spelled out in formula form so
# the editor can show users exactly what they are starting from; it must stay
# numerically identical to engine.process_group (a test proves it).
#
# The two thickness-normalised forms are builtins for the same reason: they
# are the standard way to turn a path-length-dependent absorbance into a
# material property, and writing the um -> cm conversion by hand is exactly
# where a factor of 10^4 goes missing. t is in um, so t_cm = t * 1e-4 and
# alpha = ln(10) * A / t_cm comes out in cm^-1; A/t stays in um^-1.
BUILTINS = (
    _builtin("Absorbance", "-log10((S - D) / (B - D))"),
    _builtin("Transmittance", "(S - D) / (B - D)"),
    _builtin("Absorption coefficient", "log(10) * A / (t * 1e-4)", "cm^-1"),
    _builtin("A/t", "A / t", "um^-1"),
)


def default_quantities():
    """Fresh copies of the builtins (the module constant stays untouched)."""
    return [dict(q) for q in BUILTINS]


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
def write_quantity_csv(path, wl, values, quantity, meta=None):
    """Write one custom quantity to its own two-column CSV; returns path.

    Columns are Wavelength_nm and the quantity's key, NaN as an empty cell,
    UTF-8, no line-ending translation -- the same conventions as engine's
    write_absorbance_csv, so both kinds of export open identically. Custom
    quantities always go to their OWN file: the absorbance schema is frozen.

    meta (optional) is written first as '# key: value' comment lines -- the
    formula, unit, trace label, whatever the caller wants the file to carry.
    Phase F2 owns the filename and the provenance sidecar.
    """
    wl = np.asarray(wl, float)
    vals = np.asarray(values, float)
    if wl.shape != vals.shape:
        raise FormulaError("wavelength and value columns differ in length "
                           "(%d vs %d)" % (wl.size, vals.size))
    key = str((quantity or {}).get("key") or "").strip() or "value"
    with open(path, "w", newline="", encoding="utf-8") as f:
        # csv.writer ends rows with \r\n; comments match so the file has one
        # line ending throughout
        for k, v in (meta or {}).items():
            f.write("# %s: %s\r\n" % (k, v))
        w = csv.writer(f)
        w.writerow(["Wavelength_nm", key])
        for row in zip(wl, vals):
            w.writerow(["" if (isinstance(v, float) and np.isnan(v)) else v
                        for v in row])
    return path
