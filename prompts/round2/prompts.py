#!/usr/bin/env python3
"""Build and fill the round-2 prompts.

  python prompts.py build
      Regenerate the readable prompt files from the two templates:
        solver-blender.md, solver-openusd.md, solver-any.md, judge.md      (default choices)
        alternatives/judge.parts-strict.md        (the one decision still open; others via --option)

  python prompts.py solver --variant blender --scene path/to/scene.json [--bound "..."] [--option up=vector ...]
      Print the solver prompt for one scene. {RECONSTRUCTION_BOUND} is filled from the scene's
      `scope` field ("Reconstruction scope" in the registry), or from --bound.

  python prompts.py judge --scene path/to/scene.json --query <query_id> [--som] [--option parts=strict]
  python prompts.py judge --what "the gap in mm between ..." [--som]
      Print the judge prompt for one measurement. The judge sees only the phrase (the query's
      `what_to_measure`, or one composed from definition/points/object/moment/frame/unit) and the
      optional set-of-mark image; never gt_value, gt_uncertainty, how_measured, evidence or why_hard.

Template syntax (solver.template.md, judge.template.md):
  ::: blender openusd        block kept only for the listed variants; closed by a line ':::'
  ::: up=vector              block kept only when that option is chosen (tokens can be mixed)
  {{blender: A || openusd: B || any: C}}   inline choice by variant
  {{up=axis: A || up=vector: B}}           inline choice by option
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VARIANTS = ("blender", "openusd", "any")
# option -> (default, alternative). `build` writes the alternative file only for decisions still open;
# decided ones stay switchable with --option.
OPTIONS = {
    "up": ("axis", "vector"),        # decided 2026-11-03: axis (one world axis points up; origin/orientation free)
    "tools": ("open", "graphics"),   # decided 2026-11-03: open (any software incl. SfM and pretrained vision)
    "web": ("off", "lookup"),        # decided 2026-11-03: off (internet for installs and docs only)
    "parts": ("lenient", "strict"),  # OPEN, tested both ways: unmodelled part -> locate on object | -> missing
    "som": ("no", "yes"),            # two judge versions, both kept: without / with a set-of-mark image
}
SOLVER_OPTIONS = ("up", "tools", "web")
JUDGE_OPTIONS = ("parts",)
JUDGE_VERSIONS = {"judge": {"som": "no"}, "judge-som": {"som": "yes"}}
OPEN_DECISIONS = ("parts",)
DEFAULTS = {k: v[0] for k, v in OPTIONS.items()}
INLINE = re.compile(r"\{\{(.+?)\}\}", re.S)

# The judge gets one phrase, {WHAT_TO_MEASURE}. It comes from the query's `what_to_measure` field; for older
# records without it, it is composed from definition / point_a..c / object / moment / frame_index / gt_unit.
# Two versions: judge.md (no image) and judge-som.md (a set-of-mark image the runner saves as som.png).


def _matches(token, variant, opts):
    if "=" in token:
        k, v = token.split("=", 1)
        if k not in OPTIONS or v not in OPTIONS[k]:
            raise SystemExit(f"unknown option in template: {token}")
        return opts[k] == v
    if token not in VARIANTS:
        raise SystemExit(f"unknown variant in template: {token}")
    return token == variant


def render(template, variant=None, opts=None):
    opts = {**DEFAULTS, **(opts or {})}
    out, keep = [], True
    for line in template.splitlines():
        s = line.strip()
        if s.startswith(":::"):
            tokens = s[3:].split()
            vs = [t for t in tokens if "=" not in t]
            os_ = [t for t in tokens if "=" in t]
            keep = (not vs or any(_matches(t, variant, opts) for t in vs)) and all(
                _matches(t, variant, opts) for t in os_)
            continue
        if keep:
            out.append(line)

    def pick(m):
        for part in m.group(1).split("||"):
            key, _, text = part.partition(":")
            if _matches(key.strip(), variant, opts):
                return text.strip()
        return ""

    text = INLINE.sub(pick, "\n".join(out))
    if "{{" in text or "}}" in text:
        raise SystemExit("unbalanced {{ }} in template")
    return re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"


def solver_text(variant, opts=None):
    return render((HERE / "solver.template.md").read_text(), variant, opts)


def judge_text(opts=None):
    return render((HERE / "judge.template.md").read_text(), None, opts)


def build():
    alt = HERE / "alternatives"
    alt.mkdir(exist_ok=True)
    written = []
    for v in VARIANTS:
        (HERE / f"solver-{v}.md").write_text(solver_text(v))
        written.append(f"solver-{v}.md")
        for k in (k for k in SOLVER_OPTIONS if k in OPEN_DECISIONS):
            name = f"solver-{v}.{k}-{OPTIONS[k][1]}.md"
            (alt / name).write_text(solver_text(v, {k: OPTIONS[k][1]}))
            written.append(f"alternatives/{name}")
    for base, vopts in JUDGE_VERSIONS.items():
        (HERE / f"{base}.md").write_text(judge_text(vopts))
        written.append(f"{base}.md")
        for k in (k for k in JUDGE_OPTIONS if k in OPEN_DECISIONS):
            name = f"{base}.{k}-{OPTIONS[k][1]}.md"
            (alt / name).write_text(judge_text({**vopts, k: OPTIONS[k][1]}))
            written.append(f"alternatives/{name}")
    print("\n".join(written))


def parse_options(pairs, allowed):
    opts = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        if k not in allowed or v not in OPTIONS[k]:
            raise SystemExit(f"bad --option {p!r}; allowed: " +
                             ", ".join(f"{a}={'|'.join(OPTIONS[a])}" for a in allowed))
        opts[k] = v
    return opts


def load_scene(path):
    return json.loads(Path(path).read_text())


def fill_solver(variant, scene_path=None, bound=None, opts=None):
    if bound is None:
        if not scene_path:
            raise SystemExit("give --scene or --bound")
        bound = (load_scene(scene_path).get("scope") or "").strip()
    if not bound:
        raise SystemExit("the scene has no `scope` (Reconstruction scope); give --bound")
    return solver_text(variant, opts).replace("{RECONSTRUCTION_BOUND}", bound)


def compose_what(q):
    """One phrase from the structured query fields (for records without `what_to_measure`)."""
    def f(k):
        v = q.get(k)
        return "" if v is None else str(v).strip()
    parts = [f("definition").rstrip(".").replace("of the normalized video", "of the video (frames count from 0)")]
    for k, label in (("point_a", "A"), ("point_b", "B"), ("point_c", "C")):
        if f(k):
            parts.append(f"{label} is the {f(k)}" if not f(k).lower().startswith(("the ", "a ", "an ")) else f"{label} is {f(k)}")
    if f("object"):
        parts.append(f"The object is the {f('object')}" if not f("object").lower().startswith("the ") else f"The object is {f('object')}")
    if f("moment"):
        parts.append(f"Measure it at this moment: {f('moment')}")
    if f("frame_index") and f"frame {f('frame_index')}" not in f("definition"):
        parts.append(f"Measure it in frame {f('frame_index')} of the video (frames count from 0)")
    if f("gt_unit"):
        parts.append(f"Give the value in {f('gt_unit')}")
    text = ". ".join(p for p in parts if p) + "."
    return text[0].upper() + text[1:]


def fill_judge(scene_path=None, query_id=None, opts=None, what=None, som=None):
    if what is None:
        if not (scene_path and query_id):
            raise SystemExit("give --what, or --scene and --query")
        scene = load_scene(scene_path)
        q = next((q for q in scene.get("queries", []) if q.get("query_id") == query_id), None)
        if q is None:
            ids = [q.get("query_id") for q in scene.get("queries", [])]
            raise SystemExit(f"query {query_id!r} not in scene; have {ids}")
        what = (q.get("what_to_measure") or "").strip() or compose_what(q)
        if som is None:
            som = bool(q.get("som_image"))
    if not what.strip():
        raise SystemExit("empty measurement description")
    values = {"WHAT_TO_MEASURE": what.strip()}
    lines = []
    for line in judge_text({**(opts or {}), "som": "yes" if som else "no"}).splitlines():
        used = re.findall(r"\{([A-Z_]+)\}", line)
        if any(u in values and not values[u] for u in used):
            continue
        for u in used:
            if u in values:
                line = line.replace("{" + u + "}", values[u])
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    s = sub.add_parser("solver")
    s.add_argument("--variant", choices=VARIANTS, required=True)
    s.add_argument("--scene")
    s.add_argument("--bound")
    s.add_argument("--option", action="append", metavar="KEY=VALUE")
    j = sub.add_parser("judge")
    j.add_argument("--scene")
    j.add_argument("--query")
    j.add_argument("--what", help="the measurement phrase (instead of --scene/--query)")
    j.add_argument("--som", action="store_true", default=None,
                   help="use the set-of-mark version (judge-som.md); the runner saves the image next to submission/ as som.png. "
                        "Default: on when the query has a som_image")
    j.add_argument("--option", action="append", metavar="KEY=VALUE")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        build()
    elif a.cmd == "solver":
        sys.stdout.write(fill_solver(a.variant, a.scene, a.bound, parse_options(a.option, SOLVER_OPTIONS)))
    else:
        sys.stdout.write(fill_judge(a.scene, a.query, parse_options(a.option, JUDGE_OPTIONS), a.what, a.som))


if __name__ == "__main__":
    main()
