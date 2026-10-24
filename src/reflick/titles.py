"""Separate what cinemas add to film titles from the titles themselves.

'Modern Times LIVE mit Babylon Orchester Berlin'
    -> ('Modern Times', ['Live mit Babylon Orchester Berlin'])

Only clear event add-ons are split off: live music or shows, cuts,
premieres, guests and Q&As. Dashes and colons that belong to a title
('Nordstream - Die Sprengung', '2001: A Space Odyssey') stay.
"""

import re
import unicodedata

# "... LIVE mit Babylon Orchester", ": Live Shadow Cast", "with LIVE Orchestra".
LIVE_RE = re.compile(r"(?i)[\s:–-]+((?:with\s+|mit\s+)?live\b.*)$")
# Words that make a "live ..." ending an event rather than part of the title
# (unlike "To Live and Die in L.A.").
LIVE_EVENT_WORDS = re.compile(r"(?i)\b(?:orchest\w*|shadow|band|music|musik|mit|with|begleit\w*)\b")
SUFFIX_RES = [
    re.compile(r"(?i):\s+(director's cut|premiere\b.*)$"),
    re.compile(r"(?i)\s+[-–]\s+(.*\b(?:gäst\w*|guests?|premiere|q&a|eröffnung)\b.*)$"),
]
PREFIX_RE = re.compile(r"(?i)^(.*\bpremiere)\s*:\s+(?=\S)")
# "The Killer (1989)": the year is shown separately, so it's dropped without a badge.
YEAR_SUFFIX_RE = re.compile(r"\s*\((?:18|19|20)\d{2}\)$")


def tidy_addon(text: str) -> str:
    """'with LIVE Orchestra' -> 'Live Orchestra', 'GERMAN PREMIERE' -> 'German Premiere'."""
    text = re.sub(r"(?i)^(?:with|mit)\s+(?=live\b)", "", text.strip(" -–:"))
    words = [w.capitalize() if w.isupper() and w.isalpha() and len(w) > 2 else w for w in text.split()]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def split_addons(title: str) -> tuple[str, list[str]]:
    addons: list[str] = []
    title = YEAR_SUFFIX_RE.sub("", title)
    if m := PREFIX_RE.match(title):
        addons.append(tidy_addon(m.group(1)))
        title = title[m.end():]
    changed = True
    while changed:
        changed = False
        m = LIVE_RE.search(title)
        if m and (m.group(1).lower() == "live" or LIVE_EVENT_WORDS.search(m.group(1))):
            addons.insert(0, tidy_addon(m.group(1)))
            title, changed = title[: m.start()], True
            continue
        for pattern in SUFFIX_RES:
            if m := pattern.search(title):
                addons.insert(0, tidy_addon(m.group(1)))
                title, changed = title[: m.start()], True
                break
    return title.strip(" -–:"), addons


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def display_title(cinema_title: str, verified_title: str | None) -> str:
    """The title to show: OMDb's when it differs in substance (e.g. it drops
    'Chaplin's'), otherwise the cinema's, which keeps accents and spacing
    ('Cléo from 5 to 7' rather than OMDb's 'Cleo from 5 to 7')."""
    if verified_title and _fold(verified_title) != _fold(cinema_title):
        return verified_title
    return cinema_title
