"""ffmpeg-piped video writer (raw rgb24 -> libx264 yuv420p)."""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import numpy as np


class VideoWriter:
    """Pipe (H,W,3) uint8 frames to ffmpeg.

    VideoWriter(path, width, height, fps=30, crf=18, preset="veryfast", audio=None)
    Use as a context manager or call close(). Odd sizes are padded to even.
    If `audio` (a file path) is given it is muxed in (AAC) and the output is cut at the shorter stream.
    """

    def __init__(self, path, width, height, fps=30, crf=18, preset="veryfast", audio=None,
                 audio_offset=0.0, extra_args=None):
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg not found on PATH")
        self.path, self.width, self.height, self.fps = str(path), int(width), int(height), fps
        d = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(d, exist_ok=True)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{self.width}x{self.height}", "-r", str(fps), "-i", "-"]
        if audio:
            if audio_offset:
                cmd += ["-itsoffset", str(audio_offset)]
            cmd += ["-i", str(audio)]
        vf = "pad=ceil(iw/2)*2:ceil(ih/2)*2,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                "-movflags", "+faststart"]
        if audio:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
        cmd += list(extra_args or []) + [self.path]
        self._err = tempfile.TemporaryFile()
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._err)
        self.frames = 0
        self._closed = False

    def write(self, frame: np.ndarray) -> None:
        f = np.asarray(frame)
        if f.dtype != np.uint8:
            f = np.clip(f * (255.0 if f.dtype.kind == "f" and f.max() <= 1.0 else 1.0), 0, 255).astype(np.uint8)
        if f.ndim == 3 and f.shape[2] == 4:
            f = f[:, :, :3]
        if f.shape != (self.height, self.width, 3):
            raise ValueError(f"frame shape {f.shape} != {(self.height, self.width, 3)}")
        try:
            self._proc.stdin.write(np.ascontiguousarray(f).tobytes())
        except (BrokenPipeError, OSError):
            raise RuntimeError("ffmpeg died: " + self._stderr()) from None
        self.frames += 1

    def _stderr(self) -> str:
        try:
            self._err.seek(0)
            return self._err.read().decode(errors="replace")[-2000:]
        except Exception:
            return ""

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._proc.stdin.close()
        except Exception:
            pass
        rc = self._proc.wait()
        msg = self._stderr()
        self._err.close()
        if rc != 0:
            raise RuntimeError(f"ffmpeg failed (rc={rc}): {msg}")

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._closed = True
            return False
        self.close()
        return False
