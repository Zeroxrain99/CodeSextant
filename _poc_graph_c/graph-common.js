// 功能 C PoC 共用層：載入圖資料 + 確定性社群佈局 + 冷色域科技感配色。
// PoC-A(WebGL2) 與 PoC-B(WebGPU/TSL) 都 import 這支 → 同資料同座標同配色、唯一差別是渲染後端，公平對照。

export async function loadGraph(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error('載入圖資料失敗 ' + url + ' : ' + r.status);
  return r.json();
}

// seeded PRNG（mulberry32）：兩個 PoC 用同 seed → 座標完全一致、截圖可逐點對照。
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hslToRgb(h, s, l) {
  let r, g, b;
  if (s === 0) { r = g = b = l; }
  else {
    const hue2rgb = (p, q, t) => {
      if (t < 0) t += 1; if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3); g = hue2rgb(p, q, h); b = hue2rgb(p, q, h - 1 / 3);
  }
  return [r, g, b];
}

// 冷色域高飽和調色盤（青→藍綠→藍→紫，科技感、對齊研究「像星圖非義大利麵」）。
export function communityPalette(C) {
  const pal = [];
  for (let i = 0; i < C; i++) {
    const hue = (170 + (i / Math.max(1, C)) * 120) / 360; // 170°cyan → 290°violet
    pal.push(hslToRgb(hue, 0.85, 0.62));
  }
  return pal;
}

// 節點顏色：生產社群吃彩色調色盤；測試帶/孤點帶降成灰（視覺一眼區隔「非生產架構」）。
// 紀律轉美（紅藍 SSOT §3）：health 低→去飽和往灰（爛碼褪色），但**保留 hue**（社群身分不變）；
// health=null(UNKNOWN，如 class/variable 無指紋)→中性不褪（C2：不洗滿分也不亂褪）。
// 單一真相源：hasLayout 與 fallback 兩分支共用，未來改配色只改這裡（變數收斂紀律）。
function nodeColor(community, pal, i, health) {
  if (community === 'Ltest') return [0.30, 0.32, 0.38];      // 測試帶：暗藍灰、最不搶眼
  if (community === 'Lsingleton') return [0.46, 0.48, 0.54]; // 孤點帶：中灰
  const base = pal[i];
  if (health == null) return base;                           // UNKNOWN 中性、不動
  const sat = 0.25 + 0.75 * health;                          // health 0→0.25 灰 / 1→1.0 鮮
  const lum = 0.299 * base[0] + 0.587 * base[1] + 0.114 * base[2];  // 往亮度插值＝去飽和
  return [lum + (base[0] - lum) * sat, lum + (base[1] - lum) * sat, lum + (base[2] - lum) * sat];
}

// 確定性社群佈局：每社群一個中心（散在大環上），群內高斯散佈 → 天然「亂中有序」色塊星雲。
// 回傳給渲染器直接吃的 typed array buffers。
export function buildBuffers(graph) {
  const comms = [...new Set(graph.nodes.map(n => n.community))];
  const ci = new Map(comms.map((c, i) => [c, i]));
  const C = comms.length;
  const N = graph.nodes.length;
  const pal = communityPalette(C);
  const pos = new Float32Array(N * 3);
  const col = new Float32Array(N * 3);
  const siz = new Float32Array(N);
  const hasLayout = graph.meta && graph.meta.layout;   // 有後端 spectral 落盤座標就直接讀

  if (hasLayout) {
    // ── 結構決定形狀：讀後端確定性 spectral 的 node.x/y/z（零前端隨機）──
    graph.nodes.forEach((n, k) => {
      const i = ci.get(n.community);
      const ok = Number.isFinite(n.x) && Number.isFinite(n.y) && Number.isFinite(n.z);
      if (ok) { pos[k * 3] = n.x; pos[k * 3 + 1] = n.y; pos[k * 3 + 2] = n.z; }
      else { pos[k * 3] = 0; pos[k * 3 + 1] = 0; pos[k * 3 + 2] = 0; }   // R4 防呆：NaN 退原點
      const c = nodeColor(n.community, pal, i, n.health);
      col[k * 3] = c[0]; col[k * 3 + 1] = c[1]; col[k * 3 + 2] = c[2];
      // 測試/孤點帶縮小（不搶生產架構主視覺）；生產節點 rank 越高越大
      const isAux = n.community === 'Ltest' || n.community === 'Lsingleton';
      siz[k] = (isAux ? 2.4 : 4.5) + (n.rank || 0) * (isAux ? 6.0 : 20.0);
    });
  } else {
    // ── 向後相容 fallback：無 meta.layout 走原本固定模板球/環 + seed42 高斯散佈 ──
    const rnd = mulberry32(42);
    const small = N < 2000;          // 社群少的小圖（如 real 598/5 社群）走球狀分布，不擠平面
    const R = small ? 660 : 1700;
    const centers = comms.map((_c, i) => {
      if (small) {
        const y = C > 1 ? 1 - (i / (C - 1)) * 1.7 : 0;
        const rad = Math.sqrt(Math.max(0, 1 - y * y));
        const phi = i * 2.399963;
        return [Math.cos(phi) * rad * R, y * R * 0.78, Math.sin(phi) * rad * R];
      }
      const ang = (i / C) * Math.PI * 2;
      const rr = R * (0.62 + 0.38 * rnd());
      return [Math.cos(ang) * rr, Math.sin(ang) * rr, (rnd() - 0.5) * 420];
    });
    const spread = small ? 360 : (50 + Math.sqrt(N) * 0.32);
    graph.nodes.forEach((n, k) => {
      const i = ci.get(n.community);
      const ctr = centers[i];
      const r = Math.pow(rnd(), 0.6) * spread;
      const a = rnd() * Math.PI * 2;
      const z = (rnd() - 0.5) * spread * 0.7;
      pos[k * 3] = ctr[0] + Math.cos(a) * r;
      pos[k * 3 + 1] = ctr[1] + Math.sin(a) * r;
      pos[k * 3 + 2] = ctr[2] + z;
      const c = nodeColor(n.community, pal, i, n.health);
      col[k * 3] = c[0]; col[k * 3 + 1] = c[1]; col[k * 3 + 2] = c[2];
      siz[k] = 2.2 + (n.rank || 0) * 22.0;
    });
  }

  const E = graph.edges.length;
  const lpos = new Float32Array(E * 2 * 3);
  const lcol = new Float32Array(E * 2 * 3);
  graph.edges.forEach((e, k) => {
    const s = e.source, t = e.target;
    const sameComm = graph.nodes[s].community === graph.nodes[t].community;
    const dim = sameComm ? 0.16 : 0.03; // 群內邊淡、跨群邊近乎隱形 → 讓節點團塊主導（R6 連線降亮）
    for (let z = 0; z < 3; z++) {
      lpos[k * 6 + z] = pos[s * 3 + z];
      lpos[k * 6 + 3 + z] = pos[t * 3 + z];
      const cc = (col[s * 3 + z] + col[t * 3 + z]) * 0.5 * dim;
      lcol[k * 6 + z] = cc;
      lcol[k * 6 + 3 + z] = cc;
    }
  });

  // ── D6 死碼透明度：未接線節點半透明（下限 0.4＝可見但脫團，不隱形喪失「該被看見」診斷）──
  const alpha = new Float32Array(N);
  graph.nodes.forEach((n, k) => { alpha[k] = n.dead ? 0.4 : 1.0; });

  // ── D5 重複碼暗弧：同結構指紋的孿生節點連暗紅弧（複用 LineSegments，獨立於佈局邊）──
  const clone = graph.clone_edges || [];
  const clE = clone.length;
  const clpos = new Float32Array(clE * 2 * 3);
  const clcol = new Float32Array(clE * 2 * 3);
  const CLONE_RGB = [0.55, 0.10, 0.12];   // 暗紅＝重複碼暗債警示
  clone.forEach((e, k) => {
    const s = e[0], t = e[1];
    for (let z = 0; z < 3; z++) {
      clpos[k * 6 + z] = pos[s * 3 + z];
      clpos[k * 6 + 3 + z] = pos[t * 3 + z];
      clcol[k * 6 + z] = CLONE_RGB[z];
      clcol[k * 6 + 3 + z] = CLONE_RGB[z];
    }
  });

  return { N, E, C, pos, col, siz, lpos, lcol, alpha, clE, clpos, clcol };
}
