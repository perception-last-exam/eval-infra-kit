# Test runs

Scripts that ran the Round 2 prompt tests on the GPU server. They run each solver headless, resume it after usage limits, run the judges, then summarize the runs and build a results page with videos.

Runs live outside the repo, in a runs folder (default `../round2-runs` next to this checkout):

```
<runs>/
  _videos/<scene_id>.mp4          normalized input videos (prompts/round2/normalize_video.py)
  _bin/ffmpeg                     static ffmpeg, put first on PATH for the agents
  <scene_id>/<variant>/           round 1: Codex only; variant = blender | openusd | any
  <scene_id>/<agent>-<variant>/   later rounds: agent = codex | claude
      solver/input.mp4            the only file the solver starts with
      solver/output/              what the solver wrote (check with prompts/round2/check_output.py)
      judge/<query_id>[.strict]/  one fresh judge session per query, with a copy of output/ as submission/
      logs/                       prompts, JSONL event streams, exits, start/end times
```

Scene files are read from `<examples>/<person>/<scene_id>/scene.json` (default `../registry-demo/_examples`).

| Variable | Default | Used for |
|---|---|---|
| `R2S_RUNS` | `../round2-runs` | runs folder |
| `R2S_EXAMPLES` | `../registry-demo/_examples` | scene.json files |
| `R2S_CHECK_PYTHON` | the current Python | interpreter for `check_output.py` in `summarize.py` |
| `FFMPEG` | `<runs>/_bin/ffmpeg`, else `ffmpeg` on PATH | report videos |

## Scripts

| Script | What it does |
|---|---|
| `run_pipeline.sh <scene> <variant> <gpu>` | Round 1: one Codex solver, then every judge prompt in `<runs>/<scene>/judge-prompts/` in parallel. Write those prompts with `prompts.py judge`; use `--option parts=strict` for the `.strict` versions |
| `resume_driver.py` | Round 1 follow-up. Resumes solvers that a usage limit cut off, in their own sessions, then runs the judges that are missing |
| `round2b_driver.py` | Picks round 1's best variant and runs it with Codex on s02–s04 and Claude Code on s01–s04, then judges every run. Prepared but never run |
| `round2c_driver.py` | Reconstruction only, no judges. Codex and Claude Code × Blender and OpenUSD on the three difficulty anchors (s02–s04), 12 runs at once |
| `summarize.py` | Writes `<runs>/summary.json`: solver status and time, format check, each judge's value and relative error against GT. Also writes an HTML table, `runs-fragment.html` |
| `report/build_media.py` | Builds into `<runs>/_report/media/`: side-by-side input/render videos, still-frame grids, and the judges' and solvers' check images |
| `report/build_report.py` | Writes `<runs>/_report/round2-test-runs.html` from `summary.json` and the media, plus `files.json` listing the media to publish with it |

Scene lists, variants and GPU assignments are constants at the top of each driver; edit them for a new round.

## How the agents are run

The solver and judge prompts come from `prompts/round2/prompts.py`; the reconstruction bound is the scene's `scope`.

```
# Codex: sandboxed to its own folder, with network on for package installs
codex exec --json --skip-git-repo-check -s workspace-write -c sandbox_workspace_write.network_access=true \
  -m gpt-6.1-sol -c model_reasoning_effort=max -o logs/solver.last.md "<prompt>"
# Claude Code: auto permission mode, no MCP servers, no web tools
claude -p --model claude-opus-5-5 --effort max --permission-mode auto --strict-mcp-config \
  --disallowedTools WebSearch WebFetch --output-format stream-json --verbose "<prompt>"
```

Each run starts in `solver/` with only `input.mp4`, under `timeout 5h` (judges get 2 h).

**Usage limits:** when a session stops on a usage limit, the driver reads the reset time from the message, waits until then, and resumes the same session with a short "continue where you stopped" prompt. Each resume goes to `solver-resumeN.jsonl`.
- **Codex:** "try again at Nov 4th, 2026 1:05 AM", or a bare "11:20 AM", which means today, or tomorrow if that time has passed.
- **Claude Code:** the final `result` event, with "limit reached|<epoch>" or "resets 3pm".
- When no time can be parsed, the driver retries every 30 minutes.
