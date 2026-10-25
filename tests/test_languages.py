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
        (None, None),
        ("", None),
        # Unknown versions are kept as the cinema writes them.
        ("Japanisch  mit Untertiteln", "Japanisch mit Untertiteln"),
    ],
)
def test_language_version(raw, expected):
    assert language_version(raw) == expected
