import pytest

from reflick.languages import language_version


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("OV", "OV"),
        ("OF", "OV"),
        ("engl. OV", "OV"),
        ("OmeU", "OmeU"),
        ("OmU", "OmdU"),
        ("OmdU", "OmdU"),
        ("DF", "DF"),
        ("oD", "oD"),
        ("Russische Zwischentitel und deutsche Untertitel", "OmdU"),
        # Written out, as on Sinema Transtopia's and Kino Krokodil's film pages.
        ("Spanisch mit englischen Untertitel", "OmeU"),
        ("Deutsch mit englischen Untertiteln", "OmeU"),
        ("Englisch mit deutschen Untertiteln", "OmdU"),
        ("Russisch mit deutschen UT", "OmdU"),
        ("Amharisch mit EN Untertiteln", "OmeU"),
        ("Tschechisch | Englisch mit deutschen UT", "OmdU"),
        # Both kinds of subtitles: no single code fits, so it stays as written.
        ("Französisch mit deutschen und englischen UT", "Französisch mit deutschen und englischen UT"),
        ("deutsche Originalfassung", None),
        (None, None),
        ("", None),
        # Unknown versions are kept as the cinema writes them.
        ("Japanisch  mit Untertiteln", "Japanisch mit Untertiteln"),
    ],
)
def test_language_version(raw, expected):
    assert language_version(raw) == expected
