#!/usr/bin/env python3
"""Round 2c (user request 2026-11-04 ~09:20): reconstruction only, no judges.
Codex (gpt-6.1-sol, max) and Claude Code (claude-opus-5-5, max) x {blender, openusd} x
{IMG_1580 = demo-yuzhou-s02, IMG_1583 = demo-yuzhou-s03, IMG_1587 = demo-yuzhou-s04} = 12 runs, all started at once.
Usage limits are waited out and the same session is resumed. Runs live in <scene>/<agent>-<variant>/{solver,logs}.
"""
import json, os, re, shutil, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]  # the eval-infra-kit checkout
R = Path(os.environ.get("R2S_RUNS", KIT.parent / "round2-runs"))  # run folders, _videos/, _bin/ (ffmpeg)
K = KIT / "prompts" / "round2"
EXAMPLES = Path(os.environ.get("R2S_EXAMPLES", KIT.parent / "registry-demo" / "_examples"))  # <person>/<scene_id>/scene.json
EX = EXAMPLES / "yuzhou"
LOG = R / "round2c_driver.log"
SCENES = {"demo-yuzhou-s02": "IMG_1580", "demo-yuzhou-s03": "IMG_1583", "demo-yuzhou-s04": "IMG_1587"}
VARIANTS = ["blender", "openusd"]
AGENTS = ["codex", "claude"]
GPUS = ["5", "7", "3", "2"]
MODEL = ["-m", "gpt-6.1-sol", "-c", "model_reasoning_effort=max"]
NET = ["-c", "sandbox_workspace_write.network_access=true"]
CLAUDE = ["claude", "-p", "--model", "claude-opus-5-5", "--effort", "max", "--permission-mode", "auto",
          "--strict-mcp-config", "--disallowedTools", "WebSearch", "WebFetch", "--output-format", "stream-json", "--verbose"]
CONTINUE = ("Your previous turn was cut off by a usage limit before you finished. Continue the task from where "
            "you stopped and complete everything the original instructions ask for in output/.")
_lock = threading.Lock()


def say(msg):
    with _lock, LOG.open("a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def env(gpu):
    return dict(os.environ, PATH=f"{R}/_bin:" + os.environ["PATH"], CUDA_VISIBLE_DEVICES=gpu)


def bare_time(s):
    s = s.strip().lower().replace(" ", "")
    fmt = "%I:%M%p" if ":" in s else "%I%p"
    t = datetime.strptime(s, fmt).time()
    dt = datetime.combine(datetime.now().date(), t)
    return dt + timedelta(days=1) if dt < datetime.now() - timedelta(minutes=5) else dt


def codex_reset(text):
    full = list(re.finditer(r"try again at ([A-Z][a-z]{2} \d{1,2})(?:st|nd|rd|th)?, (\d{4}) (\d{1,2}:\d{2} [AP]M)", text))
    bare = list(re.finditer(r"try again at (\d{1,2}:\d{2} [AP]M)", text))
    try:
        if full and (not bare or full[-1].start() >= bare[-1].start()):
            m = full[-1]
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y %I:%M %p")
        if bare:
            return bare_time(bare[-1].group(1))
    except ValueError:
        pass
    return datetime.now() + timedelta(minutes=30)


def claude_result(jsonl):
    res = None
    for line in jsonl.open(errors="replace"):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("type") == "result":
            res = e
    return res


def claude_reset(text):
    m = re.search(r"limit reached\|(\d{10})", text)
    if m:
        return datetime.fromtimestamp(int(m.group(1)))
    m = re.search(r"resets (?:at )?(\d{1,2}(?::\d{2})?\s?[ap]m)", text, re.I)
    if m:
        try:
            return bare_time(m.group(1))
        except ValueError:
            pass
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


def run(job):
    agent, scene, variant, gpu = job
    tag = f"{agent} {scene}({SCENES[scene]}) {variant}"
    d = R / scene / f"{agent}-{variant}"
    sol, log = d / "solver", d / "logs"
    sol.mkdir(parents=True, exist_ok=True)
    log.mkdir(parents=True, exist_ok=True)
    shutil.copy(R / "_videos" / f"{scene}.mp4", sol / "input.mp4")
    prompt = subprocess.check_output(["python3", str(K / "prompts.py"), "solver", "--variant", variant,
                                      "--scene", str(EX / scene / "scene.json")], text=True)
    (log / "solver-prompt.md").write_text(prompt)
    (log / "solver.start").write_text(datetime.now().isoformat())
    say(f"{tag}: start (GPU {gpu})")
    session = None
    p = None
    for attempt in range(1, 13):
        out = log / ("solver.jsonl" if attempt == 1 else f"solver-resume{attempt - 1}.jsonl")
        if agent == "codex":
            if attempt == 1:
                cmd = ["timeout", "5h", "codex", "exec", "--json", "--skip-git-repo-check", "-s", "workspace-write", *NET, *MODEL,
                       "-o", str(log / "solver.last.md"), prompt]
            else:
                cmd = ["timeout", "5h", "codex", "exec", "resume", "--json", "--skip-git-repo-check",
                       "-c", 'sandbox_mode="workspace-write"', *NET, *MODEL, "-o", str(log / "solver.last.md"), session, CONTINUE]
        else:
            cmd = ["timeout", "5h", *CLAUDE, prompt] if attempt == 1 else ["timeout", "5h", *CLAUDE, "--resume", session, CONTINUE]
        with out.open("w") as fo, (log / out.name.replace(".jsonl", ".stderr")).open("w") as fe:
            p = subprocess.run(cmd, cwd=sol, env=env(gpu), stdout=fo, stderr=fe)
        (log / "solver.exit").write_text(str(p.returncode))
        if session is None:
            for line in out.open(errors="replace"):
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                session = e.get("thread_id") or e.get("session_id")
                if session:
                    break
        text = tail(out) + tail(log / out.name.replace(".jsonl", ".stderr"), 3000)
        if agent == "codex":
            hit, crashed = "usage limit" in text, False
            reset = codex_reset(text) if hit else None
        else:
            res = claude_result(out)
            rtext = json.dumps(res) if res else text
            hit = bool(re.search(r"usage limit|limit reached|hit your .*limit|rate.limit", rtext, re.I)) and (res is None or res.get("is_error"))
            crashed = res is None and p.returncode not in (0, 124)
            reset = claude_reset(rtext) if hit else None
        if p.returncode == 124:
            say(f"{tag}: session hit the 5 h timeout; resuming")
            if not session:
                break
            continue
        if crashed and session and not hit:
            say(f"{tag}: exited {p.returncode} without a result; resuming in 1 min")
            time.sleep(60)
            continue
        if not hit or not session:
            break
        say(f"{tag}: usage limit, waiting until {reset}")
        wait_until(reset)
    (log / "solver.end").write_text(datetime.now().isoformat())
    outs = sorted(f.name for f in (sol / "output").iterdir()) if (sol / "output").is_dir() else []
    say(f"{tag}: done, exit {p.returncode if p else None}, output: {' '.join(outs)}")


def main():
    jobs, i = [], 0
    for scene in SCENES:
        for variant in VARIANTS:
            for agent in AGENTS:
                jobs.append((agent, scene, variant, GPUS[i % len(GPUS)]))
                i += 1
    say(f"round 2c started: {len(jobs)} runs, no judges")
    with ThreadPoolExecutor(len(jobs)) as ex:
        list(ex.map(run, jobs))
    say("all done")


if __name__ == "__main__":
    main()
