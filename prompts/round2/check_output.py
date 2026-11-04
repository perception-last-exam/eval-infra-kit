#!/usr/bin/env python3
"""Check a solver's output/ folder against the round-2 output format (format only, not accuracy).

  python check_output.py path/to/output [--video path/to/input.mp4] [--json]

Checks: required files; manifest fields, unique ids, parent/relation targets; camera.json has one valid
entry per video frame; render.mp4 matches the video's frame count, size and rate; particle arrays;
and that every manifest scene_path resolves in the scene file (USD via pxr, .blend via `blender`, .glb via trimesh)
with a bbox close to the declared bbox_m. Exit code 1 if any error.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REQUIRED = ("id", "name", "description", "parent", "scene_path", "type", "material", "mass_kg",
            "density_kg_m3", "bbox_m")

BLENDER_SCRIPT = r"""
import bpy, json, sys
from mathutils import Vector
out = sys.argv[sys.argv.index("--") + 1]
f0 = int(sys.argv[sys.argv.index("--") + 2])
bpy.context.scene.frame_set(f0)
dg = bpy.context.evaluated_depsgraph_get()
res = {}
def tree(o):
    yield o
    for c in o.children_recursive:
        yield c
for o in bpy.data.objects:
    if True:
        pts = []
        for x in tree(o):
            if x.type in {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD"}:
                e = x.evaluated_get(dg)
                try:
                    m = e.to_mesh()
                except Exception:
                    m = None
                if m is not None:
                    mw = e.matrix_world
                    pts += [mw @ v.co for v in m.vertices]
                    e.to_mesh_clear()
        if pts:
            res[o.name] = [[min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]]
        else:
            res[o.name] = None
res["__frames__"] = [bpy.context.scene.frame_start, bpy.context.scene.frame_end, bpy.context.scene.render.fps]
json.dump(res, open(out, "w"))
"""


class Report:
    def __init__(self):
        self.errors, self.warnings, self.info = [], [], {}

    def err(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)


def ffprobe(path):
    exe = os.environ.get("FFPROBE", "ffprobe")
    if not shutil.which(exe):
        return None
    out = subprocess.check_output([exe, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,r_frame_rate,nb_read_frames", "-of", "json", str(path)])
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {"w": s["width"], "h": s["height"], "fps": float(num) / float(den), "n": int(s["nb_read_frames"])}


def bbox_close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a[0] + a[1], b[0] + b[1]))


def resolve_scene(out, man, rep):
    scene = out / str(man.get("scene_file", ""))
    if not scene.is_file():
        rep.err(f"scene_file {man.get('scene_file')!r} not found")
        return
    ents = man.get("entities", [])
    ext = scene.suffix.lower()
    got = {}
    if ext in (".usd", ".usda", ".usdc", ".usdz"):
        try:
            from pxr import Usd, UsdGeom
        except ImportError:
            rep.warn("pxr not installed; USD prims not checked")
            return
        stage = Usd.Stage.Open(str(scene))
        t = float(man.get("video_frame_0_scene_frame", 0))
        cache = UsdGeom.BBoxCache(Usd.TimeCode(t), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
        rep.info["usd_upAxis"] = UsdGeom.GetStageUpAxis(stage)
        rep.info["usd_metersPerUnit"] = UsdGeom.GetStageMetersPerUnit(stage)
        mpu = UsdGeom.GetStageMetersPerUnit(stage) or 1.0
        n = man.get("n_frames")
        if n and (stage.GetStartTimeCode(), stage.GetEndTimeCode()) != (0, n - 1) and stage.HasAuthoredTimeCodeRange():
            rep.warn(f"USD time codes {stage.GetStartTimeCode()}..{stage.GetEndTimeCode()} are not 0..{n - 1}")
        for e in ents:
            p = stage.GetPrimAtPath(str(e.get("scene_path")))
            if not p or not p.IsValid():
                got[e.get("id")] = "missing"
                continue
            r = cache.ComputeWorldBound(p).ComputeAlignedRange()
            got[e.get("id")] = None if r.IsEmpty() else [[v * mpu for v in r.GetMin()], [v * mpu for v in r.GetMax()]]
    elif ext == ".blend":
        exe = os.environ.get("BLENDER", "blender")
        if not shutil.which(exe):
            rep.warn("blender not on PATH; .blend objects not checked")
            return
        with tempfile.TemporaryDirectory() as td:
            sp, op = Path(td) / "c.py", Path(td) / "o.json"
            sp.write_text(BLENDER_SCRIPT)
            f0 = int(man.get("video_frame_0_scene_frame", 1))
            subprocess.run([exe, "--background", "--factory-startup", str(scene), "--python", str(sp), "--",
                            str(op), str(f0)], capture_output=True, timeout=900)
            if not op.exists():
                rep.err(".blend could not be opened by blender")
                return
            objs = json.loads(op.read_text())
        bf = objs.pop("__frames__", None)
        rep.info["blend_frames"] = bf
        n = man.get("n_frames")
        if bf and n and (bf[1] - bf[0] + 1 != n or abs(bf[2] - float(man.get("fps", bf[2]))) > 0.01):
            rep.warn(f"Blender frame range {bf[0]}..{bf[1]} at {bf[2]} fps does not cover {n} frames at {man.get('fps')} fps")
        for e in ents:
            sp = e.get("scene_path")
            got[e.get("id")] = objs[sp] if sp in objs else "missing"
    elif ext in (".glb", ".gltf"):
        try:
            import trimesh
        except ImportError:
            rep.warn("trimesh not installed; glTF nodes not checked")
            return
        import numpy as np
        sc = trimesh.load(str(scene), force="scene")
        children = getattr(sc.graph.transforms, "children", {}) or {}
        geom_nodes = set(sc.graph.nodes_geometry)
        for e in ents:
            sp = e.get("scene_path")
            if sp not in sc.graph.nodes:
                got[e.get("id")] = "missing"
                continue
            todo, sub = [sp], []
            while todo:
                n = todo.pop()
                sub.append(n)
                todo += list(children.get(n, []))
            pts = []
            for n in sub:
                if n in geom_nodes:
                    T, g = sc.graph[n]
                    pts.append(trimesh.transformations.transform_points(sc.geometry[g].vertices, T))
            if pts:
                v = np.concatenate(pts)
                got[e.get("id")] = [v.min(0).tolist(), v.max(0).tolist()]
            else:
                got[e.get("id")] = None
    else:
        rep.err(f"scene_file extension {ext} is not OpenUSD, .blend or .glb")
        return
    miss = [k for k, v in got.items() if v == "missing"]
    empty = [k for k, v in got.items() if v is None]
    if miss:
        rep.err(f"{len(miss)} scene_path(s) do not resolve: {miss[:8]}")
    if empty:
        rep.err(f"{len(empty)} entities have no geometry: {empty[:8]}")
    bad = []
    for e in ents:
        g = got.get(e.get("id"))
        b = e.get("bbox_m") or {}
        if isinstance(g, list) and "min" in b and "max" in b:
            size = max(max(b["max"][i] - b["min"][i] for i in range(3)), 1e-3)
            if not bbox_close(g, [b["min"], b["max"]], max(0.002, 0.02 * size)):
                bad.append(e.get("id"))
    if bad:
        rep.warn(f"{len(bad)} entities' bbox_m differs from their geometry by > 2%: {bad[:8]}")
    rep.info["entities_resolved"] = sum(isinstance(v, list) for v in got.values())


def check(out, video=None):
    rep = Report()
    out = Path(out)
    for f in ("manifest.json", "camera.json", "render.mp4", "src/build.sh", "NOTES.md"):
        if not (out / f).exists():
            rep.err(f"missing {f}")
    man = {}
    try:
        man = json.loads((out / "manifest.json").read_text())
    except Exception as e:
        rep.err(f"manifest.json unreadable: {e}")
    ents = man.get("entities", []) if isinstance(man, dict) else []
    rep.info["entities"] = len(ents)
    rep.info["parts"] = sum(1 for e in ents if e.get("parent"))
    rep.info["types"] = sorted({str(e.get("type")) for e in ents})
    if man:
        for k in ("scene_file", "units", "origin", "n_frames", "fps"):
            if k not in man:
                rep.err(f"manifest lacks {k}")
        if "up_axis" not in man and "up" not in man:
            rep.err("manifest gives neither up_axis nor up")
        if "video_frame_0_scene_frame" not in man:
            rep.err("manifest lacks video_frame_0_scene_frame")
    ids = [e.get("id") for e in ents]
    if len(set(ids)) != len(ids):
        rep.err("entity ids are not unique")
    idset = set(ids)
    for e in ents:
        lack = [k for k in REQUIRED if k not in e]
        if lack:
            rep.err(f"entity {e.get('id')!r} lacks {lack}")
        if e.get("parent") and e["parent"] not in idset:
            rep.err(f"entity {e.get('id')!r} has unknown parent {e['parent']!r}")
        for r in e.get("relations") or []:
            if isinstance(r, dict) and r.get("target") not in idset:
                rep.warn(f"entity {e.get('id')!r} relation to unknown {r.get('target')!r}")
        if e.get("particles") and not (out / e["particles"]).exists():
            rep.err(f"entity {e.get('id')!r} particles file missing")
    vid = ffprobe(video) if video else None
    n = vid["n"] if vid else man.get("n_frames")
    rep.info["video"] = vid
    try:
        cam = json.loads((out / "camera.json").read_text())
        frames = cam.get("frames", [])
        rep.info["camera_frames"] = len(frames)
        if n and len(frames) != n:
            rep.err(f"camera.json has {len(frames)} frames, video has {n}")
        import numpy as np
        badK = badR = 0
        for f in frames:
            K = np.array(f.get("K"), float)
            T = np.array(f.get("cam_to_world"), float)
            if K.shape != (3, 3) or K[0, 0] <= 0:
                badK += 1
            if T.shape != (4, 4) or abs(np.linalg.det(T[:3, :3]) - 1) > 1e-3 or np.abs(T[:3, :3] @ T[:3, :3].T - np.eye(3)).max() > 1e-3:
                badR += 1
        if badK:
            rep.err(f"{badK} camera frames have a bad K")
        if badR:
            rep.err(f"{badR} camera frames have a non-rigid cam_to_world")
        if vid and (cam.get("width"), cam.get("height")) != (vid["w"], vid["h"]):
            rep.err(f"camera.json size {cam.get('width')}x{cam.get('height')} != video {vid['w']}x{vid['h']}")
        if frames:
            rep.info["fx_frame0"] = frames[0]["K"][0][0]
    except Exception as e:
        rep.err(f"camera.json unreadable: {e}")
    if (out / "render.mp4").exists() and vid:
        r = ffprobe(out / "render.mp4")
        rep.info["render"] = r
        if (r["n"], r["w"], r["h"]) != (vid["n"], vid["w"], vid["h"]) or abs(r["fps"] - vid["fps"]) > 0.01:
            rep.err(f"render.mp4 {r} does not match video {vid}")
    for p in sorted((out / "particles").glob("*.npz")) if (out / "particles").is_dir() else []:
        try:
            import numpy as np
            z = np.load(p)
            pos, vol = z["pos"], z["volume_m3"]
            if pos.ndim != 3 or pos.shape[2] != 3 or (n and pos.shape[0] != n) or vol.shape != (pos.shape[1],):
                rep.err(f"{p.name}: pos {pos.shape}, volume_m3 {vol.shape}")
            rep.info.setdefault("particles", {})[p.name] = list(pos.shape)
        except Exception as e:
            rep.err(f"{p.name} unreadable: {e}")
    if man:
        resolve_scene(out, man, rep)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--video")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rep = check(a.output, a.video)
    if a.json:
        print(json.dumps({"errors": rep.errors, "warnings": rep.warnings, "info": rep.info}, default=str))
    else:
        for m in rep.errors:
            print("ERROR  ", m)
        for m in rep.warnings:
            print("WARN   ", m)
        print("INFO   ", json.dumps(rep.info, default=str))
        print("OK" if not rep.errors else f"{len(rep.errors)} error(s)")
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
