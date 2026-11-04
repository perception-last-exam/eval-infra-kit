#!/usr/bin/env python3
"""Summarize the round-2 prompt test runs: solver status, format check, judge values, error vs GT.
Writes summary.json and runs-fragment.html into the runs folder ($R2S_RUNS)."""
import html
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]  # the eval-infra-kit checkout
R = Path(os.environ.get("R2S_RUNS", KIT.parent / "round2-runs"))  # run folders, _videos/, _bin/ (ffmpeg)
K = KIT / "prompts" / "round2"
EXAMPLES = Path(os.environ.get("R2S_EXAMPLES", KIT.parent / "registry-demo" / "_examples"))  # <person>/<scene_id>/scene.json
PY = os.environ.get("R2S_CHECK_PYTHON", sys.executable)  # a Python with what check_output.py needs
FRAG = R / "runs-fragment.html"  # HTML table of the runs, for embedding in a review page
SCENES = {"demo-yuzhou-s01": "yuzhou", "demo-diwu-s01": "diwu"}
VARIANTS = ("blender", "openusd", "any")
REAL_GT = {"demo-diwu-s01-q1"}  # Di Wu's recorded 250 mL; the other demo GT values are illustrative


def tokens(jsonl):
    tot = {"input": 0, "cached": 0, "output": 0}
    n_cmd = 0
    if not jsonl.exists():
        return tot, 0
    for line in jsonl.open():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("type") == "turn.completed":
            u = e.get("usage", {})
            tot["input"] += u.get("input_tokens", 0)
            tot["cached"] += u.get("cached_input_tokens", 0)
            tot["output"] += u.get("output_tokens", 0)
        if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "command_execution":
            n_cmd += 1
    return tot, n_cmd


def minutes(a, b):
    try:
        return round((datetime.fromisoformat(b.read_text().strip()) - datetime.fromisoformat(a.read_text().strip())).total_seconds() / 60)
    except Exception:
        return None


SCALE = {"mm": ("m", 1e-3), "cm": ("m", 1e-2), "m": ("m", 1.0), "ml": ("m3", 1e-6), "l": ("m3", 1e-3),
         "cm3": ("m3", 1e-6), "m3": ("m3", 1.0), "g": ("kg", 1e-3), "kg": ("kg", 1.0), "px": ("px", 1.0),
         "deg": ("deg", 1.0), "degc": ("degc", 1.0), "percent": ("percent", 1.0), "%": ("percent", 1.0)}


def to_unit(v, unit_from, unit_to):
    """Convert v from the judge's unit to the GT unit; None if they are not comparable."""
    a = SCALE.get(str(unit_from or unit_to).strip().lower().replace("³", "3").replace("°c", "degc"))
    b = SCALE.get(str(unit_to).strip().lower().replace("³", "3").replace("°c", "degc"))
    if not a or not b or a[0] != b[0]:
        return None
    return v * a[1] / b[1]


def main():
    env = dict(os.environ, PATH=f"{R}/_bin:" + os.environ["PATH"])
    out = []
    for scene, who in SCENES.items():
        sj = json.loads(next(EXAMPLES.glob(f"*/{scene}/scene.json")).read_text())
        qs = {q["query_id"]: q for q in sj["queries"]}
        for v in VARIANTS:
            d = R / scene / v
            log = d / "logs"
            row = {"scene": scene, "variant": v}
            row["solver_exit"] = (log / "solver.exit").read_text().strip() if (log / "solver.exit").exists() else None
            row["solver_min"] = minutes(log / "solver.start", log / "solver.end") if (log / "solver.end").exists() else None
            row["tokens"], row["commands"] = tokens(log / "solver.jsonl")
            resumes = sorted(log.glob("solver-resume*.jsonl"), key=lambda p: int(p.stem.replace("solver-resume", "")))
            for rp in resumes:
                tk, nc = tokens(rp)
                row["commands"] += nc
                for k in tk:
                    row["tokens"][k] += tk[k]
                m = minutes(rp.with_suffix(".start"), rp.with_suffix(".end"))
                if m is not None and row["solver_min"] is not None:
                    row["solver_min"] += m
            row["resumes"] = len(resumes)
            sj_log = resumes[-1] if resumes else log / "solver.jsonl"
            row["limit_hit"] = sj_log.exists() and "usage limit" in sj_log.read_text()[-4000:]
            o = d / "solver" / "output"
            if o.is_dir():
                r = subprocess.run([PY, str(K / "check_output.py"), str(o), "--video", str(d / "solver" / "input.mp4"), "--json"],
                                   capture_output=True, text=True, env=env, timeout=1800)
                try:
                    row["check"] = json.loads(r.stdout)
                except Exception:
                    row["check"] = {"errors": [f"checker crashed: {r.stderr[-300:]}"], "warnings": [], "info": {}}
                files = sorted(p.name for p in o.iterdir())
                row["files"] = files
                try:
                    row["scene_size_mb"] = round(sum(f.stat().st_size for f in o.rglob("*") if f.is_file()) / 1e6, 1)
                except Exception:
                    pass
            judges = []
            for qid, q in qs.items():
                for ver, suf in (("lenient", ""), ("strict", ".strict")):
                    j = {"query_id": qid, "version": ver, "kind": q.get("kind"), "gt": q.get("gt_value"),
                         "unit": q.get("gt_unit"), "gt_real": qid in REAL_GT}
                    res = d / "judge" / (qid + suf) / "result.json"
                    ex = log / f"judge-{qid}{suf}.exit"
                    j["exit"] = ex.read_text().strip() if ex.exists() else None
                    if res.exists():
                        try:
                            rj = json.loads(res.read_text())
                            j.update({"value": rj.get("value"), "status": rj.get("status"), "judge_unit": rj.get("unit"),
                                      "entities": rj.get("entities"), "method": rj.get("method"), "notes": rj.get("notes"),
                                      "frame": rj.get("frame")})
                            if isinstance(j["value"], (int, float)) and j["gt"]:
                                cv = to_unit(j["value"], j.get("judge_unit"), j["unit"])
                                if cv is not None:
                                    j["value_in_gt_unit"] = cv
                                    j["rel_err"] = abs(cv - j["gt"]) / abs(j["gt"])
                                else:
                                    j["status"] = f"{j['status']} (unit {j.get('judge_unit')!r} not comparable)"
                            j["correct10"] = bool(j.get("rel_err") is not None and j["rel_err"] <= 0.10
                                                  and j["status"] not in ("missing", "invalid"))
                        except Exception as ex_:
                            j["status"] = f"bad result.json: {ex_}"
                    judges.append(j)
            row["judges"] = judges
            out.append(row)
    (R / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    FRAG.write_text(fragment(out))
    print(json.dumps([{k: r.get(k) for k in ("scene", "variant", "solver_exit", "solver_min")} for r in out]))


def fragment(rows):
    e = html.escape
    parts = ['<p>Two of your scenes × three solver variants, each in a fresh Codex session (gpt-6.1-sol, reasoning effort max). '
             'Codex ran in its workspace-write sandbox, which only writes inside its run folder, with network on for installs. '
             'Then two fresh judge sessions per query (same model and effort), lenient and strict about parts that were not modelled, each seeing only <code>submission/</code>.</p>',
             '<p class="small">Ground truth: <b>demo-diwu-s01-q1</b> (250 mL) is Di Wu\'s recorded value. The other GT numbers in these demo records are '
             'illustrative, so their errors test the pipeline, not the model.</p>']
    note = R / "status_note.html"
    if note.exists():
        parts.insert(1, note.read_text())
    for scene in SCENES:
        parts.append(f"<h3>{e(scene)}</h3>")
        for r in [x for x in rows if x["scene"] == scene]:
            c = r.get("check", {})
            info = c.get("info", {})
            st = ("done" if r["solver_exit"] == "0" else f"exit {r['solver_exit']}") if r["solver_exit"] is not None else "running"
            if r.get("limit_hit"):
                st = "stopped by the Codex usage limit"
            t = r["tokens"]
            parts.append(f'<h4>{e(r["variant"])} · solver {e(st)}'
                         + (f' · {r["solver_min"]} min' if r.get("solver_min") is not None else "")
                         + (f' (resumed {r["resumes"]}×)' if r.get("resumes") else "")
                         + f' · {r["commands"]} commands' + (f' · {t["output"]:,} output tokens' if t["output"] else '') + '</h4>')
            li = []
            if r.get("files") is not None:
                li.append(f"<li><b>Output:</b> {e(', '.join(r['files']))}"
                          + (f" ({r['scene_size_mb']} MB)" if r.get("scene_size_mb") is not None else "") + "</li>")
                li.append(f"<li><b>Scene:</b> {info.get('entities', 0)} entities ({info.get('parts', 0)} parts); types {e(', '.join(info.get('types', [])))}; "
                          f"{info.get('entities_resolved', '?')} resolve to geometry; camera frames {info.get('camera_frames', '?')}; "
                          f"fx at frame 0 {e(str(round(info['fx_frame0'], 1)) if isinstance(info.get('fx_frame0'), (int, float)) else '?')} px</li>")
                errs, warns = c.get("errors", []), c.get("warnings", [])
                fmt = ('<span class="ok">format OK</span>' if not errs else
                       f'<span class="bad">{len(errs)} format error(s)</span>: ' + e("; ".join(errs[:4])))
                if warns:
                    fmt += ' · <span class="warn">warnings</span>: ' + e("; ".join(warns[:3]))
                if r["solver_exit"] is None:
                    fmt = "runs when the solver finishes (output so far is partial)"
                elif r.get("limit_hit"):
                    fmt = ("partial output; it stopped before its final steps. " + fmt)
                li.append(f"<li><b>Format check:</b> {fmt}</li>")
            parts.append('<ul class="tight">' + "".join(li) + "</ul>")
            qids = list(dict.fromkeys(j["query_id"] for j in r["judges"]))
            lines = []
            for qid in qids:
                js = {j["version"]: j for j in r["judges"] if j["query_id"] == qid}
                any_j = js.get("lenient") or js.get("strict")
                if not any(("value" in j or j.get("status") or j.get("exit") is not None) for j in js.values()):
                    continue
                def one(j):
                    if "value" not in j and not j.get("status"):
                        if j.get("exit") is not None:
                            lj = R / r["scene"] / r["variant"] / "logs" / f"judge-{j['query_id']}{'' if j['version'] == 'lenient' else '.strict'}.jsonl"
                            why = "refused by the Codex usage limit" if lj.exists() and "usage limit" in lj.read_text() else f"exit {e(str(j.get('exit')))}"
                            return f"{j['version']}: not run ({why})"
                        return f"{j['version']}: running"
                    v = j.get("value")
                    val = "null" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else e(str(v)))
                    err = f", {j['rel_err'] * 100:.1f}% off" if "rel_err" in j else ""
                    verdict = '<span class="ok">within 10%</span>' if j.get("correct10") else '<span class="bad">wrong</span>'
                    return f"{j['version']}: {val} {e(j.get('judge_unit') or j['unit'])}{err} · {verdict} · status {e(str(j.get('status')))}"
                gt = f"GT {any_j['gt']:g} {e(any_j['unit'])}" + ("" if any_j["gt_real"] else " (illustrative)")
                meth = (js.get("lenient") or {}).get("method") or (js.get("strict") or {}).get("method") or ""
                lines.append(f"<li><b>{e(qid.split('-')[-1])} {e(any_j['kind'] or '')}</b>, {gt}<br>"
                             + "<br>".join(one(js[k]) for k in ("lenient", "strict") if k in js)
                             + (f'<br><span class="small">How: {e(meth[:260])}</span>' if meth else "") + "</li>")
            if lines:
                parts.append('<ul class="tight">' + "".join(lines) + "</ul>")
    return "\n".join(parts)


if __name__ == "__main__":
    main()
