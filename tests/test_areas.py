from lagosdata.areas import assign, bbox_for, nearest_area, zone_of
from lagosdata.config import AreaDef, Corridor, load_areas
from lagosdata.record import CORE_ZONE, OUTSIDE, RING_ZONE, UNASSIGNED
from pathlib import Path

REG = load_areas(Path(__file__).resolve().parents[1] / 'config' / 'areas.yaml').areas
MAG = ['Anthony / Anthony Village', 'Maryland / Mende', 'Ilupeju', 'Gbagada', 'Obanikoro', 'Palmgrove', 'Ojota']


def test_shipped_centroids():
    assert (REG['Anthony / Anthony Village'].lat, REG['Anthony / Anthony Village'].lng) == (6.55982, 3.36915)
    assert REG['Maryland / Mende'].radius_km == 1.30


def test_assign_by_coordinates():
    assert assign(6.5600, 3.3695, '', MAG, REG)[0] == 'Anthony / Anthony Village'
    assert assign(6.5723, 3.3670, 'Ikeja', MAG, REG)[0] == 'Maryland / Mende'   # address text ignored when coords exist


def test_outside_is_kept_not_dropped():
    area, d = assign(6.6200, 3.3000, '', MAG, REG)
    assert area == OUTSIDE and d > 1.6


def test_no_coordinates_falls_back_to_address_name():
    assert assign('', '', '12 Ikorodu Rd, Anthony Village, Lagos', MAG, REG)[0] == 'Anthony / Anthony Village'
    assert assign('', '', 'Mende, Maryland', MAG, REG)[0] == 'Maryland / Mende'
    assert assign('', '', 'Somewhere, Lagos', MAG, REG)[0] == UNASSIGNED


def test_corridor_geometry():
    reg = {'Strip': AreaDef(corridor=Corridor(**{'from': (6.44, 3.47), 'to': (6.47, 3.57), 'width_km': 2.0}))}
    assert assign(6.455, 3.52, '', ['Strip'], reg)[0] == 'Strip'
    assert assign(6.50, 3.52, '', ['Strip'], reg)[0] == OUTSIDE


def test_zone():
    core = MAG[:2]
    assert zone_of(MAG[0], core) == CORE_ZONE and zone_of('Ojota', core) == RING_ZONE
    assert zone_of(OUTSIDE, core) == OUTSIDE


def test_bbox_covers_all_areas():
    s, w, n, e = bbox_for(MAG, REG, 0)
    for a in MAG:
        assert s <= REG[a].lat <= n and w <= REG[a].lng <= e


def test_nearest_area_flat_earth():
    name, d, inside = nearest_area(6.55982, 3.36915, {k: REG[k] for k in MAG})
    assert name == 'Anthony / Anthony Village' and d == 0 and inside
