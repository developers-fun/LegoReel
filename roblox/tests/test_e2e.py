import os, sys, subprocess, json
import numpy as np
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _gl():
    try:
        import moderngl
        moderngl.create_standalone_context(backend="egl", require=330).release()
        return True
    except Exception:
        try:
            import moderngl
            moderngl.create_standalone_context(require=330).release()
            return True
        except Exception:
            return False


@pytest.mark.skipif(not _gl(), reason="no GL")
def test_render_one_second(tmp_path):
    from r6reel.director import Director
    sc = Director("@street\nMilo (shocked): Wow that was close.", seed=2, size=(180, 320), fps=30).build()
    out = str(tmp_path / "o.mp4")
    sc.render(out, start=0, end=1.0, preview=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames,width,height", "-of", "json", out], capture_output=True, text=True).stdout
    st = json.loads(probe)["streams"][0]
    assert int(st["nb_read_frames"]) == 30 and int(st["width"]) == 180
    f = sc.render_frame(0.5, size=(180, 320))
    assert f.shape == (320, 180, 3) and f.std() > 8
