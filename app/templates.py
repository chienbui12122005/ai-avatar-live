"""HTML rendering. Kept out of main.py so routes stay thin.

Plain f-strings + a shared page wrapper — no template engine dependency.
All user-supplied values are passed through ``esc`` (html.escape).
"""

import html
import time
from typing import Optional

from app.jobs import Job
from app.profiles import BEHAVIORS

STATUS_COLORS = {
    "pending": "#8a6d3b",
    "running": "#1f6feb",
    "done": "#1a7f37",
    "failed": "#cf222e",
}


def esc(s) -> str:
    return html.escape(str(s))


def _fmt_time(ts: Optional[float]) -> str:
    if not ts:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
  :root {{ --bg:#0d1117; --card:#161b22; --border:#30363d; --fg:#e6edf3; --muted:#8b949e; --accent:#1f6feb; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; background:var(--bg); color:var(--fg); margin:0; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:24px 20px 60px; }}
  header nav {{ display:flex; gap:18px; padding:14px 20px; border-bottom:1px solid var(--border); background:var(--card); }}
  header nav a {{ color:var(--fg); text-decoration:none; font-weight:600; }}
  header nav a:hover {{ color:var(--accent); }}
  h1 {{ font-size:22px; }} h2 {{ font-size:18px; }}
  a {{ color:#58a6ff; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:18px 20px; margin:16px 0; }}
  label {{ display:block; font-size:13px; color:var(--muted); margin:12px 0 4px; }}
  input, select, button, textarea {{ font:inherit; }}
  input[type=text], input[type=number], input[type=file], select {{
    width:100%; padding:9px 10px; background:#0d1117; color:var(--fg);
    border:1px solid var(--border); border-radius:7px; }}
  button {{ background:var(--accent); color:#fff; border:0; border-radius:7px; padding:10px 18px; font-weight:600; cursor:pointer; }}
  button.secondary {{ background:#21262d; border:1px solid var(--border); }}
  button.danger {{ background:#21262d; color:#f85149; border:1px solid var(--border); }}
  button:hover {{ filter:brightness(1.1); }}
  table {{ width:100%; border-collapse:collapse; }}
  th, td {{ text-align:left; padding:9px 10px; border-bottom:1px solid var(--border); font-size:14px; vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; }}
  .badge {{ display:inline-block; padding:2px 10px; border-radius:20px; color:#fff; font-size:12px; font-weight:600; }}
  pre.log {{ background:#010409; border:1px solid var(--border); border-radius:8px; padding:14px;
    overflow:auto; max-height:480px; font-size:12.5px; line-height:1.45; white-space:pre-wrap; word-break:break-word; }}
  .muted {{ color:var(--muted); font-size:13px; }}
  .row {{ display:flex; gap:24px; flex-wrap:wrap; }}
  .row > * {{ flex:1; min-width:260px; }}
  video {{ width:100%; border-radius:8px; background:#000; }}
  .pill {{ display:inline-block; background:#21262d; border:1px solid var(--border); border-radius:20px; padding:2px 10px; font-size:12px; margin:2px 4px 2px 0; }}
  .clip-set {{ background:#0d1117; border:1px solid var(--border); border-radius:8px; padding:6px 10px; }}
</style>
</head>
<body>
<header><nav>
  <a href="/">🎬 Generate</a>
  <a href="/videos">📁 Videos</a>
  <a href="/profiles">👤 Profiles</a>
  <a href="/health">⚙ Health</a>
</nav></header>
<div class="wrap">
{body}
</div>
</body>
</html>"""


def status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#6e7681")
    return f'<span class="badge" style="background:{color}">{esc(status)}</span>'


def home(profiles: list[dict]) -> str:
    if profiles:
        opts = "".join(
            f'<option value="{esc(p["slug"])}">{esc(p["name"])}</option>' for p in profiles
        )
        profile_select = f'<select name="profile"><option value="">— none —</option>{opts}</select>'
    else:
        profile_select = (
            '<select name="profile" disabled><option>No profiles yet</option></select>'
            '<div class="muted">Create one on the <a href="/profiles">Profiles</a> page.</div>'
        )
    behavior_opts = "".join(f'<option value="{b}">{b}</option>' for b in BEHAVIORS)

    return page(
        "Generate",
        f"""
<h1>AI Teacher Avatar</h1>
<form class="card" action="/generate" method="post" enctype="multipart/form-data">
  <div class="row">
    <div>
      <h2>Option A — Use a profile</h2>
      <label>Teacher profile</label>
      {profile_select}
      <label>Behavior</label>
      <select name="behavior">{behavior_opts}</select>
    </div>
    <div>
      <h2>Option B — Upload a clip</h2>
      <label>Teacher image/video (overrides profile)</label>
      <input type="file" name="teacher_file" accept="image/*,video/*">
    </div>
  </div>
  <hr style="border-color:var(--border); margin:20px 0;">
  <div class="row">
    <div>
      <label>Audio (wav/mp3) — blank uses default</label>
      <input type="file" name="audio_file" accept="audio/*">
    </div>
    <div>
      <label>bbox_shift</label>
      <input type="number" name="bbox_shift" value="0">
    </div>
    <div>
      <label>MuseTalk version</label>
      <select name="version"><option value="v15">v1.5</option><option value="v1">v1.0</option></select>
    </div>
  </div>
  <p style="margin-top:18px;"><button type="submit">Generate Avatar Video</button></p>
  <p class="muted">Pick a profile + behavior, or upload a clip. Uploading a clip overrides the profile.</p>
</form>
""",
    )


def job_page(job: Job) -> str:
    src = job.profile and f"profile <b>{esc(job.profile)}</b> / {esc(job.behavior)}" or esc(job.teacher_name)
    video_block = ""
    if job.status == "done":
        video_block = f"""
<div class="card" id="video-card">
  <h2>Result</h2>
  <video controls autoplay src="/video/{esc(job.id)}"></video>
  <p><a href="/video/{esc(job.id)}" download>Download MP4</a></p>
</div>"""

    return page(
        f"Job {job.id}",
        f"""
<h1>Render job <code>{esc(job.id)}</code> <span id="status">{status_badge(job.status)}</span></h1>
<div class="card">
  <table>
    <tr><th>Source</th><td>{src}</td></tr>
    <tr><th>Audio</th><td>{esc(job.audio_name or "(default)")}</td></tr>
    <tr><th>Version / bbox_shift</th><td>{esc(job.version)} / {esc(job.bbox_shift)}</td></tr>
    <tr><th>Render time</th><td id="rendertime">—</td></tr>
    <tr><th>Error</th><td id="error" style="color:#f85149"></td></tr>
  </table>
</div>
<div class="card">
  <h2>Live log</h2>
  <pre class="log" id="log">(waiting for output…)</pre>
</div>
<div id="result-slot">{video_block}</div>

<script>
const jobId = {job.id!r};
let done = false;
function fmtDur(s) {{ if (s==null) return "—"; s=Math.round(s); const m=Math.floor(s/60); return m? m+"m "+(s%60)+"s" : s+"s"; }}
async function poll() {{
  if (done) return;
  try {{
    const r = await fetch(`/job/${{jobId}}/status`);
    const d = await r.json();
    document.getElementById("status").innerHTML = d.status_badge;
    document.getElementById("log").textContent = d.log || "(no output yet)";
    document.getElementById("log").scrollTop = document.getElementById("log").scrollHeight;
    document.getElementById("rendertime").textContent = fmtDur(d.render_seconds);
    if (d.error) document.getElementById("error").textContent = d.error;
    if (d.status === "done" || d.status === "failed") {{
      done = true;
      if (d.status === "done" && d.has_video && !document.getElementById("video-card")) {{
        document.getElementById("result-slot").innerHTML =
          `<div class="card" id="video-card"><h2>Result</h2>`+
          `<video controls autoplay src="/video/${{jobId}}"></video>`+
          `<p><a href="/video/${{jobId}}" download>Download MP4</a></p></div>`;
      }}
    }}
  }} catch (e) {{}}
  if (!done) setTimeout(poll, 1500);
}}
poll();
</script>
""",
    )


def videos_page(rows_data: list[dict]) -> str:
    if rows_data:
        rows = "".join(
            f"""<tr>
  <td><code>{esc(r['job_id'])}</code></td>
  <td>{esc(r['file'])}</td>
  <td>{esc(r['size'])}</td>
  <td>{esc(r['mtime'])}</td>
  <td>
    <a href="/result/{esc(r['job_id'])}">View</a> ·
    <a href="/video/{esc(r['job_id'])}" download>Download</a>
    <form action="/videos/{esc(r['job_id'])}/delete" method="post" style="display:inline"
      onsubmit="return confirm('Delete job {esc(r['job_id'])}?')">
      <button class="danger" type="submit" style="padding:3px 10px;font-size:12px;">Delete</button>
    </form>
  </td>
</tr>"""
            for r in rows_data
        )
    else:
        rows = '<tr><td colspan="5" class="muted">No videos yet</td></tr>'

    return page(
        "Videos",
        f"""
<h1>Generated videos</h1>
<div class="card">
  <table>
    <tr><th>Job</th><th>File</th><th>Size</th><th>Created</th><th>Action</th></tr>
    {rows}
  </table>
</div>
""",
    )


def result_page(job_id: str) -> str:
    return page(
        f"Result {job_id}",
        f"""
<h1>Video <code>{esc(job_id)}</code></h1>
<div class="card">
  <video controls autoplay src="/video/{esc(job_id)}"></video>
  <p><a href="/video/{esc(job_id)}" download>Download MP4</a> · <a href="/videos">All videos</a> · <a href="/">Generate another</a></p>
</div>
""",
    )


def profiles_page(profiles: list[dict]) -> str:
    cards = []
    for p in profiles:
        clips = p.get("clips", {})
        clip_row = "".join(
            f'<span class="pill" style="{"" if b in clips else "opacity:.4"}">{esc(b)}{" ✓" if b in clips else ""}</span>'
            for b in BEHAVIORS
        )
        upload_forms = "".join(
            f"""<form action="/profiles/{esc(p['slug'])}/upload" method="post" enctype="multipart/form-data" style="display:inline-block; margin:4px 6px 0 0;">
  <input type="hidden" name="behavior" value="{esc(b)}">
  <input type="file" name="clip" accept="image/*,video/*" required style="display:inline-block;width:auto;font-size:12px;">
  <button class="secondary" type="submit" style="padding:5px 10px;font-size:12px;">Set {esc(b)}</button>
</form>"""
            for b in BEHAVIORS
        )
        cards.append(
            f"""<div class="card">
  <h2>{esc(p['name'])} <span class="muted">/{esc(p['slug'])}</span></h2>
  <div class="clip-set">{clip_row}</div>
  <div style="margin-top:10px;">{upload_forms}</div>
  <form action="/profiles/{esc(p['slug'])}/delete" method="post" style="margin-top:12px;"
    onsubmit="return confirm('Delete profile {esc(p['name'])}?')">
    <button class="danger" type="submit" style="padding:4px 12px;font-size:12px;">Delete profile</button>
  </form>
</div>"""
        )
    cards_html = "".join(cards) if cards else '<p class="muted">No profiles yet.</p>'

    return page(
        "Profiles",
        f"""
<h1>Teacher profiles</h1>
<form class="card" action="/profiles" method="post">
  <label>New profile name</label>
  <div style="display:flex; gap:10px;">
    <input type="text" name="name" placeholder="Teacher A" required>
    <button type="submit" style="white-space:nowrap;">Create</button>
  </div>
  <p class="muted">After creating, upload a clip for each behavior ({", ".join(BEHAVIORS)}).</p>
</form>
{cards_html}
""",
    )
