#!/usr/bin/env python3
"""Build the Round 2 test-run report page from summary.json, media/manifest.json and the solver outputs."""
import glob, html, json, os, re
from datetime import datetime
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
R = Path(os.environ.get("R2S_RUNS", KIT.parent / "round2-runs"))
EXAMPLES = Path(os.environ.get("R2S_EXAMPLES", KIT.parent / "registry-demo" / "_examples"))
HERE = R / "_report"  # output folder: media/, round2-test-runs.html, files.json
MEDIA = HERE / "media"
OUT = HERE / "round2-test-runs.html"
summary = json.loads((R / "summary.json").read_text())
media = json.loads((MEDIA / "manifest.json").read_text())
LABEL = {"blender": "Blender", "openusd": "OpenUSD", "any": "Any tool"}
SCENE_NAME = {"demo-yuzhou-s01": "Desk with a mirror", "demo-diwu-s01": "Pour-over coffee"}
SCENE_BLURB = {
    "demo-yuzhou-s01": "Yu Zhou's desk: laptop, pink tape measure, battery pack, two boxes and a filing cabinet, partly filmed through a tall mirror. 887 frames, 1080×1920.",
    "demo-diwu-s01": "Di Wu's pour-over: a V60 dripper on a glass server on a scale, coffee dripping into the server. 483 frames, 720×1280.",
}
SCENE_FILE = {"blender": "scene.blend", "openusd": "USD", "any": None}
esc = html.escape


def scene_json(scene):
    return json.loads(Path(glob.glob(f"{EXAMPLES}/*/{scene}/scene.json")[0]).read_text())


def fmt(x):
    if x is None:
        return "–"
    ax = abs(x)
    if ax >= 1000:
        return f"{x:,.0f}"
    if ax >= 100:
        return f"{x:.0f}"
    if ax >= 10:
        return f"{x:.1f}"
    if ax >= 1:
        return f"{x:.2f}"
    return f"{x:.3g}"


UNIT = {"cm": " cm", "mm": " mm", "px": " px", "mL": " mL", "g": " g", "kg": " kg", "deg": "°", "degC": " °C", "percent": "%"}


def u(unit):
    return UNIT.get(unit, f" {unit}")


def off_text(j):
    v, gt = j.get("value_in_gt_unit"), j.get("gt")
    if v is None or gt in (None, 0):
        return ""
    r = v / gt
    if j.get("correct10"):
        band = "within 5%" if abs(r - 1) <= 0.05 else "within 10%"
        return f'<span class="ok">{abs(r - 1) * 100:.1f}% {"high" if r > 1 else "low"} · {band}</span>'

    if r <= 0:
        return '<span class="bad">100% low</span>'
    if r >= 2:
        return f'<span class="bad">{r:.1f}× too high</span>'
    if r <= 0.5:
        return f'<span class="bad">{(1 - r) * 100:.0f}% low</span>'
    return f'<span class="bad">{abs(r - 1) * 100:.0f}% {"high" if r > 1 else "low"}</span>'


rows = {(r["scene"], r["variant"]): r for r in summary}
now = datetime.now()

# ---------------------------------------------------------------- headline numbers
n_judges_total = sum(len(scene_json(s)["queries"]) * 2 * 3 for s in SCENE_NAME)
n_judged = sum(1 for r in summary for j in r["judges"] if j.get("value") is not None or j.get("status"))
pairs = []
for r in summary:
    by = {}
    for j in r["judges"]:
        by.setdefault(j["query_id"], {})[j["version"]] = j
    for q, d in by.items():
        a, b = d.get("lenient", {}).get("value_in_gt_unit"), d.get("strict", {}).get("value_in_gt_unit")
        if a is not None and b is not None:
            pairs.append(abs(a - b) / max(abs(a), abs(b), 1e-9))
within = sum(1 for r in summary for j in r["judges"] if j.get("correct10"))
scored = sum(1 for r in summary for j in r["judges"] if j.get("rel_err") is not None)
solvers_done = sum(1 for r in summary if "render.mp4" in r["files"] and "NOTES.md" in r["files"])

css = r"""
<title>Round 2 Test Runs</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@600;700&display=swap">
<style>
/* Layout: one wide column (max 1280px), each section a native <details>; media first, numbers next, run details folded. */
:root{
  --bg:#f6f8fb; --fg:#162033; --soft:#33415a; --line:#cfd8e6; --panel:#ffffff;
  --accent:#2556c4; --ok:#17794a; --bad:#b4311f; --code-bg:#f1f5fc; --code-fg:#17233b;
  --display:"IBM Plex Sans Condensed","IBM Plex Sans","Helvetica Neue",Arial,sans-serif;
  --body:"IBM Plex Sans","Helvetica Neue",Arial,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#111723; --fg:#e7edf7; --soft:#c3cee0; --line:#2d384c; --panel:#172031;
  --accent:#8fb2ff; --ok:#5fd39a; --bad:#ff8a76; --code-bg:#1f2a42; --code-fg:#e9f0ff; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#111723; --fg:#e7edf7; --soft:#c3cee0; --line:#2d384c; --panel:#172031;
  --accent:#8fb2ff; --ok:#5fd39a; --bad:#ff8a76; --code-bg:#1f2a42; --code-fg:#e9f0ff; color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:16px/1.55 var(--body)}
.wrap{max-width:1280px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1,h2,h3,h4{font-family:var(--display);text-wrap:balance;margin:0}
h1{font-size:2.1rem;line-height:1.15;letter-spacing:.005em}
.sub{color:var(--soft);margin:.35em 0 0}
.model{margin:.6em 0 0;font-weight:600;font-size:1.05rem}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:18px 0 8px}
.bar button{font:500 1rem var(--body);color:var(--accent);background:transparent;border:1px solid var(--line);border-radius:6px;padding:6px 12px;cursor:pointer}
.bar button:hover{border-color:var(--accent)}
.bar button:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
details{margin:0}
summary{cursor:pointer;list-style:none;display:flex;gap:.45em;align-items:baseline}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸";color:var(--accent);font-size:1em;line-height:1;transition:transform .15s;display:inline-block;width:.8em}
details[open]>summary::before{transform:rotate(90deg)}
@media (prefers-reduced-motion:reduce){summary::before{transition:none}}
section.top>details{border-top:1px solid var(--line);padding:18px 0}
section.top>details>summary h2{font-size:1.6rem}
.body{display:flex;flex-direction:column;gap:18px;margin-top:14px;padding-left:.2em;min-width:0}
details.sub2>summary h3{font-size:1.25rem}
details.sub3>summary h4{font-size:1.05rem}
.main{border:1px solid var(--accent);border-radius:8px;padding:12px;background:var(--panel);display:flex;flex-direction:column;gap:8px}
.main .lbl{font:600 .8rem var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
video,img{display:block;max-width:100%;height:auto;border-radius:4px}
.cap{color:var(--soft);font-size:.95rem;margin:0}
ul{margin:0;padding-left:1.1em}
li{margin:.2em 0}
p{margin:0;max-width:75ch}
.ok{color:var(--ok);font-weight:600}
.bad{color:var(--bad);font-weight:600}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:.95em}
.q{display:flex;flex-direction:column;gap:6px;padding:12px 0;border-bottom:1px solid var(--line)}
.q:last-child{border-bottom:0}
.q h4{font-size:1.05rem}
.q .gt{color:var(--soft)}
.q ul{list-style:none;padding:0}
.q li b{display:inline-block;min-width:5.5em}
.real{color:var(--ok);font-weight:600}
.example{color:var(--soft);font-style:italic}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.gallery figure{margin:0;display:flex;flex-direction:column;gap:4px;min-width:0}
.gallery figcaption{font-size:.9rem;color:var(--soft)}
pre{background:var(--code-bg);color:var(--code-fg);border:1px solid var(--line);border-radius:6px;padding:12px 14px;font:13.5px/1.5 var(--mono);white-space:pre-wrap;word-break:break-word;max-height:28em;overflow:auto;margin:0}
pre *{background:transparent}
a{color:var(--accent)}
.method{font-size:.95rem;display:flex;flex-direction:column;gap:8px}
.method b{font-weight:600}
</style>
"""

out = [css, '<div class="wrap">',
       '<h1>Round 2 test runs</h1>',
       f'<p class="model">Every run on this page is GPT: Codex with gpt-6.1-sol at max reasoning effort, for both the solvers and the judges. No Claude runs have been made yet.</p>',
       f'<p class="sub">Three solver prompt variants (Blender, OpenUSD, any tool) on two scenes. Runs stopped on request at 9:03 AM PST; page built {now:%b %-d, %-I:%M %p} PST.</p>',
       '<div class="bar"><button type="button" id="collapse">Collapse all</button><button type="button" id="expand">Expand all</button></div>',
       '<section class="top">']

# ---------------------------------------------------------------- status
lp = sorted(pairs)
out.append('<details open><summary><h2>Where things stand</h2></summary><div class="body"><ul>')
real = [(r["variant"], j) for r in summary for j in r["judges"] if j["query_id"] == "demo-diwu-s01-q1" and j["version"] == "lenient" and j.get("value_in_gt_unit") is not None]
real_txt = "; ".join(f'{LABEL[v]} {fmt(j["value_in_gt_unit"])} mL ({abs(j["value_in_gt_unit"]/250-1)*100:.1f}% {"high" if j["value_in_gt_unit"] > 250 else "low"})' for v, j in real)
desk_scored = sum(1 for r in summary if r["scene"] == "demo-yuzhou-s01" for j in r["judges"] if j.get("rel_err") is not None)
desk_within = sum(1 for r in summary if r["scene"] == "demo-yuzhou-s01" for j in r["judges"] if j.get("correct10"))
out.append(f'<li><b>Solvers:</b> all {solvers_done} finished, each with a scene file, manifest, camera track, render video and notes.</li>')
out.append(f'<li><b>Judges:</b> {n_judged} of {n_judges_total} measurements done. The other {n_judges_total - n_judged} (coffee scene: 3 for OpenUSD, 4 for any tool) were stopped before they ran.</li>')
out.append(f'<li><b>The one real ground truth, Di Wu\'s 250 mL of coffee:</b> {real_txt}. Both are within 5%. Both solvers got there by reading the scale display (252.2 g) and the server\'s printed mL marks, so this video nearly gives the answer away.</li>')
out.append(f'<li><b>Example-value questions:</b> on the desk scene, {desk_within} of {desk_scored} answers are within 10% of the example values; these values are made up, so the misses are not real errors. The coffee mass (example value 520 g) came out at 478 g with the Blender prompt.</li>')
if lp:
    out.append(f'<li><b>Lenient vs strict judge:</b> on the {len(lp)} questions measured both ways, the two answers differ by {lp[len(lp)//2]*100:.1f}% at the median and {lp[-1]*100:.0f}% at most, so the choice rarely matters on these scenes.</li>')
out.append('<li><b>The renders track the video closely.</b> All three desk runs reproduce the room, desk, laptop, tape measure, cabinet and mirror from the same camera path. All three coffee runs model the dripper, glass server, scale, bottle and the coffee itself as particles.</li>')
out.append('<li><b>Pixel questions through the mirror:</b> frame 412 is filmed through the mirror, and the desk solvers modelled the mirror. For the battery pack\'s pixel area, three judges projected the object straight through the camera, found it off-screen, and returned 0 px; the any-tool judges returned 10,547 px. For the A-to-B pixel distance, the Blender judge projected directly (6,792 px) while the OpenUSD and any-tool judges projected the reflection (about 330 px). The judge prompt should say that pixel questions mean what the frame shows, reflections included.</li>')
out.append('<li><b>Not run:</b> round 2b (Codex on the three difficulty anchors, Claude Code Opus 5.5 on four scenes) was stopped before it started.</li>')
out.append('</ul></div></details>')

# ---------------------------------------------------------------- per scene
for scene in SCENE_NAME:
    sj = scene_json(scene)
    m = media[scene]
    out.append(f'<details open><summary><h2>{esc(SCENE_NAME[scene])} <span class="num">({scene})</span></h2></summary><div class="body">')
    out.append(f'<p>{esc(SCENE_BLURB[scene])}</p>')
    pending = [LABEL[v] for v in LABEL if not m["runs"][v]["render"]]
    note = f' The {", ".join(pending)} render is not finished yet, so its pane is blank.' if pending else ""
    out.append(f'<div class="main"><span class="lbl">Main</span><video src="media/{m["video"]}" poster="media/{m["poster"]}" controls muted loop playsinline preload="metadata"></video>'
               f'<p class="cap">Left to right: input video, Blender, OpenUSD, any tool. Each render uses the solver\'s own reconstructed camera.{note}</p></div>')

    # answers
    qs = sj["queries"]
    out.append(f'<details class="sub2" open><summary><h3>Answers ({len(qs)} questions)</h3></summary><div class="body" style="gap:0">')
    for i, q in enumerate(qs, 1):
        qid = q["query_id"]
        real = qid == "demo-diwu-s01-q1"
        what = q.get("what_to_measure") or q["definition"]
        out.append(f'<div class="q"><h4>Q{qid.rsplit("q",1)[1]} · {esc(what[0].upper() + what[1:])}</h4>')
        out.append(f'<p class="gt">Ground truth <span class="num">{fmt(q["gt_value"])}{u(q["gt_unit"])}</span> · '
                   + ('<span class="real">real measurement</span>' if real else '<span class="example">example value</span>') + '</p><ul>')
        methods = []
        for v in LABEL:
            r = rows.get((scene, v))
            js = {j["version"]: j for j in (r["judges"] if r else []) if j["query_id"] == qid}
            le, st = js.get("lenient", {}), js.get("strict", {})
            if le.get("value_in_gt_unit") is None and st.get("value_in_gt_unit") is None:
                out.append(f'<li><b>{LABEL[v]}</b> judge not run (stopped)</li>')
                continue
            parts = []
            for name, j in (("lenient", le), ("strict", st)):
                if j.get("value_in_gt_unit") is not None:
                    parts.append(f'<span class="num">{fmt(j["value_in_gt_unit"])}{u(q["gt_unit"])}</span> {name}')
                else:
                    parts.append(f'{name} not run')
            base = le if le.get("value_in_gt_unit") is not None else st
            flag = " · judge marked it ambiguous" if base.get("status") == "ambiguous" else ""
            out.append(f'<li><b>{LABEL[v]}</b> {" · ".join(parts)} · {off_text(base)}{flag}</li>')
            for name, j in (("lenient", le), ("strict", st)):
                if j.get("method") or j.get("notes"):
                    methods.append(f'<div><b>{LABEL[v]}, {name}:</b> {esc(j.get("method") or "")} {esc(j.get("notes") or "")}</div>')
        out.append('</ul>')
        if methods:
            out.append(f'<details class="sub3"><summary><h4>How the judges measured it</h4></summary><div class="body method">{"".join(methods)}</div></details>')
        out.append('</div>')
    out.append('</div></details>')

    # frames grid
    fr = ", ".join(str(f) for f in m["frames"])
    out.append(f'<details class="sub2" open><summary><h3>Frames side by side</h3></summary><div class="body">'
               f'<img src="media/{m["grid"]}" alt="Input and rendered frames {fr} for each prompt variant" loading="lazy">'
               f'<p class="cap">Frames {fr}. Columns: input, Blender, OpenUSD, any tool.</p></div></details>')

    # per run
    for v in LABEL:
        r = rows.get((scene, v))
        mr = m["runs"][v]
        c = (r.get("check") or {}) if r else {}
        info = c.get("info") or {}
        done = r and "render.mp4" in r["files"] and "NOTES.md" in r["files"]
        state = "finished" if done else "still running"
        out.append(f'<details class="sub2"><summary><h3>{LABEL[v]} run · {state}</h3></summary><div class="body"><ul>')
        sessions = (r.get("resumes") or 0) + 1
        out.append(f'<li><b>Solver time:</b> <span class="num">{r.get("solver_min")}</span> min of work across {sessions} session{"s" if sessions > 1 else ""} (the rest was waiting out usage limits), {r.get("commands")} shell commands.</li>')
        types = ", ".join(info.get("types") or [])
        out.append(f'<li><b>Reconstruction:</b> <span class="num">{info.get("entities")}</span> objects and parts in the manifest ({types}). Scene files {r.get("scene_size_mb")} MB.</li>')
        parts = info.get("particles") or {}
        if parts:
            pl = "; ".join(f'{k.replace(".npz","").replace("_"," ")}: {s[1]:,} particles × {s[0]} frames' for k, s in parts.items())
            out.append(f'<li><b>Liquids and grains:</b> {esc(pl)}.</li>')
        errs, warns = c.get("errors") or [], c.get("warnings") or []
        if not errs and not warns:
            out.append('<li><b>Format check:</b> <span class="ok">passed</span>.</li>')
        else:
            out.append(f'<li><b>Format check:</b> {esc("; ".join(errs + warns))}.</li>')
        out.append('</ul>')
        if mr["judge_images"]:
            out.append('<details class="sub3"><summary><h4>Judge inspection images</h4></summary><div class="body"><div class="gallery">')
            for im in mr["judge_images"]:
                qn = im["judge"].replace(scene + "-", "").upper().replace(".STRICT", " strict")
                stem = Path(im["src"]).stem.replace("_", " ")
                out.append(f'<figure><img src="media/{im["file"]}" alt="{esc(stem)}" loading="lazy"><figcaption>{esc(qn)} · {esc(stem)}</figcaption></figure>')
            out.append('</div></div></details>')
        if mr["solver_images"]:
            out.append('<details class="sub3"><summary><h4>Solver\'s own check images</h4></summary><div class="body"><div class="gallery">')
            for im in mr["solver_images"]:
                stem = Path(im["src"]).stem
                cap = f"fitted server outline over frame {int(stem.split('_')[-1])}" if "server_overlay" in stem else f"{Path(im['src']).parent.name.replace('_', ' ')}, frame {int(re.sub(r'\D', '', stem) or 0)}"
                out.append(f'<figure><img src="media/{im["file"]}" alt="{esc(cap)}" loading="lazy"><figcaption>{esc(cap)}</figcaption></figure>')
            out.append('</div></div></details>')
        notes = R / scene / v / "solver/output/NOTES.md"
        if notes.exists():
            out.append(f'<details class="sub3"><summary><h4>Solver\'s NOTES.md</h4></summary><div class="body"><pre>{esc(notes.read_text())}</pre></div></details>')
        out.append('</div></details>')
    out.append('</div></details>')

# ---------------------------------------------------------------- next
out.append('<details open><summary><h2>Stopped, not run</h2></summary><div class="body"><ul>')
out.append('<li><b>Coffee-scene judges:</b> OpenUSD strict volume, both OpenUSD mass judges, and all four any-tool judges.</li>')
out.append('<li><b>Round 2b:</b> Codex on the three difficulty anchors, and Claude Code (Opus 5.5, max effort) on the desk scene plus the three anchors.</li>')
out.append('<li>Both drivers skip finished work, so either can be restarted later without redoing anything.</li>')
out.append('</ul></div></details>')
out.append('<details><summary><h2>About these numbers</h2></summary><div class="body"><ul>')
out.append('<li>Each question is measured twice: the lenient judge counts parts that were not modelled as part of the parent object; the strict judge does not. A missing object counts as wrong in both.</li>')
out.append('<li>"% low" and "× too high" compare the lenient answer (or strict, when lenient is missing) with the ground truth.</li>')
out.append('<li>Solver and judge prompts: <a href="https://claude.ai/artifact/MBHSXJWGfvi8Dnj25iEPVF" target="_blank" rel="noopener">Round 2 prompts page</a>.</li>')
out.append(f'<li>All files are in <span class="num">{esc(str(R))}/</span>.</li>')
out.append('</ul></div></details>')
out.append('</section></div>')
out.append("""<script>
document.getElementById('collapse').onclick=()=>document.querySelectorAll('details').forEach(d=>d.open=false);
document.getElementById('expand').onclick=()=>document.querySelectorAll('details').forEach(d=>d.open=true);
</script>""")
OUT.write_text("\n".join(out))
files = {f"media/{p.name}": str(p) for p in MEDIA.iterdir() if p.suffix in (".mp4", ".jpg")}
(HERE / "files.json").write_text(json.dumps(files, indent=0))
print(OUT, len(OUT.read_text()), "bytes;", len(files), "media files")
