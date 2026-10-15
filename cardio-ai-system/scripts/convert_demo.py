"""Build the PulseIQ walkthrough MP4 from the two recorded takes.

Usage:
    .venv/Scripts/python.exe scripts/convert_demo.py

Reads  docs/demo/raw-take1.webm + docs/demo/raw-take2.webm
Writes docs/demo/pulseiq-walkthrough.mp4

One file, deliberately. The pipeline used to write the same encode twice, as
``pulseiq-demo.mp4`` and ``pulseiq-linkedin.mp4``, and both were committed — two
identical 4 MB blobs in the repository, and a project page that described them as
a landscape cut and a vertical cut when they were byte-for-byte the same
footage. A post attaches the same file the README links.

Pipeline: normalize both takes to 30 fps, speed up 1.2x (removes dead air,
keeps motion readable), concatenate, encode H.264 yuv420p + faststart so
LinkedIn/GitHub accept it. The slow on-device LLM wait is already cut
between the takes; no audio track (the app demo is visual).
"""

import subprocess
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "docs" / "demo"
TAKE1 = DEMO / "raw-take1.webm"
TAKE2 = DEMO / "raw-take2.webm"
SPEED = 1.2
FPS = 30

OUT = DEMO / "pulseiq-walkthrough.mp4"


def main() -> int:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError:
        print("imageio-ffmpeg is required: pip install imageio-ffmpeg")
        return 1
    ffmpeg = get_ffmpeg_exe()
    for take in (TAKE1, TAKE2):
        if not take.exists() or take.stat().st_size == 0:
            print(f"missing take: {take}")
            return 1

    cmd = [
        ffmpeg, "-y",
        "-i", str(TAKE1),
        "-i", str(TAKE2),
        "-filter_complex",
        (
            f"[0:v]fps={FPS},setpts=PTS/{SPEED}[v0];"
            f"[1:v]fps={FPS},setpts=PTS/{SPEED}[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[out]"
        ),
        "-map", "[out]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-an",
        str(OUT),
    ]
    print("encoding…")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2000:])
        return 1
    print(f"  {OUT.name}  {OUT.stat().st_size / 1_048_576:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
