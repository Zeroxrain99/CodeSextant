"""Self-contained dashboard served by the daemon's ``GET /`` endpoint.

The same HTML document can run in a browser, a Tauri webview, or an IDE webview.
It uses inline CSS and JavaScript so it works without a network connection.
Dynamic data comes from the daemon's existing endpoints. ``render_panel()``
returns static HTML without server-side interpolation.
"""
from __future__ import annotations

# Pure static skeleton: every dynamic value is filled in by the <script> below
# after it fetches the same-origin endpoints.
_PANEL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CodeSextant · Code Map Overview</title>
<style>
  :root {
    --bg:#0a0e14; --card:#141a22; --card2:#0f141b; --border:#232b36;
    --fg:#e6edf3; --dim:#8b949e; --faint:#5b6573;
    --accent:#2dd4bf; --accent-dim:#1c8c7f;
    --ok:#3fb950; --warn:#d29922; --err:#f85149;
    --mono:ui-monospace,"Cascadia Code","Consolas","Sarasa Mono TC",monospace;
    --sans:"Segoe UI","Microsoft JhengHei",system-ui,sans-serif;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--fg); font-family:var(--sans);
    font-size:14px; line-height:1.55; -webkit-font-smoothing:antialiased;
  }
  .wrap { max-width:1120px; margin:0 auto; padding:24px 20px 64px; }
  header { display:flex; align-items:center; gap:14px; margin-bottom:6px; }
  .logo {
    width:34px; height:34px; border-radius:8px; flex:none;
    background:linear-gradient(135deg,var(--accent),var(--accent-dim));
    display:flex; align-items:center; justify-content:center;
    font-weight:700; color:#04201c; font-size:18px;
  }
  h1 { font-size:20px; margin:0; font-weight:650; letter-spacing:.5px; }
  h1 small { color:var(--dim); font-weight:400; font-size:13px; margin-left:8px; }
  .badge {
    margin-left:auto; display:inline-flex; align-items:center; gap:7px;
    padding:5px 12px; border-radius:999px; font-size:12.5px; font-weight:600;
    border:1px solid var(--border); background:var(--card);
  }
  .dot { width:9px; height:9px; border-radius:50%; background:var(--faint); }
  .dot.ok { background:var(--ok); box-shadow:0 0 8px var(--ok); }
  .dot.err { background:var(--err); box-shadow:0 0 8px var(--err); }
  .sub { color:var(--dim); font-size:12.5px; margin:2px 0 22px; }
  .card {
    background:var(--card); border:1px solid var(--border); border-radius:12px;
    padding:18px 20px; margin-bottom:18px;
  }
  .card h2 {
    font-size:14px; margin:0 0 14px; color:var(--dim); font-weight:600;
    text-transform:none; letter-spacing:.3px;
    display:flex; align-items:center; gap:8px;
  }
  .card h2 .n { color:var(--accent); font-family:var(--mono); }
  .grid {
    display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px 22px;
  }
  .kv { display:flex; flex-direction:column; gap:2px; }
  .kv .k { color:var(--faint); font-size:11.5px; }
  .kv .v { font-family:var(--mono); font-size:13px; word-break:break-all; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--border); }
  th { color:var(--faint); font-weight:600; font-size:11.5px; white-space:nowrap; }
  td.num { font-family:var(--mono); text-align:right; color:var(--fg); }
  td.path { font-family:var(--mono); font-size:12px; word-break:break-all; max-width:380px; }
  tr.gone td.path { color:var(--err); }
  .tag {
    display:inline-block; font-size:10.5px; padding:1px 7px; border-radius:5px;
    background:var(--card2); border:1px solid var(--border); color:var(--dim); margin-left:6px;
  }
  .tag.gone { color:var(--err); border-color:#5a2622; }
  button {
    font-family:var(--sans); font-size:12px; cursor:pointer; color:var(--fg);
    background:var(--card2); border:1px solid var(--border); border-radius:7px;
    padding:5px 11px; transition:.12s;
  }
  button:hover:not(:disabled) { border-color:var(--accent); color:var(--accent); }
  button:disabled { opacity:.4; cursor:not-allowed; }
  button.primary { background:var(--accent-dim); border-color:var(--accent-dim); color:#eafffb; }
  button.primary:hover:not(:disabled) { background:var(--accent); color:#04201c; }
  .actions { display:flex; gap:6px; flex-wrap:wrap; }
  .toolbar { display:flex; gap:8px; align-items:center; margin-bottom:14px; }
  .toolbar .spacer { margin-left:auto; }
  input[type=text], input[type=number] {
    font-family:var(--mono); font-size:12.5px; color:var(--fg);
    background:var(--card2); border:1px solid var(--border); border-radius:7px; padding:6px 9px;
  }
  input:focus { outline:none; border-color:var(--accent); }
  .detail { background:var(--card2); border-radius:8px; padding:12px 14px; margin:2px 0 4px; }
  .detail .row { display:flex; justify-content:space-between; gap:12px; padding:3px 0;
    font-family:var(--mono); font-size:12px; border-bottom:1px dashed var(--border); }
  .detail .row:last-child { border-bottom:none; }
  .detail .rk { color:var(--accent); }
  .muted { color:var(--faint); }
  .empty { color:var(--faint); text-align:center; padding:26px; font-size:13px; }
  .err-line { color:var(--err); font-size:12.5px; font-family:var(--mono); }
  .hint { color:var(--faint); font-size:11.5px; margin-top:8px; }
  a { color:var(--accent); text-decoration:none; }
  .spin { display:inline-block; width:11px; height:11px; border:2px solid var(--border);
    border-top-color:var(--accent); border-radius:50%; animation:s .7s linear infinite; vertical-align:-1px; }
  @keyframes s { to { transform:rotate(360deg); } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="logo">CS</div>
    <h1>CodeSextant <small>Code Map Overview</small></h1>
    <span class="badge"><span id="hdot" class="dot"></span><span id="hstat">Connecting…</span></span>
  </header>
  <div class="sub">A local code map shared by AI coding agents and developers. Projects stay on this machine.</div>

  <div class="card">
    <h2>Service status</h2>
    <div id="health" class="grid"><div class="muted">Loading <span class="spin"></span></div></div>
  </div>

  <div class="card">
    <h2>Indexed projects <span class="n" id="pcount">&mdash;</span></h2>
    <div class="toolbar">
      <span class="muted" id="dbdir"></span>
      <span class="spacer"></span>
      <button onclick="loadAll()">↻ Refresh</button>
    </div>
    <div id="projects"><div class="empty">Loading <span class="spin"></span></div></div>
    <div class="hint">"Reindex" updates changed files. "Map" lists the most important symbols that fit the token budget. "References" shows callers for a symbol.</div>
  </div>

  <div class="card">
    <h2>Markdown link check <span class="n" id="lgstat">&mdash;</span></h2>
    <div class="toolbar">
      <span class="muted">Scan configured Markdown namespaces for dangling wiki links and unindexed nodes. The scan is read-only.</span>
      <span class="spacer"></span>
      <button class="primary" onclick="loadLinks()">Scan</button>
    </div>
    <div id="linkgraph"><div class="empty">Press "Scan" to run the check.</div></div>
    <div class="hint">Dangling links point to missing nodes. Unindexed nodes are advisory and are never deleted.</div>
  </div>

  <div class="sub muted" style="text-align:center;margin-top:28px">
    CodeSextant daemon · <span id="footport"></span> · This panel is served by the daemon's <code>GET /</code> and can be embedded in a Tauri shell or an IDE extension webview.
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"'`]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;","`":"&#96;"}[c]));

function fmtTime(epoch) {
  if (!epoch) return "-";
  const d = new Date(epoch * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function fmtUptime(sec) {
  if (sec == null) return "-";
  sec = Math.floor(sec);
  if (sec < 60) return sec + "s";
  if (sec < 3600) return Math.floor(sec/60) + "m " + (sec%60) + "s";
  return Math.floor(sec/3600) + "h " + Math.floor((sec%3600)/60) + "m";
}

async function api(path, opts) {
  const session = sessionStorage.getItem("codesextant.session");
  const headers = new Headers((opts && opts.headers) || {});
  if (session) headers.set("X-CodeSextant-Session", session);
  const r = await fetch(path, {...(opts || {}), headers});
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) {
    throw new Error("Dashboard session missing or expired. Run `codesextant gui` to open a new session.");
  }
  if (!r.ok) throw new Error(data.error || (r.status + " " + r.statusText));
  return data;
}

async function loadHealth() {
  try {
    const h = await api("/health");
    $("hdot").className = "dot ok";
    $("hstat").textContent = h["status_text"] || "Ready";
    $("footport").textContent = "127.0.0.1:" + h.port;
    const rows = [
      ["Product / service", (h.product||"CodeSextant") + " / " + (h.service||"codesextant")],
      ["Process PID", h.pid],
      ["Port", h.port],
      ["Uptime", fmtUptime(h.uptime_sec)],
      ["Engine version", h.engine_version || "-"],
      ["Database directory", h["db_dir"]],
      ["Log file", h["log_file"]],
    ];
    $("health").innerHTML = rows.map(([k,v]) =>
      `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join("");
  } catch (e) {
    $("hdot").className = "dot err";
    $("hstat").textContent = "Offline";
    $("health").innerHTML = `<div class="err-line">Cannot reach the daemon: ${esc(e.message)}</div>`;
  }
}

async function loadProjects() {
  try {
    const d = await api("/projects");
    $("pcount").textContent = d.count;
    $("dbdir").textContent = "Database directory: " + d.db_dir;
    window.__projects = d.projects;
    if (!d.projects.length) {
      $("projects").innerHTML = `<div class="empty">No projects indexed yet. One will appear here once any agent triggers codesextant (or calls /reindex).</div>`;
      return;
    }
    const head = `<tr><th>Project path</th><th>Files</th><th>Symbols</th><th>Reference edges</th><th>Last indexed</th><th>Actions</th></tr>`;
    // Key each row by project_key (a sha1: unique per machine and independent of
    // position), so no reordering can misalign a row. This matches the project's
    // "one sha1 database per project, never crossed" discipline. A positional
    // index would point at the wrong project after a background refresh.
    const body = d.projects.map((p) => {
      if (p.error) {
        return `<tr><td class="path">${esc(p.db_file)}</td><td colspan="5" class="err-line">${esc(p.error)}</td></tr>`;
      }
      const k = esc(p.project_key);
      const gone = p.path_exists === false;
      const pathCell = esc(p.repo_path || p.db_file) + (gone ? `<span class="tag gone">path no longer exists</span>` : "");
      const acts = `<div class="actions">
        <button class="primary" data-act="reindex" data-key="${k}" ${gone?"disabled":""}>Reindex</button>
        <button data-act="map" data-key="${k}" ${gone?"disabled":""}>Map</button>
        <button data-act="refs" data-key="${k}" ${gone?"disabled":""}>References</button>
      </div>`;
      return `<tr class="${gone?"gone":""}">
        <td class="path">${pathCell}</td>
        <td class="num" id="files-${k}">${p.indexed_files}</td>
        <td class="num" id="syms-${k}">${p.symbols}</td>
        <td class="num" id="refs-${k}">${p.refs}</td>
        <td class="num muted" id="time-${k}">${fmtTime(p.last_indexed_at)}</td>
        <td>${acts}</td></tr>
        <tr id="detail-${k}" style="display:none"><td colspan="6"><div class="detail" id="detailbox-${k}"></div></td></tr>`;
    }).join("");
    $("projects").innerHTML = `<table>${head}${body}</table>`;
    $("projects").querySelectorAll("button[data-act]").forEach(b => {
      b.onclick = () => onAction(b.dataset.act, b.dataset.key, b);
    });
  } catch (e) {
    $("projects").innerHTML = `<div class="err-line">Failed to load the project list: ${esc(e.message)}</div>`;
  }
}

function projByKey(key) { return (window.__projects || []).find(x => x.project_key === key); }

function showDetail(key, html) {
  const row = $("detail-" + key), box = $("detailbox-" + key);
  if (box) box.innerHTML = html;
  if (row) row.style.display = "";
}

async function refreshRowStats(key) {
  // After a reindex, update only this row's numbers instead of rebuilding the whole
  // table. That keeps other expanded detail panes open, and keeps the "reindex
  // complete" message that was just shown on this row (rebuilding the table would
  // wipe it; M4).
  try {
    const d = await api("/projects");
    window.__projects = d.projects;
    const p = d.projects.find(x => x.project_key === key);
    if (!p || p.error) return;
    const set = (id, v) => { const el = $(id + "-" + key); if (el) el.textContent = v; };
    set("files", p.indexed_files); set("syms", p.symbols);
    set("refs", p.refs); set("time", fmtTime(p.last_indexed_at));
  } catch (e) { /* a failed partial refresh must not disturb the completion message already shown */ }
}

async function onAction(act, key, btn) {
  const p = projByKey(key);
  if (!p) return;
  if (act === "reindex") {
    const old = btn.textContent; btn.disabled = true; btn.innerHTML = 'Reindexing <span class="spin"></span>';
    try {
      const r = await api("/reindex", { method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ project: p.repo_path }) });
      showDetail(key, `<div class="row"><span class="rk">Reindex complete</span><span>${r.indexed} files indexed · ${r.skipped} skipped · ${r.removed} removed · ${r.symbols_total} symbols · ${r.elapsed_sec}s</span></div>`);
      await refreshRowStats(key);
    } catch (e) { showDetail(key, `<div class="err-line">Reindex failed: ${esc(e.message)}</div>`); }
    finally { btn.disabled = false; btn.textContent = old; }
  } else if (act === "map") {
    showDetail(key, `<span class="muted">Loading map <span class="spin"></span></span>`);
    try {
      const r = await api(`/get_map?project=${encodeURIComponent(p.repo_path)}&budget=8000`);
      const note = r.note ? `<div class="hint">${esc(r.note)}</div>` : "";
      const rows = (r.symbols||[]).map(s =>
        `<div class="row"><span class="rk">${esc(s.kind)} ${esc(s.name)}</span><span class="muted">${esc(shortPath(s.path, p.repo_path))}:${s.line}</span></div>`).join("");
      showDetail(key, `<div class="muted" style="margin-bottom:6px">Top ${r.count} symbols by importance (about ${r.approx_tokens} tokens)</div>${rows||'<div class="muted">None</div>'}${note}`);
    } catch (e) { showDetail(key, `<div class="err-line">Failed to load the map: ${esc(e.message)}</div>`); }
  } else if (act === "refs") {
    showDetail(key, `<div style="display:flex;gap:8px;align-items:center">
      <input type="text" id="sym-${key}" placeholder="symbol name (e.g. check)" style="flex:1">
      <button class="primary" id="symgo-${key}">Find</button></div>
      <div id="symres-${key}" class="hint">Enter a function or class name to see which files call it.</div>`);
    const go = async () => {
      const sym = $("sym-"+key).value.trim();
      if (!sym) return;
      const res = $("symres-"+key); res.innerHTML = `<span class="muted">jedi is resolving <span class="spin"></span></span>`;
      try {
        const r = await api("/find_references", { method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({ project: p.repo_path, symbol: sym }) });
        const hi = r.high_confidence || [], lo = r.low_confidence || [];
        const cand = (r.candidate_definitions||[]).length;
        const hiRows = hi.slice(0,40).map(x =>
          `<div class="row"><span class="rk">${esc(shortPath(x.src_path, p.repo_path))}:${x.line}</span><span class="muted">high confidence</span></div>`).join("");
        let warn = "";
        if (hi.length === 0 && lo.length > 0)
          warn = `<div class="hint">Everything came back low confidence. Usually the src-root is wrong (a project using a src/ layout must point at .../src), or this symbol is not defined in this project.</div>`;
        res.innerHTML = `<div class="muted" style="margin-bottom:6px">${cand} candidate definitions · ${hi.length} high-confidence references · ${lo.length} low-confidence</div>${hiRows||'<div class="muted">No high-confidence references</div>'}${warn}`;
      } catch (e) { res.innerHTML = `<div class="err-line">Reference lookup failed: ${esc(e.message)}</div>`; }
    };
    $("symgo-"+key).onclick = go;
    $("sym-"+key).addEventListener("keydown", ev => { if (ev.key === "Enter") go(); });
    $("sym-"+key).focus();
  }
}

function shortPath(full, root) {
  if (full && root && full.startsWith(root)) return "." + full.slice(root.length);
  return full;
}

async function loadLinks() {
  // Link checks run on demand and are not part of the main dashboard refresh.
  const box = $("linkgraph");
  box.innerHTML = `<div class="empty">Scanning <span class="spin"></span></div>`;
  try {
    const d = await api("/links");
    if (!d.available) { $("lgstat").textContent = "unavailable"; box.innerHTML = `<div class="err-line">${esc(d.reason || "linkgraph unavailable")}</div>`; return; }
    const dang = d.dangling || [], orph = d.orphans_by_ns || {};
    $("lgstat").textContent = `${d.nodes} nodes`;
    const dRows = dang.slice(0, 60).map(x =>
      `<div class="row"><span class="rk">[${esc(x.from_ns)}] ${esc(x.from)}</span><span class="err-line">→ [[${esc(x.to)}]] does not exist</span></div>`).join("");
    const oRows = Object.entries(orph).map(([ns, lst]) =>
      `<div class="row"><span class="rk">[${esc(ns)}] (advisory)</span><span class="muted">${lst.slice(0, 14).map(esc).join(", ")}${lst.length > 14 ? " …+" + (lst.length - 14) : ""}</span></div>`).join("");
    const disc = d.discipline_tail === null
      ? `<div class="row"><span class="rk">Discipline source</span><span class="muted">not configured (optional: set the CODESEXTANT_DISCIPLINE_LOG environment variable to a line-delimited JSON audit file)</span></div>`
      : `<div class="row"><span class="rk">Discipline source tail</span><span class="muted">${(d.discipline_tail || []).length} entries · ${esc(d.discipline_source || "source not reported")}</span></div>`;
    box.innerHTML = `<div class="detail">
      <div class="row"><span class="rk">🔗 dangling links</span><span>${dang.length ? dang.length + " (fix these)" : "0 (clean ✓)"}</span></div>${dRows}
      <div class="row"><span class="rk">unindexed nodes</span><span class="muted">advisory only</span></div>${oRows}
      ${disc}</div>`;
  } catch (e) { $("lgstat").textContent = "failed"; box.innerHTML = `<div class="err-line">Scan failed: ${esc(e.message)}</div>`; }
}

async function loadAll() { await Promise.all([loadHealth(), loadProjects()]); }
loadAll();
window.addEventListener('focus', loadAll);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) loadAll();
});
</script>
</body>
</html>
"""


def render_panel() -> str:
    """Return the complete panel HTML (self-contained, no external dependencies)."""
    return _PANEL_HTML
