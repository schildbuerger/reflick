import pytest

from reflick.titles import display_title, split_addons


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "Modern Times LIVE mit Babylon Orchester Berlin",
            ("Modern Times", ["Live mit Babylon Orchester Berlin"]),
        ),
        ("Metropolis LIVE Babylon Orchester Berlin", ("Metropolis", ["Live Babylon Orchester Berlin"])),
        ("Chaplin's The Gold Rush with LIVE Orchestra", ("Chaplin's The Gold Rush", ["Live Orchestra"])),
        ("The Rocky Horror Picture Show: Live Shadow Cast", ("The Rocky Horror Picture Show", ["Live Shadow Cast"])),
        ("The Exorcist: Director's Cut", ("The Exorcist", ["Director's Cut"])),
        ("Life Support - GERMAN PREMIERE with Guests!", ("Life Support", ["German Premiere with Guests!"])),
        ("The Answering Machine: Premiere with Guests!", ("The Answering Machine", ["Premiere with Guests!"])),
        ("Becoming Kim - mit Gästen!", ("Becoming Kim", ["Mit Gästen!"])),
        ("BERLATIN Premiere: ALBUM DE FAMILIA", ("ALBUM DE FAMILIA", ["Berlatin Premiere"])),
    ],
)
def test_addons_become_badges(title, expected):
    assert split_addons(title) == expected


@pytest.mark.parametrize(
    "title",
    [
        "Nordstream - Die Sprengung",
        "2001: A Space Odyssey",
        "Dr. Strangelove or: How I Learned to Stop Worrying and Love the Bomb",
        "Quiz 3000 – Du bist die Katastrophe!",
        "To Live and Die in L.A.",
        "Live and Let Die",
    ],
)
def test_real_titles_stay_intact(title):
    assert split_addons(title) == (title, [])


def test_display_title_prefers_verified_title_when_it_differs():
    assert display_title("Chaplin's The Gold Rush", "The Gold Rush") == "The Gold Rush"


def test_display_title_keeps_cinema_spelling_when_only_accents_differ():
    assert display_title("Cléo from 5 to 7", "Cleo from 5 to 7") == "Cléo from 5 to 7"
    assert display_title("Former East / Former West", "Former East/Former West") == (
        "Former East / Former West"
    )


def test_display_title_without_match():
    assert display_title("Sühne", None) == "Sühne"
