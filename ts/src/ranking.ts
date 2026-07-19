// 重要度排序模組 — PageRank 給「最重要的 N 個符號」（全 TS 重寫 P1，平移自 Python codesextant/ranking.py）。
//
// 設計來源（抄 PoC / aider repomap 思路）：把「被定義的符號」當圖節點、引用邊（誰用了誰）當連結；
// 一個符號被越多「本身也重要」的符號引用 → 它越重要（PageRank 的遞迴定義）。純 power iteration（冪迭代）、
// 無 networkx/scipy 依賴（保持引擎輕量）。
//
// 平移原則（對照凍結的 Python 版黃金測試 ground truth：test/fixtures/expected_ranking.json）：
//   - 浮點 IEEE 754 double 兩語言一致；只要運算「順序」逐行對齊，分數可對到極小容差。
//   - symbol_id 字串格式（path::scope::name::line）與 Python f-string 完全一致 → scores 的 key 跨語言可對照。
//   - dict/Counter → Map、list → array；遍歷順序（Map 保插入序、array 保 push 序）對齊 Python，保浮點累加序一致。
//   - env 解析嚴格對齊 Python float()/int()（空字串/非數字字串退 default、int 不接受小數點字串）。
//
// 架構備註（P1 暫態）：import storage.normPath 複用「對齊 Python normcase(abspath())」的單一真相源（引用邊
//   def_path/src_path 與符號 path 必須走同一正規化才對得上節點）。代價＝載入時連帶 storage（拖 better-sqlite3）；
//   ranking 程式碼本身零 sqlite 調用、仍是純算法。待 namegraph.ts 也需此正規化時抽成獨立 paths.ts 共用。
//
// 職責（單一）：吃「符號清單 + 引用邊清單」，吐出帶 rank 分數、由高到低排序的符號。不碰 SQLite、不碰 ts-morph。
// 所有狀態都在函數內局部，重入安全、無全域污染。
import { normPath } from "./storage.js";

// 高信心引用邊的權重（jedi/ts-morph 確認的指向比名稱比對可信，給更高權重）。
const CONFIDENCE_WEIGHT: Record<string, number> = { high: 1.0, low: 0.25 };

/** ranking 的輸入符號（比 storage.SymbolRow 寬鬆：path/end_line/scope 皆可缺，對齊 Python 的 dict.get 容錯）。
 *  index signature 讓 rank_symbols 能 {...s, rank} 原樣保留其他欄位回傳。 */
export interface RankSymbol {
  name: string;
  line: number;
  path?: string | null;
  scope?: string | null;
  end_line?: number | null;
  kind?: string | null;
  [extra: string]: unknown;
}

/** ranking 的輸入引用邊（欄位皆可選，對齊 Python e.get(...) 容錯；def 未解析時 def_path/def_line 為 null）。 */
export interface RankRef {
  def_path?: string | null;
  def_line?: number | null;
  src_path?: string | null;
  src_line?: number | null;
  confidence?: string;
}

// ── env helpers（嚴格對齊 Python float()/int() 的「非法字串退 default」語義）──

/** 對齊 Python float(os.environ.get(name, ""))：空/非數字字串退 default（Python 對這些 raise ValueError）。 */
function envFloat(name: string, def: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return def; // float("")/float("  ") 皆 raise
  const v = Number(raw);
  return Number.isNaN(v) ? def : v; // "1.5x" → NaN → default（對齊 Python raise）
}

/** 對齊 Python int(os.environ.get(name, ""))：只接受整數字串，"5.5"/""/"abc"/"0x1f" 皆退 default。 */
function envInt(name: string, def: number): number {
  const raw = process.env[name];
  if (raw === undefined) return def;
  const t = raw.trim();
  if (!/^[+-]?\d+$/.test(t)) return def; // Python int() 對小數點/非數字字串 raise
  return parseInt(t, 10);
}

/** 命名規範的公開符號（含底線分隔或大小寫混合＝snake/camel/Pascal）。 */
export function wellNamed(name: string): boolean {
  if (name.startsWith("_")) return false;
  return name.includes("_") || (name !== name.toLowerCase() && name !== name.toUpperCase());
}

/** queue 5（邊權重符號品質係數，aider 啟發式）——凸顯架構性公開 API、壓低低訊號/氾濫符號。
 *  well-named 公開符號(len>=門檻) ×WELLNAMED；私有 _開頭 ×PRIVATE；在 >N 檔重複定義(氾濫名) ×COMMON。 */
export function symbolQualityMult(name: string, definesCount: number): number {
  let mult = 1.0;
  if (name.startsWith("_")) {
    mult *= envFloat("CODESEXTANT_RANK_PRIVATE_MULT", 0.1);
  } else if (name.length >= envInt("CODESEXTANT_RANK_WELLNAMED_MINLEN", 8) && wellNamed(name)) {
    mult *= envFloat("CODESEXTANT_RANK_WELLNAMED_MULT", 10.0);
  }
  if (definesCount > envInt("CODESEXTANT_RANK_COMMON_THRESHOLD", 5)) {
    mult *= envFloat("CODESEXTANT_RANK_COMMON_MULT", 0.1);
  }
  return mult;
}

/** 符號的唯一識別：path::scope::name::line。用 line 一起當 id，避免同檔同名互相蓋掉。
 *  ⚠ 與 Python f-string 完全一致（黃金測試的 scores key 靠此對照）。 */
export function symbolId(sym: RankSymbol): string {
  return `${sym.path}::${sym.scope ?? ""}::${sym.name}::${sym.line}`;
}

/** 路徑正規化（對齊 Python os.path.normcase(os.path.abspath()) if path else ""）。 */
function norm(path: string | null | undefined): string {
  return path ? normPath(path) : "";
}

/** 從 symbol_id 取出 line（id 格式 path::scope::name::line）。解析不到回極大值（對齊 Python 1<<30）。 */
function lineOf(sid: string): number {
  const i = sid.lastIndexOf("::");
  if (i === -1) return 1 << 30;
  const v = Number(sid.slice(i + 2));
  return Number.isNaN(v) ? 1 << 30 : v;
}

/** queue 4（query-aware PageRank）——把呼叫端顯式傳入的 focus set 轉成 personalization 向量。
 *  ⛔ boost 來源是「呼叫端顯式說我在改 X」(focusSymbols/focusFiles)，非監聽對話/接 LLM（守零雲端鐵則）。
 *  focus 命中符號的 teleport 權重 +boost 倍。無 focus 回 null（退均勻 teleport＝原靜態行為）。 */
export function buildPersonalization(
  symbols: RankSymbol[],
  focusSymbols?: string[] | null,
  focusFiles?: string[] | null,
): Map<string, number> | null {
  const fs = new Set(focusSymbols ?? []);
  const ff = new Set((focusFiles ?? []).map((f) => norm(f)));
  if (fs.size === 0 && ff.size === 0) return null;
  const boost = envFloat("CODESEXTANT_PAGERANK_FOCUS_BOOST", 10.0);
  const p = new Map<string, number>();
  for (const s of symbols) {
    let w = 1.0;
    if (fs.has(s.name)) w += boost;
    if (ff.has(norm(s.path))) w += boost;
    p.set(symbolId(s), w);
  }
  return p;
}

/** 對符號圖跑 PageRank，回傳 Map{symbol_id → score}。
 *
 *  邊方向：src（引用端所在檔的代表符號）→ def（被引用的符號定義）。PageRank 讓分數從引用端流向被引用端，
 *  所以「被很多重要符號引用」的符號得高分。src 對應不到節點時（如模組頂層呼叫），當外部入流均攤計入。
 *  queue 5：邊權重疊「被引用符號的品質係數」。queue 4：personalization 灌進 teleport＝query-aware；null 退均勻。
 *  symbols 為空回空 Map。所有中間狀態皆局部，呼叫間互不影響。 */
export function computePagerank(
  symbols: RankSymbol[],
  refs: RankRef[],
  opts: {
    damping?: number;
    maxIter?: number;
    tol?: number;
    personalization?: Map<string, number> | null;
  } = {},
): Map<string, number> {
  const { damping = 0.85, maxIter = 100, tol = 1.0e-6, personalization = null } = opts;
  if (symbols.length === 0) return new Map();

  const nodeIds = symbols.map((s) => symbolId(s));
  const n = nodeIds.length;
  const idx = new Map<string, number>();
  nodeIds.forEach((sid, i) => idx.set(sid, i)); // 重複 id 後寫贏（對齊 Python dict comprehension）
  const nameOf = new Map<string, string>();
  nodeIds.forEach((sid, i) => nameOf.set(sid, symbols[i]!.name));

  // queue 5：name → 在幾個 distinct (name, normPath) 定義（過於常見＝低訊號，邊權重打折）。
  const seenNp = new Set<string>();
  const defines = new Map<string, number>();
  for (const s of symbols) {
    const k = `${s.name} ${norm(s.path)}`;
    if (!seenNp.has(k)) {
      seenNp.add(k);
      defines.set(s.name, (defines.get(s.name) ?? 0) + 1);
    }
  }

  // (檔絕對路徑, 定義行) → symbol_id（讓引用邊的 def_path/def_line 對上節點）；
  // 檔絕對路徑 → 該檔第一個符號 symbol_id（當引用端代表節點）。
  const byPos = new Map<string, string>();
  const fileRep = new Map<string, string>();
  for (const s of symbols) {
    const p = s.path;
    if (p === null || p === undefined) continue; // 對齊 Python `if p is None: continue`（空字串不跳）
    const sid = symbolId(s);
    const np = norm(p);
    byPos.set(`${np} ${s.line}`, sid);
    const cur = fileRep.get(np);
    if (cur === undefined || s.line < lineOf(cur)) fileRep.set(np, sid);
  }

  // path → sorted [(line, end_line, sid)]：給「src_line 映射到包含它的 caller 符號」用。
  // 紅隊 L1-HIGH 修正（Python 端）：同檔邊來源用「真正包含 src_line 的 caller」當節點，而非 collapse 到
  // 檔第一符號 fileRep——否則被呼叫者剛好是檔第一符號時邊成 i==j 被跳過，同檔引用結構對 PageRank 不可見。
  const byBody = new Map<string, Array<[number, number, string]>>();
  for (const s of symbols) {
    const p = s.path;
    if (p === null || p === undefined) continue;
    const np = norm(p);
    const el = Number(s.end_line ?? s.line) || s.line; // 對齊 int(s.get("end_line", line) or line)
    let arr = byBody.get(np);
    if (arr === undefined) {
      arr = [];
      byBody.set(np, arr);
    }
    arr.push([s.line, el, symbolId(s)]);
  }
  for (const arr of byBody.values()) {
    // 對齊 Python tuple sort：(line, end_line, sid) 字典序；sid 用 code-unit 比較（中文在 BMP 同 code point）。
    arr.sort((a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0));
  }

  // src_line 映射到「包含它的最內層符號」當來源節點；無 src_line / 找不到 → fallback fileRep。
  const srcNode = (
    srcPath: string | null | undefined,
    srcLine: number | null | undefined,
  ): string | undefined => {
    const np = srcPath ? norm(srcPath) : "";
    if (srcLine && byBody.has(np)) {
      let best: string | undefined = undefined;
      for (const [ln, el, sid] of byBody.get(np)!) {
        if (ln > srcLine) break;
        if (ln <= srcLine && srcLine <= el) best = sid; // 持續更新→最內層（line 最大者）
      }
      if (best !== undefined) return best;
    }
    return fileRep.get(np);
  };

  // 建鄰接 outTargets[i] = [(j, weight), ...]；外部入流 externalInflow[j]。
  const outTargets: Array<Array<[number, number]>> = Array.from({ length: n }, () => []);
  const externalInflow = new Map<number, number>();

  for (const e of refs) {
    const dp = e.def_path ?? null;
    const dl = e.def_line ?? null;
    if (dp === null || dl === null) continue;
    const target = byPos.get(`${norm(dp)} ${dl}`);
    if (target === undefined) continue;
    const j = idx.get(target)!;
    let w = CONFIDENCE_WEIGHT[e.confidence ?? "low"] ?? 0.25;
    // queue 5：疊被引用符號的品質係數。
    const tname = nameOf.get(target) ?? "";
    w *= symbolQualityMult(tname, defines.get(tname) ?? 1);

    const srcRep = srcNode(e.src_path, e.src_line);
    if (srcRep === undefined) {
      externalInflow.set(j, (externalInflow.get(j) ?? 0.0) + w);
      continue;
    }
    const i = idx.get(srcRep)!;
    if (i === j) continue;
    outTargets[i]!.push([j, w]);
  }

  const nRefs = Math.max(1, refs.length);
  // queue 4：personalization teleport 向量 P（focus 偏好）；無則均勻 1/n（原靜態行為，向後相容）。
  let P: number[];
  if (personalization !== null && personalization.size > 0) {
    let totP = 0;
    for (const sid of nodeIds) totP += personalization.get(sid) ?? 1.0;
    if (totP === 0) totP = 1.0;
    P = nodeIds.map((sid) => (personalization.get(sid) ?? 1.0) / totP);
  } else {
    P = new Array<number>(n).fill(1.0 / n);
  }
  let score = [...P];

  for (let iter = 0; iter < maxIter; iter++) {
    const newScore = P.map((pj) => (1.0 - damping) * pj);
    let danglingSum = 0.0;
    for (let i = 0; i < n; i++) {
      const edges = outTargets[i]!;
      if (edges.length === 0) {
        danglingSum += score[i]!;
        continue;
      }
      let totalW = 0;
      for (const [, w] of edges) totalW += w;
      if (totalW <= 0) {
        danglingSum += score[i]!;
        continue;
      }
      for (const [j, w] of edges) newScore[j]! += damping * score[i]! * (w / totalW);
    }
    if (danglingSum) {
      // dangling 質量按 personalization 分布回流（aider dangling=P）。
      for (let j = 0; j < n; j++) newScore[j]! += damping * danglingSum * P[j]!;
    }
    for (const [j, infl] of externalInflow) {
      newScore[j]! += (damping * infl) / nRefs;
    }

    let delta = 0;
    for (let i = 0; i < n; i++) delta += Math.abs(newScore[i]! - score[i]!);
    score = newScore;
    if (delta < tol) break;
  }

  const out = new Map<string, number>();
  for (let i = 0; i < n; i++) out.set(nodeIds[i]!, score[i]!);
  return out;
}

/** 對符號排重要度，回傳帶 "rank" 分數、由高到低排序的符號清單（原欄位 + rank）。
 *  topN 給了就只回前 N 個。focusSymbols/focusFiles（queue 4 query-aware）：呼叫端顯式傳入「在改/在問的
 *  符號/檔」，讓排序偏向相關處；不傳＝原靜態結構中心度排序。 */
export function rankSymbols<T extends RankSymbol>(
  symbols: T[],
  refs: RankRef[],
  opts: {
    topN?: number | null;
    damping?: number;
    focusSymbols?: string[] | null;
    focusFiles?: string[] | null;
  } = {},
): Array<T & { rank: number }> {
  const { topN = null, damping = 0.85, focusSymbols = null, focusFiles = null } = opts;
  const personalization = buildPersonalization(symbols, focusSymbols, focusFiles);
  const scores = computePagerank(symbols, refs, { damping, personalization });
  const ranked = symbols.map((s) => ({ ...s, rank: scores.get(symbolId(s)) ?? 0.0 }));
  // 穩定降序：rank 相同保持原相對順序（對齊 Python sort(reverse=True) 的穩定性）。
  ranked.sort((a, b) => b.rank - a.rank);
  return topN !== null ? ranked.slice(0, topN) : ranked;
}
