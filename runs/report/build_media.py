#!/usr/bin/env python3
"""Make report media: per-scene comparison video (input | each variant render), per-scene still grids, judge/solver images."""
import json, os, shutil, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

KIT = Path(__file__).resolve().parents[2]
R = Path(os.environ.get("R2S_RUNS", KIT.parent / "round2-runs"))
OUT = R / "_report" / "media"
FF = os.environ.get("FFMPEG") or (str(R / "_bin/ffmpeg") if (R / "_bin/ffmpeg").exists() else shutil.which("ffmpeg") or "ffmpeg")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LABEL = {"input": "Input video", "blender": "Blender", "openusd": "OpenUSD", "any": "Any tool"}
SCENES = {"demo-yuzhou-s01": {"frames": [0, 412, 700], "n": 887}, "demo-diwu-s01": {"frames": [0, 240, 482], "n": 483}}
VARIANTS = ["blender", "openusd", "any"]
W, H = 360, 640
manifest = {}


def render_path(scene, v):
    p = R / scene / v / "solver/output/render.mp4"
    return p if p.exists() else None


def comparison_video(scene):
    dst = OUT / f"{scene}-compare.mp4"
    srcs = [("input", R / "_videos" / f"{scene}.mp4")] + [(v, render_path(scene, v)) for v in VARIANTS]
    args, filt, labels = [FF, "-y", "-v", "error"], [], []
    k = 0
    for i, (name, p) in enumerate(srcs):
        txt = LABEL[name] if p else f"{LABEL[name]} (rendering)"
        dt = f"drawtext=fontfile={FONT}:text='{txt}':x=12:y=12:fontsize=24:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8"
        if p:
            args += ["-i", str(p)]
            filt.append(f"[{k}:v]fps=30,scale={W}:{H},setsar=1,{dt}[p{i}]")
            k += 1
        else:
            filt.append(f"color=c=0x30343c:s={W}x{H}:r=30:d={SCENES[scene]['n']/30:.3f},{dt}[p{i}]")
        labels.append(f"[p{i}]")
    filt.append("".join(labels) + f"hstack=inputs={len(labels)}:shortest=1[v]")
    args += ["-filter_complex", ";".join(filt), "-map", "[v]", "-frames:v", str(SCENES[scene]["n"]),
             "-c:v", "libx264", "-crf", "28", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(dst)]
    subprocess.run(args, check=True)
    # poster = middle frame
    subprocess.run([FF, "-y", "-v", "error", "-ss", f"{SCENES[scene]['frames'][1]/30:.3f}", "-i", str(dst), "-frames:v", "1", "-q:v", "4", str(OUT / f"{scene}-compare.jpg")], check=True)
    return dst.name


def grab(video, frame, dst):
    subprocess.run([FF, "-y", "-v", "error", "-i", str(video), "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", str(dst)], check=True)
    return Image.open(dst).convert("RGB")


def still_grid(scene):
    """rows: input + variants, cols: chosen frames; cell 270x480 with labels."""
    cw, ch, pad, top = 270, 480, 6, 34
    rows = [("input", R / "_videos" / f"{scene}.mp4")] + [(v, render_path(scene, v)) for v in VARIANTS]
    frames = SCENES[scene]["frames"]
    font = ImageFont.truetype(FONT, 20)
    small = ImageFont.truetype(FONT, 18)
    gw = pad + len(rows) * (cw + pad)
    gh = top + len(frames) * (ch + pad) + pad
    # layout: columns = sources (input, blender, openusd, any) so it reads like the video; rows = frames
    img = Image.new("RGB", (gw, gh), (245, 246, 248))
    d = ImageDraw.Draw(img)
    tmp = OUT / "_tmp.png"
    for c, (name, p) in enumerate(rows):
        x = pad + c * (cw + pad)
        d.text((x + 4, 8), LABEL[name], fill=(20, 24, 32), font=font)
        for r, fr in enumerate(frames):
            y = top + r * (ch + pad)
            if p:
                cell = grab(p, fr, tmp).resize((cw, ch), Image.LANCZOS)
                img.paste(cell, (x, y))
            else:
                d.rectangle([x, y, x + cw, y + ch], fill=(48, 52, 60))
                d.text((x + 12, y + ch // 2 - 10), "still rendering", fill=(235, 235, 235), font=small)
            if c == 0:
                d.text((x + 8, y + 8), f"frame {fr}", fill=(255, 255, 255), font=small, stroke_width=2, stroke_fill=(0, 0, 0))
    tmp.unlink(missing_ok=True)
    dst = OUT / f"{scene}-frames.jpg"
    img.save(dst, quality=84)
    return dst.name


def shrink(src, dst, maxw=1000):
    im = Image.open(src).convert("RGB")
    if im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.LANCZOS)
    im.save(dst, quality=82)
    return dst.name


def judge_images(scene, v):
    out = []
    jd = R / scene / v / "judge"
    if not jd.is_dir():
        return out
    for q in sorted(jd.iterdir()):
        if not (q / "result.json").exists():
            continue
        imgs = sorted(p for p in q.rglob("*.png") if "submission" not in p.parts and ".measure_env" not in p.parts and "site-packages" not in str(p))
        for p in imgs[:3]:
            name = f"{scene}-{v}-judge-{q.name}-{p.stem}.jpg"
            out.append({"judge": q.name, "file": shrink(p, OUT / name, 900), "src": str(p.relative_to(R))})
    return out


def solver_images(scene, v):
    w = R / scene / v / "solver/work"
    picks = []
    for pat in ["server_overlay_*.png", "previews_final/*.png", "previews/*.png", "fit_*.jpg", "grounds_views.jpg", "marks.jpg"]:
        picks += sorted(w.glob(pat))
    seen, out = set(), []
    for p in picks:
        if p in seen:
            continue
        seen.add(p)
        if len(out) >= 4:
            break
        name = f"{scene}-{v}-solver-{p.parent.name}-{p.stem}.jpg"
        out.append({"file": shrink(p, OUT / name, 700), "src": str(p.relative_to(R))})
    return out


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for scene in SCENES:
        manifest[scene] = {"video": comparison_video(scene), "poster": f"{scene}-compare.jpg", "grid": still_grid(scene),
                           "frames": SCENES[scene]["frames"], "runs": {}}
        for v in VARIANTS:
            manifest[scene]["runs"][v] = {"render": bool(render_path(scene, v)), "judge_images": judge_images(scene, v), "solver_images": solver_images(scene, v)}
        print(scene, "ok", flush=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
