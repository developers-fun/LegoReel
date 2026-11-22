import os
import sys
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples"))

moderngl = pytest.importorskip("moderngl")
from r6reel.renderer import Renderer, DrawItem, CameraState, Lighting, PostFx
from r6reel.util import color, compose, look_at, perspective
from r6reel.video import VideoWriter
from renderer_demo import box, sphere


@pytest.fixture(scope="module")
def rend():
    try:
        r = Renderer(160, 288, samples=2)
    except Exception as e:  # no GL available
        pytest.skip(f"no GL context: {e}")
    yield r
    r.close()


def scene(cast=True):
    B, S = box(), sphere(seg=16)
    return [
        DrawItem(B, compose((0, -0.5, 0), (0, 0, 0), (60, 1, 60)), (0.4, 0.75, 0.3)),
        DrawItem(B, compose((0, 2, 0), (0, 0, 0), (2, 4, 2)), (0.9, 0.3, 0.3), cast_shadow=cast),
        DrawItem(B, compose((8, 1, 5), (0, 30, 0), (2, 2, 2)), (0.3, 0.4, 0.9)),
        DrawItem(S, compose((-7, 1, 6), (0, 0, 0), (2, 2, 2)), (1, 0.9, 0.2), material="smooth"),
    ]


CAM = CameraState(eye=(0, 22, 0.01), target=(0, 0, 0), up=(0, 0, -1), fov_y=60)
LIGHT = Lighting(sun_dir=(-1, -1.2, 0), shadow_extent=20)


def lum(img, p):
    return img[p[1] - 2:p[1] + 3, p[0] - 2:p[0] + 3].astype(float).mean()


def proj(world, w=160, h=288):
    vp = perspective(CAM.fov_y, w / h, CAM.near, CAM.far) @ look_at(CAM.eye, CAM.target, CAM.up)
    c = vp @ np.append(world, 1.0)
    c = c[:3] / c[3]
    return int((c[0] * 0.5 + 0.5) * w), int((1 - (c[1] * 0.5 + 0.5)) * h)


def test_not_blank_and_shape(rend):
    img = rend.render(scene(), CAM, LIGHT, PostFx())
    assert img.shape == (288, 160, 3) and img.dtype == np.uint8
    assert img.std() > 8 and img.max() > 150


def test_shadow_darker_than_lit(rend):
    img = rend.render(scene(), CAM, LIGHT, PostFx.off())
    shadow = lum(img, proj((-3.0, 0, 0)))     # sun travels toward -x -> shadow on -x side
    lit = lum(img, proj((3.0, 0, 0)))
    assert shadow < lit * 0.85, (shadow, lit)
    nocast = rend.render(scene(cast=False), CAM, LIGHT, PostFx.off())
    assert lum(nocast, proj((-3.0, 0, 0))) > shadow * 1.15


def test_deterministic(rend):
    a = rend.render(scene(), CAM, LIGHT, PostFx(grain=0.03, seed=3))
    b = rend.render(scene(), CAM, LIGHT, PostFx(grain=0.03, seed=3))
    assert np.array_equal(a, b)


def test_post_effects_run(rend):
    base = rend.render(scene(), CAM, LIGHT, PostFx.off())
    for kw in (dict(bloom=0.8), dict(chroma=0.01), dict(blur_dir=(0.05, 0.0), blur_amount=1.0), dict(flash=0.5)):
        fx = PostFx.off(); [setattr(fx, k, v) for k, v in kw.items()]
        assert not np.array_equal(rend.render(scene(), CAM, LIGHT, fx), base), kw
    black = rend.render(scene(), CAM, LIGHT, PostFx(fade=1.0))
    assert black.max() <= 2


def test_glass_and_texture(rend):
    from PIL import Image
    B = box()
    tex = Image.fromarray((np.indices((8, 8)).sum(0) % 2 * 255).astype(np.uint8)).convert("RGB")
    items = scene() + [DrawItem(B, compose((0, 1, 6), (0, 0, 0), (3, 2, 0.2)), (0.5, 0.8, 1), material="glass"),
                       DrawItem(B, compose((4, 1, -6), (0, 0, 0), (2, 2, 2)), texture=tex, key="chk", uv_scale=(2, 2))]
    img = rend.render(items, CAM, LIGHT)
    assert img.std() > 8


def test_motion_blur(rend):
    items = scene()
    fn = lambda t: (items, CameraState(eye=(t * 20, 22, 0.01), target=(t * 20, 0, 0), up=(0, 0, -1)), LIGHT, None)
    img = rend.render_motion_blur(fn, 0.0, shutter=1.0, subsamples=3)
    assert img.shape == (288, 160, 3)


def test_color_util():
    assert color("#ff8000") == (1.0, 128 / 255, 0.0)
    assert color((255, 0, 0)) == (1.0, 0.0, 0.0)
    assert color((0.2, 0.3, 0.4)) == (0.2, 0.3, 0.4)


def test_video_writer(tmp_path):
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("no ffmpeg")
    p = tmp_path / "a.mp4"
    with VideoWriter(str(p), 64, 48, fps=30) as vw:
        for i in range(5):
            vw.write(np.full((48, 64, 3), i * 40, np.uint8))
    assert p.stat().st_size > 500
