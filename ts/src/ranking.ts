// Importance ranking module: PageRank for "the N most important symbols" (full TypeScript rewrite,
// P1; ported from Python codesextant/ranking.py).
//
// Design, taken from the PoC and aider's repomap: defined symbols are graph nodes and reference edges
// (who uses whom) are the links; the more symbols that are themselves important reference a symbol,
// the more important that symbol is (PageRank's recursive definition). Plain power iteration, with no
// networkx or scipy dependency, which keeps the engine light.
//
// Porting rules, checked against the frozen Python version's golden-test ground truth
// (test/fixtures/expected_ranking.json):
//   - IEEE 754 doubles behave identically in both languages; as long as the *order* of operations
//     lines up statement for statement, the scores match to a very small tolerance.
//   - The symbol_id string format (path::scope::name::line) is identical to the Python f-string, so
//     the keys of scores can be compared across languages.
//   - dict/Counter → Map, list → array. Iteration order (a Map keeps insertion order, an array keeps
//     push order) matches Python, which keeps floating-point accumulation order identical.
//   - Environment parsing follows Python's float()/int() strictly: an empty or non-numeric string
//     falls back to the default, and int refuses a string with a decimal point.
//
// Architecture note (temporary for P1): importing storage.normPath reuses the single source of truth
//   for "match Python's normcase(abspath())": a reference edge's def_path/src_path and a symbol's
//   path have to go through the same normalization to land on the same node. The cost is that loading
//   this module pulls in storage, and with it better-sqlite3; the ranking code itself makes no sqlite
//   calls and remains pure algorithm. Once namegraph.ts needs the same normalization, extract it into
//   a shared paths.ts.
//
// Single responsibility: take a list of symbols and a list of reference edges, return the symbols
// carrying a rank score, sorted high to low. It touches neither SQLite nor ts-morph. All state is
// local to the functions, so it is re-entrant and pollutes nothing global.
import { normPath } from "./storage.js";

// Weights for reference edges by confidence. A link confirmed by jedi or ts-morph is more
// trustworthy than a name match, so it weighs more.
const CONFIDENCE_WEIGHT: Record<string, number> = { high: 1.0, low: 0.25 };

/** A symbol going into ranking. Looser than storage.SymbolRow: path, end_line and scope may all be
 *  absent, matching the dict.get tolerance on the Python side.
 *  The index signature is what lets rank_symbols return {...s, rank} with every other field intact. */
export interface RankSymbol {
  name: string;
  line: number;
  path?: string | null;
  scope?: string | null;
  end_line?: number | null;
  kind?: string | null;
  [extra: string]: unknown;
}

/** A reference edge going into ranking. Every field is optional, matching Python's e.get(...)
 *  tolerance; def_path and def_line are null when the definition was never resolved. */
export interface RankRef {
  def_path?: string | null;
  def_line?: number | null;
  src_path?: string | null;
  src_line?: number | null;
  confidence?: string;
}

// ── env helpers (following Python's float()/int() semantics exactly: an invalid string falls back to
//    the default) ──

/** Matches Python's float(os.environ.get(name, "")): an empty or non-numeric string falls back to the
 *  default, which is where Python raises ValueError. */
function envFloat(name: string, def: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return def; // float("") and float("  ") both raise
  const v = Number(raw);
  return Number.isNaN(v) ? def : v; // "1.5x" → NaN → default (Python raises here)
}

/** Matches Python's int(os.environ.get(name, "")): only integer strings are accepted, so "5.5", "",
 *  "abc" and "0x1f" all fall back to the default. */
function envInt(name: string, def: number): number {
  const raw = process.env[name];
  if (raw === undefined) return def;
  const t = raw.trim();
  if (!/^[+-]?\d+$/.test(t)) return def; // Python's int() raises on decimal points and non-numeric strings
  return parseInt(t, 10);
}

/** A public symbol that follows a naming convention: it contains an underscore separator or mixes
 *  case, i.e. snake_case, camelCase or PascalCase. */
export function wellNamed(name: string): boolean {
  if (name.startsWith("_")) return false;
  return name.includes("_") || (name !== name.toLowerCase() && name !== name.toUpperCase());
}

/** queue 5 (symbol quality factor on edge weights, an aider heuristic): bring architectural public
 *  APIs forward and push low-signal or ubiquitous symbols back.
 *  A well-named public symbol (length >= the threshold) gets ×WELLNAMED; a private one starting with
 *  _ gets ×PRIVATE; one defined in more than N files (a ubiquitous name) gets ×COMMON. */
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

/** A symbol's unique id: path::scope::name::line. Including line keeps same-named symbols in one file
 *  from overwriting each other.
 *  ⚠ Identical to the Python f-string; the golden test's scores keys depend on it. */
export function symbolId(sym: RankSymbol): string {
  return `${sym.path}::${sym.scope ?? ""}::${sym.name}::${sym.line}`;
}

/** Path normalization (matches Python's os.path.normcase(os.path.abspath()) if path else ""). */
function norm(path: string | null | undefined): string {
  return path ? normPath(path) : "";
}

/** Pull the line out of a symbol_id (format path::scope::name::line). Returns a very large value when
 *  it cannot be parsed, matching Python's 1<<30. */
function lineOf(sid: string): number {
  const i = sid.lastIndexOf("::");
  if (i === -1) return 1 << 30;
  const v = Number(sid.slice(i + 2));
  return Number.isNaN(v) ? 1 << 30 : v;
}

/** queue 4 (query-aware PageRank): turn the focus set the caller passes in into a personalization
 *  vector.
 *  ⛔ The boost comes from the caller explicitly stating "I am working on X" (focusSymbols/
 *  focusFiles), never from listening to a conversation or calling an LLM. The zero-cloud rule holds.
 *  Symbols hit by the focus get boost added to their teleport weight. With no focus this returns
 *  null, which falls back to uniform teleport, the original static behaviour. */
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

/** Run PageRank over the symbol graph and return Map{symbol_id → score}.
 *
 *  Edge direction: src (the representative symbol of the file the reference sits in) → def (the
 *  referenced symbol's definition). PageRank flows score from the referencing side to the referenced
 *  side, so a symbol referenced by many important symbols scores high. When src maps to no node (a
 *  module-top-level call, for instance), it is counted as evenly-shared external inflow.
 *  queue 5 multiplies the edge weight by the referenced symbol's quality factor. queue 4 feeds
 *  personalization into teleport, which is what makes it query-aware; null falls back to uniform.
 *  An empty symbols list returns an empty Map. Every intermediate is local, so calls cannot affect
 *  each other. */
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
  nodeIds.forEach((sid, i) => idx.set(sid, i)); // on a duplicate id the later write wins (matching the Python dict comprehension)
  const nameOf = new Map<string, string>();
  nodeIds.forEach((sid, i) => nameOf.set(sid, symbols[i]!.name));

  // queue 5: name → the number of distinct (name, normPath) definitions it has. Too common means low
  // signal, and the edge weight is discounted accordingly.
  const seenNp = new Set<string>();
  const defines = new Map<string, number>();
  for (const s of symbols) {
    const k = `${s.name} ${norm(s.path)}`;
    if (!seenNp.has(k)) {
      seenNp.add(k);
      defines.set(s.name, (defines.get(s.name) ?? 0) + 1);
    }
  }

  // (absolute file path, definition line) → symbol_id, so a reference edge's def_path/def_line can
  // find its node; absolute file path → the symbol_id of that file's first symbol, used as the
  // representative node for the referencing side.
  const byPos = new Map<string, string>();
  const fileRep = new Map<string, string>();
  for (const s of symbols) {
    const p = s.path;
    if (p === null || p === undefined) continue; // matches Python's `if p is None: continue` (an empty string is not skipped)
    const sid = symbolId(s);
    const np = norm(p);
    byPos.set(`${np} ${s.line}`, sid);
    const cur = fileRep.get(np);
    if (cur === undefined || s.line < lineOf(cur)) fileRep.set(np, sid);
  }

  // path → sorted [(line, end_line, sid)], used to map a src_line to the caller symbol containing it.
  // Red-team L1-HIGH fix (made on the Python side): for an edge inside one file, use the caller that
  // actually contains src_line as the node instead of collapsing to the file's first symbol
  // (fileRep). Otherwise, whenever the callee happens to be the file's first symbol, the edge
  // becomes i==j and is skipped, leaving same-file reference structure invisible to PageRank.
  const byBody = new Map<string, Array<[number, number, string]>>();
  for (const s of symbols) {
    const p = s.path;
    if (p === null || p === undefined) continue;
    const np = norm(p);
    const el = Number(s.end_line ?? s.line) || s.line; // matches int(s.get("end_line", line) or line)
    let arr = byBody.get(np);
    if (arr === undefined) {
      arr = [];
      byBody.set(np, arr);
    }
    arr.push([s.line, el, symbolId(s)]);
  }
  for (const arr of byBody.values()) {
    // Matches the Python tuple sort: (line, end_line, sid) lexicographic. sid compares by code unit,
    // which orders identically to code point for anything in the BMP.
    arr.sort((a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0));
  }

  // Map a src_line to the innermost symbol containing it and use that as the source node; with no
  // src_line, or when nothing matches, fall back to fileRep.
  const srcNode = (
    srcPath: string | null | undefined,
    srcLine: number | null | undefined,
  ): string | undefined => {
    const np = srcPath ? norm(srcPath) : "";
    if (srcLine && byBody.has(np)) {
      let best: string | undefined = undefined;
      for (const [ln, el, sid] of byBody.get(np)!) {
        if (ln > srcLine) break;
        if (ln <= srcLine && srcLine <= el) best = sid; // keep updating → ends on the innermost one (largest line)
      }
      if (best !== undefined) return best;
    }
    return fileRep.get(np);
  };

  // Build the adjacency outTargets[i] = [(j, weight), ...], plus external inflow in externalInflow[j].
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
    // queue 5: multiply in the referenced symbol's quality factor.
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
  // queue 4: the personalization teleport vector P (the focus preference); without one, a uniform
  // 1/n, which is the original static behaviour and stays backward compatible.
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
      // Dangling mass flows back along the personalization distribution (aider uses dangling=P).
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

/** Rank symbols by importance and return them carrying a "rank" score, sorted high to low (the
 *  original fields plus rank).
 *  Passing topN returns only the first N. focusSymbols/focusFiles (queue 4, query-aware) are the
 *  symbols and files the caller explicitly says are being edited or asked about, which biases the
 *  ranking toward them; omit them for the original static structural-centrality ranking. */
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
  // Stable descending sort: equal ranks keep their original relative order, matching the stability of
  // Python's sort(reverse=True).
  ranked.sort((a, b) => b.rank - a.rank);
  return topN !== null ? ranked.slice(0, topN) : ranked;
}
