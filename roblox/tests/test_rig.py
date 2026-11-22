import numpy as np
from r6reel import rig, clips
from r6reel.avatar import Avatar
from r6reel.anim import poses_equal


def test_standing_feet_on_ground_head_top():
    ms = rig.part_models({})
    assert abs(rig.lowest_y({})) < 1e-9
    assert np.allclose(ms["Torso"][:3, 3], (0, 3, 0))
    top = ms["Head"][:3, 3][1] + rig.HEAD_VISUAL[1] / 2
    assert 5.0 <= top <= 5.2
    assert np.allclose(ms["Right Leg"][:3, 3], (0.5, 1, 0)) and np.allclose(ms["Left Leg"][:3, 3], (-0.5, 1, 0))


def test_arms_hang_from_shoulders():
    ms = rig.part_models({})
    assert np.allclose(ms["Right Arm"][:3, 3], (1.5, 3, 0))
    assert np.allclose(ms["Left Arm"][:3, 3], (-1.5, 3, 0))


def test_arm_raised_forward_90():
    ms = rig.part_models({"Right Shoulder": (90, 0, 0)})
    m = ms["Right Arm"]
    assert np.allclose(m[:3, 3], (1.5, 3.5, -0.5), atol=1e-9)
    hand = m @ np.array([0, -1, 0, 1])
    assert hand[2] < -1.4 and abs(hand[1] - 3.5) < 1e-9          # points forward (-Z), horizontal


def test_arm_raised_sideways_and_mirror():
    r = rig.part_models({"Right Shoulder": (0, 0, 90)})["Right Arm"] @ np.array([0, -1, 0, 1])
    l = rig.part_models({"Left Shoulder": (0, 0, -90)})["Left Arm"] @ np.array([0, -1, 0, 1])
    assert r[0] > 2.4 and l[0] < -2.4 and abs(r[0] + l[0]) < 1e-9


def test_leg_forward_and_euler_roundtrip():
    m = rig.part_models({"Right Hip": (90, 0, 0)})["Right Leg"] @ np.array([0, -1, 0, 1])
    assert m[2] < -1 and abs(m[1] - 2.0) < 1e-9
    R = rig.euler_to_matrix(30, 40, 50)
    assert np.allclose(rig.euler_to_matrix(*rig.matrix_to_euler(R)), R)
    cf = rig.cframe((1, 2, 3), (0, 90, 0))
    assert np.allclose(cf[:3, 3], (1, 2, 3)) and np.allclose(cf @ [0, 0, -1, 1], (0, 2, 3, 1))


def test_meshes_valid_and_outward():
    for n in rig.PARTS:
        m = rig.part_mesh(n)
        p, i = m.positions, m.indices
        fn = np.cross(p[i[:, 1]] - p[i[:, 0]], p[i[:, 2]] - p[i[:, 0]])
        assert ((fn * m.normals[i[:, 0]]).sum(1) >= -1e-9).all()
        assert m.uvs.min() >= -1e-6 and m.uvs.max() <= 1 + 1e-6
    assert np.allclose(rig.part_mesh("Torso").positions.max(0), (1, 1, 0.5), atol=1e-6)


def test_clothing_template_uv_lands_in_rect():
    uv = rig.part_mesh("Torso").uvs
    x, y, w, h = rig.TEMPLATE_RECTS["Torso"]["front"]
    # some vertices must sample inside the front rect
    px, py = uv[:, 0] * 585, (1 - uv[:, 1]) * 559
    inside = (px >= x) & (px <= x + w) & (py >= y) & (py <= y + h)
    assert inside.sum() >= 9


def test_avatar_draw_items():
    av = Avatar(shirt_color="#ff0000", pants_color="#0000ff", hair="bun", accessories=["glasses", "backpack"])
    items = av.draw_items({}, np.eye(4))
    keys = [i.key for i in items]
    assert len(set(keys)) == len(keys) and len(items) >= 6
    assert items[1].texture.size == (585, 559)
    assert Avatar(face="shock").draw_items({})[0].texture.size == (512, 256)


def test_all_hair_and_accessories_build():
    from r6reel.avatar import ACCESSORIES
    for n in ACCESSORIES:
        assert Avatar(accessories=[n]).draw_items({})


def test_edge_styles():
    prev = rig.get_edge_style()
    try:
        assert prev == "smooth"
        n_s = sum(len(rig.part_mesh(p).indices) for p in rig.PARTS)
        assert n_s < 6000
        rig.set_edge_style("classic")
        n_c = sum(len(rig.part_mesh(p).indices) for p in rig.PARTS)
        assert n_c < n_s
        # sizes/FK unchanged: extents identical in both styles
        assert np.allclose(rig.part_mesh("Torso").positions.max(0), (1, 1, 0.5), atol=1e-6)
        rig.set_edge_style("smooth")
        for n in rig.PARTS:
            m = rig.part_mesh(n)
            assert np.allclose(np.abs(m.positions).max(0), np.array(rig.VISUAL_SIZE[n]) / 2, atol=1e-5)
        assert np.allclose(np.linalg.norm(rig.part_mesh("Left Arm").normals, axis=1), 1, atol=1e-4)
        a = Avatar(edge_style="classic").draw_items({})
        b = Avatar(edge_style="smooth").draw_items({})
        assert len(a[1].mesh.indices) < len(b[1].mesh.indices)
        import pytest
        with pytest.raises(ValueError):
            rig.set_edge_style("bogus")
    finally:
        rig.set_edge_style(prev)
