"""Appearance preferences data for SPARTA: the App-font catalogue and the
retired-theme map.

Pure data and pure functions. Nothing here touches Tk, so the tables can
be read by tests and by the guide tooling without a display.

Three jobs:

1. APP FONT. The program draws its own chrome in one family. The user
   picks that family from a short curated list. The tool hides a family
   that the machine does not have.
2. RETIRED THEMES. The two Dyslexic themes are gone. A settings file that
   names one maps to a live theme plus the OpenDyslexic font.
3. CHROME HINTS. 'Find a setting' searches the right-panel sections. The
   hints below say where a top-bar control lives.
"""

# ---------------------------------------------------------------------------
# 1. App font
# ---------------------------------------------------------------------------
# The brand face. DESIGN_RULES rule 44: Jost is the typeface, and
# _resolve_ui_font falls back through Century Gothic and Bahnschrift to
# Segoe UI when Jost is missing.
BRAND_FONT = "Jost"

# The curated list, in the order the picker shows it. Each entry is
# (setting value, family the tool asks Tk for, fallback family or None).
# Jost leads because it is the default. OpenDyslexic follows because it
# is the accessibility choice the two retired themes carried. The rest
# are faces that ship with Windows.
APP_FONTS = (
    ("Jost", BRAND_FONT, None),
    ("OpenDyslexic", "OpenDyslexic", "Comic Sans MS"),
    ("Comic Sans MS", "Comic Sans MS", None),
    ("Arial", "Arial", None),
    ("Segoe UI", "Segoe UI", None),
    ("Georgia", "Georgia", None),
    ("Verdana", "Verdana", None),
    ("Trebuchet MS", "Trebuchet MS", None),
)
DEFAULT_APP_FONT = "Jost"


def font_choices(families):
    """The App-font values this machine can really draw.

    `families` is the set of family names Tk reports. Jost always stays:
    _resolve_ui_font owns its fallback chain. Every other entry needs its
    family or its fallback to be present.
    """
    fams = set(families or ())
    out = []
    for value, fam, fallback in APP_FONTS:
        if value == DEFAULT_APP_FONT:
            out.append(value)
        elif fam in fams or (fallback and fallback in fams):
            out.append(value)
    return out


def font_families(value, families, brand):
    """(body, semibold) families for one App-font value.

    `brand` is the (body, semibold) pair _resolve_ui_font picked. A face
    that carries all of its weights in one family stands in for both
    slots. An absent family falls back, then to the brand pair.
    """
    fams = set(families or ())
    for val, fam, fallback in APP_FONTS:
        if val != value:
            continue
        if val == DEFAULT_APP_FONT:
            return brand
        if fam in fams:
            return fam, fam
        if fallback and fallback in fams:
            return fallback, fallback
        break
    return brand


# ---------------------------------------------------------------------------
# 2. Retired themes
# ---------------------------------------------------------------------------
# v1.4.9 R9a: the dyslexia-friendly face is a font, so the two themes
# that carried it retire. A settings file, a session or a project that
# names one maps to {theme, App font}. Dyslexic Light sat on a warm
# cream ground and maps to Standard Light. Dyslexic Dark wore the
# Rainbow palette and maps to Rainbow.
RETIRED_THEMES = {
    "dyslexiclight": ("light", "OpenDyslexic"),
    "dyslexicdark": ("rainbow", "OpenDyslexic"),
}


def live_theme(name):
    """The theme key that is really available for a stored theme name."""
    return RETIRED_THEMES.get(name, (name, None))[0]


def retired_note(name):
    """One log line for a theme the tool migrated, or None."""
    row = RETIRED_THEMES.get(name)
    if not row:
        return None
    return ("Theme '%s' is retired. The tool uses theme '%s' with the "
            "%s font." % (name, row[0], row[1]))


# ---------------------------------------------------------------------------
# 3. Chrome that lives outside the right panel
# ---------------------------------------------------------------------------
# 'Find a setting' searches the right-panel sections. Theme sits on the
# top bar. App font, App text size, Helper tips and Performance mode sit
# in the top bar's Settings panel. A search for them finds no section,
# so the tool answers with one line that says where the control is.
CHROME_HINTS = (
    (("font", "typeface", "dyslexic", "opendyslexic", "jost", "comic",
      "arial", "verdana", "georgia", "segoe", "trebuchet"),
     "Font is in the top bar's Settings panel."),
    (("theme", "dark mode", "light mode", "colorblind", "high contrast"),
     "Theme is in the top bar."),
    (("text size", "font size", "interface size", "ui size"),
     "Text size is in the top bar's Settings panel."),
    (("tooltip", "helper", "hover tip"),
     "Helper tips is in the top bar's Settings panel."),
    (("performance mode", "slow machine", "responsiveness"),
     "Performance mode is in the top bar's Settings panel."),
    (("tutorial", "guided tour", "walkthrough"),
     "Tutorial is in the top bar's Settings panel."),
)


def chrome_hint(query):
    """One line telling the user where a top-bar control is, or None."""
    q = (query or "").strip().lower()
    if len(q) < 3:
        return None
    for keys, msg in CHROME_HINTS:
        for k in keys:
            if q in k or k in q:
                return msg
    return None
