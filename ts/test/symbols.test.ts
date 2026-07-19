// symbols.ts 黃金測試 — 對照凍結的 Python 版 v0.15.0 抽符號輸出（ground truth）。
//
// ground truth 由 scratchpad/gen_ground_truth.py 用 Python 版對 fixtures/samples/ 下每檔抽符號生成，
// 存於 fixtures/expected/<name>.json。本測試對同一樣本檔用 TS 版 extractSymbols 抽符號，deep-equal
// 對照——一致即證 TS 版與 Python 版抽符號 parity（藍圖 §四 P1 過關判據）。
//
// 樣本涵蓋 16 語言全部 kind + 關鍵特例：Python module-var assignment / 巢狀 function scope、
// JS 解構跳過、TS interface/type/abstract、Go type_spec、Rust impl scope、C++ qualified declarator
// (Widget::doIt→doIt)、Kotlin name_rules、Ruby keyword-token (module/class/singleton_method)、
// C# constructor/property/record、Swift enum→class 限制。
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { extractSymbols, type SymbolDef } from "../src/symbols.js";

const here = dirname(fileURLToPath(import.meta.url));
const samplesDir = join(here, "fixtures", "samples");
const expectedDir = join(here, "fixtures", "expected");

const sampleFiles = readdirSync(samplesDir).sort();

describe("symbols 黃金測試（對照 Python 版 v0.15.0 ground truth）", () => {
  it("16 個語言樣本全到位（防漏測）", () => {
    expect(sampleFiles.length).toBe(16);
  });

  for (const name of sampleFiles) {
    it(`${name} 抽符號與 Python 版一致`, { timeout: 30000 }, async () => {
      const got = await extractSymbols(join(samplesDir, name));
      const expected = JSON.parse(
        readFileSync(join(expectedDir, `${name}.json`), "utf-8"),
      ) as SymbolDef[];
      expect(got).toEqual(expected);
    });
  }
});
