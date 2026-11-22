"""Tests for r6reel.captions (timing, range, output format, word changes, fallbacks)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from r6reel import captions as cap  # noqa: E402

TEXT = "Then the bus door opened, and nobody was inside. Nobody at all!"
SIZES = [(360, 640), (540, 960), (1080, 1920)]


@pytest.fixture(autouse=True)
def _clear_caches():
    yield


def _bbox(rgba):
    ys, xs = np.nonzero(rgba[..., 3])
    return xs.min(), xs.max() + 1, ys.min(), ys.max() + 1


# ---------------------------------------------------------------- timing

def test_from_text_timing_is_monotonic_and_within_bounds():
    tr = cap.Captions.from_text(TEXT, 1.0, 9.0)
    starts = [w[1] for w in tr.words]
    ends = [w[2] for w in tr.words]
    assert len(tr.words) == len(TEXT.split())
    assert starts[0] == pytest.approx(1.0)
    assert ends[-1] == pytest.approx(9.0)
    for a, b, s, e in zip(starts, ends, starts[1:], ends[:-1]):
        assert a < b
        assert s == pytest.approx(e)          # contiguous: each word starts when the last ends
        assert s > a
    assert all(1.0 - 1e-9 <= s and e <= 9.0 + 1e-9 for s, e in zip(starts, ends))


def test_natural_length_from_words_per_sec():
    words = TEXT.split()
    tr = cap.Captions.from_text("one two three", 0.0, words_per_sec=3.0)
    total = tr.t_end - tr.t_start
    assert total == pytest.approx(3 / 3.0, rel=1e-6)   # no punctuation, so no pauses
    tr_wpm = cap.Captions.from_text("one two three", 0.0, wpm=180)
    assert tr_wpm.t_end == pytest.approx(total)
    assert len(words) > 0


def test_longer_words_take_longer():
    tr = cap.Captions.from_text("a extraordinarily", 0.0, 4.0)
    d_short = tr.words[0][2] - tr.words[0][1]
    d_long = tr.words[1][2] - tr.words[1][1]
    assert d_long > 2 * d_short


def test_very_short_words_have_a_floor():
    tr = cap.Captions.from_text("I a", 0.0, 2.0)
    d_i, d_a = (w[2] - w[1] for w in tr.words)
    assert d_i == pytest.approx(d_a)
    assert d_i > 0.5                          # neither is squeezed to nothing


def test_punctuation_adds_a_pause():
    plain = cap.Captions.from_text("cat dog", 0.0, 3.0)
    punct = cap.Captions.from_text("cat. dog", 0.0, 3.0)
    gap_plain = plain.words[0][2] - plain.words[0][1]
    gap_punct = punct.words[0][2] - punct.words[0][1]
    assert gap_punct > gap_plain


def test_empty_text_gives_empty_track():
    tr = cap.Captions.from_text("   ", 0.0, 2.0)
    assert tr.words == []
    assert cap.render_caption(tr, 1.0, 540, 960) is None


def test_from_text_rejects_bad_times():
    with pytest.raises(ValueError):
        cap.Captions.from_text("hi there", 2.0, 1.0)
    with pytest.raises(ValueError):
        cap.Captions.from_text("hi there", 0.0, words_per_sec=0)


def test_from_words_keeps_given_times_and_validates():
    tr = cap.Captions.from_words([("Hello", 0.0, 0.5), ("world", 0.5, 1.2)])
    assert tr.words == [("Hello", 0.0, 0.5), ("world", 0.5, 1.2)]
    with pytest.raises(ValueError):
        cap.Captions.from_words([("bad", 1.0, 1.0)])
    with pytest.raises(ValueError):
        cap.Captions.from_words([("a", 0.0, 1.0), ("b", 0.5, 2.0)])


def test_unknown_style_rejected():
    with pytest.raises(ValueError):
        cap.Captions.from_text("hi", 0, 1, style="neon")
    tr = cap.Captions.from_text("hi there", 0.0, 2.0)
    with pytest.raises(ValueError):
        cap.render_caption(tr, 0.5, 540, 960, style="neon")


# ---------------------------------------------------------------- range

def test_render_is_none_outside_range_and_in_gaps():
    tr = cap.Captions.from_words([("Hello", 1.0, 2.0), ("world", 3.0, 4.0)])
    assert cap.render_caption(tr, 0.5, 540, 960) is None      # before
    assert cap.render_caption(tr, 2.5, 540, 960) is None      # gap
    assert cap.render_caption(tr, 4.0, 540, 960) is None      # at / after end
    assert cap.render_caption(tr, 9.0, 540, 960) is None
    assert cap.render_caption(tr, 1.5, 540, 960) is not None
    assert cap.render_caption(tr, 3.0, 540, 960) is not None


# ---------------------------------------------------------------- output format

@pytest.mark.parametrize("style", cap.STYLES)
@pytest.mark.parametrize("W,H", SIZES)
def test_output_shape_dtype_and_content(style, W, H):
    tr = cap.Captions.from_text(TEXT, 0.0, 6.0, style=style)
    out = cap.render_caption(tr, 1.0, W, H)
    assert out.shape == (H, W, 4)
    assert out.dtype == np.uint8
    assert out[..., 3].max() == 255 or out[..., 3].max() > 200
    assert (out[..., 3] > 0).sum() > 0


@pytest.mark.parametrize("style", cap.STYLES)
def test_caption_stays_inside_side_margins_and_centred(style):
    W, H = 540, 960
    tr = cap.Captions.from_text("Then the bus door opened and nobody", 0.0, 4.0, style=style)
    for t in (0.2, 1.0, 2.0, 3.2):
        out = cap.render_caption(tr, t, W, H, y=0.62)
        x0, x1, y0, y1 = _bbox(out)
        assert x0 >= 0.05 * W and x1 <= 0.95 * W
        assert abs((x0 + x1) / 2 - W / 2) < 0.02 * W
        assert abs((y0 + y1) / 2 - 0.62 * H) < 0.05 * H


def test_y_moves_block():
    tr = cap.Captions.from_text("Hello there", 0.0, 2.0)
    low = _bbox(cap.render_caption(tr, 0.5, 540, 960, y=0.35))
    high = _bbox(cap.render_caption(tr, 0.5, 540, 960, y=0.62))
    assert high[2] - low[2] > 0.2 * 960 * 0.9


def test_font_scales_with_width():
    tr = cap.Captions.from_text("Hello", 0.0, 2.0, style="yellow_pop")
    small = _bbox(cap.render_caption(tr, 0.5, 360, 640))
    big = _bbox(cap.render_caption(tr, 0.5, 1080, 1920))
    assert (big[3] - big[2]) / 1920 == pytest.approx((small[3] - small[2]) / 640, rel=0.25)


# ---------------------------------------------------------------- word changes

def test_active_index_follows_time():
    tr = cap.Captions.from_text(TEXT, 0.0, 6.0)
    seen = []
    for t in np.arange(0.0, 6.0, 0.05):
        i = tr.active_index(float(t))
        if i is not None and (not seen or seen[-1] != i):
            seen.append(i)
    assert seen == list(range(len(tr.words)))


def test_current_word_changes_the_frame():
    tr = cap.Captions.from_text("alpha beta gamma", 0.0, 3.0, style="yellow_pop")
    a = cap.render_caption(tr, 0.5, 540, 960)
    b = cap.render_caption(tr, 1.5, 540, 960)
    assert not np.array_equal(a, b)


def test_yellow_pop_highlights_current_word_in_yellow():
    tr = cap.Captions.from_text("alpha beta", 0.0, 2.0, style="yellow_pop")
    out = cap.render_caption(tr, tr.words[1][1] + 0.1, 540, 960)   # "beta" is current, "alpha" earlier
    rgb = out[..., :3][out[..., 3] > 200]
    yellow = np.all(np.abs(rgb.astype(int) - np.array(cap.YELLOW)) < 40, axis=1)
    white = np.all(rgb > 230, axis=1)
    assert yellow.any() and white.any()


def test_storytime_shows_at_most_three_words_and_resets_on_punctuation():
    words = "one two three four. five".split()
    tr = cap.Captions.from_text(" ".join(words), 0.0, 5.0)
    raw = [w[0] for w in tr.words]
    a, b = cap._style_window("storytime", 3, 5)
    assert b - a <= 3
    assert raw[3] == "four."
    lo, _ = cap._phrase_bounds(raw, 4)
    assert lo == 4                                   # the new phrase starts at "five"


def test_pop_scale_keyframes():
    assert cap.pop_scale(0.0) == pytest.approx(0.8)
    assert cap.pop_scale(2 / 30) == pytest.approx(1.08)
    assert cap.pop_scale(4 / 30) == pytest.approx(1.0)
    assert cap.pop_scale(1.0) == pytest.approx(1.0)


# ---------------------------------------------------------------- robustness

def test_emoji_and_non_latin_do_not_crash():
    tr = cap.Captions.from_text("Wow \U0001F525 Привет 中文 end", 0.0, 4.0)
    for style in cap.STYLES:
        for t in (0.2, 1.5, 3.0):
            out = cap.render_caption(tr, t, 540, 960, style=style)
            assert out is None or out.shape == (960, 540, 4)


def test_emoji_only_word_renders_nothing_and_no_tofu():
    tr = cap.Captions.from_words([("\U0001F525", 0.0, 1.0)])
    assert cap.render_caption(tr, 0.5, 540, 960) is None


def test_missing_glyph_probe_detects_tofu():
    assert cap._has_glyph("a")
    assert not cap._has_glyph("\U0001F525")


def test_font_falls_back_when_assets_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(cap, "FONT_DIR", tmp_path / "none")
    monkeypatch.setattr(cap, "_download_font", lambda: None)
    cap._font_path.cache_clear()
    cap._font.cache_clear()
    cap._has_glyph.cache_clear()
    cap._display_text.cache_clear()
    cap._sprite.cache_clear()
    try:
        tr = cap.Captions.from_text("fallback works", 0.0, 2.0)
        out = cap.render_caption(tr, 0.5, 540, 960)
        assert out.shape == (960, 540, 4)
    finally:
        cap._font_path.cache_clear()
        cap._font.cache_clear()
        cap._has_glyph.cache_clear()
        cap._display_text.cache_clear()
        cap._sprite.cache_clear()


def test_composite_blends_and_preserves_shape():
    frame = np.full((4, 6, 3), 100, np.uint8)
    rgba = np.zeros((4, 6, 4), np.uint8)
    rgba[1, 2] = (255, 0, 0, 255)
    rgba[2, 3] = (0, 0, 255, 128)
    out = cap.composite(frame, rgba)
    assert out.shape == frame.shape and out.dtype == np.uint8
    assert tuple(out[1, 2]) == (255, 0, 0)
    assert abs(int(out[2, 3, 2]) - 178) <= 2
    assert tuple(out[0, 0]) == (100, 100, 100)
    assert np.array_equal(cap.composite(frame, None), frame)
