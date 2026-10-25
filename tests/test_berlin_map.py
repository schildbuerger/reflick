import re

import pytest

from reflick.berlin_map import Projection, berlin_map, distance_m, labelled, pins, view_box
from reflick.models import Cinema


def cinema(id: str, lat: float | None, lon: float | None) -> Cinema:
    return Cinema(id, id.title(), "", "", "", lat, lon)


DELPHI = cinema("delphi", 52.5061, 13.3285)
LUX = cinema("lux", 52.50557, 13.32961)
PARIS = cinema("paris", 52.50436, 13.32999)
KANT = cinema("kant", 52.5067, 13.3084)
BRANDENBURGER_TOR = (13.3777, 52.5163)


def test_the_map_has_all_twelve_districts_rivers_and_the_ring():
    geo = berlin_map()
    assert len(geo.districts) == 12
    assert {"Mitte", "Neukölln", "Spandau"} <= {d.name for d in geo.districts}
    assert geo.water.startswith("M") and geo.ring.endswith("Z")
    # Berlin is drawn 1000 units wide; a city centre point lands inside.
    x, y = geo.projection.point(*BRANDENBURGER_TOR)
    assert 0 < x < 1000 and 0 < y < 1000


def test_projection_keeps_distances_in_proportion():
    p = Projection(west=13.0, north=53.0, scale=1000, k=0.6)
    assert p.point(13.0, 53.0) == (0, 0)
    assert p.point(13.1, 52.9) == (60, 100)  # a degree of longitude is shorter
    assert p.path([[13.0, 53.0], [13.1, 52.9]], closed=True) == "M0,0 60,100Z"


def test_neighbouring_cinemas_share_a_pin():
    p = berlin_map().projection
    found = pins([KANT, PARIS, DELPHI, LUX, cinema("nowhere", None, None)], p)
    assert [[c.id for c in pin.cinemas] for pin in found] == [["delphi", "lux", "paris"], ["kant"]]
    assert found[0].name == "Delphi, Lux, Paris"
    assert distance_m(DELPHI, KANT) > 1000


def test_view_box_frames_the_cinemas_with_a_margin():
    p = berlin_map().projection
    x, y, w, h = view_box([DELPHI, KANT, cinema("nowhere", None, None)], p)
    for c in (DELPHI, KANT):
        cx, cy = p.point(c.lon, c.lat)
        assert x < cx < x + w and y < cy < y + h
    with pytest.raises(ValueError):
        view_box([cinema("nowhere", None, None)], p)


def test_district_names_are_moved_inside_the_view_box():
    geo = berlin_map()
    p = geo.projection
    box = view_box([cinema("a", 52.48, 13.30), cinema("b", 52.55, 13.45)], p)
    shown = labelled(geo.districts, box)
    assert "Mitte" in {d.name for d in shown}
    assert "Spandau" not in {d.name for d in shown}  # far west, out of view
    x, _, w, _ = box
    for d in shown:
        assert x <= d.label[0] <= x + w


def test_map_data_has_compact_coordinates():
    # Four decimals (~10 m) are plenty for a city map and keep the page small.
    path = berlin_map().districts[0].path
    assert not re.search(r"\.\d{2,}", path)
