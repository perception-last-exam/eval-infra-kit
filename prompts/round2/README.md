# Round 2 inference prompts

Two kinds of prompt:
- **Solver:** the model rebuilds the scene from the video.
- **Judge:** a coding agent reads one number off that rebuilt scene for one query.

The judge's number is compared with the collector's ground truth (GT). It is correct if it is within 10% of the GT value.

```
input.mp4 + {RECONSTRUCTION_BOUND} ──► solver (Blender | OpenUSD | any) ──► output/
                                         scene file, manifest.json, camera.json, render.mp4, particles/, src/, NOTES.md
output/ (as submission/) + one query's wording ──► judge ──► result.json: value in the query's unit
value vs gt_value ──► relative error ≤ 10 % = correct
```

## Files

| File | What it is |
|---|---|
| `solver-blender.md`, `solver-openusd.md`, `solver-any.md` | The three solver prompts. They differ only in the scene format and the details tied to it. |
| `judge.md`, `judge-som.md` | The judge prompt without and with a set-of-mark image. Both are lenient about parts that were not modelled |
| `alternatives/` | The strict versions of both judges, for the one decision still open (see "Decisions" below) |
| `solver.template.md`, `judge.template.md` | Sources. Edit these, then run `python prompts.py build` |
| `prompts.py` | `build` regenerates the files above; `solver` and `judge` print a prompt filled in for one scene or query |
| `normalize_video.py` | Turns the phone video into the `input.mp4` everyone uses |
| `check_output.py` | Checks a solver's `output/` against the format, not its accuracy: files, manifest, camera frames, the render's frame count, and whether each `scene_path` resolves with a matching bbox |

## Variables

**Solver:** the only variable is `{RECONSTRUCTION_BOUND}`.
- It is filled from the scene's `scope` field, shown as "Reconstruction scope" in the registry, e.g. "the desk top and every object on it".
- The paths are fixed: `input.mp4` and `output/` in the run folder.

```
python prompts.py solver --variant blender --scene path/to/scene.json > prompt.md
python prompts.py solver --variant openusd --bound "the vase" --option up=vector > prompt.md
```

**Judge:** one measurement per run, in two versions.

| File | Inputs |
|---|---|
| `judge.md` | `{WHAT_TO_MEASURE}` only |
| `judge-som.md` | `{WHAT_TO_MEASURE}` plus a set-of-mark image, `som.png`, next to `submission/` |

- **`{WHAT_TO_MEASURE}`:** one phrase saying exactly what to measure, with its unit and, if needed, the frame or moment.
  - Example: "the straight-line distance in cm from the tip of the pink tape measure's metal hook to the front-right top corner of the white battery pack".
  - It comes from the query's `what_to_measure` field. For older records without it, the phrase is composed from `definition`, `point_a`…`point_c`, `object`, `moment`, `frame_index` and `gt_unit`.
- **`som.png`:** a frame or photo with numbered marks that the phrase can refer to ("the gap between marks 1 and 2").
  - Save it as `som.png` in the judge's folder. With Codex, also attach it with `-i som.png`; Claude Code opens it from the folder.
  - The SoM version tells the judge to use it only to identify things, never to measure on it.
  - For pixel queries, don't put marks exactly on the GT points; the judge could match the marks instead of measuring.

The judge never sees `gt_value`, `gt_uncertainty`, `how_measured`, `evidence`, `why_hard` or the video. It reports `value` and `unit` in `result.json`, and the scorer converts units (mm/cm/m, mL/L, g/kg).

```
python prompts.py judge --scene path/to/scene.json --query yuzhou-s01-q3 > judge-prompt.md          # judge.md
python prompts.py judge --scene path/to/scene.json --query yuzhou-s01-q3 --som > judge-prompt.md    # judge-som.md
python prompts.py judge --what "the gap in mm between the plug face (mark 1) and the socket face (mark 2)" --som
```
A query with a `som_image` field gets the SoM version automatically.

## Decisions

**Decided on 2026-11-03: use the defaults.**
- **Up direction:** origin and horizontal orientation are free, but one world axis must point up.
- **Tools:** open. Anything is allowed, including SfM and pretrained vision models.
- **Internet:** only for installs and docs, never for looking up the scene's products.

The other versions stay switchable for later tracks, for example `--option up=vector`, `--option tools=graphics` and `--option web=lookup`.

**Still open, and being tested both ways: what the judge does when a named part was not modelled.**

| Version | File | A named part (hook, lid, plug) that was not modelled as its own entity |
|---|---|---|
| Lenient (default) | `judge.md`, `judge-som.md` | Located on the object's geometry; status `approximate` |
| Strict | `alternatives/judge.parts-strict.md`, `alternatives/judge-som.parts-strict.md` | Reported as `missing`, which counts as wrong |

In both versions:
- An object the reconstruction does not contain at all is `missing`, and that counts as wrong.
- Points that are features of an object's shape, such as a corner, an edge or the top face, are always located on its geometry.

Fixed choices, not offered as options:
- **Units:** meters.
- **Mass:** an entity's `mass_kg` includes its parts but not its contents (a full bottle = bottle + liquid).
- **Frame numbering:** frames are 0-based in `input.mp4`, everywhere. `camera.json` entry *i* is video frame *i*. Blender frame *i + 1* is video frame *i*, and USD time code *i* is video frame *i*.
- **Camera:** OpenCV axes (+z forward, +x right, +y down); pixel (0, 0) is the top-left corner of the image.
- **Where numbers come from:** the judge measures geometry. It reads declared values only for mass, density, material, composition and temperature.
- **Judge isolation:** the judge never sees the video or the GT.

## Running it (no sandbox this round)

1. **Make `input.mp4`.**
   - Run `python normalize_video.py IMG_1234.MOV input.mp4`.
   - It applies the rotation flag, sets a constant frame rate, tone-maps HDR to SDR, and drops audio, GPS and all other metadata.
   - Pick every query's `frame_index` on this file, not on the MOV.
   - It needs ffmpeg 5.1 or newer, built with zscale; static builds and Homebrew both have it.
2. **Make one fresh folder per attempt**, containing only `input.mp4`. Keep `scene.json` and the GT anywhere the agent won't look.
3. **Run the solver from inside that folder.**
   - Codex:
     ```
     codex exec --json --skip-git-repo-check -s workspace-write -c sandbox_workspace_write.network_access=true \
       -m gpt-6.1-sol -c model_reasoning_effort=max -o ../solver.last.md "$(cat ../prompt.md)" > ../solver.jsonl
     ```
     The workspace-write sandbox only lets it write inside the folder, and turning network on allows `pip install`.
   - Claude Code:
     ```
     claude -p "$(cat ../prompt.md)" --model claude-opus-5-5 --effort max --disallowedTools WebSearch WebFetch \
       --permission-mode bypassPermissions --output-format stream-json --verbose > ../solver.jsonl
     ```
     `bypassPermissions` runs every command without asking. Use it only on a machine or account with nothing you would mind it touching.
   - Keep the `.jsonl` trajectory next to the attempt.
   - Check the format with `python check_output.py output --video input.mp4`. This needs `blender` for `.blend` and `usd-core` for USD.
4. **Run the judge for each query.**
   - Make a fresh folder containing only `submission/` (a copy of the solver's `output/`). Run `judge.md` from there with the same commands.
   - For the SoM version, also put the image in that folder as `som.png`, run `judge-som.md`, and add `-i som.png` for Codex.
   - It writes `result.json` and ends with `VALUE: <number> <unit>`.
   - Running the judge 3 times and taking the median is safer. If the three runs disagree by more than 2.5 %, the query's wording is ambiguous: reword it.
5. **Score.**
   - Relative error is `|value − gt_value| / |gt_value|`. It is correct if ≤ 0.10; 5 % and 20 % can also be reported.
   - A result marked `missing` or `invalid` counts as wrong.
   - Record each result in the scene's `results` list with `prompt_version` set to e.g. `r2-blender-v1`.
