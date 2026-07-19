"""codesextant C4 — 中文面板（給 daemon GET / 吐出的自包含 HTML）。

一份 HTML 三處共用（設計 §多前端）：
  - daemon 本身 GET /        （瀏覽器直接開 http://127.0.0.1:8790/）
  - 獨立 Tauri 殼            （iframe / webview 載入同一個 daemon URL）
  - AI King 擴充 webview     （iframe 嵌同一個 daemon URL）

刻意自包含（內嵌 CSS + 原生 JS，零外部 CDN）——對齊 CodeSextant「常駐本機、
零雲端零金鑰」定位：沒網路也能開面板。面板只是「呈現層」，資料一律由前端
fetch daemon 既有端點（/health /projects /status /reindex /get_map /find_references），
所以這份 render_panel() 回傳的是「不含資料的靜態骨架」，不需 server 端字串插值
（也順帶避開 Python 字串與 CSS/JS 大括號的衝突）。
"""
from __future__ import annotations

# 純靜態骨架：所有動態資料由下方 <script> fetch 同源端點後填入。
_PANEL_HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CodeSextant CodeSextant — 代碼地圖總覽</title>
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
    <div class="logo">碼</div>
    <h1>CodeSextant <small>CodeSextant · 代碼地圖總覽</small></h1>
    <span class="badge"><span id="hdot" class="dot"></span><span id="hstat">連線中…</span></span>
  </header>
  <div class="sub">常駐本機、零雲端零金鑰的代碼地圖服務——所有 AI 代理共用同一份「真 import 解析」全局關聯圖。</div>

  <div class="card">
    <h2>服務狀態</h2>
    <div id="health" class="grid"><div class="muted">載入中 <span class="spin"></span></div></div>
  </div>

  <div class="card">
    <h2>已索引專案 <span class="n" id="pcount">—</span></h2>
    <div class="toolbar">
      <span class="muted" id="dbdir"></span>
      <span class="spacer"></span>
      <button onclick="loadAll()">↻ 重新整理</button>
    </div>
    <div id="projects"><div class="empty">載入中 <span class="spin"></span></div></div>
    <div class="hint">「重建」＝重新索引（只重算改過的檔，增量很快）。「看地圖」＝列該專案 token 預算內最重要的符號。「查引用」＝某符號被誰呼叫。</div>
  </div>

  <div class="card">
    <h2>md 連結衛生 <span class="n" id="lgstat">—</span></h2>
    <div class="toolbar">
      <span class="muted">memory / HANDOFF / kb / SKILL / cbua 的 wiki 連結死鏈與孤兒（唯讀·只列不刪）</span>
      <span class="spacer"></span>
      <button class="primary" onclick="loadLinks()">掃描</button>
    </div>
    <div id="linkgraph"><div class="empty">按「掃描」現算（唯讀·約 1 秒·按需不自動跑）。</div></div>
    <div class="hint">dangling＝指向不存在節點的 [[連結]]（該修）；orphan＝索引缺連非 dead（advisory ⛔只列不刪；skill/cbua 孤兒多屬正常）。SSOT：LLM_WIKI優化AI環境_紅藍CBUA最佳解_2026-07-09.md</div>
  </div>

  <div class="sub muted" style="text-align:center;margin-top:28px">
    CodeSextant daemon · <span id="footport"></span> · 此面板由 daemon <code>GET /</code> 提供，可嵌入 Tauri 殼或 AI King 擴充。
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"'`]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;","`":"&#96;"}[c]));

function fmtTime(epoch) {
  if (!epoch) return "—";
  const d = new Date(epoch * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function fmtUptime(sec) {
  if (sec == null) return "—";
  sec = Math.floor(sec);
  if (sec < 60) return sec + " 秒";
  if (sec < 3600) return Math.floor(sec/60) + " 分 " + (sec%60) + " 秒";
  return Math.floor(sec/3600) + " 小時 " + Math.floor((sec%3600)/60) + " 分";
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || (r.status + " " + r.statusText));
  return data;
}

async function loadHealth() {
  try {
    const h = await api("/health");
    $("hdot").className = "dot ok";
    $("hstat").textContent = h["狀態"] || "就緒";
    $("footport").textContent = "127.0.0.1:" + h.port;
    const rows = [
      ["產品 / 服務", (h.product||"CodeSextant") + " / " + (h.service||"codesextant")],
      ["進程 PID", h.pid],
      ["連接埠 port", h.port],
      ["已運行", fmtUptime(h.uptime_sec)],
      ["引擎版本", h.engine_version || "—"],
      ["庫目錄", h["庫目錄"]],
      ["log 檔", h["log檔"]],
    ];
    $("health").innerHTML = rows.map(([k,v]) =>
      `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join("");
  } catch (e) {
    $("hdot").className = "dot err";
    $("hstat").textContent = "離線";
    $("health").innerHTML = `<div class="err-line">無法連上 daemon：${esc(e.message)}</div>`;
  }
}

async function loadProjects() {
  try {
    const d = await api("/projects");
    $("pcount").textContent = d.count;
    $("dbdir").textContent = "庫目錄：" + d.db_dir;
    window.__projects = d.projects;
    if (!d.projects.length) {
      $("projects").innerHTML = `<div class="empty">尚無已索引專案。任一代理觸發 codesextant（或呼叫 /reindex）後會出現在這裡。</div>`;
      return;
    }
    const head = `<tr><th>專案路徑</th><th>檔</th><th>符號</th><th>引用邊</th><th>最後索引</th><th>操作</th></tr>`;
    // 用 project_key（sha1，全機唯一、與位置無關）當每列的 key——任何重排都不會錯位，
    // 與本專案「sha1 分庫不混線」紀律一致（位置下標在背景刷新後會對到錯的專案）。
    const body = d.projects.map((p) => {
      if (p.error) {
        return `<tr><td class="path">${esc(p.db_file)}</td><td colspan="5" class="err-line">${esc(p.error)}</td></tr>`;
      }
      const k = esc(p.project_key);
      const gone = p.path_exists === false;
      const pathCell = esc(p.repo_path || p.db_file) + (gone ? `<span class="tag gone">路徑已不存在</span>` : "");
      const acts = `<div class="actions">
        <button class="primary" data-act="reindex" data-key="${k}" ${gone?"disabled":""}>重建</button>
        <button data-act="map" data-key="${k}" ${gone?"disabled":""}>看地圖</button>
        <button data-act="refs" data-key="${k}" ${gone?"disabled":""}>查引用</button>
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
    $("projects").innerHTML = `<div class="err-line">讀取專案列表失敗：${esc(e.message)}</div>`;
  }
}

function projByKey(key) { return (window.__projects || []).find(x => x.project_key === key); }

function showDetail(key, html) {
  const row = $("detail-" + key), box = $("detailbox-" + key);
  if (box) box.innerHTML = html;
  if (row) row.style.display = "";
}

async function refreshRowStats(key) {
  // reindex 後只更新該列數字（不整表重建）——保留其他已展開的 detail，
  // 也保留本列剛顯示的「重建完成」訊息（整表重建會把它清掉，M4）。
  try {
    const d = await api("/projects");
    window.__projects = d.projects;
    const p = d.projects.find(x => x.project_key === key);
    if (!p || p.error) return;
    const set = (id, v) => { const el = $(id + "-" + key); if (el) el.textContent = v; };
    set("files", p.indexed_files); set("syms", p.symbols);
    set("refs", p.refs); set("time", fmtTime(p.last_indexed_at));
  } catch (e) { /* 局部刷新失敗不影響已顯示的完成訊息 */ }
}

async function onAction(act, key, btn) {
  const p = projByKey(key);
  if (!p) return;
  if (act === "reindex") {
    const old = btn.textContent; btn.disabled = true; btn.innerHTML = '重建中 <span class="spin"></span>';
    try {
      const r = await api("/reindex", { method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ project: p.repo_path }) });
      showDetail(key, `<div class="row"><span class="rk">重建完成</span><span>新索引 ${r.indexed} 檔 · 略過 ${r.skipped} · 移除 ${r.removed} · 符號 ${r.symbols_total} · 耗時 ${r.elapsed_sec}s</span></div>`);
      await refreshRowStats(key);
    } catch (e) { showDetail(key, `<div class="err-line">重建失敗：${esc(e.message)}</div>`); }
    finally { btn.disabled = false; btn.textContent = old; }
  } else if (act === "map") {
    showDetail(key, `<span class="muted">載入地圖 <span class="spin"></span></span>`);
    try {
      const r = await api(`/get_map?project=${encodeURIComponent(p.repo_path)}&budget=1500`);
      const note = r.note ? `<div class="hint">${esc(r.note)}</div>` : "";
      const rows = (r.symbols||[]).map(s =>
        `<div class="row"><span class="rk">${esc(s.kind)} ${esc(s.name)}</span><span class="muted">${esc(shortPath(s.path, p.repo_path))}:${s.line}</span></div>`).join("");
      showDetail(key, `<div class="muted" style="margin-bottom:6px">最重要的 ${r.count} 個符號（約 ${r.approx_tokens} token）</div>${rows||'<div class="muted">無</div>'}${note}`);
    } catch (e) { showDetail(key, `<div class="err-line">看地圖失敗：${esc(e.message)}</div>`); }
  } else if (act === "refs") {
    showDetail(key, `<div style="display:flex;gap:8px;align-items:center">
      <input type="text" id="sym-${key}" placeholder="符號名（例：check）" style="flex:1">
      <button class="primary" id="symgo-${key}">查</button></div>
      <div id="symres-${key}" class="hint">輸入要查的函數 / 類別名稱，看它被哪些檔呼叫。</div>`);
    const go = async () => {
      const sym = $("sym-"+key).value.trim();
      if (!sym) return;
      const res = $("symres-"+key); res.innerHTML = `<span class="muted">jedi 解析中 <span class="spin"></span></span>`;
      try {
        const r = await api("/find_references", { method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({ project: p.repo_path, symbol: sym }) });
        const hi = r.high_confidence || [], lo = r.low_confidence || [];
        const cand = (r.candidate_definitions||[]).length;
        const hiRows = hi.slice(0,40).map(x =>
          `<div class="row"><span class="rk">${esc(shortPath(x.src_path, p.repo_path))}:${x.line}</span><span class="muted">高信心</span></div>`).join("");
        let warn = "";
        if (hi.length === 0 && lo.length > 0)
          warn = `<div class="hint">全部低信心——多半是 src-root 沒對（採 src/ 佈局的專案要指到 .../src），或此符號非定義在本專案。</div>`;
        res.innerHTML = `<div class="muted" style="margin-bottom:6px">候選定義 ${cand} 處 · 高信心引用 ${hi.length} · 低信心 ${lo.length}</div>${hiRows||'<div class="muted">無高信心引用</div>'}${warn}`;
      } catch (e) { res.innerHTML = `<div class="err-line">查引用失敗：${esc(e.message)}</div>`; }
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
  // Phase 1（wiki linkgraph·2026-07-09）：按需現算，⛔不進 loadAll（裁決：按需除錯工具、不推到眼前）
  const box = $("linkgraph");
  box.innerHTML = `<div class="empty">掃描中 <span class="spin"></span></div>`;
  try {
    const d = await api("/links");
    if (!d.available) { $("lgstat").textContent = "不可用"; box.innerHTML = `<div class="err-line">${esc(d.reason || "linkgraph 不可用")}</div>`; return; }
    const dang = d.dangling || [], orph = d.orphans_by_ns || {};
    $("lgstat").textContent = `${d.nodes} 節點`;
    const dRows = dang.slice(0, 60).map(x =>
      `<div class="row"><span class="rk">[${esc(x.from_ns)}] ${esc(x.from)}</span><span class="err-line">→ [[${esc(x.to)}]] 不存在</span></div>`).join("");
    const oRows = Object.entries(orph).map(([ns, lst]) =>
      `<div class="row"><span class="rk">[${esc(ns)}]${(ns === "skill" || ns === "cbua") ? "（多屬正常）" : "（★該進索引？）"}</span><span class="muted">${lst.slice(0, 14).map(esc).join("、")}${lst.length > 14 ? " …+" + (lst.length - 14) : ""}</span></div>`).join("");
    const disc = d.discipline_tail === null
      ? `<div class="row"><span class="rk">紀律源</span><span class="muted">無契約（wiredo_discipline.jsonl 空·可選源）</span></div>`
      : `<div class="row"><span class="rk">紀律源 tail</span><span class="muted">${(d.discipline_tail || []).length} 筆 · ~/.concinno/audit/wiredo_discipline.jsonl</span></div>`;
    box.innerHTML = `<div class="detail">
      <div class="row"><span class="rk">🔗 dangling 死連結</span><span>${dang.length ? dang.length + " 條（該修）" : "0（乾淨 ✓）"}</span></div>${dRows}
      <div class="row"><span class="rk">🟡 orphans 孤兒</span><span class="muted">advisory·⛔只列不刪</span></div>${oRows}
      ${disc}</div>`;
  } catch (e) { $("lgstat").textContent = "失敗"; box.innerHTML = `<div class="err-line">掃描失敗：${esc(e.message)}</div>`; }
}

async function loadAll() { await Promise.all([loadHealth(), loadProjects()]); }
loadAll();
setInterval(loadHealth, 5000);  // 服務狀態每 5 秒自動刷新（uptime / 離線偵測）
</script>
</body>
</html>
"""


def render_panel() -> str:
    """回傳完整的中文面板 HTML（自包含、無外部依賴）。"""
    return _PANEL_HTML
