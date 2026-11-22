"""Tests for scenery primitives, Part/Prop/World and the builders. No GL needed."""
import math

import numpy as np
import pytest

from r6reel import primitives as P
from r6reel import world as W
from r6reel.mesh import Mesh


def _tris(m: Mesh) -> np.ndarray:
    return m.positions[m.indices].astype(float)


def _signed_volume(m: Mesh) -> float:
    t = _tris(m)
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def _check_mesh(m: Mesh):
    assert len(m.indices) > 0
    assert np.all(np.isfinite(m.positions)) and np.all(np.isfinite(m.uvs))
    assert np.allclose(np.linalg.norm(m.normals, axis=1), 1.0, atol=1e-4)
    assert m.indices.max() < len(m.positions)
    # every non-degenerate triangle winds counter-clockwise relative to its vertex normals
    t = _tris(m)
    cr = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ok = np.linalg.norm(cr, axis=1) > 1e-9
    nsum = m.normals[m.indices].sum(axis=1)
    assert np.all(np.einsum("ij,ij->i", cr[ok], nsum[ok]) > 0)


CLOSED_SHAPES = {
    "box": lambda: P.box((2, 3, 4)),
    "box_bevel": lambda: P.box((2, 3, 4), bevel=0.3),
    "rounded_box": lambda: P.rounded_box((2, 3, 4), 0.4),
    "wedge": lambda: P.wedge((2, 3, 4)),
    "cylinder_y": lambda: P.cylinder(1, 2),
    "cylinder_x": lambda: P.cylinder(1, 2, axis="x"),
    "cylinder_z": lambda: P.cylinder(1, 2, axis="z"),
    "sphere": lambda: P.sphere(1.0),
    "cone": lambda: P.cone(1.0, 2.0),
    "prism": lambda: P.prism([(0, 0), (2, 0), (1, 2)], 3, axis="z"),
}


@pytest.mark.parametrize("name", list(CLOSED_SHAPES))
def test_primitive_mesh_valid(name):
    m = CLOSED_SHAPES[name]()
    assert isinstance(m, Mesh)
    _check_mesh(m)
    assert _signed_volume(m) > 0, "closed solid must have positive signed volume"


def test_box_volume_and_flat_normals():
    m = P.box((2, 3, 4))
    assert _signed_volume(m) == pytest.approx(24.0)
    assert len(m.positions) == 24  # one vertex set per flat face
    assert set(np.round(np.abs(m.normals), 6).ravel()) <= {0.0, 1.0}


def test_wedge_orientation_matches_roblox_convention():
    m = P.wedge((1, 1, 1))
    assert _signed_volume(m) == pytest.approx(0.5)
    # high edge at the back (+Z) and top (+Y)
    top = m.positions[m.positions[:, 1] > 0.4]
    assert np.allclose(top[:, 2], 0.5)
    # sloped face normal points up and toward -Z
    slope = m.normals[np.abs(m.normals[:, 1] - 1 / math.sqrt(2)) < 1e-4]
    assert len(slope) > 0
    assert np.allclose(slope[0], [0, 1 / math.sqrt(2), -1 / math.sqrt(2)], atol=1e-5)


def test_cylinder_and_sphere_volumes_close_to_analytic():
    assert _signed_volume(P.cylinder(1, 2, segments=64)) == pytest.approx(math.pi * 2, rel=0.01)
    assert _signed_volume(P.sphere(1.0, segments=48)) == pytest.approx(4 / 3 * math.pi, rel=0.05)
    assert _signed_volume(P.cone(1.0, 2.0, segments=48)) == pytest.approx(math.pi * 2 / 3, rel=0.03)


def test_cylinder_axis_moves_length_direction():
    for axis, idx in (("x", 0), ("y", 1), ("z", 2)):
        p = P.cylinder(0.5, 4.0, axis=axis).positions
        assert p[:, idx].max() == pytest.approx(2.0)
        assert p[:, idx].min() == pytest.approx(-2.0)


def test_plane_faces_up_and_tiles_uvs():
    m = P.plane((4, 2), uv_tile=(3, 1))
    _check_mesh(m)
    assert np.allclose(m.normals, [0, 1, 0])
    assert m.uvs.max(axis=0) == pytest.approx([3, 1])


def test_primitives_are_cached_and_never_copied_on_repeat():
    assert P.box((1, 2, 3)) is P.box((1, 2, 3))
    assert P.sphere(0.5) is P.sphere(0.5)
    assert P.box((1, 2, 3)) is not P.box((1, 2, 4))


def test_rounded_box_rejects_radius_too_large():
    with pytest.raises(ValueError):
        P.rounded_box((1, 1, 1), 0.6)


# ---- Part, Prop, World -----------------------------------------------------------------

def test_part_parses_hex_colour_and_rejects_bad_material():
    part = W.Part(P.box(), "#ff8000")
    assert part.color == pytest.approx((1.0, 128 / 255, 0.0))
    with pytest.raises(ValueError):
        W.Part(P.box(), "#ffffff", material="gold")


def test_prop_position_and_child_composition():
    part = W.Part(P.box((2, 2, 2)), (1, 1, 1), position=(1, 0, 0))
    child = W.Prop(name="child", parts=[part], position=(0, 0, 5))
    parent = W.Prop(name="parent", children=[child], position=(10, 0, 0), rotation=(0, 90, 0))
    (item,) = parent.to_draw_items()
    # part origin -> child offset gives local (1,0,5); parent Ry(90) maps it to (5,0,-1); parent translation adds (10,0,0)
    origin = item.model @ np.array([0, 0, 0, 1.0])
    assert origin[:3] == pytest.approx([15, 0, -1], abs=1e-9)
    assert item.model.shape == (4, 4)


def test_draw_item_fields_and_emissive_for_glass_and_neon():
    glass = W.Prop(parts=[W.Part(P.box(), (1, 1, 1), material="glass")])
    neon = W.Prop(parts=[W.Part(P.box(), (1, 1, 1), material="neon")])
    assert glass.to_draw_items()[0].emissive == pytest.approx(0.1)
    assert neon.to_draw_items()[0].emissive == pytest.approx(1.0)
    item = W.Prop(parts=[W.Part(P.box(), (1, 0, 0), texture="x.png")]).to_draw_items()[0]
    assert item.texture == "x.png" and item.material == "plastic"


def test_world_add_get_unique_names_and_lighting():
    world = W.World(sun_dir=(0, -2, 0), fog_density=0.02)
    a = world.add(W.ball(name="ball"))
    b = world.add(W.ball(name="ball"))
    assert a.name == "ball" and b.name == "ball_2"
    assert world.get("ball_2") is b
    with pytest.raises(KeyError):
        world.get("missing")
    light = world.lighting()
    assert set(light) == {"sun_dir", "sun_color", "sun_intensity", "ambient", "sky_top", "sky_bottom",
                          "fog_color", "fog_density"}
    assert np.linalg.norm(light["sun_dir"]) == pytest.approx(1.0)
    assert light["fog_color"] == light["sky_bottom"]
    assert len(world.draw_items()) == 2


def test_ground_top_surface_is_at_y0():
    items = W.ground(size=(10, 10)).to_draw_items()
    top = max(float((it.mesh.positions @ it.model[:3, :3].T + it.model[:3, 3])[:, 1].max()) for it in items)
    assert top == pytest.approx(0.0)


# ---- builders and scenes ---------------------------------------------------------------

BUILDERS = [
    W.ground, W.road, W.sidewalk, W.house, W.apartment_block, W.skyscraper, W.tree, W.bush, W.fence,
    W.lamp_post, W.bench, W.table, W.chair, W.desk, W.locker_row, W.door, W.window_wall, W.sign, W.car,
    W.umbrella, W.cloud, W.brick_wall, W.stairs, W.crate, W.ball, W.duck_toy, W.coin,
]
SCENES = [W.classroom, W.cafeteria, W.school_hallway, W.bedroom, W.town_square]


@pytest.mark.parametrize("builder", BUILDERS, ids=lambda f: f.__name__)
def test_builder_returns_nonempty_prop(builder):
    prop = builder()
    assert isinstance(prop, W.Prop)
    assert prop.name
    items = prop.to_draw_items()
    assert len(items) > 0
    for it in items:
        assert isinstance(it.mesh, Mesh)
        assert it.model.shape == (4, 4) and it.model.dtype == np.float64
        assert len(it.color) == 3


@pytest.mark.parametrize("scene", SCENES, ids=lambda f: f.__name__)
def test_scene_builds_and_is_large_enough(scene):
    prop = scene()
    assert len(prop.to_draw_items()) > 10


def test_builders_accept_arguments_and_tree_kinds():
    assert len(W.tree("pine").parts) == 4
    assert len(W.tree("round").parts) == 4
    with pytest.raises(ValueError):
        W.tree("palm")
    assert len(W.apartment_block(floors=3).to_draw_items()) > len(W.apartment_block(floors=1).to_draw_items())


def test_crowd_positions_are_deterministic_and_inside_area():
    a = W.crowd_positions(12, area=(20, 10), seed=3)
    b = W.crowd_positions(12, area=(20, 10), seed=3)
    assert a == b and len(a) == 12
    for x, z in a:
        assert -10 <= x <= 10 and -5 <= z <= 5
    assert W.crowd_positions(4, area=8, seed=0) != W.crowd_positions(4, area=8, seed=1)
