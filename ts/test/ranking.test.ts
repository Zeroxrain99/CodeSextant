// ranking.ts 黃金測試 — 對照凍結的 Python 版 ranking.py（ground truth = fixtures/expected_ranking.json，
// 由 test/gen_ranking_gt.py 生成）。input(symbols/refs/opts) 由 Python gen 定義、TS 餵同樣 input 比對輸出，
// 杜絕「TS/Python case 定義漂移」。浮點 PageRank 用 toBeCloseTo（IEEE 754 兩語言一致、容差防末位）。
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  wellNamed,
  symbolQualityMult,
  buildPersonalization,
  computePagerank,
  rankSymbols,
  type RankSymbol,
  type RankRef,
} from "../src/ranking.js";

const here = dirname(fileURLToPath(import.meta.url));

interface RankingGroundTruth {
  wellnamed: Array<{ name: string; result: boolean }>;
  quality: Array<{ name: string; defines: number; mult: number }>;
  personalization: Array<{
    symbols: RankSymbol[];
    focus_symbols: string[] | null;
    focus_files: string[] | null;
    result: Record<string, number> | null;
  }>;
  pagerank: Array<{
    label: string;
    symbols: RankSymbol[];
    refs: RankRef[];
    opts: { focus_symbols?: string[]; focus_files?: string[] };
    ranked_names: string[];
    scores: Record<string, number>;
  }>;
}
const gt = JSON.parse(
  readFileSync(join(here, "fixtures", "expected_ranking.json"), "utf-8"),
) as RankingGroundTruth;

describe("ranking 黃金測試 — wellNamed 對照 Python 版", () => {
  for (const c of gt.wellnamed) {
    it(`wellNamed(${c.name}) === ${c.result}`, () => {
      expect(wellNamed(c.name)).toBe(c.result);
    });
  }
});

describe("ranking 黃金測試 — symbolQualityMult 對照 Python 版", () => {
  for (const c of gt.quality) {
    it(`mult(${c.name}, defines=${c.defines})`, () => {
      expect(symbolQualityMult(c.name, c.defines)).toBeCloseTo(c.mult, 12);
    });
  }
});

describe("ranking 黃金測試 — buildPersonalization 對照 Python 版", () => {
  gt.personalization.forEach((c, i) => {
    it(`personalization #${i}（focus_symbols=${JSON.stringify(c.focus_symbols)}）`, () => {
      const p = buildPersonalization(c.symbols, c.focus_symbols, c.focus_files);
      if (c.result === null) {
        expect(p).toBeNull();
        return;
      }
      expect(p).not.toBeNull();
      const obj = Object.fromEntries(p!);
      // 同一組 symbol_id key + 每個權重值對照（兩語言 symbol_id 字串格式一致）
      expect(new Set(Object.keys(obj))).toEqual(new Set(Object.keys(c.result)));
      for (const [k, v] of Object.entries(c.result)) {
        expect(obj[k]).toBeCloseTo(v, 12);
      }
    });
  });
});

describe("ranking 黃金測試 — computePagerank + rankSymbols 對照 Python 版", () => {
  for (const c of gt.pagerank) {
    const focusSymbols = c.opts.focus_symbols ?? null;
    const focusFiles = c.opts.focus_files ?? null;

    it(`pagerank「${c.label}」— rankSymbols 排序與 Python 一致`, () => {
      const ranked = rankSymbols(c.symbols, c.refs, { focusSymbols, focusFiles });
      expect(ranked.map((s) => s.name)).toEqual(c.ranked_names);
    });

    it(`pagerank「${c.label}」— computePagerank 分數與 Python 一致`, () => {
      const pers = buildPersonalization(c.symbols, focusSymbols, focusFiles);
      const scores = computePagerank(c.symbols, c.refs, { personalization: pers });
      // 節點數一致
      expect(scores.size).toBe(Object.keys(c.scores).length);
      // 每個 symbol_id 的分數對照（9 位小數容差）
      for (const [sid, sc] of Object.entries(c.scores)) {
        const got = scores.get(sid);
        expect(got, `score for ${sid}`).toBeDefined();
        expect(got!).toBeCloseTo(sc, 9);
      }
    });
  }
});
