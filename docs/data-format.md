# Scene & query format (draft v0.1, for round 2)

One record per **scene** and one per **query** (a single measurement with a number). In JSON a scene holds its
queries. In a spreadsheet or website they become two tables joined by `scene_id`, one row per scene and one row per
query. The second table is exactly the existing "Second Round Data Collection" sheet, with more columns.

**Flexible by design.** Every field below is a suggestion except the core query fields. Custom values (a new kind,
domain, unit or challenge) are fine. Any extra field a collector adds, on a scene or a query, is kept, shown on the
registry and exported. Any folder layout under your own folder works.

**Core query fields** (the registry flags these in red when missing):
- `metric_domain`: one answer, from the list or your own
- `challenges`: one or more, from the list and/or your own
- `robotics_link`: a sentence on the connection to a real-world application or robotics failure mode
- `definition`, `gt_value` and `gt_unit`: what is scored

Registry: https://claude.ai/artifact/D1iSfGBnq3Zr8h8RXBYUfx (source in `registry/index.html`).
Inference prompts (solver and judge) that consume these records: `prompts/round2/` (README there).

Correctness rule used everywhere: a model answer is **correct if its relative error is ≤ 10 %**. A query is
**accepted** only if *every* attempt of *every* top model + harness at max effort is incorrect (accuracy exactly 0).

## Scene fields

No coordinate frame is given: the agent defines its own coordinate system (no origin, axis or capture fields).


| Field | Type | Filled by | Notes |
|---|---|---|---|
| `scene_id` | string | collector | `<collector>-s<NN>`, e.g. `yuzhou-s03`; also the Drive folder name |
| `collector` | string | collector | |
| `status` | enum | collector / kit | `draft` → `ready` (GT complete) → `tested` (models run) → `accepted` / `rejected` |
| `environment` | enum | collector | `home` `office` `kitchen` `outdoor` `lab` `store` `other` |
| `summary` | text | collector | What is in the scene and what happens in it (dynamic scenes: the action) |
| `scope` | text | collector | **Reconstruction scope**: what the model must rebuild, e.g. "the desk and everything on top of it". Goes into the prompt |
| `input_video` | path | collector | Original file as exported from the phone, in `input/` |
| `device` | text | kit (auto) | Phone make/model, read from metadata |
| `resolution`, `fps`, `duration_s`, `n_frames` | numbers | kit (auto) | Read from the normalized video |
| `calibration_video` | path | collector (optional) | Checkerboard clip with the same phone, lens and settings; enables intrinsics GT |
| `evidence_dir` | path | collector | Photos or video of measurement readings |

## Query fields

| Field | Type | Notes |
|---|---|---|
| `query_id` | string | `<scene_id>-q<N>` |
| `metric_domain` | enum (single) | `rigid_distance` `deformable_distance` `liquid_volume` `object_weight` `robot_state` `temperature` `material_composition` `image_frame` `camera` `physical_property` (exploratory: stiffness, friction, …) |
| `kind` | enum | How the number is computed from the model's scene (see below) |
| `point_a`, `point_b`, `point_c` | text | Endpoints in words, specific enough that a stranger could put a finger on them. Unused ones are blank |
| `object` | text | For object-level kinds (volume, weight, pixel area, …) |
| `definition` | text | One sentence saying exactly what the number is, e.g. "straight-line distance from A to B" |
| `what_to_measure` | text | **What the judge sees.** One phrase that says exactly what to measure, with its unit and, if needed, the frame or moment, e.g. "the straight-line distance in cm from the tip of the pink tape measure's metal hook to the front-right top corner of the white battery pack". If blank, the kit composes it from `definition`, the points, `object`, `moment`, `frame_index` and `gt_unit` |
| `som_image` | path (optional) | A set-of-mark image (a frame or photo with numbered marks) the phrase may refer to ("the gap between marks 1 and 2"), in `evidence/`. Shown to the judge only to identify things. For pixel queries, don't put marks exactly on the GT points: the judge could match them instead of measuring |
| `moment` | text | Dynamic scenes: which state ("start", "end", "after the 2nd fold"). Image-frame kinds: `frame_index` instead |
| `frame_index` | int | `image_frame` queries only: 0-based frame of the normalized `input.mp4` (made with `prompts/round2/normalize_video.py`), never of the original MOV |
| `gt_value` | number | |
| `gt_unit` | enum | `mm` `cm` `m` `mL` `g` `kg` `degC` `deg` `px` `percent` |
| `gt_uncertainty` | number | ± in the same unit. **Must be ≤ 2.5 % of `gt_value`**; otherwise GT noise, not the model, decides pass/fail at 10 % |
| `how_measured` | text | Instrument and procedure ("steel tape, hook on A, read at B, 3 readings: 41.1 / 41.2 / 41.2 cm") |
| `evidence` | paths | Files in `evidence_dir`, named `<query_id>_*.jpg` |
| `challenges` | enum (multi) | `occlusion` `clutter_stacking` `fast_or_shaky_camera` `frame_format` `low_light` `zoom_or_lens` `degraded_optics` `reflection_mirror` `transparency` `visual_illusion` `dynamic_scene` `imagined_state` `long_context` `needle_in_haystack` `physical_gap` `fit_affordance` `deformable` `small_or_thin` `irregular_shape` `color` `voice` `other`, plus your own (the Round 2 sign-up sheet's Challenges tab describes each) |
| `robotics_link` | text | Real-world task or robot failure mode this number matters for |
| `why_hard` | text | Why you expect top models to miss by more than 10 % |
| `pilot` | list (optional) | Quick self-tests: `[{model, harness, effort, predicted, rel_error}]` |

**`kind` → how the evaluator computes it from the submitted scene**

| kind | Computed as | Domains |
|---|---|---|
| `distance` | straight line between two surface points | rigid, deformable, robot_state |
| `extent` | object size along a stated direction | rigid, deformable |
| `gap` | closest surface-to-surface distance between two objects | rigid (physical gaps, fit) |
| `height_above` | vertical distance from a point to a surface | rigid, deformable |
| `angle` | angle at B between A and C | robot_state, rigid |
| `path_length` | length along a flexible object (cable, belt, towel edge) | deformable |
| `volume` | enclosed volume of a closed mesh | liquid_volume |
| `mass` | the object's `mass_kg` property | object_weight |
| `declared` | a named property (temperature, composition fraction) | temperature, material_composition |
| `px_distance` | pixel distance between two projected points at `frame_index` | image_frame |
| `px_area` | visible pixel area of an object at `frame_index` (needs a GT mask) | image_frame |
| `focal_length` | focal length in px at `frame_index` (needs `calibration_video`) | camera |

Also on queries: `notes` (free text) and `results` (filled by the kit, never by collectors:
`[{model, harness, effort, attempt, prompt_version, predicted, run_id}]`). On scenes: `notes`, and `schema`
(`"r2s-scene/0.1"`) plus `demo: true` for demo records. Challenge list also includes `irregular_shape`.

## Drive folder convention

Shared root: `Second-Round-Data-Collection` (https://drive.google.com/drive/folders/1IOUYD7-bWOdYgqBpK6qQsautl8f_y29H).
Each folder at the top is one person, named with their name; the registry uses that name as the collector. Files placed
directly at the top (not inside a person's folder) are ignored. A suggested layout inside your folder, not a requirement:

```
Second-Round-Data-Collection/<your name>/<scene_id>/
  input/          original video, untouched (no screen recordings, no files re-shared through chat apps)
  evidence/       photos or video of each reading, e.g. <query_id>_*.jpg
  calibration/    optional checkerboard clip
  thumbnail.jpg   optional; otherwise the kit makes one
  scene.json      from the registry's builder, or written by hand
```

The sync walks every folder under the root. A folder with videos but no `scene.json` still shows up in the
registry's "On Google Drive" table.

## Example

```json
{
  "scene_id": "yuzhou-s01",
  "collector": "Yu Zhou",
  "status": "ready",
  "environment": "office",
  "summary": "White desk with a tape measure, a battery pack and two partly opened boxes.",
  "scope": "the desk top and every object on it",
  "input_video": "input/IMG_1601.MOV",
  "calibration_video": null,
  "evidence_dir": "evidence/",
  "queries": [
    {
      "query_id": "yuzhou-s01-q1",
      "metric_domain": "rigid_distance",
      "kind": "distance",
      "point_a": "tip of the metal hook of the pink tape measure",
      "point_b": "front-right top corner of the white battery pack",
      "definition": "straight-line distance from A to B",
      "gt_value": 41.2, "gt_unit": "cm", "gt_uncertainty": 0.2,
      "how_measured": "steel tape from A to B, 3 readings 41.1/41.2/41.2 cm",
      "evidence": ["evidence/yuzhou-s01-q1_tape.jpg"],
      "challenges": ["small_or_thin"],
      "robotics_link": "approach distance when picking up the tape measure",
      "why_hard": "no reference object of known size is fully visible"
    }
  ]
}
```

Values in the example are illustrative.
