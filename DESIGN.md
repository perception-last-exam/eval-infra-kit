# eval-infra-kit — design proposal (v0)

Status: draft for discussion, 2026-11-03. Nothing here is built yet.

## 0. What this kit is for

Two questions, answered quickly for any candidate scene:

1. **Is the scene actually hard?** Do GPT-6.1 Sol + Codex (max) and Opus 5.5 + Claude Code (max) both fail its
   measurements at Pass@2?
2. **Can we evaluate it reliably?** Given what the collector recorded, does our evaluator compute the same
   number every time, from the model's output, for every measurement?

Leaderboards, websites and public release are out of scope for v0. Speed of iteration on prompts and metrics is
the priority.

Scoring rule (fixed by the team): every metric is a single number with ground truth (GT), scored by relative
error. **Correct = relative error ≤ 10 %.** 5 % and 20 % may be reported as diagnostics. No IoU, Chamfer, SSIM or
other similarity scores.

Release bar (decided 2026-11-03): every query in the released dataset must be failed by *every* attempt of
*every* best model + best harness at max effort, so accuracy is exactly 0 per query. Round-2 data is exploratory
(creative, hard, deterministic to evaluate) and is not expected to meet this bar or to ship.

The scene/query record format is in `docs/data-format.md`.

---

## 1. Facts that shape the design

**The collected data (round 1 survey)**

| Collector | State | Usable for the harness |
|---|---|---|
| Di Wu (ex01_macbook, ex02_coffee) | GT JSON + Blender measure scripts + 5/10/20 % scorer + agent run | ex02 as-is; ex01 needs object mapping + abs-floor decision |
| lmgyuan / Yuan Yuan (ikea_bed_1) | blind input, 9 catalog dimensions, 2 frozen runs | yes, but GT is catalog-nominal and mapping was manual |
| Rui Sun (10 tasks) | videos + agent outputs, **no GT values** | needs GT pass |
| Yimin Wang (10 IKEA scenes) | videos + photos + Gaussian splats (no metric scale) | needs GT definitions + values |
| Yuan Yuan (3 with/without-measurement pairs) | videos only | needs GT written down |
| Cheng-Fu, Yu Zhou | raw videos only | needs everything |

Takeaway: the bottleneck is not running models, it is **getting measurements written down in a form a
machine can score.** The scene package format (section 3) is the most important artifact in the kit.

**The videos (55 files checked)**

- 40/55 are variable frame rate; 30 and 60 fps are mixed. "The frame at t = 12.3 s" is ambiguous.
- 52/55 are stored landscape (1920x1080) with a 90°/270° rotation flag, and iPhones also write a *timed*
  orientation track. Annotating and rendering in different orientations would silently break every 2D metric.
- No video carries focal length, zoom or lens metadata (only make/model; 17 Pro adds optical center).
  **There is no intrinsics GT unless we capture it separately.**
- Default iPhone capture is HDR (HLG) with stabilization on; stabilization crops and warps per frame.

**Feasibility probe on this server (Blender 4.5.14 LTS, headless)**

- Cycles on H100 (OptiX): one 1080x1920 object-index pass in 0.27 s; Workbench 1 s; EEVEE works headless.
- Analytic projection from the Blender camera (K, pose) matches Blender's own projection to 0.001 px, so 2D
  keypoint metrics can be computed exactly without image processing.
- USD export keeps object names as Xform prims and `mass_kg` as `userProperties:mass_kg` (not
  `physics:mass`). **Re-importing USD into Blender renames objects after their mesh data** ("box" -> "Cube"), so
  the evaluator must read USD with `pxr` directly, never via Blender's importer.
- No Docker on this machine; Apptainer 1.5.4 is available. Codex CLI 0.166 and Claude Code 2.1.318 are installed
  and both have headless modes with JSON event logs.

---

## 2. Design principles

1. **Score the scene, not the side files.** Numbers come from geometry and the camera in the submitted scene.
   `objects.json` is an index (names, descriptions) and a consistency check, never the source of a score. The
   only declared values that get scored are properties that have no geometry (mass, temperature, composition).
2. **The harness renders, not the model.** 2D metrics are computed from the submitted scene and camera by
   projection, or by a pinned render at the GT frame only. The model's `render.mp4` is for demos and
   self-checking. Reason: reading numbers off the model's video would need someone to find the keypoints in it
   (not deterministic), and that video can disagree with the scene.
3. **Shrink what the evaluator agent decides.** The coding agent used for evaluation does exactly one thing: it
   *binds* a measurement written in words ("tip of the tape measure's hook") to entities in the submission,
   using a small vocabulary of primitives. Loading, projecting, rendering, computing and comparing are fixed code.
4. **The binder never sees GT.** No values, and no GT click locations or masks. Otherwise it can, consciously or
   not, pick the interpretation that matches the answer. For 2D metrics this matters even more: a binder that sees
   the GT click can choose the 3D point that projects onto it, which makes the metric trivially satisfiable.
5. **Every frame reference is a frame index into one canonical, normalized video**, shared by the model, the
   annotators and the evaluator.
6. **Pin everything** (prompt version, container image, Blender, model, effort, tool policy) and hash it into the
   run ID, so results are comparable across iterations.

---

## 3. Scene package (what collectors produce)

```
scenes/<scene_id>/
  public/                    # the ONLY thing mounted into the inference sandbox
    input.mp4                # normalized: rotation applied, constant frame rate, SDR, metadata stripped
    task.json                # scope, n_frames, fps, width, height  (no answers; no coordinate frame)
  private/
    gt.json                  # measurements (schema below)
    annotations/             # click JSON, masks for 2D metrics, on normalized frames
    evidence/                # photos of tape / scale readings, notes on how each value was obtained
  source/                    # original MOV + provenance (never mounted)
```

`r2s video normalize` produces `input.mp4` from the original MOV (apply rotation, convert to constant frame rate at
native fps, tone-map HDR to SDR, strip metadata) plus `frames.json` (index -> source timestamp). Annotators click on
frames exported from that same file.

`gt.json` (values illustrative):

```json
{
  "scene_id": "yu_desk_001",
  "units": "m",
  "measurements": [
    {"id": "m01", "kind": "distance_3d",
     "a": "tip of the metal hook of the pink tape measure",
     "b": "front-right top corner of the white Meta battery pack",
     "value": 0.412, "unit": "m", "uncertainty": 0.002,
     "domain": "rigid_distance", "challenges": ["occlusion"],
     "robotics_link": "approach distance for pick-and-place", "evidence": ["evidence/m01.jpg"]},
    {"id": "m02", "kind": "px_distance", "frame_index": 412,
     "a": "tip of the metal hook of the pink tape measure", "b": "top-left corner of the teal box",
     "value": 233.4, "unit": "px", "uncertainty": 2.0,
     "gt_annotation": "annotations/m02.json"},
    {"id": "m03", "kind": "mask_area_px", "frame_index": 412,
     "object": "white Meta battery pack (visible part)",
     "value": 18450, "unit": "px", "uncertainty": 400, "gt_annotation": "annotations/m03_mask.png"}
  ]
}
```

`domain`, `challenges` and `robotics_link` are exactly the Round-2 spreadsheet columns, so the spreadsheet can be
generated from these files.

---

## 4. Inference kit

**Sandbox.** One Apptainer image: Blender 4.5.14 LTS on PATH, `usd-core`, ffmpeg, numpy, scipy, opencv, pillow,
trimesh. The agent CLI runs on the host, inside a fresh per-attempt workspace containing `public/`, an empty
`output/` and `OUTPUT_SPEC.md`; its shell tool runs inside the image. Network policy: the model API only. Web
search and fetch are disabled in both CLIs, and tool commands have no network. That blocks catalog lookups and
`pip install`. (Di Wu allowed web lookup and lmgyuan didn't; we need one rule, or two explicitly named tracks.)

**Runner.** `r2s infer --scene <id> --agent codex:gpt-6.1-sol:max --attempts 2 --prompt v1`
- Adapters: `codex exec --json -m ... -c model_reasoning_effort=...` and
  `claude -p --output-format stream-json --model ... --effort ...`.
- Records the full event trajectory, final message, wall time, token usage, exit status, output hashes, and the
  hashes of the prompt, `OUTPUT_SPEC.md` and the container image.
- Wall-clock cap per attempt (default 2 h), parallel across scenes, resumable.
- A cheap post-run validator: required files exist, `scene.blend` opens, the camera covers frames 1..N, USD loads
  in `pxr`, names are unique, closed meshes are actually closed.

**Prompt v1 (proposed; superseded for round 2 by `prompts/round2/`: three solver variants, a judge prompt, no sandbox).** Short and scene-specific. Everything format-related lives in a fixed, versioned
`OUTPUT_SPEC.md` that is identical for every scene. This follows the "minimal prompt" rule while still making the
output machine-checkable.

```text
Recreate the scene in public/input.mp4 as a metric 3D scene: {SCOPE}.
Model every object in scope as its own object, true to its real shape, size, material and placement;
anything not fixed to something else is a separate object. Also recover the camera: its intrinsics and
its pose at every frame of the video.
Choose your own world coordinate system; units are meters.
Write everything to output/ exactly as specified in OUTPUT_SPEC.md.
```

`OUTPUT_SPEC.md` requires:
- `scene.blend` (Blender 4.5): one object per physically separate item; unique snake_case names; solid objects as
  closed meshes; liquids as their own closed mesh; a `mass_kg` custom property on every object.
- One camera named `Camera`, pinhole, with frames 1..N matching video frames 1..N (N, fps and resolution come from
  `task.json`). Lens and sensor may be keyframed if the zoom changes.
- `scene.usda`, exported from the same scene.
- `objects.json`: `{name: {description, aabb_world_m: [xmin, ymin, zmin, xmax, ymax, zmax], mass_kg, material}}`.
- `render.mp4`: N frames at the video's fps and resolution. Any render engine and quality.
- `build.py` that regenerates `scene.blend` from scratch.

**Changes from the current draft prompt, and why:**
- **"Highest possible visual quality" dropped.** It competes with metric accuracy for the time budget. Demo-quality
  renders can be made later from the scene.
- **No separate rendered USD video.** There is no standard headless USD renderer. Exporting USD from the same scene
  avoids two independently authored scenes that disagree.
- **No coordinate frame given (decided 2026-11-04).** The agent defines its own coordinate system, so every score
  must be frame-invariant. Open: vertical measures ("height above the table") need an up direction, so either the
  agent declares one or the evaluator estimates it from the supporting surface.
- **Exact frame and resolution correspondence.** Without it, models render 10 frames at 960x540 and nothing lines up.
- **Bounding-box format pinned.** Includes a `description` per object, which is what makes binding by meaning
  possible later.

---

## 5. Evaluation kit

```
submission ──► normalize (pinned Blender + pxr, deterministic)
                 world-space meshes per object (.npz), camera K/pose per frame, custom props, USD↔blend check
           ──► bind (coding agent, K independent runs, GT hidden)
                 binding.json: each measurement → primitive expression over submission names, or "unbindable: why"
           ──► compute (fixed code)       ──► score (fixed code)         ──► report
                 numbers per measurement       rel. error, 5/10/20 % tiers      per scene × model × attempt
```

**Primitive vocabulary (v0).**
- Points: `bbox_corner(obj, ±x±y±z)`, `extreme_point(obj, dir)`, `centroid(obj)`, `face_center(obj, dir)`,
  `nearest_surface_point(obj, to=point)`, and `surface_point(obj, xyz)` as an escape hatch (snapped to the mesh,
  must be justified in text).
- 3D measures: `distance(p, q)`, `extent(obj, axis | object-derived axis)`, `gap(obj_a, obj_b)` (min mesh
  distance), `height_above(p, obj)`, `angle(p, q, r)`, `volume(obj)` (closed meshes only), `curve_length(obj)`
  (centerline length for cables and belts), and `declared(obj, "mass_kg")`.
- 2D measures at frame i, from the submitted camera: `px(p, i)` (a point projected through K and pose, with an
  occlusion flag from a ray cast); then `px_distance(p, q, i)`, `px_to_corners(p, i)`, `mask_area_px(obj, i)`
  (pinned object-index render: Cycles, 1 sample, no filter), and `focal_px(i)`.

Di Wu's `measure_ex0N.py` already implements several of these (laptop axes from a min-area rectangle, contact rim,
`bmesh.calc_volume`). Port them into this vocabulary.

**Binder agent.** Its inputs are the definitions with values stripped, `objects.json`, an object-ID-colored render
of the submission from six fixed views, the primitive reference, and read access to the normalized meshes. Its
output is `binding.json`. It runs K = 3 times: two runs with a small model at medium effort, one with a strong
model. This follows the "small model, medium effort" idea from the instructions doc.

**Reliability (answers question 2).** For each measurement, compare the K computed values. If their spread exceeds
a quarter of the tightest tier being reported (for example 1.25 % when 5 % is used), the measurement is flagged
`ambiguous_definition`. It is excluded from the verdict until its wording is fixed. A measurement every binder
marks `unbindable` (the object is missing) is a model failure; one only some binders mark is an evaluator failure.

**GT-quality gate.** If `uncertainty / value` is larger than a tier, that tier is disabled for that measurement.
Example: Di Wu's f05 has GT 10 mm with roughly 1 mm uncertainty, so only the 20 % tier is meaningful; the 5 % tier
would test the ruler, not the model. This keeps "only relative error" while removing tiers we can't actually
verify.

**Scoring.** Per measurement: relative error, pass/fail per tier, and Di Wu's 3/2/1/0 points (5/10/20 %). Per scene:
the fraction of measurements passed per tier, and "all passed" (Rui's overall-vs-process split).

**Verdict (answers question 1).** A query is *accepted* only if no attempt of any target model is within 10 %. A
single correct attempt rejects it.

---

## 6. 2D frame metrics — how they work and where they break

Computed by projecting the bound 3D point through the submitted camera at GT frame i. There are no keypoint
detectors and no image matching on the model's video.

**Pitfalls and mitigations**

1. **Scale blindness.** Scaling the whole scene and the camera path by s produces identical images. 2D metrics
   cannot test absolute metric size; they test shape, layout, camera pose and intrinsics consistency. Keep at least
   one 3D metric in every scene.
2. **Focal length vs. distance ambiguity.** With little depth variation, zooming in and moving back look almost
   the same (the dolly-zoom effect), so `focal_px` is ill-posed unless the scene has real depth range.
3. **No intrinsics GT exists today** (section 1). Either capture one calibration video (checkerboard) per
   phone × lens × zoom with stabilization off and lens auto-switching off, or capture with an ARKit logging app that
   records per-frame intrinsics. Otherwise drop intrinsics metrics.
4. **Pinhole vs. a real phone.** Lens distortion (strong on 0.5x), rolling shutter and stabilization warp leave
   pixel residuals even for a perfect reconstruction. Prefer GT points away from image edges, on sharp frames, and
   record capture settings.
5. **Relative error on pixel distances depends on position.** At 5 %, a keypoint 60 px from a corner gets a 3 px
   tolerance; one 1,000 px away gets 50 px. Prefer distances between two keypoints, or keep keypoints well inside
   the frame.
6. **Mask area is projected pixel area, not physical surface area.** A SAM mask on the input frame gives pixels;
   that is what the GT can support. Small masks make relative error unstable, so set a minimum area.
7. **Occlusion.** A model's point can be hidden behind another object in its own scene. Policy needed: still score
   the projection, or count it as a fail. Proposal: score it and report the flag.
8. **Billboard gaming.** A camera-facing plane textured with the video frames reproduces every frame. Bound points
   must lie on closed meshes with real extent, and 3D metrics in the same scene catch it.

---

## 7. Validating the evaluator itself

1. **Perturbation tests (synthetic, exact).** Build a scene in Blender with known geometry and camera, then create
   "submissions" by applying known edits: uniform scale ×1.07, move one object 3 cm, focal length +5 %, rotate the
   camera 1°. Check that every primitive and the scorer return the analytically expected errors. These become the
   unit tests.
2. **Cross-check against independent code.** Run the kit on Di Wu's ex02 submission. Its numbers must match
   `measure_ex02.py`.
3. **Binder agreement on real data** (section 5).

---

## 8. Open decisions

| Decision | Proposal |
|---|---|
| Acceptance unit: measurement or scene | **Decided:** per query. Accept only if all attempts of all top models are > 10 % off (accuracy exactly 0) |
| Tier used for acceptance | **Decided:** 10 %. GT uncertainty must be ≤ 2.5 % of the value, or the "failure" may be GT noise |
| Canonical scored format | `scene.blend` in pinned Blender, with the USD export checked to agree within ε |
| Tool policy | Offline, with Blender, numpy, scipy and opencv. No pretrained perception models (Depth Anything, SAM, VGGT) in v0 |
| Web access | Off for the main track |
| Blender version | 4.5.14 LTS (verified here; matches lmgyuan). Di Wu used 5.2.3, and files saved in 5.x may not open in 4.5 |
| Occluded 2D keypoints | Score the projection and report the occlusion flag |
| Relative error vs. absolute floor for tiny GT | GT-quality gate (section 5) instead of an absolute floor |

---

## 9. Build order (thin vertical slice first)

1. **M0.** `r2s video normalize`, the scene package schema, and a converter for Di Wu ex02. Normalizer and compute
   library that reproduce `measure_ex02.py` on the existing ex02 submission. Perturbation tests.
2. **M1.** Apptainer image and `r2s infer` with Codex and Claude adapters. Pass@2 on ex02 plus one new desk scene
   that has both 3D and 2D measurements.
3. **M2.** Binder prompt with K-run agreement. 2D primitives (projection, object-index mask area) on the desk scene.
4. **M3.** Per-scene report and acceptance verdict, plus a one-page "how to package a scene" guide for collectors
   (or Yuan's annotation site writes `gt.json` directly).

Proposed layout:

```
eval-infra-kit/
  DESIGN.md
  schemas/            task, gt, objects, binding (JSON Schema)
  prompts/
    inference/v1/     task_prompt.md, OUTPUT_SPEC.md
    eval/v1/          binder.md, primitives.md
  sandbox/            r2s.def (Apptainer), pinned requirements
  r2s/                video.py, infer.py, normalize_blend.py, normalize_usd.py,
                      primitives.py, bind.py, score.py, report.py
  tests/              synthetic perturbation tests
  scenes/             (git-ignored or LFS) example packages
```
