#!/usr/bin/env python3
"""Round 2b: after the first test round finishes, pick its best solver variant and run it on more scenes.

- Codex (gpt-6.1-sol, max) on the three difficulty anchors demo-yuzhou-s02..s04.
- Claude Code (claude-opus-5-5, max) on demo-yuzhou-s01..s04.
- Every run is judged with the same judge as round 1 (Codex gpt-6.1-sol max), lenient and strict.
Usage limits on either service are waited out. Runs live in <scene>/<agent>-<variant>/{solver,judge,logs}.
"""
import json
import os
import re
import shutil
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait as fwait
from datetime import datetime, timedelta
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]  # the eval-infra-kit checkout
R = Path(os.environ.get("R2S_RUNS", KIT.parent / "round2-runs"))  # run folders, _videos/, _bin/ (ffmpeg)
K = KIT / "prompts" / "round2"
EXAMPLES = Path(os.environ.get("R2S_EXAMPLES", KIT.parent / "registry-demo" / "_examples"))  # <person>/<scene_id>/scene.json
EX = EXAMPLES / "yuzhou"
LOG = R / "round2b_driver.log"
CODEX_SCENES = ["demo-yuzhou-s02", "demo-yuzhou-s03", "demo-yuzhou-s04"]
CLAUDE_SCENES = ["demo-yuzhou-s01", "demo-yuzhou-s02", "demo-yuzhou-s03", "demo-yuzhou-s04"]
CODEX = ["codex", "exec", "--json", "--skip-git-repo-check", "-s", "workspace-write",
         "-c", "sandbox_workspace_write.network_access=true", "-m", "gpt-6.1-sol", "-c", "model_reasoning_effort=max"]
CLAUDE = ["claude", "-p", "--model", "claude-opus-5-5", "--effort", "max", "--permission-mode", "auto",
          "--strict-mcp-config", "--disallowedTools", "WebSearch", "WebFetch", "--output-format", "stream-json", "--verbose"]
CONTINUE = ("Your previous turn was cut off by a usage limit before you finished. Continue the task from where "
            "you stopped and complete everything the original instructions ask for in output/.")
GPUS = ["4", "5", "7"]
_lock = threading.Lock()
_gpu = [0]


def say(msg):
    with _lock, LOG.open("a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def next_gpu():
    with _lock:
        _gpu[0] += 1
        return GPUS[_gpu[0] % len(GPUS)]


def env(gpu):
    return dict(os.environ, PATH=f"{R}/_bin:" + os.environ["PATH"], CUDA_VISIBLE_DEVICES=gpu)


def _codex_reset(text):
    """Parse the last 'try again at ...' in text: either 'Nov 4th, 2026 1:05 AM' or a bare '11:20 AM' (today, else tomorrow)."""
    full = list(re.finditer(r"try again at ([A-Z][a-z]{2} \d{1,2})(?:st|nd|rd|th)?, (\d{4}) (\d{1,2}:\d{2} [AP]M)", text))
    bare = list(re.finditer(r"try again at (\d{1,2}:\d{2} [AP]M)", text))
    if full and (not bare or full[-1].start() >= bare[-1].start()):
        m = full[-1]
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y %I:%M %p")
        except ValueError:
            return None
    if bare:
        t = datetime.strptime(bare[-1].group(1), "%I:%M %p").time()
        dt = datetime.combine(datetime.now().date(), t)
        if dt < datetime.now() - timedelta(minutes=5):
            dt += timedelta(days=1)
        return dt
    return None


def codex_reset(text):
    return _codex_reset(text) or datetime.now() + timedelta(minutes=30)


def claude_reset(text):
    m = re.search(r"limit reached\|(\d{10})", text)
    if m:
        return datetime.fromtimestamp(int(m.group(1)))
    return datetime.now() + timedelta(minutes=30)


def wait_until(t):
    t = t + timedelta(minutes=2)
    while datetime.now() < t:
        time.sleep(min(300, max(5, (t - datetime.now()).total_seconds())))


def tail(p, n=8000):
    try:
        return Path(p).read_text(errors="replace")[-n:]
    except FileNotFoundError:
        return ""


# ------------------------------------------------------------------ best variant from round 1
def pick_best():
    s = json.loads((R / "summary.json").read_text())
    score = {}
    for row in s:
        v = row["variant"]
        sc = score.setdefault(v, {"within": 0, "errors": 0, "rel": []})
        sc["errors"] += len((row.get("check") or {}).get("errors", []))
        for j in row["judges"]:
            if j.get("correct10"):
                sc["within"] += 1
            if "rel_err" in j:
                sc["rel"].append(j["rel_err"])
    order = ["blender", "openusd", "any"]
    best = sorted(score, key=lambda v: (-score[v]["within"], score[v]["errors"],
                                        statistics.median(score[v]["rel"]) if score[v]["rel"] else 9e9, order.index(v)))[0]
    out = {v: {"within_10pct": d["within"], "format_errors": d["errors"],
               "median_rel_err": statistics.median(d["rel"]) if d["rel"] else None, "n_scored": len(d["rel"])} for v, d in score.items()}
    (R / "round2b_best_variant.json").write_text(json.dumps({"best": best, "rule": "most judge results within 10%, then fewest format errors, then lowest median relative error", "scores": out}, indent=1))
    say(f"best variant: {best} {out}")
    return best


# ------------------------------------------------------------------ runs
def scene_json(scene):
    return EX / scene / "scene.json"


def run_solver(agent, scene, variant, judge_pool, futures):
    d = R / scene / f"{agent}-{variant}"
    sol, log = d / "solver", d / "logs"
    sol.mkdir(parents=True, exist_ok=True)
    log.mkdir(parents=True, exist_ok=True)
    shutil.copy(R / "_videos" / f"{scene}.mp4", sol / "input.mp4")
    prompt = subprocess.check_output(["python3", str(K / "prompts.py"), "solver", "--variant", variant, "--scene", str(scene_json(scene))], text=True)
    (log / "solver-prompt.md").write_text(prompt)
    gpu = next_gpu()
    say(f"{agent} {scene} {variant}: solver start (GPU {gpu})")
    (log / "solver.start").write_text(datetime.now().isoformat())
    session = None
    for attempt in range(1, 12):
        out = log / ("solver.jsonl" if attempt == 1 else f"solver-resume{attempt - 1}.jsonl")
        if agent == "codex":
            if attempt == 1:
                cmd = ["timeout", "5h", *CODEX, "-o", str(log / "solver.last.md"), prompt]
            else:
                cmd = ["timeout", "5h", "codex", "exec", "resume", "--json", "--skip-git-repo-check",
                       "-c", 'sandbox_mode="workspace-write"', "-c", "sandbox_workspace_write.network_access=true",
                       "-m", "gpt-6.1-sol", "-c", "model_reasoning_effort=max", "-o", str(log / "solver.last.md"), session, CONTINUE]
        else:
            cmd = ["timeout", "5h", *CLAUDE, prompt] if attempt == 1 else ["timeout", "5h", *CLAUDE, "--resume", session, CONTINUE]
        with out.open("w") as fo, (log / out.name.replace(".jsonl", ".stderr")).open("w") as fe:
            p = subprocess.run(cmd, cwd=sol, env=env(gpu), stdout=fo, stderr=fe)
        (log / "solver.exit").write_text(str(p.returncode))
        text = tail(out)
        if session is None:
            for line in out.open(errors="replace"):
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                session = e.get("thread_id") or e.get("session_id") or session
                if session:
                    break
        if agent == "codex":
            hit = "usage limit" in text
            reset = codex_reset(text) if hit else None
        else:
            hit = bool(re.search(r"usage limit|limit reached|rate limit", text, re.I)) and p.returncode != 0 or "limit reached|" in text
            reset = claude_reset(text) if hit else None
        if not hit or not session:
            break
        say(f"{agent} {scene} {variant}: usage limit, waiting until {reset}")
        wait_until(reset)
    (log / "solver.end").write_text(datetime.now().isoformat())
    say(f"{agent} {scene} {variant}: solver done, exit {p.returncode}")
    for name in judge_names(scene):
        futures.append(judge_pool.submit(run_judge, agent, scene, variant, name))


def judge_names(scene):
    qids = [q["query_id"] for q in json.loads(scene_json(scene).read_text())["queries"]]
    return [q + suf for q in qids for suf in ("", ".strict")]


def run_judge(agent, scene, variant, name):
    d = R / scene / f"{agent}-{variant}"
    log = d / "logs"
    qid = name.replace(".strict", "")
    opt = ["--option", "parts=strict"] if name.endswith(".strict") else []
    prompt = subprocess.check_output(["python3", str(K / "prompts.py"), "judge", "--scene", str(scene_json(scene)), "--query", qid, *opt], text=True)
    (log / f"judge-{name}-prompt.md").write_text(prompt)
    j = d / "judge" / name
    for attempt in range(1, 11):
        if j.exists():
            shutil.rmtree(j)
        j.mkdir(parents=True)
        if (d / "solver" / "output").is_dir():
            shutil.copytree(d / "solver" / "output", j / "submission")
        out = log / f"judge-{name}.jsonl"
        with out.open("w") as fo, (log / f"judge-{name}.stderr").open("w") as fe:
            p = subprocess.run(["timeout", "2h", *CODEX, "-o", str(log / f"judge-{name}.last.md"), prompt],
                               cwd=j, env=env(next_gpu()), stdout=fo, stderr=fe)
        (log / f"judge-{name}.exit").write_text(str(p.returncode))
        text = tail(out)
        if "usage limit" not in text:
            say(f"judge {agent} {scene} {variant} {name}: exit {p.returncode}, result {'yes' if (j / 'result.json').exists() else 'no'}")
            return
        reset = codex_reset(text)
        say(f"judge {agent} {scene} {variant} {name}: usage limit, waiting until {reset}")
        wait_until(reset)


def main():
    say("round 2b driver started; waiting for round 1 to finish")
    while "all done" not in tail(R / "resume_driver.log", 20000):
        time.sleep(120)
    subprocess.run(["python3", str(R / "summarize.py")], cwd=R)
    best = pick_best()
    judge_pool = ThreadPoolExecutor(3)
    futures = []
    with ThreadPoolExecutor(2) as codex_lane, ThreadPoolExecutor(2) as claude_lane:
        jobs = [codex_lane.submit(run_solver, "codex", s, best, judge_pool, futures) for s in CODEX_SCENES]
        jobs += [claude_lane.submit(run_solver, "claude", s, best, judge_pool, futures) for s in CLAUDE_SCENES]
        fwait(jobs)
    while True:
        pending = [f for f in futures if not f.done()]
        if not pending:
            break
        fwait(pending)
    judge_pool.shutdown(wait=True)
    say("all done")


if __name__ == "__main__":
    main()
