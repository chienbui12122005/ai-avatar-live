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
  <a href="/live">📺 Live</a>
  <a href="/playground">⚡ Playground</a>
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


def live_page(slug: str) -> str:
    """Full-bleed avatar stage: loops the profile's `idle` clip, switches to a
    freshly rendered speaking clip (with audio) when one appears, then returns to
    idle. Built to be captured by OBS (Browser Source) -> Virtual Camera -> Zoom.
    """
    s = esc(slug)
    return f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live · {s}</title>
<style>
  html,body {{ margin:0; height:100%; background:#000; overflow:hidden; }}
  #stage1, #stage2 {{ position:fixed; inset:0; width:100%; height:100%; object-fit:contain; background:#000; z-index:1; }}
  #overlay {{ position:fixed; inset:0; display:flex; align-items:center; justify-content:center;
    background:#000; color:#e6edf3; font-family:system-ui,sans-serif; cursor:pointer; z-index:10; }}
  #overlay button {{ font-size:20px; padding:14px 28px; border:0; border-radius:10px;
    background:#1f6feb; color:#fff; cursor:pointer; }}
  #badge {{ position:fixed; top:10px; left:10px; z-index:5; font-family:system-ui,sans-serif;
    font-size:12px; color:#8b949e; background:rgba(0,0,0,.4); padding:3px 9px; border-radius:12px; }}
</style></head>
<body>
<video id="stage1" playsinline></video>
<video id="stage2" playsinline style="display:none;"></video>
<div id="badge">● idle</div>
<div id="overlay"><button id="startbtn">▶ Start avatar stage</button></div>
<script>
const slug = {slug!r};
const stage1 = document.getElementById('stage1');
const stage2 = document.getElementById('stage2');
const badge = document.getElementById('badge');
const overlay = document.getElementById('overlay');

let activeVid = stage1;
let nextVid = stage2;
let lastTs = 0, speaking = false, pending = null;

// Segment-streaming state (chunked renders)
let segMode = false, segUrl = "", segUrls = [], segPlay = 0, segDone = false, segWaiting = false;

function idleSrc() {{ return `/profile-clip/${{slug}}/idle`; }}
function setBadge(t) {{ badge.textContent = t; }}

// Bind ended listeners to both elements
stage1.addEventListener('ended', onVideoEnded);
stage2.addEventListener('ended', onVideoEnded);

function swapAndPlay(loop = false, muted = false) {{
  // Pause and hide active
  activeVid.pause();
  activeVid.style.display = 'none';
  activeVid.muted = true;
  activeVid.loop = false;
  
  // Show and play next
  nextVid.style.display = 'block';
  nextVid.muted = muted;
  nextVid.loop = loop;
  nextVid.play().catch(() => {{}});
  
  // Swap references
  const tmp = activeVid;
  activeVid = nextVid;
  nextVid = tmp;
}}

function playIdle() {{
  speaking = false; segMode = false; segWaiting = false; setBadge('● idle');
  nextVid.oncanplay = null;
  nextVid.src = idleSrc();
  nextVid.load();
  swapAndPlay(true, true);
}}

function playClip(url) {{
  speaking = true; segMode = false; segWaiting = false; setBadge('● speaking');
  nextVid.oncanplay = null;
  nextVid.src = url;
  nextVid.load();
  swapAndPlay(false, false);
}}

// --- chunked streaming ---
function startSegments(url) {{
  speaking = true; segMode = true; setBadge('● speaking (stream)');
  segUrl = url; segUrls = []; segPlay = 0; segDone = false; segWaiting = false;
  pollSegments();
}}

async function pollSegments() {{
  if (!segMode) return;
  try {{
    const d = await (await fetch(segUrl)).json();
    segUrls = d.segments.map(s => s.url);
    segDone = !!d.done;
  }} catch (e) {{}}
  
  // Start segment 0 once ready and we have buffered at least 2 segments (or render is complete)
  if (segPlay === 0 && (segUrls.length >= 2 || segDone)) {{
    playNextSegment();
  }} else if (segWaiting && segPlay < segUrls.length) {{
    // Resume streaming if we were waiting
    playNextSegment();
  }}
  
  if (segMode && !(segDone && segPlay >= segUrls.length)) {{
    setTimeout(pollSegments, 600);
  }}
}}

function playNextSegment() {{
  if (segPlay < segUrls.length) {{
    segWaiting = false;
    const nextUrl = segUrls[segPlay++];
    
    // Check if nextVid is already preloaded with this URL
    const isPreloaded = nextVid.src && nextVid.src.includes(nextUrl);
    if (!isPreloaded) {{
      nextVid.oncanplay = null;
      nextVid.src = nextUrl;
      nextVid.load();
    }}
    
    const triggerPlay = () => {{
      swapAndPlay(false, false);
      
      // Pre-preload the next segment immediately if available
      if (segPlay < segUrls.length) {{
        const urlToPreload = segUrls[segPlay];
        setTimeout(() => {{
          if (segMode && !segWaiting) {{
            nextVid.oncanplay = null;
            nextVid.src = urlToPreload;
            nextVid.load();
          }}
        }}, 50);
      }}
    }};
    
    if (nextVid.readyState >= 3) {{
      triggerPlay();
    }} else {{
      nextVid.oncanplay = () => {{
        nextVid.oncanplay = null;
        triggerPlay();
      }};
    }}
  }}
}}

function onVideoEnded(e) {{
  if (e.target !== activeVid) return; // ignore events from pre-loading buffer
  
  if (segMode) {{
    if (segPlay < segUrls.length) {{
      playNextSegment();
    }} else if (segDone) {{
      playIdle();
    }} else {{
      // Render caught up, play idle loop as temporary fallback buffer
      segWaiting = true;
      setBadge('● speaking (buffering)');
      nextVid.oncanplay = null;
      nextVid.src = idleSrc();
      nextVid.load();
      swapAndPlay(true, true);
    }}
    return;
  }}
  
  if (!speaking) return;
  if (pending) {{
    const u = pending;
    pending = null;
    playClip(u);
  }} else {{
    playIdle();
  }}
}}

async function poll() {{
  try {{
    const r = await fetch(`/api/latest?profile=${{encodeURIComponent(slug)}}&since=${{lastTs}}`);
    const d = await r.json();
    if (d.job) {{
      lastTs = d.job.finished_at || lastTs;
      if (d.job.chunked) startSegments(d.job.segments_url);
      else if (speaking) pending = d.job.video_url;
      else playClip(d.job.video_url);
    }}
  }} catch (e) {{}}
  setTimeout(poll, 1500);
}}

async function start() {{
  try {{
    const r = await fetch(`/api/latest?profile=${{encodeURIComponent(slug)}}`);
    const d = await r.json();
    lastTs = d.job ? (d.job.finished_at || 0) : 0;
  }} catch (e) {{}}
  overlay.style.display = 'none';
  playIdle();
  poll();
}}
document.getElementById('startbtn').addEventListener('click', start);
</script>
</body></html>"""


def profiles_page(profiles: list[dict]) -> str:
    cards = []
    for p in profiles:
        slug = esc(p["slug"])
        clips = p.get("clips", {})
        prepared = p.get("prepared", {})
        clip_row = "".join(
            f'<span class="pill" style="{"" if b in clips else "opacity:.4"}">'
            f'{esc(b)}{" ✓" if b in clips else ""}{" ⚡" if b in prepared else ""}</span>'
            for b in BEHAVIORS
        )
        # Per-behavior controls: upload a clip + (if a clip exists) prepare its cache.
        rows = []
        for b in BEHAVIORS:
            has_clip = b in clips
            is_prep = b in prepared
            prep_btn = (
                f"""<form action="/profiles/{slug}/prepare" method="post" style="display:inline-block; margin-left:6px;">
  <input type="hidden" name="behavior" value="{esc(b)}">
  <button class="secondary" type="submit" style="padding:5px 10px;font-size:12px;" {"" if has_clip else "disabled"}>
    {"Re-prepare ⚡" if is_prep else "Prepare ⚡"}</button>
</form>"""
            )
            rows.append(
                f"""<div style="margin:6px 0;">
  <form action="/profiles/{slug}/upload" method="post" enctype="multipart/form-data" style="display:inline-block;">
    <input type="hidden" name="behavior" value="{esc(b)}">
    <b style="display:inline-block;width:74px;">{esc(b)}</b>
    <input type="file" name="clip" accept="image/*,video/*" required style="display:inline-block;width:auto;font-size:12px;">
    <button class="secondary" type="submit" style="padding:5px 10px;font-size:12px;">Set</button>
  </form>{prep_btn}
</div>"""
            )
        upload_forms = "".join(rows)
        cards.append(
            f"""<div class="card">
  <h2>{esc(p['name'])} <span class="muted">/{slug}</span></h2>
  <div class="clip-set">{clip_row}</div>
  <p class="muted" style="margin:8px 0 0;">✓ = clip uploaded · ⚡ = avatar prepared (cached → faster render)</p>
  <div style="margin-top:10px;">{upload_forms}</div>
  <form action="/profiles/{slug}/delete" method="post" style="margin-top:12px;"
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
<div class="row" style="gap:20px;">
  <form class="card" action="/profiles" method="post" style="flex:1.5; margin:0;">
    <h2>Create New Profile</h2>
    <label>New profile name</label>
    <div style="display:flex; gap:10px;">
      <input type="text" name="name" placeholder="Teacher A" required>
      <button type="submit" style="white-space:nowrap;">Create</button>
    </div>
    <p class="muted">After creating, upload a clip for each behavior ({", ".join(BEHAVIORS)}).</p>
  </form>
  
  <div class="card" style="flex:1; margin:0; display:flex; flex-direction:column; justify-content:space-between;">
    <div>
      <h2>Import Samples</h2>
      <p class="muted" style="margin-top:6px; font-size:13px;">
        Tự động tạo các Profile giáo viên từ các video mẫu có sẵn trong thư mục cài đặt của MuseTalk (như yongen.mp4, sun.mp4...).
      </p>
    </div>
    <form action="/profiles/init-sample" method="post" style="margin-top:12px;">
      <button type="submit" class="secondary" style="width:100%;">⚡ Import Samples from MuseTalk</button>
    </form>
  </div>
</div>
<div style="margin-top:20px;">
  {cards_html}
</div>
""",
    )


def playground_page(profiles: list[dict]) -> str:
    import json
    # Build JS-accessible map of which clips exist and which are prepared
    prof_map = {}
    for p in profiles:
        prof_map[p["slug"]] = {
            "name": p["name"],
            "clips": p.get("clips", {}),
            "prepared": p.get("prepared", {})
        }
    prof_map_json = json.dumps(prof_map)

    if profiles:
        opts = "".join(
            f'<option value="{esc(p["slug"])}">{esc(p["name"])}</option>' for p in profiles
        )
        profile_select = f'<select id="play-profile" name="profile" onchange="updateProfileState()">{opts}</select>'
    else:
        profile_select = (
            '<select id="play-profile" name="profile" disabled><option value="">No profiles yet</option></select>'
        )

    behavior_opts = "".join(f'<option value="{b}">{b}</option>' for b in BEHAVIORS)

    return page(
        "Realtime Playground",
        f"""
<style>
  .play-layout {{ display: flex; gap: 24px; flex-wrap: wrap; margin-top: 16px; }}
  .play-col-ctrl {{ flex: 1; min-width: 320px; display: flex; flex-direction: column; gap: 16px; }}
  .play-col-stage {{ flex: 1.2; min-width: 380px; display: flex; flex-direction: column; align-items: center; }}
  
  /* Stage Video Box */
  .stage-box {{
    width: 100%;
    position: relative;
    border-radius: 12px;
    background: #000;
    overflow: hidden;
    aspect-ratio: 16/9;
    box-shadow: 0 0 15px rgba(0, 0, 0, 0.5);
    border: 3px solid #30363d;
    transition: all 0.5s ease;
  }}
  .stage-box.idle {{ border-color: #1a7f37; box-shadow: 0 0 20px rgba(26, 127, 55, 0.25); }}
  .stage-box.streaming {{ border-color: #1f6feb; box-shadow: 0 0 25px rgba(31, 111, 235, 0.4); animation: pulse-border 2s infinite ease-in-out; }}
  .stage-box.error {{ border-color: #cf222e; box-shadow: 0 0 20px rgba(207, 34, 46, 0.45); }}
  
  #play-video1, #play-video2 {{
    position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; background: #000;
  }}
  
  .stage-badge {{
    position: absolute; top: 12px; left: 12px; z-index: 5;
    font-size: 12px; font-weight: 600; color: #fff;
    padding: 3px 10px; border-radius: 20px;
    background: rgba(0, 0, 0, 0.6); display: flex; align-items: center; gap: 6px;
  }}
  .stage-badge .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
  .stage-badge.idle .dot {{ background: #2ea043; }}
  .stage-badge.streaming .dot {{ background: #58a6ff; animation: blink 1.2s infinite; }}
  .stage-badge.error .dot {{ background: #f85149; }}
  
  @keyframes blink {{ 0%, 100% {{ opacity: 0.3; }} 50% {{ opacity: 1; }} }}
  @keyframes pulse-border {{
    0%, 100% {{ border-color: #1f6feb; }}
    50% {{ border-color: #58a6ff; }}
  }}
  
  /* Upload Area */
  .drop-zone {{
    border: 2px dashed var(--border); border-radius: 8px; padding: 24px;
    text-align: center; background: #0d1117; cursor: pointer; transition: border-color 0.2s;
  }}
  .drop-zone:hover, .drop-zone.dragover {{ border-color: var(--accent); }}
  .drop-zone input[type=file] {{ display: none; }}
  
  /* Alert Banner */
  .warn-banner {{
    background: rgba(240, 184, 0, 0.1); border: 1px solid rgba(240, 184, 0, 0.35);
    border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 13.5px;
    color: #e3b341; display: none; align-items: flex-start; gap: 8px;
  }}
  
  /* Log Console */
  .log-console {{
    background: #010409; border: 1px solid var(--border); border-radius: 8px;
    padding: 12px; font-family: monospace; font-size: 12px; color: #39ff14;
    overflow-y: auto; height: 260px; white-space: pre-wrap; word-break: break-all;
    box-shadow: inset 0 0 10px rgba(0, 255, 0, 0.05);
  }}
  
  /* Steps indicator */
  .steps-wrap {{ display: flex; justify-content: space-between; margin-top: 14px; padding: 0 4px; }}
  .step-item {{ text-align: center; font-size: 11px; color: var(--muted); flex: 1; position: relative; }}
  .step-item::after {{
    content: ""; position: absolute; top: 12px; left: 50%; width: 100%;
    height: 2px; background: var(--border); z-index: 1;
  }}
  .step-item:last-child::after {{ display: none; }}
  .step-dot {{
    width: 24px; height: 24px; border-radius: 50%; border: 2px solid var(--border);
    background: var(--card); margin: 0 auto 6px; display: flex; align-items: center;
    justify-content: center; font-weight: bold; position: relative; z-index: 2;
    transition: all 0.3s;
  }}
  .step-item.active .step-dot {{ border-color: var(--accent); color: #fff; background: var(--accent); }}
  .step-item.done .step-dot {{ border-color: #2ea043; color: #fff; background: #2ea043; }}
  .step-item.active {{ color: var(--fg); }}
  .step-item.done {{ color: #2ea043; }}
</style>

<h1>Realtime Avatar Playground ⚡</h1>
<p class="muted">Upload an audio file and see the virtual teacher lip-sync in realtime (using cache + warm model worker).</p>

<div class="play-layout">
  <!-- Controls -->
  <div class="play-col-ctrl">
    <div class="card" style="margin:0;">
      <h2>Config & Upload</h2>
      
      <!-- Warning Banner -->
      <div id="warn-banner" class="warn-banner">
        <span style="font-size:16px;">⚠️</span>
        <div>
          <b>Hành vi này chưa được chuẩn bị (Prepared)!</b><br>
          Hệ thống sẽ chạy ở chế độ Batch chậm hơn và không hỗ trợ phát livestream (streaming). 
          Vui lòng vào trang <a href="/profiles" style="color:#58a6ff;">Profiles</a> nhấn <b>Prepare ⚡</b> trước.
        </div>
      </div>
      
      <div class="row" style="gap:12px; margin-bottom:12px;">
        <div>
          <label>Teacher profile</label>
          {profile_select}
        </div>
        <div>
          <label>Behavior</label>
          <select id="play-behavior" name="behavior" onchange="updateProfileState()">{behavior_opts}</select>
        </div>
      </div>
      
      <div class="row" style="gap:12px; margin-bottom:12px;">
        <div>
          <label>bbox_shift</label>
          <input type="number" id="play-bbox" value="0">
        </div>
        <div>
          <label>Version</label>
          <select id="play-version"><option value="v15">v1.5</option><option value="v1">v1.0</option></select>
        </div>
      </div>
      
      <label>Audio File (wav, mp3)</label>
      <div id="dropzone" class="drop-zone" onclick="document.getElementById('play-audio').click()">
        <span id="dropzone-text">📁 Click or drag audio file here</span>
        <input type="file" id="play-audio" accept="audio/*" onchange="handleFileSelected(this)">
      </div>
      
      <div style="margin-top: 16px;">
        <button id="btn-stream" style="width:100%; display:flex; align-items:center; justify-content:center; gap:8px;" onclick="startGeneration()">
          🚀 Generate & Stream Realtime
        </button>
      </div>
      
      <!-- Steps Indicator -->
      <div class="steps-wrap">
        <div id="step-1" class="step-item"><div class="step-dot">1</div>Upload</div>
        <div id="step-2" class="step-item"><div class="step-dot">2</div>Worker</div>
        <div id="step-3" class="step-item"><div class="step-dot">3</div>Stream</div>
        <div id="step-4" class="step-item"><div class="step-dot">4</div>Done</div>
      </div>
    </div>
    
    <div class="card" style="margin:0;">
      <h2>Live Log Console</h2>
      <div id="play-log" class="log-console">Waiting for render request...</div>
    </div>
  </div>
  
  <!-- Stage Display -->
  <div class="play-col-stage">
    <div id="stage-wrapper" class="stage-box idle" style="position:relative;">
      <div id="badge-status" class="stage-badge idle">
        <span class="dot"></span> <span id="badge-text">Idle</span>
      </div>
      <video id="play-video1" playsinline></video>
      <video id="play-video2" playsinline style="display:none;"></video>
    </div>
    <div style="margin-top:10px; text-align:center;">
      <p id="player-desc" class="muted">Currently playing loop: <b>idle.mp4</b></p>
      <div style="display:flex; gap:10px; justify-content:center;">
        <button class="secondary" style="padding:6px 12px; font-size:13px;" onclick="toggleAudioMute()">Toggle Mute</button>
      </div>
    </div>
  </div>
</div>

<script>
const profMap = {prof_map_json};
const video1 = document.getElementById("play-video1");
const video2 = document.getElementById("play-video2");
const stageWrapper = document.getElementById("stage-wrapper");
const badgeStatus = document.getElementById("badge-status");
const badgeText = document.getElementById("badge-text");
const playerDesc = document.getElementById("player-desc");
const btnStream = document.getElementById("btn-stream");
const warnBanner = document.getElementById("warn-banner");
const logConsole = document.getElementById("play-log");

let activeVid = video1;
let nextVid = video2;

// Drag & drop handling
const dropzone = document.getElementById("dropzone");
dropzone.addEventListener("dragover", e => {{ e.preventDefault(); dropzone.classList.add("dragover"); }});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", e => {{
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files.length) {{
    document.getElementById("play-audio").files = e.dataTransfer.files;
    handleFileSelected(document.getElementById("play-audio"));
  }}
}});

function handleFileSelected(input) {{
  const name = input.files[0] ? input.files[0].name : "";
  document.getElementById("dropzone-text").innerHTML = name ? `🎵 Selected: <b>${{name}}</b>` : "📁 Click or drag audio file here";
}}

// Bind ended listeners to both elements
video1.addEventListener("ended", onVideoEnded);
video2.addEventListener("ended", onVideoEnded);

function swapAndPlay(loop = false, muted = false) {{
  // Pause and hide active
  activeVid.pause();
  activeVid.style.display = 'none';
  activeVid.muted = true;
  activeVid.loop = false;
  
  // Show and play next
  nextVid.style.display = 'block';
  nextVid.muted = muted;
  nextVid.loop = loop;
  nextVid.play().catch(() => {{}});
  
  // Swap references
  const tmp = activeVid;
  activeVid = nextVid;
  nextVid = tmp;
}}

// Initialize and update profile selection video state
function updateProfileState() {{
  const slug = document.getElementById("play-profile").value;
  const behavior = document.getElementById("play-behavior").value;
  
  if (!slug) return;
  const prof = profMap[slug];
  if (!prof) return;
  
  // Show warning banner if behavior not prepared
  const isPrepared = prof.prepared && prof.prepared[behavior];
  warnBanner.style.display = isPrepared ? "none" : "flex";
  
  // Load idle/preview video in player if available
  const hasClip = prof.clips && prof.clips[behavior];
  if (hasClip) {{
    activeVid.oncanplay = null;
    activeVid.src = `/profile-clip/${{slug}}/${{behavior}}`;
    activeVid.loop = true;
    activeVid.muted = true;
    activeVid.play().catch(() => {{}});
    playerDesc.innerHTML = `Currently previewing behavior: <b>${{behavior}}</b>`;
  }} else {{
    // Fallback to idle clip if the requested behavior clip doesn't exist
    const hasIdle = prof.clips && prof.clips["idle"];
    if (hasIdle) {{
      activeVid.oncanplay = null;
      activeVid.src = `/profile-clip/${{slug}}/idle`;
      activeVid.loop = true;
      activeVid.muted = true;
      activeVid.play().catch(() => {{}});
      playerDesc.innerHTML = `No clip for ${{behavior}}, previewing: <b>idle</b>`;
    }} else {{
      activeVid.removeAttribute("src");
      playerDesc.innerHTML = `<span style="color:#cf222e">Please upload behavior clips for this profile!</span>`;
    }}
  }}
}}

function toggleAudioMute() {{
  activeVid.muted = !activeVid.muted;
}}

// Streaming Playback State
let playMode = "idle"; // idle, streaming, playing_full
let segmentsList = [];
let playedIndex = 0;
let streamingFinished = false;
let isPlayingSegment = false;
let pollTimeout = null;
let statusInterval = null;
let segWaiting = false;

function setStageState(state, text) {{
  playMode = state;
  stageWrapper.className = `stage-box ${{state}}`;
  badgeStatus.className = `stage-badge ${{state}}`;
  badgeText.textContent = text;
}}

function updateStepStatus(stepNum, status) {{
  const el = document.getElementById(`step-${{stepNum}}`);
  if (!el) return;
  el.className = `step-item ${{status}}`;
}}

function resetSteps() {{
  for(let i=1; i<=4; i++) updateStepStatus(i, "");
}}

async function startGeneration() {{
  const profile = document.getElementById("play-profile").value;
  const behavior = document.getElementById("play-behavior").value;
  const audioFile = document.getElementById("play-audio").files[0];
  const bboxShift = document.getElementById("play-bbox").value;
  const version = document.getElementById("play-version").value;
  
  if (!profile) {{ alert("Please choose a teacher profile."); return; }}
  if (!audioFile) {{ alert("Please select or drag an audio file first."); return; }}
  
  // Reset streaming state variables
  segmentsList = [];
  playedIndex = 0;
  streamingFinished = false;
  isPlayingSegment = false;
  segWaiting = false;
  if (pollTimeout) clearTimeout(pollTimeout);
  if (statusInterval) clearInterval(statusInterval);
  
  resetSteps();
  updateStepStatus(1, "done");
  updateStepStatus(2, "active");
  
  btnStream.disabled = true;
  btnStream.textContent = "⌛ Rendering...";
  logConsole.textContent = "Sending request to server...";
  setStageState("streaming", "Generating...");
  
  const formData = new FormData();
  formData.append("profile", profile);
  formData.append("behavior", behavior);
  formData.append("audio", audioFile);
  formData.append("bbox_shift", bboxShift);
  formData.append("version", version);
  
  try {{
    const res = await fetch("/api/generate", {{
      method: "POST",
      body: formData
    }});
    const data = await res.json();
    
    if (data.error) {{
      throw new Error(data.error);
    }}
    
    logConsole.textContent = `Job created: ${{data.job_id}}\nWaiting for worker output...`;
    
    // Start polling job status/logs
    statusInterval = setInterval(() => pollJobStatus(data.job_id), 1200);
    
    if (data.chunked) {{
      // Worker supports streaming chunking! We can poll and play segments immediately
      updateStepStatus(2, "done");
      updateStepStatus(3, "active");
      pollSegments(data.segments_url);
    }} else {{
      // Full render mode (Batch or realtime without chunks): must wait until complete
      logConsole.textContent += `\nNo chunking enabled. Waiting for full rendering...`;
    }}
    
  }} catch (err) {{
    logConsole.textContent = `[ERROR] ${{err.message || err}}`;
    btnStream.disabled = false;
    btnStream.textContent = "🚀 Generate & Stream Realtime";
    setStageState("error", "Error");
    resetSteps();
  }}
}}

async function pollJobStatus(jobId) {{
  try {{
    const res = await fetch(`/job/${{jobId}}/status`);
    const statusData = await res.json();
    
    logConsole.textContent = statusData.log || "No logs yet...";
    logConsole.scrollTop = logConsole.scrollHeight;
    
    if (statusData.status === "done") {{
      clearInterval(statusInterval);
      
      // If we are not chunked, play the full video now
      if (!statusData.chunked) {{
        updateStepStatus(2, "done");
        updateStepStatus(3, "done");
        updateStepStatus(4, "done");
        
        btnStream.disabled = false;
        btnStream.textContent = "🚀 Generate & Stream Realtime";
        
        playFullResult(`/video/${{jobId}}`);
      }} else {{
        streamingFinished = true; // Signals chunked stream that all slices are rendered
      }}
    }} else if (statusData.status === "failed") {{
      clearInterval(statusInterval);
      btnStream.disabled = false;
      btnStream.textContent = "🚀 Generate & Stream Realtime";
      setStageState("error", "Failed");
      logConsole.textContent += `\n[Job Failed] ${{statusData.error || ""}}`;
    }}
  }} catch (e) {{}}
}}

// Chunked Streaming logic
async function pollSegments(segmentsUrl) {{
  if (playMode !== "streaming") return;
  try {{
    const res = await fetch(segmentsUrl);
    const data = await res.json();
    segmentsList = data.segments.map(s => s.url);
    
    if (data.done) {{
      streamingFinished = true;
    }}
  }} catch (e) {{}}
  
  if (playedIndex === 0 && (segmentsList.length >= 2 || streamingFinished)) {{
    advanceSegment();
  }} else if (segWaiting && playedIndex < segmentsList.length) {{
    advanceSegment();
  }}
  
  // Continue polling unless finished and all segments played
  if (!(streamingFinished && playedIndex >= segmentsList.length)) {{
    pollTimeout = setTimeout(() => pollSegments(segmentsUrl), 600);
  }}
}}

function advanceSegment() {{
  if (playedIndex < segmentsList.length) {{
    isPlayingSegment = true;
    segWaiting = false;
    const url = segmentsList[playedIndex++];
    
    setStageState("streaming", `Playing segment ${{playedIndex}}...`);
    playerDesc.innerHTML = `Streaming segment <b>${{playedIndex}}</b>`;
    
    const isPreloaded = nextVid.src && nextVid.src.includes(url);
    if (!isPreloaded) {{
      nextVid.oncanplay = null;
      nextVid.src = url;
      nextVid.load();
    }}
    
    const triggerPlay = () => {{
      swapAndPlay(false, false);
      
      // Pre-buffer next segment
      if (playedIndex < segmentsList.length) {{
        const urlToPreload = segmentsList[playedIndex];
        setTimeout(() => {{
          if (playMode === "streaming" && isPlayingSegment) {{
            nextVid.oncanplay = null;
            nextVid.src = urlToPreload;
            nextVid.load();
          }}
        }}, 50);
      }}
    }};
    
    if (nextVid.readyState >= 3) {{
      triggerPlay();
    }} else {{
      nextVid.oncanplay = () => {{
        nextVid.oncanplay = null;
        triggerPlay();
      }};
    }}
  }} else if (streamingFinished) {{
    // Finished everything! Return to idle
    finishStreaming();
  }} else {{
    // Rendering is slower than playing, play idle loop temporarily (fallback buffer)
    isPlayingSegment = false;
    segWaiting = true;
    setStageState("streaming", "Buffering next segment...");
    
    const slug = document.getElementById("play-profile").value;
    nextVid.oncanplay = null;
    nextVid.src = `/profile-clip/${{slug}}/idle`;
    nextVid.load();
    swapAndPlay(true, true);
  }}
}}

function finishStreaming() {{
  isPlayingSegment = false;
  btnStream.disabled = false;
  btnStream.textContent = "🚀 Generate & Stream Realtime";
  
  updateStepStatus(3, "done");
  updateStepStatus(4, "done");
  
  alert("Realtime lip-sync finished successfully!");
  
  setStageState("idle", "Idle");
  updateProfileState();
}}

// Handle segment end transition
function onVideoEnded(e) {{
  if (e.target !== activeVid) return; // ignore events from pre-loading buffer
  if (playMode === "streaming" && segmentsList.length > 0) {{
    advanceSegment();
  }}
}}

function playFullResult(videoUrl) {{
  setStageState("streaming", "Playing complete video...");
  playerDesc.innerHTML = `Playing completed full video clip.`;
  
  nextVid.oncanplay = null;
  nextVid.src = videoUrl;
  nextVid.load();
  swapAndPlay(false, false);
  
  // Listen for full clip ended to return to idle
  activeVid.onended = () => {{
    activeVid.onended = null;
    setStageState("idle", "Idle");
    updateProfileState();
  }};
}}

// Initialize page
if (document.readyState === "loading") {{
  document.addEventListener("DOMContentLoaded", () => {{
    updateProfileState();
  }});
}} else {{
  updateProfileState();
}}
</script>
""",
    )
