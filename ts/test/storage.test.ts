// storage.ts 黃金測試 —
//   (A) 對照凍結的 Python 版 storage.py ground truth（fixtures/expected_storage.json）：
//       - project_key：TS 與 Python 算出相同 sha1 ⇒ 同專案共用同一個 .db 庫（不混線命脈）。
//       - file_content_hash：同檔同 sha256 ⇒ 增量失效 key 跨語言一致。
//   (B) 行為測試（邏輯內生、不需 Python 對照）：開庫/增量/符號 round-trip/引用邊/呼叫鏈 CTE/
//       fingerprints+comments/stats/fail-soft 列舉。
//
// ground truth 由 test/gen_storage_gt.py 用 Python 版生成。project_key 的 normcase 行為依平台，
// 故 ground truth 標記 platform，TS 端只在同平台對照（誠實 skip 跨平台）。
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  ProjectStore,
  projectKey,
  fileContentHash,
  listIndexedProjects,
  type SymbolDef,
} from "../src/storage.js";

const here = dirname(fileURLToPath(import.meta.url));
const samplesDir = join(here, "fixtures", "samples");

interface StorageGroundTruth {
  platform: string;
  project_key: Record<string, string>;
  file_content_hash: Record<string, string>;
}
const gt = JSON.parse(
  readFileSync(join(here, "fixtures", "expected_storage.json"), "utf-8"),
) as StorageGroundTruth;

// ── (A) ground truth 對照 ──
describe("storage 黃金測試 — project_key 對照 Python 版（共用 .db 庫命脈）", () => {
  const samePlatform = process.platform === gt.platform;
  for (const [path, expected] of Object.entries(gt.project_key)) {
    it(`project_key(${path}) 與 Python 版一致`, () => {
      if (!samePlatform) {
        // normcase 依平台；ground truth 是在 gt.platform 生成的，跨平台不對照（誠實 skip）。
        return;
      }
      expect(projectKey(path)).toBe(expected);
    });
  }

  it("normcase 把大小寫 + 正反斜線正規化成同一把 key", () => {
    if (process.platform !== "win32") return;
    // Windows 上 E:\Ai-King\Foo 與 E:/ai-king/foo 必須對應同一個 project_key。
    expect(projectKey("E:\\Ai-King\\Foo")).toBe(projectKey("E:/ai-king/foo"));
  });
});

describe("storage 黃金測試 — file_content_hash 對照 Python 版（增量失效 key）", () => {
  for (const [name, expected] of Object.entries(gt.file_content_hash)) {
    it(`file_content_hash(${name}) 與 Python 版一致`, () => {
      expect(fileContentHash(join(samplesDir, name))).toBe(expected);
    });
  }
});

// ── (B) 行為測試（庫隔離到臨時 CODESEXTANT_HOME）──
describe("storage 行為測試", () => {
  let tmpHome: string;
  let tmpRepo: string;
  const savedHome = process.env["CODESEXTANT_HOME"];

  beforeEach(() => {
    tmpHome = mkdtempSync(join(tmpdir(), "csx-home-"));
    tmpRepo = mkdtempSync(join(tmpdir(), "csx-repo-"));
    process.env["CODESEXTANT_HOME"] = tmpHome;
  });

  afterEach(() => {
    if (savedHome === undefined) delete process.env["CODESEXTANT_HOME"];
    else process.env["CODESEXTANT_HOME"] = savedHome;
    // Windows 上 better-sqlite3 close 後 .db handle 釋放偶有延遲 → rmSync EPERM；maxRetries 兜底。
    const rmOpts = { recursive: true, force: true, maxRetries: 5, retryDelay: 100 };
    rmSync(tmpHome, rmOpts);
    rmSync(tmpRepo, rmOpts);
  });

  const sym = (
    kind: string,
    name: string,
    line: number,
    end_line: number,
    scope = "",
  ): SymbolDef => ({ kind, name, line, end_line, scope });

  it("open 空庫 stats 全 0、schema_version 正確", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const s = store.stats();
      expect(s.indexed_files).toBe(0);
      expect(s.symbols).toBe(0);
      expect(s.refs).toBe(0);
      expect(s.schema_version).toBe(3);
      expect(s.last_indexed_at).toBeNull();
      expect(s.indexed_git_sha).toBeNull();
      expect(s.project_key).toBe(projectKey(tmpRepo));
    } finally {
      store.close();
    }
  });

  it("storeFileSymbols → getSymbols round-trip + needsReindex 增量", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const fpath = join(tmpRepo, "a.py");
      const syms = [
        sym("class", "Foo", 1, 20),
        sym("method", "bar", 3, 8, "Foo"),
        sym("function", "top", 22, 25),
      ];
      expect(store.needsReindex(fpath, "h1")).toBe(true); // 庫裡沒這檔
      store.storeFileSymbols(fpath, "h1", syms, 1000.5);
      // round-trip：欄位逐一對齊（含 scope）
      expect(store.getSymbols(fpath)).toEqual([
        { path: fpath, kind: "class", name: "Foo", line: 1, end_line: 20, scope: "" },
        { path: fpath, kind: "method", name: "bar", line: 3, end_line: 8, scope: "Foo" },
        { path: fpath, kind: "function", name: "top", line: 22, end_line: 25, scope: "" },
      ]);
      // 增量：同 hash 不重算、改 hash 要重算
      expect(store.needsReindex(fpath, "h1")).toBe(false);
      expect(store.needsReindex(fpath, "h2")).toBe(true);
      // stats 計數 + last_indexed_at（REAL 浮點原樣回）
      const s = store.stats();
      expect(s.indexed_files).toBe(1);
      expect(s.symbols).toBe(3);
      expect(s.last_indexed_at).toBe(1000.5);
      // findSymbolDefinitions
      expect(store.findSymbolDefinitions("bar").map((r) => r.name)).toEqual(["bar"]);
      // 重寫該檔（先清舊符號）
      store.storeFileSymbols(fpath, "h2", [sym("function", "only", 1, 2)], 2000);
      expect(store.getSymbols(fpath).map((r) => r.name)).toEqual(["only"]);
      expect(store.stats().symbols).toBe(1);
    } finally {
      store.close();
    }
  });

  it("removeFile 清掉符號 + 檔記錄 + 引用邊", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const fpath = join(tmpRepo, "a.py");
      store.storeFileSymbols(fpath, "h1", [sym("function", "f", 1, 5)], 1);
      store.replaceRefsFor(fpath, [
        { src_path: fpath, src_line: 2, symbol_name: "g", confidence: "low" },
      ]);
      expect(store.stats().symbols).toBe(1);
      expect(store.stats().refs).toBe(1);
      store.removeFile(fpath);
      expect(store.stats().symbols).toBe(0);
      expect(store.stats().indexed_files).toBe(0);
      expect(store.stats().refs).toBe(0);
      expect(store.allIndexedFiles()).toEqual([]);
    } finally {
      store.close();
    }
  });

  it("replaceRefsFor → allRefs round-trip（含 null def_path）", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      store.replaceRefsFor(a, [
        { src_path: a, src_line: 5, symbol_name: "g", def_path: join(tmpRepo, "b.py"), def_line: 1, confidence: "high" },
        { src_path: a, src_line: 9, symbol_name: "h", confidence: "low" }, // def 未解析 → null
      ]);
      const refs = store.allRefs();
      expect(refs.length).toBe(2);
      const low = refs.find((r) => r.symbol_name === "h")!;
      expect(low.def_path).toBeNull();
      expect(low.def_line).toBeNull();
      // 重寫該 src 檔的邊（先清舊）
      store.replaceRefsFor(a, [{ src_path: a, src_line: 1, symbol_name: "x", confidence: "low" }]);
      expect(store.allRefs().map((r) => r.symbol_name)).toEqual(["x"]);
    } finally {
      store.close();
    }
  });

  it("traverseCallGraph：up 找 caller、down 找 callee（CTE 遞迴）", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      const b = join(tmpRepo, "b.py");
      // a.py 第 1-10 行有 function f；b.py 第 1-5 行有 function g
      store.storeFileSymbols(a, "ha", [sym("function", "f", 1, 10)], 1);
      store.storeFileSymbols(b, "hb", [sym("function", "g", 1, 5)], 1);
      // f 在第 5 行呼叫 g（定義在 b.py）
      store.replaceRefsFor(a, [
        { src_path: a, src_line: 5, symbol_name: "g", def_path: b, def_line: 1, confidence: "high" },
      ]);
      // up：誰呼叫 g → f
      const callers = store.traverseCallGraph("g", b, "up");
      expect(callers.map((c) => [c.name, c.path, c.depth, c.confidence])).toEqual([
        ["f", a, 1, "high"],
      ]);
      // down：f 呼叫誰 → g
      const callees = store.traverseCallGraph("f", a, "down");
      expect(callees.map((c) => [c.name, c.path, c.depth, c.confidence])).toEqual([
        ["g", b, 1, "high"],
      ]);
      // refs 表為空（換個沒邊的符號）→ 回 []
      expect(store.traverseCallGraph("nobody", a, "up")).toEqual([]);
    } finally {
      store.close();
    }
  });

  it("traverseCallGraph 非法 direction 拋錯", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      expect(() =>
        store.traverseCallGraph("f", join(tmpRepo, "a.py"), "sideways" as "up"),
      ).toThrow();
    } finally {
      store.close();
    }
  });

  it("fingerprints + comments 落盤（含 null 欄位）不爆 + stats 計數", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const fpath = join(tmpRepo, "a.py");
      store.storeFileSymbols(fpath, "h1", [sym("function", "f", 1, 5)], 1);
      store.storeFileFingerprints(
        fpath,
        [
          { name: "f", kind: "function", line: 1, end_line: 5, shape_hash: "S1", raw_token_hash: "R1", call_hash: "C1", node_count: 10, nstmts: 3, has_control_flow: true, cognitive: 7 },
          { name: "g", kind: "function", line: 6, end_line: 9, shape_hash: "S2", cognitive: null }, // 多欄缺省 → null
        ],
        [{ line: 2, fp_value: 123 }, { line: 3, fp_value: 456 }],
      );
      store.storeFileComments(fpath, [
        { line: 1, end_line: 1, kind: "comment", is_doc: false, tag: "TODO", text: "fix me" },
        { line: 2, kind: "string", is_doc: true, owner_line: 1, text: "docstring" }, // end_line 缺省 → 用 line
      ]);
      const s = store.stats();
      expect(s.fingerprints).toBe(2);
      expect(s.comments).toBe(2);
      // removeFile 連 fingerprints/comments 一起清
      store.removeFile(fpath);
      expect(store.stats().fingerprints).toBe(0);
      expect(store.stats().comments).toBe(0);
    } finally {
      store.close();
    }
  });

  it("recordGitSha 寫入後 stats.indexed_git_sha 讀回", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      expect(store.stats().indexed_git_sha).toBeNull();
      store.recordGitSha("abc1234");
      expect(store.stats().indexed_git_sha).toBe("abc1234");
    } finally {
      store.close();
    }
  });

  // ── review 補測：CTE 信心傳播（HIGH 盲區，最易平移錯的核心邏輯）──
  it("traverseCallGraph：多跳傳遞 + confidence='low' 傳播 + max_hops 截斷", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      const b = join(tmpRepo, "b.py");
      const c = join(tmpRepo, "c.py");
      store.storeFileSymbols(a, "ha", [sym("function", "f", 1, 10)], 1);
      store.storeFileSymbols(b, "hb", [sym("function", "g", 1, 10)], 1);
      store.storeFileSymbols(c, "hc", [sym("function", "h", 1, 10)], 1);
      // f →(low) g →(high) h
      store.replaceRefsFor(a, [{ src_path: a, src_line: 5, symbol_name: "g", def_path: b, def_line: 1, confidence: "low" }]);
      store.replaceRefsFor(b, [{ src_path: b, src_line: 5, symbol_name: "h", def_path: c, def_line: 1, confidence: "high" }]);
      // up('h')：g depth1 high（g→h 那段 high）；f depth2 low（鏈含 f→g low 邊，黏性傳播）
      expect(store.traverseCallGraph("h", c, "up").map((x) => [x.name, x.depth, x.confidence])).toEqual([
        ["g", 1, "high"],
        ["f", 2, "low"],
      ]);
      // max_hops=1：只回 depth1 的 g，截斷 f
      expect(store.traverseCallGraph("h", c, "up", 1).map((x) => x.name)).toEqual(["g"]);
      // down('f')：g depth1 low（f→g low）、h depth2 low（min_conf 已 low、黏性）
      expect(store.traverseCallGraph("f", a, "down").map((x) => [x.name, x.depth, x.confidence])).toEqual([
        ["g", 1, "low"],
        ["h", 2, "low"],
      ]);
    } finally {
      store.close();
    }
  });

  it("traverseCallGraph：同節點 high+low 雙路徑取 high（MAX 聚合）+ MIN depth", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      const b = join(tmpRepo, "b.py");
      const c = join(tmpRepo, "c.py");
      store.storeFileSymbols(a, "ha", [sym("function", "x", 1, 20)], 1);
      store.storeFileSymbols(b, "hb", [sym("function", "g", 1, 10)], 1);
      store.storeFileSymbols(c, "hc", [sym("function", "h", 1, 5)], 1);
      // x →(high) h 直達；x →(low) g →(high) h 繞路。x 對 h 同時有 depth1-high 與 depth2-low 兩路徑。
      store.replaceRefsFor(a, [
        { src_path: a, src_line: 2, symbol_name: "h", def_path: c, def_line: 1, confidence: "high" },
        { src_path: a, src_line: 3, symbol_name: "g", def_path: b, def_line: 1, confidence: "low" },
      ]);
      store.replaceRefsFor(b, [{ src_path: b, src_line: 2, symbol_name: "h", def_path: c, def_line: 1, confidence: "high" }]);
      const byName = Object.fromEntries(
        store.traverseCallGraph("h", c, "up").map((n) => [n.name, n]),
      );
      // x 存在「全 high 路徑」→ MAX 聚合取 high（即使另有 low 路徑）；MIN depth=1
      expect(byName["x"]!.confidence).toBe("high");
      expect(byName["x"]!.depth).toBe(1);
      expect(byName["g"]!.confidence).toBe("high");
    } finally {
      store.close();
    }
  });

  it("traverseCallGraph：自呼叫不無限遞迴（環防護）", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      store.storeFileSymbols(a, "ha", [sym("function", "f", 1, 10)], 1);
      // f 在自己 body 內呼叫 f（遞迴）
      store.replaceRefsFor(a, [{ src_path: a, src_line: 5, symbol_name: "f", def_path: a, def_line: 1, confidence: "high" }]);
      // NOT(s.name=c.name AND s.path=c.path) 過濾自環 → 不回自己、不無限遞迴
      expect(store.traverseCallGraph("f", a, "up")).toEqual([]);
      expect(store.traverseCallGraph("f", a, "down")).toEqual([]);
    } finally {
      store.close();
    }
  });

  // ── review 補測：getSymbols() 無參全專案排序（HIGH 盲區）──
  it("getSymbols() 無參：跨檔 ORDER BY path,line（path 為主排序鍵）", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      const b = join(tmpRepo, "b.py");
      // b.py 的 line 故意比 a.py 小，驗 path 是主鍵（b 的 line1 不會插到 a 的 line9 之前）
      store.storeFileSymbols(b, "hb", [sym("function", "b2", 2, 3), sym("function", "b1", 1, 1)], 1);
      store.storeFileSymbols(a, "ha", [sym("function", "a9", 9, 9)], 1);
      expect(store.getSymbols().map((s) => [s.path, s.name])).toEqual([
        [a, "a9"],
        [b, "b1"],
        [b, "b2"],
      ]);
    } finally {
      store.close();
    }
  });

  // ── review 補測：findSymbolDefinitions 同名多定義排序（MEDIUM 盲區）──
  it("findSymbolDefinitions：同名多定義按 path,line 排序（粗篩候選契約）", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      const b = join(tmpRepo, "b.py");
      store.storeFileSymbols(b, "hb", [sym("function", "dup", 1, 1)], 1);
      store.storeFileSymbols(a, "ha", [sym("function", "dup", 5, 5), sym("function", "dup", 2, 2)], 1);
      expect(store.findSymbolDefinitions("dup").map((d) => [d.path, d.line])).toEqual([
        [a, 2],
        [a, 5],
        [b, 1],
      ]);
    } finally {
      store.close();
    }
  });

  // ── review 補測：空輸入路徑（MEDIUM 盲區）──
  it("空 symbols 仍登記 files（無頂層符號的檔也計入增量）+ 空 fingerprints 清舊", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const fpath = join(tmpRepo, "empty.py");
      store.storeFileSymbols(fpath, "h1", [], 1);
      // 無符號但 file 已登記：needsReindex false、indexed_files 計入、symbols 0
      expect(store.needsReindex(fpath, "h1")).toBe(false);
      expect(store.stats().indexed_files).toBe(1);
      expect(store.stats().symbols).toBe(0);
      // 先存非空指紋，再用空陣列清掉（executemany→for-loop 空陣列等價於 no-op + DELETE）
      store.storeFileFingerprints(fpath, [{ name: "x", shape_hash: "S" }], [{ line: 1, fp_value: 9 }]);
      expect(store.stats().fingerprints).toBe(1);
      store.storeFileFingerprints(fpath, [], []);
      expect(store.stats().fingerprints).toBe(0);
    } finally {
      store.close();
    }
  });

  // ── review 補測：getMeta default 分支直測（LOW 盲區）──
  it("getMeta：default 分支 + 寫入後讀回", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      expect(store.getMeta("nonexistent")).toBeNull();
      expect(store.getMeta("nonexistent", "fallback")).toBe("fallback");
      expect(store.getMeta("schema_version")).toBe("3"); // open 時已寫
      expect(store.getMeta("repo_path")).toBe(store.repoPath);
    } finally {
      store.close();
    }
  });

  // ── review 補測：REAL 整數值的 number-vs-float 已知 wire 差異（鎖 TS 行為）──
  it("REAL 整數值 last_indexed_at 回 number（與 Python float 的已知 wire 差異，見頭部邊界註解）", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      store.storeFileSymbols(join(tmpRepo, "a.py"), "h", [sym("function", "f", 1, 2)], 2000);
      expect(store.stats().last_indexed_at).toBe(2000);
      // JS number 不分 int/float：JSON 序列化成 "2000"（Python 為 "2000.0"）
      expect(JSON.stringify(store.stats().last_indexed_at)).toBe("2000");
    } finally {
      store.close();
    }
  });

  it("listIndexedProjects：列出正常庫 + 壞庫 fail-soft 標 error", () => {
    // 正常庫：tmpRepo 真實存在 → path_exists true
    const s1 = ProjectStore.open(tmpRepo);
    const expectedRepo = s1.repoPath; // = resolve(tmpRepo)，meta 存的 repo_path
    s1.storeFileSymbols(join(tmpRepo, "a.py"), "h1", [
      { kind: "function", name: "f", line: 1, end_line: 2, scope: "" },
    ], 1);
    s1.close();
    // 壞庫：寫垃圾到一個 .db 檔
    writeFileSync(join(tmpHome, "deadbeef.db"), "this is not a sqlite database");

    const projects = listIndexedProjects();
    // 應含 2 筆（正常 + 壞）
    expect(projects.length).toBe(2);
    const good = projects.find((p) => p.repo_path)!;
    expect(good.repo_path).toBe(expectedRepo);
    expect(good.indexed_files).toBe(1);
    expect(good.symbols).toBe(1);
    expect(good.path_exists).toBe(true);
    const bad = projects.find((p) => p.error)!;
    expect(bad.error).toContain("讀庫失敗");
    expect(bad.project_key).toBe("deadbeef");
  });
});
