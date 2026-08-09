"""
Filename-grammar tests for engine.parse_segment_filename.

These lock the parser behavior added in v1.2.x: optional segment suffix,
0 GPa allowed, missing-pressure-defaults-to-0, branch/rep in either order,
and the rejection paths. Pure string logic, no file I/O.

Grouped one test per grammar rule (not one per file name) -- every case the
suite ever asserted is still asserted, and each name carries the rule it
proves so a failure still names itself.
"""
import engine


def P(name):
    return engine.parse_segment_filename(name)


def test_full_name_and_optional_segment():
    """The canonical name, and the three ways the segment suffix may be
    absent: no suffix at all, a bare dark, and a .csv twin."""
    r = P("vis_DAC1_olivine_1p39_s.001")
    assert not r.get("skip")
    assert r["dac"] == "DAC1" and r["sample"] == "olivine"
    assert r["pressure_val"] == 1.39 and r["meas"] == "sample"
    assert r["seq"] == 1 and r["pdefault"] is False

    single = P("vis_DAC1_olivine_1p39_s")            # single stitch
    assert not single.get("skip") and single["seq"] == 1

    dark = P("vis_DAC1_olivine_1p39")                # segment optional on dark
    assert not dark.get("skip") and dark["meas"] == "dark" and dark["seq"] == 1

    twin = P("vis_DAC1_olivine_1p39_s.001.csv")      # .csv twin stripped
    assert not twin.get("skip") and twin["seq"] == 1
    assert twin["meas"] == "sample"


def test_pressure_zero_and_missing():
    """0 GPa is a real measurement; a missing pressure field defaults to 0
    but says so with pdefault."""
    zero = P("vis_DAC1_olivine_0_bg")
    assert not zero.get("skip")
    assert zero["pressure_val"] == 0.0 and zero["meas"] == "background"
    assert zero["pdefault"] is False

    gone = P("vis_DAC1_olivine_bg")
    assert not gone.get("skip")
    assert gone["pressure_val"] == 0.0 and gone["pdefault"] is True
    assert gone["meas"] == "background"

    bare = P("vis_DAC1_olivine")
    assert not bare.get("skip")
    assert bare["pressure_val"] == 0.0 and bare["pdefault"] is True


def test_branch_and_rep_either_order():
    for r in (P("vis_DAC1_olivine_1p0_s_C_2"), P("vis_DAC1_olivine_1p0_s_2_C")):
        assert not r.get("skip")
        assert r["branch"] == "C" and r["rep"] == 2


def test_rejection_paths_each_name_their_reason():
    """Every way a name is refused, with the fragment the log line prints."""
    for name, fragment in (("vis_DAC1_olivine_-1", "< 0"),
                           ("vis_DAC1_olivine_5o2_s", "not numeric"),
                           ("vis_DAC1_olivine_1p39.abc", "segment"),
                           ("vis_DAC1_olivine_1p39_bg.001.002", "extension")):
        r = P(name)
        assert r.get("skip"), name
        assert fragment in r["reason"], (name, r["reason"])
    assert P("foo_bar_baz.001").get("skip")          # not a vis_ file at all
