"""Formula-editor tests (Phase F1): whitelist evaluator, mathtext renderer,
quantity model, CSV writer.

Pure module tests, no Tk. The safety battery is the point of the first
section and is deliberately left one-case-per-test: each of those strings
must be REJECTED at validation, which in this design means it is never
evaluated at all (the module contains no eval/exec -- that is asserted too).
The absorbance builtin is proved numerically equal to engine's own
absorbance on random channels.

Everything BELOW the safety section is grouped: a battery of near-identical
numeric or typesetting cases is one test that loops, not thirty tests.
"""
import json

import numpy as np
import pytest

import formulas as F


# ---- safety battery -------------------------------------------------------
# (expression, a fragment the rejection message must contain)
BATTERY = [
    ("__import__('os')",        "unknown function"),
    ("().__class__",            "attributes are not allowed"),
    ("S[0]",                    "indexing"),
    ("S.mean()",                "method calls"),
    ("lambda: 1",               "lambda"),
    ("1 if S else 2",           "conditional"),
    ("S > B",                   "comparisons"),
    ("S and B",                 "'and' / 'or'"),
    ("not S",                   "'not'"),
    ("~S",                      "'~'"),
    ("S % B",                   "operator '%'"),
    ("S // B",                  "operator '//'"),
    ("S & B",                   "operator '&'"),
    ("S @ B",                   "operator '@'"),
    ("[x for x in S]",          "comprehensions"),
    ("(S, B)",                  "tuples"),
    ("{1: 2}",                  "dicts"),
    ("{1, 2}",                  "sets"),
    ('f"{S}"',                  "f-strings"),
    ("(S := 1)",                "':='"),
    ("'os'",                    "text is not allowed"),
    ("True",                    "numbers only"),
    ("None",                    "numbers only"),
    ("3j",                      "complex"),
    ("1e999",                   "not a finite number"),
    ("foo(S)",                  "unknown function 'foo'"),
    ("print(S)",                "unknown function 'print'"),
    ("open('x')",               "unknown function 'open'"),
    ("S(B)",                    "'S' is a column, not a function"),
    ("log10",                   "write log10(...)"),
    ("x",                       "unknown name 'x'"),
    ("log10(S, B)",             "takes 1 argument, got 2"),
    ("minimum(S)",              "takes 2 arguments, got 1"),
    ("log10(x=S)",              "keyword arguments"),
    ("S ** 9",                  "exponent 9 is too large"),
    ("S ** -9",                 "exponent -9 is too large"),
    ("2 ** 3 ** 999",           "exponent 999 is too large"),
    ("S +",                     "syntax error"),
    ("",                        "expression is empty"),
    ("    ",                    "expression is empty"),
]


@pytest.mark.parametrize("expr,fragment", BATTERY)
def test_battery_rejected(expr, fragment):
    """Every unsafe / unsupported form fails validation with a message that
    says what is wrong, and never reaches the evaluator."""
    probs = F.validate_expr(expr)
    assert probs, "%r was accepted" % expr
    assert any(fragment in p for p in probs), \
        "%r -> %r (wanted %r)" % (expr, probs, fragment)
    with pytest.raises(F.FormulaError):
        F.parse_expr(expr)
    with pytest.raises(F.FormulaError):
        F.evaluate(expr, {"S": np.ones(3), "B": np.ones(3), "D": np.zeros(3)})
    with pytest.raises(F.FormulaError):
        F.expr_to_mathtext(expr)


BANNED_BUILTINS = {"eval", "exec", "compile", "__import__", "getattr",
                   "setattr", "delattr", "globals", "locals", "vars",
                   "input", "__builtins__"}


def test_module_never_calls_eval_or_exec():
    """The whole safety argument rests on this: expressions are walked, not
    executed. A future edit that reaches for eval() must fail here. Checked
    on the parsed source, so prose in a docstring cannot trip it and a real
    call cannot hide from it."""
    import ast
    with open(F.__file__, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in BANNED_BUILTINS, "formulas.py uses %s" % node.id
        if isinstance(node, ast.Attribute):
            assert node.attr not in BANNED_BUILTINS, \
                "formulas.py uses .%s" % node.attr


def test_rejected_expression_has_no_side_effect():
    """A column value whose attributes would be touched by an attribute
    expression is never even looked at."""
    class Tripwire(object):
        def __getattr__(self, name):
            raise AssertionError("attribute %r was accessed" % name)

    for expr in ("S.mean()", "S.size", "S[0]"):
        with pytest.raises(F.FormulaError):
            F.evaluate(expr, {"S": Tripwire()})


# ---- evaluator correctness ------------------------------------------------
def _cols(n=32, seed=3):
    rng = np.random.default_rng(seed)
    wl = np.linspace(400.0, 1000.0, n)
    d = rng.uniform(50.0, 150.0, n)
    b = d + rng.uniform(100.0, 5000.0, n)
    s = d + rng.uniform(100.0, 5000.0, n)
    return {"S": s, "B": b, "D": d, "wl": wl, "t": np.full(n, 25.0),
            "A": -np.log10((s - d) / (b - d))}


CASES = [
    ("S - D",                     lambda c: c["S"] - c["D"]),
    ("(S - D) / (B - D)",         lambda c: (c["S"] - c["D"]) / (c["B"] - c["D"])),
    ("-log10((S - D) / (B - D))",
     lambda c: -np.log10((c["S"] - c["D"]) / (c["B"] - c["D"]))),
    ("10 ** (-A)",                lambda c: 10.0 ** (-c["A"])),
    ("sqrt(abs(S - B))",          lambda c: np.sqrt(np.abs(c["S"] - c["B"]))),
    ("minimum(S, B) / maximum(S, B)",
     lambda c: np.minimum(c["S"], c["B"]) / np.maximum(c["S"], c["B"])),
    ("exp(-A) * 100",             lambda c: np.exp(-c["A"]) * 100.0),
    ("log(S) / log(10)",          lambda c: np.log(c["S"]) / np.log(10.0)),
    ("wl * A ** 2",               lambda c: c["wl"] * c["A"] ** 2),
    ("1e-3 * (S + B + D)",        lambda c: 1e-3 * (c["S"] + c["B"] + c["D"])),
    ("-(S - B) - -D",             lambda c: -(c["S"] - c["B"]) - -c["D"]),
]


def test_evaluate_matches_numpy():
    """Every accepted form gives bit-comparable answers to the numpy the
    user would have written by hand."""
    c = _cols()
    for expr, ref in CASES:
        got = F.evaluate(expr, c)
        want = np.asarray(ref(c), float)
        want = np.where(np.isfinite(want), want, np.nan)
        assert got.shape == want.shape, expr
        assert np.allclose(got, want, rtol=1e-12, atol=0.0, equal_nan=True), \
            expr


def test_non_finite_becomes_nan_without_warning():
    """Divide-by-zero, log of zero and log of a negative are ordinary in this
    data; they must come back as NaN, silently."""
    import warnings
    c = {"S": np.array([1.0, 1.0, 1.0]),
         "B": np.array([1.0, 0.0, 1.0]),
         "D": np.array([0.0, 0.0, 2.0])}
    with warnings.catch_warnings():
        warnings.simplefilter("error")           # any RuntimeWarning fails
        t = F.evaluate("(S - D) / (B - D)", c)   # 1/1, 1/0 -> inf, -1/-1
        a = F.evaluate("-log10((S - D) / (B - D))", c)
        lg = F.evaluate("log10(S - B)", c)       # log10(0), log10(1), log10(0)
    assert t[0] == 1.0 and np.isnan(t[1]) and t[2] == 1.0
    assert a[0] == 0.0 and np.isnan(a[1]) and a[2] == 0.0
    assert np.isnan(lg[0]) and lg[1] == 0.0 and np.isnan(lg[2])


def test_scalar_integer_and_missing_column_inputs():
    """Constants, scalar columns, integer columns, and the two ways a data
    dict can be wrong."""
    assert float(F.evaluate("2 * 3 + 1", {})) == 7.0
    assert float(F.evaluate("S / B", {"S": 4.0, "B": 2.0})) == 2.0
    assert np.allclose(F.evaluate("S / B", {"S": np.array([6, 8]),
                                            "B": np.array([2, 4])}),
                       [3.0, 2.0])
    with pytest.raises(F.FormulaError) as e:
        F.evaluate("S - D", {"S": np.ones(4)})
    assert "no data for column 'D'" in str(e.value)
    with pytest.raises(F.FormulaError) as e:
        F.evaluate("S - D", {"S": np.ones(4), "D": np.ones(5)})
    assert "lengths differ" in str(e.value)


def test_pow_limit_boundary():
    assert F.validate_expr("S ** 8") == []
    assert F.validate_expr("S ** -8") == []
    assert F.validate_expr("S ** 9")
    # a NON-constant exponent is allowed: 10**(-A) is a real quantity
    assert F.validate_expr("10 ** (-A)") == []


# ---- aliases and inputs ---------------------------------------------------
def test_alias_resolution_in_expression_and_in_data():
    c = _cols()
    long_names = {"sample": c["S"], "background": c["B"], "dark": c["D"],
                  "wavelength": c["wl"], "absorbance": c["A"]}
    engine_keys = {"samp_c": c["S"], "bg_c": c["B"], "dark_c": c["D"],
                   "wl": c["wl"], "absorbance": c["A"],
                   "label": "not a column", "pressure_val": 1.0}
    ref = F.evaluate("(S - D) / (B - D)", c)
    for data in (long_names, engine_keys):
        assert np.allclose(F.evaluate("(S - D) / (B - D)", data), ref,
                           equal_nan=True)
    # aliases work in the expression text too, and mix with short names
    assert np.allclose(
        F.evaluate("(sample - Dark) / (BACKGROUND - D)", c), ref, equal_nan=True)

    assert F.canonical("Sample") == "S" and F.canonical("bg_c") == "B"
    assert F.canonical("nm") == "wl" and F.canonical("absorbance") == "A"
    assert F.canonical("nope") is None
    assert F.inputs_of("-log10((S - D) / (B - D))") == ["B", "D", "S"]
    assert F.inputs_of("wl * 2") == ["wl"]
    assert F.inputs_of("sqrt(absorbance)") == ["A"]
    assert F.inputs_of("2 + 2") == []


def test_new_column_needs_no_evaluator_change():
    """Phase F2 adds defringed / smoothed columns with add_column(); the
    evaluator and the renderer must pick them up as they are."""
    F.add_column("Sf", "Sample counts, defringed", "S_{f}", ("sample_defr",))
    try:
        assert F.canonical("sample_defr") == "Sf"
        got = F.evaluate("Sf / B", {"sample_defr": np.array([2.0, 4.0]),
                                    "B": np.array([1.0, 2.0])})
        assert np.allclose(got, [2.0, 2.0])
        assert F.expr_to_mathtext("Sf / B") == r"$\frac{S_{f}}{B}$"
    finally:
        F.COLUMNS.pop("Sf", None)
    assert F.canonical("Sf") is None


# ---- mathtext -------------------------------------------------------------
TEX_BATTERY = [
    ("-log10((S - D) / (B - D))", r"$-\log_{10}\left(\frac{S - D}{B - D}\right)$"),
    ("(S - D) / (B - D)",         r"$\frac{S - D}{B - D}$"),
    ("S / B",                     r"$\frac{S}{B}$"),
    ("S * B",                     r"$S\,B$"),
    ("2 * S",                     r"$2 \cdot S$"),
    ("S ** 2",                    r"$S^{2}$"),
    ("-S",                        r"$-S$"),
    ("-(S + B)",                  r"$-\left(S + B\right)$"),
    ("S - (B - D)",               r"$S - \left(B - D\right)$"),
    ("S + (B + D)",               r"$S + B + D$"),
    ("sqrt(S)",                   r"$\sqrt{S}$"),
    ("abs(S - B)",                r"$\left|S - B\right|$"),
    ("minimum(S, B)",             r"$\min\left(S,\,B\right)$"),
    ("maximum(S, B)",             r"$\max\left(S,\,B\right)$"),
    ("exp(-A)",                   r"$e^{-A}$"),
    ("exp(S) ** 2",               r"$\left(e^{S}\right)^{2}$"),
    ("10 ** (-A)",                r"$10^{-A}$"),
    ("wl * A",                    r"$\lambda\,A$"),
    ("log(S) / log(10)",          r"$\frac{\ln\left(S\right)}{\ln\left(10\right)}$"),
    ("(S / B) / (D / B)",         r"$\frac{\frac{S}{B}}{\frac{D}{B}}$"),
    ("1e-5 * S",                  r"$1{\times}10^{-5} \cdot S$"),
    ("-S ** 2",                   r"$-S^{2}$"),
    ("(wl / 1000) ** 3",          r"$\left(\frac{\lambda}{1000}\right)^{3}$"),
    ("sqrt(S) ** 2",              r"$\left(\sqrt{S}\right)^{2}$"),
    ("1e-5 ** 2",                 r"$\left(1{\times}10^{-5}\right)^{2}$"),
    ("S * (B / D)",               r"$S\,\frac{B}{D}$"),
    ("S * -B",                    r"$S\,\left(-B\right)$"),
]


@pytest.fixture(scope="module")
def mathtext_parse():
    """matplotlib's own mathtext parser -- no figure, no backend switch (the
    GUI tests in this suite share the process and their backend)."""
    pytest.importorskip("matplotlib")
    from matplotlib.mathtext import MathTextParser
    return MathTextParser("path").parse


def test_mathtext_strings_and_they_all_render(mathtext_parse):
    """Every supported form typesets to the expected LaTeX, and matplotlib
    can actually draw what came out."""
    for expr, tex in TEX_BATTERY:
        assert F.expr_to_mathtext(expr) == tex, expr
        mathtext_parse(tex)          # raises if matplotlib can't draw it


def test_builtin_latex_renders_and_bad_latex_is_caught(mathtext_parse):
    for q in F.BUILTINS:
        assert q["latex"].startswith("$") and q["latex"].endswith("$")
        mathtext_parse(q["latex"])
        assert F.mathtext_problems(q["latex"]) == []
    assert F.mathtext_problems("") == ["LaTeX is empty"]
    assert F.mathtext_problems("$x") == ["unbalanced '$' in the LaTeX"]
    bad = F.mathtext_problems(r"$\frac{a}$")
    assert bad and "does not render" in bad[0]
    assert F.mathtext_problems(r"$\alpha_{1}$") == []


# ---- quantity model -------------------------------------------------------
def test_make_quantity_autofills_and_honours_an_override():
    q = F.make_quantity("Optical density", "-log10(S / B)", unit="OD")
    assert q["key"] == "Optical_density" and q["unit"] == "OD"
    assert q["latex"] == r"$-\log_{10}\left(\frac{S}{B}\right)$"
    assert q["builtin"] is False
    assert F.validate_quantity(q) == []

    over = F.make_quantity("Ratio", "S / B", latex=r"$R_{\mathrm{obs}}$")
    assert over["latex"] == r"$R_{\mathrm{obs}}$"   # not the auto \frac
    assert F.validate_quantity(over) == []
    bad = F.make_quantity("Ratio", "S / B", latex=r"$\frac{a}$")
    assert any("does not render" in p for p in F.validate_quantity(bad))
    # clearing the override falls back to the auto form
    assert F.make_quantity("Ratio", "S / B", latex="  ")["latex"] == \
        r"$\frac{S}{B}$"


def test_invalid_quantity_stores_but_reports():
    q = F.make_quantity("Broken", "S ** 99")
    assert q["latex"] == ""
    assert any("exponent" in p for p in F.validate_quantity(q))
    assert "name is empty" in F.validate_quantity(F.make_quantity("", "S / B"))
    assert any("already called" in p for p in F.validate_quantity(
        F.make_quantity("Ratio", "S / B"), taken=["Ratio", "Other"]))


def test_quantity_json_roundtrip_and_key_slugs():
    qs = F.default_quantities() + [
        F.make_quantity("Transmittance %", "100 * (S - D) / (B - D)", unit="%"),
        F.make_quantity(u"Δ absorbance", "A - 1", latex=r"$\Delta A$")]
    back = json.loads(json.dumps(qs))
    assert back == qs
    for q in back:
        assert set(q) == {"name", "expr", "unit", "latex", "key", "builtin"}
        assert all(isinstance(q[k], str)
                   for k in ("name", "expr", "unit", "latex", "key"))
        assert isinstance(q["builtin"], bool)
        assert F.validate_quantity(q) == []

    assert F.quantity_key("Optical Density") == "Optical_Density"
    assert F.quantity_key("A/B ratio (raw)") == "A_B_ratio_raw"
    assert F.quantity_key("  spaced  out  ") == "spaced_out"
    assert F.quantity_key(u"café résumé") == "cafe_resume"
    assert F.quantity_key(u"Δα") == "quantity"   # nothing ASCII left
    assert F.quantity_key("***") == "quantity"
    assert F.quantity_key("2nd derivative") == "q2nd_derivative"
    # collisions get distinct keys, so two quantities never share a CSV column
    taken = []
    for name in ("Optical Density", "Optical-Density", "optical density!!",
                 u"Δα", u"βγ"):
        k = F.quantity_key(name, taken)
        assert k not in taken
        taken.append(k)
    assert taken == ["Optical_Density", "Optical_Density_2",
                     "optical_density", "quantity", "quantity_2"]
    assert F.make_quantity("Ratio", "S / B", taken=["Ratio"])["key"] == "Ratio_2"


def test_builtins_are_flagged_evaluate_and_copies_are_independent():
    """The shipped set is Absorbance / Transmittance plus the two v1.4.9
    thickness quantities; every one evaluates over the standard columns."""
    assert [q["name"] for q in F.BUILTINS] == [
        "Absorbance", "Transmittance", "Absorption coefficient", "A/t"]
    assert all(F.is_builtin(q) for q in F.BUILTINS)
    assert not F.is_builtin(F.make_quantity("x", "S"))
    fresh = F.default_quantities()
    fresh[0]["name"] = "clobbered"
    assert F.BUILTINS[0]["name"] == "Absorbance"

    c = _cols()                       # carries t, so alpha and A/t resolve
    for q in F.BUILTINS:
        got = F.evaluate_quantity(q, c)
        assert got.shape == c["S"].shape and np.isfinite(got).all(), q["name"]


# ---- the absorbance builtin IS the pipeline's absorbance -------------------
def test_absorbance_builtin_equals_engine(tmp_path):
    """engine.process_group and the Absorbance builtin must agree point for
    point, NaNs included, on random channels (including some where B - D or
    S - D goes negative, where absorbance is undefined)."""
    import engine

    rng = np.random.default_rng(11)
    n = 96
    wl = np.linspace(400.0, 1000.0, n)
    d = rng.uniform(50.0, 150.0, n)
    b = d + rng.uniform(-200.0, 5000.0, n)     # some B - D <= 0 -> NaN
    s = d + rng.uniform(-200.0, 5000.0, n)     # some S - D <= 0 -> NaN

    def seg(name, y):
        p = tmp_path / name
        p.write_text("".join("%.17g,%.17g\n" % (w, c) for w, c in zip(wl, y)))
        return str(p)

    meas = {"sample":     {1: {1: seg("s.001", s)}},
            "background": {1: {1: seg("b.001", b)}},
            "dark":       {1: {1: seg("d.001", d)}}}
    res = engine.process_group(("D1", "smp", "0", None),
                               {"meas": meas, "pressure_val": 0.0})
    assert len(res) == 1
    r = res[0]
    mine = F.evaluate_quantity(F.BUILTINS[0], r)     # feeds the result dict in
    theirs = np.asarray(r["absorbance"], float)
    assert np.isnan(theirs).any() and np.isfinite(theirs).sum() > n // 2
    assert np.array_equal(np.isnan(mine), np.isnan(theirs))
    assert np.allclose(mine, theirs, rtol=1e-12, atol=1e-15, equal_nan=True)

    # and transmittance is the same quotient, un-logged
    t = F.evaluate_quantity(F.BUILTINS[1], r)
    fin = np.isfinite(theirs)
    assert np.allclose(-np.log10(t[fin]), theirs[fin], rtol=1e-12)


# ---- CSV writer -----------------------------------------------------------
def test_write_quantity_csv(tmp_path):
    q = F.make_quantity("Transmittance pct", "100 * (S - D) / (B - D)", unit="%")
    assert q["key"] == "Transmittance_pct"
    wl = np.array([400.0, 500.0, 600.0])
    vals = np.array([12.5, np.nan, 0.0])
    path = str(tmp_path / "out.csv")
    got = F.write_quantity_csv(path, wl, vals, q)
    assert got == path
    with open(path, "r", newline="", encoding="utf-8") as f:
        raw = f.read()
    assert raw.startswith("Wavelength_nm,Transmittance_pct\r\n")  # engine dialect
    rows = [ln.split(",") for ln in raw.strip().split("\r\n")]
    assert rows[0] == ["Wavelength_nm", "Transmittance_pct"]
    assert rows[1] == ["400.0", "12.5"]
    assert rows[2] == ["500.0", ""]                             # NaN -> blank
    assert rows[3] == ["600.0", "0.0"]

    # meta becomes comment lines ahead of the header, in the same dialect
    path2 = str(tmp_path / "meta.csv")
    F.write_quantity_csv(path2, wl, vals, q,
                         meta={"expr": q["expr"], "unit": q["unit"],
                               "trace": "D42 fo90 1.39 GPa"})
    with open(path2, "r", newline="", encoding="utf-8") as f:
        head = f.read().split("\r\n")
    assert head[0] == "# expr: 100 * (S - D) / (B - D)"
    assert head[1] == "# unit: %"
    assert head[2] == "# trace: D42 fo90 1.39 GPa"
    assert head[3] == "Wavelength_nm,Transmittance_pct"

    with pytest.raises(F.FormulaError):
        F.write_quantity_csv(str(tmp_path / "x.csv"), np.ones(3), np.ones(4),
                             F.BUILTINS[0])
