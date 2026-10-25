"""Map the language versions cinemas print onto one short set of codes.

    OV    original version without subtitles ('OF', 'engl. OV')
    OmeU  original version with English subtitles
    OmdU  original version with German subtitles ('OmU', as usual in Berlin)
    DF    German dubbed version
    oD    no dialogue

Anything else is shown as the cinema writes it; add such outliers to OUTLIERS.
"""

import re

RULES = [
    (re.compile(r"(?:engl\.?\s*)?o[vf]"), "OV"),
    (re.compile(r"ome\.?\s*u"), "OmeU"),
    (re.compile(r"om\.?\s*d?\.?\s*u"), "OmdU"),
    (re.compile(r"df|dt\.? fassung|deutsche fassung"), "DF"),
    (re.compile(r"od|ohne dialog"), "oD"),
    # Written out: "Spanisch mit englischen Untertiteln", "Tschechisch | Englisch
    # mit deutschen UT". Both kinds of subtitles don't match, and stay as written.
    (re.compile(r".+ mit (?:englischen|engl\.?|en) (?:untertiteln?|ut)"), "OmeU"),
    (re.compile(r".+ mit (?:deutschen|dt\.?) (?:untertiteln?|ut)"), "OmdU"),
]
# Versions the rules can't read, by their casefolded text.
OUTLIERS = {
    # Silent film: the intertitles are the original language.
    "russische zwischentitel und deutsche untertitel": "OmdU",
    "deutsche zwischentitel, englische untertitel": "OmeU",
    # A German film in German: nothing to filter by (other cinemas say nothing).
    "deutsche originalfassung": None,
}


def language_version(text: str | None) -> str | None:
    """'engl. OV' -> 'OV', 'OmU' -> 'OmdU'; None for no language given."""
    key = " ".join((text or "").split()).casefold()
    if not key:
        return None
    if key in OUTLIERS:
        return OUTLIERS[key]
    return next((code for pattern, code in RULES if pattern.fullmatch(key)), " ".join(text.split()))
