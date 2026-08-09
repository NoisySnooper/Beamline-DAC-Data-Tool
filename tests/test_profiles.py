"""Naming-profile engine tests (v1.5 flexible ingestion).

Pure engine tests, no GUI. Lock the guarantees that (1) the builtin
grammar is byte-identical through the profile path, (2) custom profiles
parse reordered/re-separated names, (3) per-file overrides can fix or
resurrect anything, and (4) the segment-numbering controls added in v1.4.7
parse and validate.

Grouped one test per RULE rather than one per name: every case the suite
ever asserted is still asserted here.
"""
import numpy as np

import engine


# ---- builtin passthrough --------------------------------------------------
def test_builtin_passthrough_identical():
    names = [
        "vis_Boba_Alm100_12p5_bg_C.001",
        "vis_D42_fo90_s.003",
        "vis_D42_fo90.002",                # dark
        "vis_D42_fo90_0p5_s_D_2.004",
        "not_a_vis_file.txt",
        "vis_D42.001",                     # too few tokens -> skip
    ]
    for n in names:
        a = engine.parse_segment_filename(n)
        b = engine.parse_with_profile(n, None)
        c = engine.parse_with_profile(n, engine.BUILTIN_PROFILE)
        assert a == b == c, n


# ---- custom grammars --------------------------------------------------------
def _dash_profile():
    p = engine.default_profile("dash")
    p["prefix"] = ""
    p["sep"] = "-"
    p["pressure_decimal"] = "."
    return p


def test_custom_grammar_reordered_separated_and_optional():
    """A dash grammar with a dotted pressure, all fields present; then the
    same grammar with every optional field absent; then a prefix + comma
    decimal, including the wrong-prefix rejection."""
    p = _dash_profile()
    r = engine.parse_with_profile("D42-fo90-15.3GPa-s-C-2.003", p)
    assert not r.get("skip")
    assert r["dac"] == "D42" and r["sample"] == "fo90"
    assert abs(r["pressure_val"] - 15.3) < 1e-9
    assert r["pressure_str"] == "15p3"
    assert r["meas"] == "sample" and r["branch"] == "C"
    assert r["rep"] == 2 and r["seq"] == 3
    assert r["pdefault"] is False

    bare = engine.parse_with_profile("D42-fo90", p)
    assert not bare.get("skip")
    assert bare["pressure_val"] == 0.0 and bare["pdefault"] is True
    assert bare["meas"] == "dark" and bare["rep"] == 1 and bare["seq"] == 1

    c = engine.default_profile("comma")
    c["prefix"] = "run"
    c["pressure_decimal"] = ","
    r2 = engine.parse_with_profile("run_A_B_12,5_bg", c)
    assert not r2.get("skip")
    assert abs(r2["pressure_val"] - 12.5) < 1e-9
    assert r2["meas"] == "background"
    wrong = engine.parse_with_profile("walk_A_B_1p0_bg", c)
    assert wrong.get("skip") and "prefix" in wrong["reason"]


def test_custom_grammar_token_maps_ignore_and_trailing_junk():
    """branch_tokens, role_map, an 'ignore' column, and the trailing-token
    rejection that keeps a mistyped name out of the data."""
    p = _dash_profile()
    p["branch_tokens"] = {"up": "C", "down": "D"}
    assert engine.parse_with_profile("D42-fo90-1.5-s-up", p)["branch"] == "C"
    assert engine.parse_with_profile("D42-fo90-1.5-s-down", p)["branch"] == "D"
    empty = _dash_profile()
    empty["branch_tokens"] = {}              # falls back to the classic c / d
    r = engine.parse_with_profile("D42-fo90-1.5-s-c", empty)
    assert not r.get("skip") and r["branch"] == "C", r

    roles = _dash_profile()
    roles["role_map"] = {"ref": "background", "smp": "sample", "": "dark"}
    assert engine.parse_with_profile("D42-fo90-1.5-ref", roles)["meas"] \
        == "background"
    assert engine.parse_with_profile("D42-fo90-1.5-smp", roles)["meas"] \
        == "sample"
    assert engine.parse_with_profile("D42-fo90-1.5", roles)["meas"] == "dark"

    ign = _dash_profile()
    ign["order"] = ["ignore", "dac", "sample", "pressure", "role"]
    r2 = engine.parse_with_profile("junk-D42-fo90-2.0-s", ign)
    assert not r2.get("skip") and r2["dac"] == "D42"

    junk = engine.parse_with_profile("D42-fo90-1.5-s-whatisthis",
                                     _dash_profile())
    assert junk.get("skip") and "trailing" in junk["reason"]


def test_validate_profile():
    p = _dash_profile()
    assert engine.validate_profile(p) == []
    p["role_map"] = {"x": "nonsense"}
    p["order"] = ["sample", "wat"]
    probs = engine.validate_profile(p)
    assert any("nonsense" in s for s in probs)
    assert any("wat" in s for s in probs)
    assert any("'dac' missing" in s for s in probs)
    assert engine.validate_profile(engine.BUILTIN_PROFILE) == []


# ---- overrides --------------------------------------------------------------
def test_override_patches_resurrects_excludes_and_renumbers():
    rec = engine.parse_segment_filename("vis_D42_fo90_1p0_s.001")
    out = engine.apply_override(rec, {"pressure": "2.5", "meas": "background"})
    assert abs(out["pressure_val"] - 2.5) < 1e-9
    assert out["pressure_str"] == "2p5" and out["meas"] == "background"

    # resurrect a skipped file: role is the minimum needed
    bad = engine.parse_segment_filename("totally_random_name.001")
    assert bad.get("skip")
    res = engine.apply_override(bad, {"meas": "sample", "dac": "D9",
                                      "sample": "gl", "pressure": 3})
    assert not res.get("skip") and res["dac"] == "D9"
    assert res["pressure_str"] in ("3", "3p0")
    assert engine.apply_override(bad, {"pressure": 3}).get("skip")  # no role

    ex = engine.apply_override(rec, {"skip": True})       # explicit exclude
    assert ex.get("skip") and "excluded" in ex["reason"]

    seg = engine.parse_with_profile("D42-fo90.001", _seg_profile())
    fixed = engine.apply_override(seg, {"seq": "5"})
    assert fixed["seq"] == 5 and not fixed.get("skip")


# ---- scan_folder with profile + overrides ----------------------------------
def test_scan_folder_custom_profile(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    for n in ("D42-fo90-1.5-s.001", "D42-fo90-1.5-ref.001",
              "D42-fo90-1.5.001", "mystery.001"):
        (d / n).write_text("x")
    p = _dash_profile()
    p["role_map"] = {"ref": "background", "s": "sample", "": "dark"}
    groups, skipped = engine.scan_folder(str(d), p)
    assert len(groups) == 1
    g = groups[("D42", "fo90", "1p5", None)]
    assert set(g["meas"]) == {"sample", "background", "dark"}
    assert [s["raw"] for s in skipped] == ["mystery.001"]
    # override resurrects the mystery file into the same group
    ov = {"mystery.001": {"meas": "sample", "dac": "D42", "sample": "fo90",
                          "pressure": "1.5", "rep": 2}}
    groups2, skipped2 = engine.scan_folder(str(d), p, ov)
    assert skipped2 == []
    assert 2 in groups2[("D42", "fo90", "1p5", None)]["meas"]["sample"]


# ---- guess_profile (the Name-format dialog's Guess button) -----------------
def test_guess_recovers_the_conventions_it_ships_for():
    """The builtin underscore grammar, a dashed one with unit suffixes, and
    a single-cell folder whose shared dac token must NOT be eaten as a
    prefix."""
    prof, n = engine.guess_profile(
        ["vis_Y04_arch29_12p5_bg.001", "vis_Y04_arch29_12p5_s.001",
         "vis_Y04_arch29_12p5.001", "vis_Y04_arch29_26p0_bg.002",
         "vis_Y04_arch29_26p0_s.002"])
    assert prof["prefix"] == "vis" and prof["sep"] == "_"
    assert prof["order"][:3] == ["dac", "sample", "pressure"]
    assert prof["role_map"].get("bg") == "background"
    assert prof["role_map"].get("s") == "sample"
    assert n == 5

    names = ["IR-Y04-arch29-12.5-bg-2.001", "IR-Y04-arch29-12.5-s-2.001",
             "IR-Y04-arch29-12.5-2.001", "IR-Y04-arch29-26.0GPa-bg.002"]
    prof, n = engine.guess_profile(names)
    assert prof["sep"] == "-" and prof["prefix"] == "ir"
    assert "pressure" in prof["order"] and "role" in prof["order"]
    assert n == len(names)

    single = ["D42_ol1_10p5_bg.001", "D42_ol1_10p5_bg.002",
              "D42_ol1_10p5_s.001", "D42_ol1_10p5_s.002",
              "D42_ol1_12p0_bg.001", "D42_ol1_12p0_s.001"]
    prof, n = engine.guess_profile(single)
    assert prof["prefix"] == "" and n == len(single)
    r = engine.parse_with_profile(single[0], prof)
    assert (r["dac"], r["sample"], r["meas"]) == ("D42", "ol1", "background")

    # and it gives up gracefully rather than inventing a grammar
    _prof, n = engine.guess_profile(["IMG0001", "IMG0002", "notes"])
    assert n == 0


def test_guess_reads_the_segment_scheme():
    letters = ["run_D1_x_10.5_s.a", "run_D1_x_10.5_bg.a",
               "run_D1_x_10.5_s.b", "run_D1_x_10.5_bg.b",
               "run_D1_x_12_s.a", "run_D1_x_12_bg.a"]
    prof, n = engine.guess_profile(letters)
    assert prof["seq_sep"] == "." and prof["seq_scheme"] == "letters"
    assert prof["seq_missing"] == "reject"     # every file was numbered
    assert n == len(letters)
    r = engine.parse_with_profile("run_D1_x_10.5_s.b", prof)
    assert not r.get("skip") and r["seq"] == 2

    partial = ["run_D1_x_10.5_s.001", "run_D1_x_10.5_s.002",
               "run_D1_x_10.5_bg.001", "run_D1_x_10.5_bg.002",
               "run_D1_x_12_s", "run_D1_x_12_bg"]
    prof, n = engine.guess_profile(partial)
    assert prof["seq_sep"] == "." and prof["seq_scheme"] == "digits"
    assert prof["seq_missing"] == 1            # bare names exist -> seg 1
    assert n == len(partial)


# ---- health_flags -----------------------------------------------------------
def test_health_flags():
    clean = {"absorbance": np.linspace(0, 2, 200), "samp_c": np.ones(200),
             "bg_c": np.ones(200), "dark_c": np.zeros(200)}
    assert engine.health_flags(clean) == []

    nan = np.full(50, np.nan)
    flags = engine.health_flags({"absorbance": nan, "samp_c": nan,
                                 "bg_c": np.ones(50), "dark_c": nan})
    assert flags and flags[0][0] == "bad"
    assert "background" in flags[0][1]

    a = np.linspace(0, 2, 200)
    a[:20] = 5.0
    flags = engine.health_flags({"absorbance": a, "samp_c": np.ones(200),
                                 "bg_c": np.ones(200),
                                 "dark_c": np.zeros(200)})
    assert any("saturated" in m for _l, m in flags)


# ---- segment numbering (seq_sep / seq_scheme / seq_missing) -----------------

def _seg_profile(**kw):
    p = engine.default_profile("seg")
    p["prefix"] = ""
    p["sep"] = "-"
    p["pressure_decimal"] = "."
    p.update(kw)
    return p


def test_segment_separator_forms():
    """Zero padding is irrelevant, a multi-character separator splits at its
    RIGHTMOST occurrence (so a dotted pressure survives), and an empty
    separator means 'this convention has no segments'."""
    p = _seg_profile()
    a = engine.parse_with_profile("D42-fo90.1", p)
    b = engine.parse_with_profile("D42-fo90.001", p)
    assert a["seq"] == b["seq"] == 1
    assert engine.parse_with_profile("D42-fo90.012", p)["seq"] == 12

    m = _seg_profile(seq_sep="_seg")
    r = engine.parse_with_profile("D42-fo90_seg003", m)
    assert not r.get("skip") and r["seq"] == 3
    r = engine.parse_with_profile("D42-fo90-2.5_seg7", m)
    assert not r.get("skip") and r["seq"] == 7
    assert abs(r["pressure_val"] - 2.5) < 1e-9

    e = _seg_profile(seq_sep="")
    r = engine.parse_with_profile("D42-fo90", e)
    assert not r.get("skip") and r["seq"] == 1
    r = engine.parse_with_profile("D42-fo90.001", e)
    assert not r.get("skip") and r["seq"] == 1 and r["sample"] == "fo90.001"


def test_segment_scheme_and_missing_policy():
    p = _seg_profile(seq_scheme="letters")
    assert engine.parse_with_profile("D42-fo90.a", p)["seq"] == 1
    assert engine.parse_with_profile("D42-fo90.B", p)["seq"] == 2   # case
    assert engine.parse_with_profile("D42-fo90.aa", p)["seq"] == 27
    # a plain data extension must NOT read as a segment (len cap):
    # '.dat' stays in the token and the file counts as suffix-less
    r = engine.parse_with_profile("D42-fo90.dat", p)
    assert r["seq"] == 1 and r["sample"] == "fo90.dat"

    rej = _seg_profile(seq_missing="reject")
    r = engine.parse_with_profile("D42-fo90", rej)
    assert r.get("skip") and "segment" in r.get("reason", "")
    assert engine.parse_with_profile("D42-fo90.2", rej)["seq"] == 2

    idx = _seg_profile(seq_missing=4)
    assert engine.parse_with_profile("D42-fo90", idx)["seq"] == 4
    assert engine.parse_with_profile("D42-fo90.2", idx)["seq"] == 2


def test_segment_validator():
    assert engine.validate_profile(_seg_profile()) == []
    assert any("scheme" in s for s in
               engine.validate_profile(_seg_profile(seq_scheme="roman")))
    assert any("whole number" in s for s in
               engine.validate_profile(_seg_profile(seq_missing=0)))
    assert any("whole number" in s for s in
               engine.validate_profile(_seg_profile(seq_missing="maybe")))
    assert any("separator" in s for s in
               engine.validate_profile(_seg_profile(seq_sep="",
                                                    seq_missing="reject")))
    assert engine.validate_profile(_seg_profile(seq_missing="reject")) == []


# ---- dac / sample omissible via defaults ------------------------------------

def test_defaulted_dac_and_sample():
    p = _seg_profile()
    p["order"] = ["sample", "pressure", "role", "branch", "rep"]
    p["defaults"] = dict(p["defaults"], dac="D42")
    assert engine.validate_profile(p) == []
    r = engine.parse_with_profile("fo90-12.5-s.001", p)
    assert not r.get("skip")
    assert r["dac"] == "D42" and r["sample"] == "fo90"

    p2 = _seg_profile()
    p2["order"] = ["pressure", "role"]
    p2["defaults"] = dict(p2["defaults"], dac="D42", sample="fo90")
    r = engine.parse_with_profile("12.5-s.002", p2)
    assert not r.get("skip")
    assert (r["dac"], r["sample"], r["seq"]) == ("D42", "fo90", 2)

    # ... and without the default the validator says so
    p3 = _seg_profile()
    p3["order"] = ["sample", "pressure"]
    assert any("dac" in s for s in engine.validate_profile(p3))
    p3["defaults"] = dict(p3["defaults"], dac="D42")
    assert engine.validate_profile(p3) == []


# ---- separator alternatives -------------------------------------------------

def test_separator_alternatives_and_literal_comma():
    p = _seg_profile(sep="_,-")
    r = engine.parse_with_profile("D42-fo90_10.5-bg.001", p)
    assert not r.get("skip")
    assert (r["dac"], r["sample"], r["meas"]) == ("D42", "fo90", "background")
    assert abs(r["pressure_val"] - 10.5) < 1e-9 and r["seq"] == 1
    toks, gaps = engine.split_tokens_gaps("D42-fo90_10.5-bg", "_,-")
    assert toks == ["D42", "fo90", "10.5", "bg"]
    assert gaps == ["-", "_", "-"]
    assert engine.split_tokens("a,b,c", ",") == ["a", "b", "c"]
