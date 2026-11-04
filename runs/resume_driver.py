#!/usr/bin/env python3
"""Finish the round-2 prompt test after the Codex usage limit.

1. Wait for the reset time Codex reported.
2. Resume each solver's own Codex session (keeps its work), 2 at a time, until it ends without hitting the limit.
3. Run every judge prompt (lenient + strict) in a fresh session on a fresh copy of output/, 4 at a time.
If the limit hits again, wait for the next reset Codex reports and retry. Same sandbox as before:
workspace-write (writes only inside the run folder), network on for installs.
"""
import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]  # the eval-infra-kit checkout
R = Path(os.environ.get("R2S_RUNS", KIT.parent / "round2-runs"))  # run folders, _videos/, _bin/ (ffmpeg)
K = KIT / "prompts" / "round2"
EXAMPLES = Path(os.environ.get("R2S_EXAMPLES", KIT.parent / "registry-demo" / "_examples"))  # <person>/<scene_id>/scene.json
SCENES = ("demo-yuzhou-s01", "demo-diwu-s01")
VARIANTS = ("blender", "openusd", "any")
GPU = {"blender": "4", "openusd": "5", "any": "7"}
SANDBOX = ["-c", 'sandbox_mode="workspace-write"', "-c", "sandbox_workspace_write.network_access=true"]
MODEL = ["-m", "gpt-6.1-sol", "-c", "model_reasoning_effort=max"]
CONTINUE = ("Your previous turn was cut off by a usage limit before you finished. Continue the task from where "
            "you stopped and complete everything the original instructions ask for in output/.")
LOG = R / "resume_driver.log"
FIRST_RESET = datetime(2026, 11, 4, 1, 5)


def say(msg):
    with LOG.open("a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def reset_time(text):
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


def wait_until(t):
    t = t + timedelta(minutes=2)
    while datetime.now() < t:
        time.sleep(min(300, max(5, (t - datetime.now()).total_seconds())))


def env(gpu):
    return dict(os.environ, PATH=f"{R}/_bin:" + os.environ["PATH"], CUDA_VISIBLE_DEVICES=gpu)


def limited(jsonl):
    try:
        tail = jsonl.read_text()[-6000:]
    except FileNotFoundError:
        return None
    if "usage limit" not in tail:
        return None
    return reset_time(tail) or (datetime.now() + timedelta(minutes=30))


def thread_id(jsonl):
    for line in jsonl.open():
        e = json.loads(line)
        if e.get("type") == "thread.started":
            return e["thread_id"]
    raise SystemExit(f"no thread id in {jsonl}")


def finish_solver(scene, variant):
    d = R / scene / variant
    log = d / "logs"
    tid = thread_id(log / "solver.jsonl")
    done = len(list(log.glob("solver-resume*.jsonl")))
    for attempt in range(done + 1, done + 11):
        out = log / f"solver-resume{attempt}.jsonl"
        say(f"{scene}/{variant}: resume {attempt} of {tid}")
        (log / f"solver-resume{attempt}.start").write_text(datetime.now().isoformat())
        with out.open("w") as fo, (log / f"solver-resume{attempt}.stderr").open("w") as fe:
            p = subprocess.run(["timeout", "5h", "codex", "exec", "resume", "--json", "--skip-git-repo-check",
                                *SANDBOX, *MODEL, "-o", str(log / "solver.last.md"), tid, CONTINUE],
                               cwd=d / "solver", env=env(GPU[variant]), stdout=fo, stderr=fe)
        (log / f"solver-resume{attempt}.end").write_text(datetime.now().isoformat())
        (log / "solver.exit").write_text(str(p.returncode))
        t = limited(out)
        if t is None:
            say(f"{scene}/{variant}: solver finished, exit {p.returncode}")
            return
        say(f"{scene}/{variant}: usage limit again; waiting until {t}")
        wait_until(t)
    say(f"{scene}/{variant}: gave up after 10 more resumes")


def unfinished(scene, variant):
    log = R / scene / variant / "logs"
    last = sorted(log.glob("solver-resume*.jsonl"), key=lambda f: int(f.stem.replace("solver-resume", "")))
    return limited(last[-1] if last else log / "solver.jsonl") is not None


def judge_jobs():
    jobs = []
    for scene in SCENES:
        sj = next(EXAMPLES.glob(f"*/{scene}/scene.json"))
        qids = [q["query_id"] for q in json.loads(sj.read_text())["queries"]]
        for q in qids:  # refresh prompts from the current judge template
            soms = sorted((R / scene / "judge-prompts").glob(f"{q}.som.*"))
            som = ["--som"] if soms else []
            for suf, opt in (("", []), (".strict", ["--option", "parts=strict"])):
                txt = subprocess.check_output(["python3", str(K / "prompts.py"), "judge", "--scene", str(sj),
                                               "--query", q, *som, *opt], text=True)
                (R / scene / "judge-prompts" / f"{q}{suf}.md").write_text(txt)
        for v in VARIANTS:
            for q in qids:
                for suf in ("", ".strict"):
                    jobs.append((scene, v, q + suf))
    return jobs


def run_judge(job):
    scene, v, name = job
    d = R / scene / v
    log = d / "logs"
    j = d / "judge" / name
    if (j / "result.json").exists() and limited(log / f"judge-{name}.jsonl") is None:
        return
    if j.exists():
        shutil.rmtree(j)
    j.mkdir(parents=True)
    if (d / "solver" / "output").is_dir():
        shutil.copytree(d / "solver" / "output", j / "submission")
    prompt = (R / scene / "judge-prompts" / f"{name}.md").read_text()
    qid = name.replace(".strict", "")
    soms = sorted((R / scene / "judge-prompts").glob(f"{qid}.som.*"))
    image = []
    if soms:
        dst = j / "som.png"
        shutil.copy(soms[0], dst)
        image = ["-i", dst.name]
    (log / f"judge-{name}-prompt.md").write_text(prompt)
    for attempt in range(1, 11):
        out = log / f"judge-{name}.jsonl"
        with out.open("w") as fo, (log / f"judge-{name}.stderr").open("w") as fe:
            p = subprocess.run(["timeout", "2h", "codex", "exec", "--json", "--skip-git-repo-check",
                                "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true",
                                *MODEL, *image, "-o", str(log / f"judge-{name}.last.md"), prompt],
                               cwd=j, env=env(GPU[v]), stdout=fo, stderr=fe)
        (log / f"judge-{name}.exit").write_text(str(p.returncode))
        t = limited(out)
        if t is None:
            say(f"judge {scene}/{v}/{name}: exit {p.returncode}, result {'yes' if (j / 'result.json').exists() else 'no'}")
            return
        say(f"judge {scene}/{v}/{name}: usage limit; waiting until {t}")
        wait_until(t)
        for f in j.iterdir():  # restart fresh on a clean copy
            if f.name != "submission" and not f.name.startswith("som."):
                shutil.rmtree(f) if f.is_dir() else f.unlink()


def main():
    say(f"driver v2 started (fixed reset-time parsing; skips finished solvers and judges); waiting for reset {FIRST_RESET}")
    wait_until(FIRST_RESET)
    with ThreadPoolExecutor(2) as ex:
        list(ex.map(lambda sv: finish_solver(*sv), [(s, v) for s in SCENES for v in VARIANTS if unfinished(s, v)]))
    jobs = judge_jobs()
    say(f"solvers done; {len(jobs)} judge sessions")
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(run_judge, jobs))
    subprocess.run(["python3", str(R / "summarize.py")], cwd=R)
    say("all done")


if __name__ == "__main__":
    main()
