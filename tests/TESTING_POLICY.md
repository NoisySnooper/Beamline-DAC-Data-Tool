# SPARTA test-suite policy

Adopted in v1.4.9 (Phase T), after the suite reached 492 tests / 11 min 41 s.
The slim pass cut it to ~305 tests / ~3 min without dropping a single frozen
contract. **Every later phase follows these rules.** A change that breaks one
should change this file first, with a reason.

Measured at the end of R14: **426 tests, 4 min 35 s** (a second run, 4 min
47 s). R14 itself added 8 tests and retired 1, so under 3 s of that is the
round's; the rest is drift since the Phase T baseline and is over the
budget in section 8. Nhan's call whether the next round pays for a profile
pass or the budget moves.

The whole policy comes from one measurement: the old suite built **eight**
`app.App` instances on one shared Tk root, and every relayout, theme switch
and `update()` then paid for all eight trees. One theme switch costs ~1.9 s
with one App and ~17 s with eight. The top-40 slowest tests were essentially
the entire 701 s run.

---

## 1. One App, one root, one session

`tests/conftest.py` owns the only Tk root and the only `app.App`.

```python
from conftest import gui, shared_app

USES_APP = True                 # arms the shared reset fixture
pytestmark = gui                # skips cleanly on a headless box

@pytest.fixture(scope="module")
def a():
    return shared_app()
```

* **Never call `app.App(...)` in a test module.** The App is built lazily on
  first use, because the FIRST App on the withdrawn root is what gives that
  root its geometry.
* `USES_APP = True` at module level is what turns on `_shared_app_reset`, the
  autouse fixture that restores the shipped defaults after each test. Pure
  modules (engine, formulas, defringe, fringe core / parity) leave it off and
  never pay for Tk.
* A test that genuinely needs a SECOND launch — proving what a fresh start
  reads back from settings — takes the `fresh_app` fixture, which destroys the
  extra widget tree afterwards. There is exactly one such test today
  (`test_rescan_export.py::test_rescan_settings_roundtrip`). Leaving a second
  tree standing taxes every later relayout in the session.

## 2. State is reset centrally, not per module

`conftest.reset_app()` restores every preset-registry variable to
`app._defaults`, empties results / trace vars / dvars / caches, puts the
shipped formulas back, drops committed naming profiles, collapses extra
session tabs and destroys stray Toplevels. It is cheap by construction: it
assigns variables, never rebuilds a widget tree, and a variable already at its
default is not re-set (writing `theme_mode` alone costs ~1.9 s).

If your feature adds global state, extend `reset_app` — do not add a private
`_clean_state` fixture to your module.

## 3. Timers are cancelled, not waited out

`conftest.quiesce()` cancels the after-jobs an App queues for itself
(`_redraw_after`, the 450 ms `_snap_after` undo snapshot, the rescan poll). It
runs at both ends of every reset. Without it the next `update()` — in any test,
including a pure one — silently pays for the previous test's full replot.

Do not `sleep()` to wait a debounce out unless the debounce IS the thing under
test (`test_formula_ui._settle` is the one legitimate case, 0.3 s).

## 4. The GUI is never visible, and settings are never the user's

Non-negotiable, unchanged from earlier rounds:

* `conftest` redirects `app.SETTINGS_PATH` into a tempdir at import, before any
  test module loads. The live `.quicklook_settings.json` must be
  byte-identical after a run.
* Every Toplevel opened by a test goes through `conftest.offscreen(a)`, which
  parks it at `+3200+100` and monkeypatches `App._center_on_root`. Both kinds
  are covered: the ones the app centres and the ones that size themselves.
* Pixel-shaped assertions use `conftest.realized(size)`, which gives the root
  real geometry at the same off-screen position and puts it back afterwards.
* `conftest.close_toplevels()` runs in the reset, so a leaked dialog cannot
  survive into the next test.

## 5. One file per feature area

| file | area |
| --- | --- |
| `test_parser.py` | `engine.parse_segment_filename` grammar |
| `test_profiles.py` | naming profiles, guesser, overrides, segment numbering |
| `test_engine_run.py` | `engine.run` end to end, CSV / provenance schema |
| `test_formulas.py` | pure `formulas.py`: safety, evaluator, mathtext, model |
| `test_formula_ui.py` | the Formulas panel + editor wiring |
| `test_defringe.py` | the `defringe.py` shim's public contract |
| `test_fringe_core.py` | the vendored fringe core (Phase A) |
| `test_fringe_parity.py` | the v1.4.8 parity oracle vs `defringe_dac.py` |
| `test_legend.py` | `_ordered_legend`, branch tags |
| `test_variable.py` | the generic experiment variable |
| `test_sessions.py` | multi-tab session isolation |
| `test_rescan_export.py` | C/D-tagged CSV export, the auto-rescan poll |
| `test_qol.py` | layout, theming, icons, dialogs, settings-backed defaults |
| `test_v149.py` | decompression styling, Thickness mode, `t` builtins |
| `test_bugfixes.py` | the v1.4.8 bug-hunt regressions (F1-F8, C1-C3) |

New coverage joins an existing file. A new file needs a new feature area.

A FEEDBACK ROUND is a feature area of its own, and each one keeps a file:
`test_r4.py`, `test_r5.py`, `test_r6a.py`, `test_r6b_fringe.py`,
`test_r7_fidelity.py`, `test_w1b.py`, `test_w1c.py`, `test_r14.py`. A round
file holds ONE test per ruling, so the file reads as the round's contract
and a later round can retire a ruling by name.

| file | round |
| --- | --- |
| `test_r14.py` | the Settings dropdown, the Detection card, the Defringe switch, the four 3D switches, Graphics 'rich' -> 'best', the ridge zorder, the pop-out's full screen, and the tour's coverage of all of it |

## 6. Group asserts; a battery is a loop, not a parametrize

One test per RULE, not one per input. Ten spellings of a bad unit, six bogus
HDROP handles, twenty-eight typeset expressions: these are `for` loops inside
one test, each assertion carrying the input in its message so a failure still
names itself. `pytest.mark.parametrize` earns its keep only where the cases are
independently interesting — today that is exactly one battery, the formula
evaluator's **safety** list in `test_formulas.py`, which stays one-case-per-test
on purpose.

Merge aggressively where the SETUP is the expensive part:

* everything that must survive a **theme switch** is asserted inside a single
  walk over the themes (`test_qol.py`);
* everything **pixel-shaped** shares one `realized()` block;
* everything a **loaded series** proves is proved by one load
  (`test_v149.py`, `test_sessions.py`);
* a dialog that several assertions need is opened once.

## 7. What may never be thinned

Reduction targets redundancy, never safety. These stay complete:

* the formula evaluator **safety battery** (whitelist / injection) and the
  "formulas.py contains no eval/exec" source check;
* engine **parser edge cases** and every **CSV / provenance schema** assertion
  (field names, counts, sidecar contents, byte identity with engine's writer);
* **defringe** behaviour and `test_fringe_parity.py`, the v1.4.8 oracle — it
  runs in ~14 s and must not be weakened;
* **theme self-heal / visibility** checks;
* **settings round-trips** (what reaches the file, and what a fresh launch
  reads back);
* the `python app.py --selftest` honesty gate.

## 8. Runtime budget

Per file, on this machine:

| file | budget |
| --- | --- |
| any pure module file | < 1 s |
| `test_fringe_core.py` | ~15 s |
| `test_fringe_parity.py` | ~15 s (subprocess oracle) |
| any GUI file | ≤ 45 s |
| **whole suite** | **≤ 4 min** |

If a GUI file goes over budget, the fix is fewer expensive OPERATIONS (App
builds, theme switches, session switches, `realized()` blocks, `_redraw_now`
calls, series loads) — not fewer assertions.

Profile with `python -m pytest tests/ -q --durations=20` before and after any
change that adds GUI tests.
