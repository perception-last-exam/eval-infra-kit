#!/usr/bin/env python3
"""Make the input.mp4 every model, annotator and judge uses for one scene.

  python normalize_video.py IMG_1234.MOV input.mp4 [--fps 30]

- applies the phone's rotation flag (portrait stays portrait)
- constant frame rate at the native rate (iPhone 29.97/30 -> 30), so "frame i" means one thing
- HDR (HLG / PQ) tone-mapped to SDR BT.709
- drops audio, GPS location, device make/model and all other metadata

Frame indices everywhere (queries' frame_index, camera.json, judge) are 0-based frames of this file.
Needs ffmpeg and ffprobe on PATH (or set FFMPEG / FFPROBE).
"""
import argparse
import json
import os
import subprocess
import sys
from fractions import Fraction

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
           "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def probe(path, count=False):
    cmd = [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json"]
    if count:
        cmd.insert(1, "-count_frames")
    return json.loads(subprocess.check_output(cmd + [path]))["streams"][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--fps", type=float, help="output frame rate (default: native, rounded)")
    ap.add_argument("--crf", type=int, default=16)
    a = ap.parse_args()

    st = probe(a.src)
    fps = a.fps or round(float(Fraction(st.get("r_frame_rate") or st["avg_frame_rate"])))
    hdr = st.get("color_transfer") in ("arib-std-b67", "smpte2084")
    vf = [TONEMAP] if hdr else ["format=yuv420p"]
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", a.src,
           "-map", "0:v:0", "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
           "-fps_mode", "cfr", "-r", str(fps), "-vf", ",".join(vf),
           "-c:v", "libx264", "-crf", str(a.crf), "-preset", "slow",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
           "-movflags", "+faststart", a.dst]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit("ffmpeg failed (needs ffmpeg >= 5.1 with zscale for HDR input)")

    out = probe(a.dst, count=True)
    info = {"width": out["width"], "height": out["height"], "fps": fps,
            "n_frames": int(out["nb_read_frames"]), "hdr_tonemapped": hdr}
    print(json.dumps(info))


if __name__ == "__main__":
    main()
