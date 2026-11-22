"""Contact sheet of every caption style at four timestamps, written to out/captions_demo.png."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from r6reel import captions as cap  # noqa: E402

W, H = 540, 960
TEXT = "Then the bus door opened, and nobody was inside."
TIMES = (0.5, 1.4, 2.3, 3.4)
CELL = (270, 480)
PAD = 12
LABEL_W = 130


def gray_gradient(w, h):
    top, bottom = 118, 152
    col = np.linspace(top, bottom, h, dtype=np.float32)[:, None]
    grad = np.repeat(col, w, axis=1)
    rgb = np.stack([grad, grad, grad], axis=-1).astype(np.uint8)
    return rgb


def main():
    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    bg = gray_gradient(W, H)
    sheet = Image.new("RGB", (LABEL_W + len(TIMES) * (CELL[0] + PAD) + PAD,
                              len(cap.STYLES) * (CELL[1] + PAD) + PAD), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    label_font = ImageFont.load_default(size=18)
    for r, style in enumerate(cap.STYLES):
        track = cap.Captions.from_text(TEXT, 0.0, 4.0, style=style)
        y0 = PAD + r * (CELL[1] + PAD)
        draw.text((PAD, y0 + CELL[1] // 2), style, fill=(230, 230, 230), font=label_font, anchor="lm")
        for c, t in enumerate(TIMES):
            rgba = cap.render_caption(track, t, W, H, y=0.62)
            frame = cap.composite(bg, rgba)
            thumb = Image.fromarray(frame).resize(CELL, Image.Resampling.LANCZOS)
            x0 = LABEL_W + PAD + c * (CELL[0] + PAD)
            sheet.paste(thumb, (x0, y0))
    dest = out_dir / "captions_demo.png"
    sheet.save(dest)
    print(dest)


if __name__ == "__main__":
    main()
