// storage.ts golden tests:
//   (A) Against the frozen Python storage.py ground truth (fixtures/expected_storage.json):
//       - project_key: TypeScript and Python compute the same sha1, so one project shares one .db,
//         which is what keeps projects from crossing wires.
//       - file_content_hash: the same file gives the same sha256, so the incremental invalidation key
//         agrees across languages.
//   (B) Behavioural tests (self-contained logic, no Python comparison needed): opening a database,
//       incrementality, symbol round-trip, reference edges, the call-chain CTE, fingerprints and
//       comments, stats, and fail-soft listing.
//
// The ground truth is generated from the Python version by test/gen_storage_gt.py. project_key's
// normcase behaviour is platform-dependent, so the ground truth records its platform and the
// TypeScript side only compares on a matching platform, and skips honestly elsewhere.
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

// ── (A) ground truth comparison ──
describe("storage golden tests: project_key against Python (what keeps one project on one .db)", () => {
  const samePlatform = process.platform === gt.platform;
  for (const [path, expected] of Object.entries(gt.project_key)) {
    it(`project_key(${path}) matches the Python version`, () => {
      if (!samePlatform) {
        // normcase is platform-dependent and the ground truth was generated on gt.platform, so there
        // is nothing to compare across platforms, so skip honestly.
        return;
      }
      expect(projectKey(path)).toBe(expected);
    });
  }

  it("normcase folds case and slash direction into one key", () => {
    if (process.platform !== "win32") return;
    // On Windows, E:\Ai-King\Foo and E:/ai-king/foo have to map to the same project_key.
    expect(projectKey("E:\\Ai-King\\Foo")).toBe(projectKey("E:/ai-king/foo"));
  });
});

describe("storage golden tests: file_content_hash against Python (the incremental invalidation key)", () => {
  for (const [name, expected] of Object.entries(gt.file_content_hash)) {
    it(`file_content_hash(${name}) matches the Python version`, () => {
      expect(fileContentHash(join(samplesDir, name))).toBe(expected);
    });
  }
});

// ── (B) behavioural tests (the database is isolated in a temporary CODESEXTANT_HOME) ──
describe("storage behaviour", () => {
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
    // On Windows the .db handle is sometimes released a moment after better-sqlite3 close, which
    // makes rmSync fail with EPERM; maxRetries covers that.
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

  it("opening an empty database gives all-zero stats and the right schema_version", () => {
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

  it("storeFileSymbols → getSymbols round-trip, plus needsReindex incrementality", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const fpath = join(tmpRepo, "a.py");
      const syms = [
        sym("class", "Foo", 1, 20),
        sym("method", "bar", 3, 8, "Foo"),
        sym("function", "top", 22, 25),
      ];
      expect(store.needsReindex(fpath, "h1")).toBe(true); // the database has never seen this file
      store.storeFileSymbols(fpath, "h1", syms, 1000.5);
      // round-trip: every field comes back, scope included
      expect(store.getSymbols(fpath)).toEqual([
        { path: fpath, kind: "class", name: "Foo", line: 1, end_line: 20, scope: "" },
        { path: fpath, kind: "method", name: "bar", line: 3, end_line: 8, scope: "Foo" },
        { path: fpath, kind: "function", name: "top", line: 22, end_line: 25, scope: "" },
      ]);
      // incrementality: the same hash needs no recompute, a changed hash does
      expect(store.needsReindex(fpath, "h1")).toBe(false);
      expect(store.needsReindex(fpath, "h2")).toBe(true);
      // stats counts, plus last_indexed_at (a REAL comes back as given)
      const s = store.stats();
      expect(s.indexed_files).toBe(1);
      expect(s.symbols).toBe(3);
      expect(s.last_indexed_at).toBe(1000.5);
      // findSymbolDefinitions
      expect(store.findSymbolDefinitions("bar").map((r) => r.name)).toEqual(["bar"]);
      // rewrite the file (old symbols are cleared first)
      store.storeFileSymbols(fpath, "h2", [sym("function", "only", 1, 2)], 2000);
      expect(store.getSymbols(fpath).map((r) => r.name)).toEqual(["only"]);
      expect(store.stats().symbols).toBe(1);
    } finally {
      store.close();
    }
  });

  it("removeFile clears symbols, the file row and the reference edges", () => {
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

  it("replaceRefsFor → allRefs round-trip, including a null def_path", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      store.replaceRefsFor(a, [
        { src_path: a, src_line: 5, symbol_name: "g", def_path: join(tmpRepo, "b.py"), def_line: 1, confidence: "high" },
        { src_path: a, src_line: 9, symbol_name: "h", confidence: "low" }, // definition unresolved → null
      ]);
      const refs = store.allRefs();
      expect(refs.length).toBe(2);
      const low = refs.find((r) => r.symbol_name === "h")!;
      expect(low.def_path).toBeNull();
      expect(low.def_line).toBeNull();
      // rewrite that source file's edges (the old ones are cleared first)
      store.replaceRefsFor(a, [{ src_path: a, src_line: 1, symbol_name: "x", confidence: "low" }]);
      expect(store.allRefs().map((r) => r.symbol_name)).toEqual(["x"]);
    } finally {
      store.close();
    }
  });

  it("traverseCallGraph: up finds callers, down finds callees (recursive CTE)", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      const b = join(tmpRepo, "b.py");
      // a.py has function f on lines 1-10; b.py has function g on lines 1-5
      store.storeFileSymbols(a, "ha", [sym("function", "f", 1, 10)], 1);
      store.storeFileSymbols(b, "hb", [sym("function", "g", 1, 5)], 1);
      // f calls g on line 5 (g is defined in b.py)
      store.replaceRefsFor(a, [
        { src_path: a, src_line: 5, symbol_name: "g", def_path: b, def_line: 1, confidence: "high" },
      ]);
      // up: who calls g → f
      const callers = store.traverseCallGraph("g", b, "up");
      expect(callers.map((c) => [c.name, c.path, c.depth, c.confidence])).toEqual([
        ["f", a, 1, "high"],
      ]);
      // down: whom f calls → g
      const callees = store.traverseCallGraph("f", a, "down");
      expect(callees.map((c) => [c.name, c.path, c.depth, c.confidence])).toEqual([
        ["g", b, 1, "high"],
      ]);
      // a symbol with no edges gives back []
      expect(store.traverseCallGraph("nobody", a, "up")).toEqual([]);
    } finally {
      store.close();
    }
  });

  it("traverseCallGraph throws on an invalid direction", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      expect(() =>
        store.traverseCallGraph("f", join(tmpRepo, "a.py"), "sideways" as "up"),
      ).toThrow();
    } finally {
      store.close();
    }
  });

  it("fingerprints + comments persist with null fields without blowing up, and stats counts them", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const fpath = join(tmpRepo, "a.py");
      store.storeFileSymbols(fpath, "h1", [sym("function", "f", 1, 5)], 1);
      store.storeFileFingerprints(
        fpath,
        [
          { name: "f", kind: "function", line: 1, end_line: 5, shape_hash: "S1", raw_token_hash: "R1", call_hash: "C1", node_count: 10, nstmts: 3, has_control_flow: true, cognitive: 7 },
          { name: "g", kind: "function", line: 6, end_line: 9, shape_hash: "S2", cognitive: null }, // several fields omitted → null
        ],
        [{ line: 2, fp_value: 123 }, { line: 3, fp_value: 456 }],
      );
      store.storeFileComments(fpath, [
        { line: 1, end_line: 1, kind: "comment", is_doc: false, tag: "TODO", text: "fix me" },
        { line: 2, kind: "string", is_doc: true, owner_line: 1, text: "docstring" }, // end_line omitted → falls back to line
      ]);
      const s = store.stats();
      expect(s.fingerprints).toBe(2);
      expect(s.comments).toBe(2);
      // removeFile clears fingerprints and comments too
      store.removeFile(fpath);
      expect(store.stats().fingerprints).toBe(0);
      expect(store.stats().comments).toBe(0);
    } finally {
      store.close();
    }
  });

  it("recordGitSha writes a sha that stats.indexed_git_sha reads back", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      expect(store.stats().indexed_git_sha).toBeNull();
      store.recordGitSha("abc1234");
      expect(store.stats().indexed_git_sha).toBe("abc1234");
    } finally {
      store.close();
    }
  });

  // ── added after review: CTE confidence propagation (a HIGH blind spot, and the core logic most
  //    easily got wrong in the port) ──
  it("traverseCallGraph: multi-hop transitivity, confidence='low' propagation, max_hops truncation", () => {
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
      // up('h'): g is depth 1 high (the g→h leg is high); f is depth 2 low (its chain includes the
      // low f→g edge, and low is sticky)
      expect(store.traverseCallGraph("h", c, "up").map((x) => [x.name, x.depth, x.confidence])).toEqual([
        ["g", 1, "high"],
        ["f", 2, "low"],
      ]);
      // max_hops=1: only depth-1 g comes back, f is truncated
      expect(store.traverseCallGraph("h", c, "up", 1).map((x) => x.name)).toEqual(["g"]);
      // down('f'): g is depth 1 low (f→g is low), h is depth 2 low (min_conf is already low, and it sticks)
      expect(store.traverseCallGraph("f", a, "down").map((x) => [x.name, x.depth, x.confidence])).toEqual([
        ["g", 1, "low"],
        ["h", 2, "low"],
      ]);
    } finally {
      store.close();
    }
  });

  it("traverseCallGraph: a node reached by both a high and a low path takes high (MAX) and MIN depth", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      const b = join(tmpRepo, "b.py");
      const c = join(tmpRepo, "c.py");
      store.storeFileSymbols(a, "ha", [sym("function", "x", 1, 20)], 1);
      store.storeFileSymbols(b, "hb", [sym("function", "g", 1, 10)], 1);
      store.storeFileSymbols(c, "hc", [sym("function", "h", 1, 5)], 1);
      // x →(high) h directly, and x →(low) g →(high) h the long way round. So x reaches h by both a
      // depth-1 high path and a depth-2 low path.
      store.replaceRefsFor(a, [
        { src_path: a, src_line: 2, symbol_name: "h", def_path: c, def_line: 1, confidence: "high" },
        { src_path: a, src_line: 3, symbol_name: "g", def_path: b, def_line: 1, confidence: "low" },
      ]);
      store.replaceRefsFor(b, [{ src_path: b, src_line: 2, symbol_name: "h", def_path: c, def_line: 1, confidence: "high" }]);
      const byName = Object.fromEntries(
        store.traverseCallGraph("h", c, "up").map((n) => [n.name, n]),
      );
      // x has an all-high path, so the MAX aggregation gives high even though a low path also exists;
      // MIN depth = 1
      expect(byName["x"]!.confidence).toBe("high");
      expect(byName["x"]!.depth).toBe(1);
      expect(byName["g"]!.confidence).toBe("high");
    } finally {
      store.close();
    }
  });

  it("traverseCallGraph: a self-call does not recurse forever (cycle guard)", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      store.storeFileSymbols(a, "ha", [sym("function", "f", 1, 10)], 1);
      // f calls f inside its own body (recursion)
      store.replaceRefsFor(a, [{ src_path: a, src_line: 5, symbol_name: "f", def_path: a, def_line: 1, confidence: "high" }]);
      // NOT(s.name=c.name AND s.path=c.path) filters the self-loop, so it neither returns itself nor
      // recurses forever
      expect(store.traverseCallGraph("f", a, "up")).toEqual([]);
      expect(store.traverseCallGraph("f", a, "down")).toEqual([]);
    } finally {
      store.close();
    }
  });

  // ── added after review: whole-project ordering from getSymbols() with no argument (a HIGH blind spot) ──
  it("getSymbols() with no argument: ORDER BY path,line across files, with path as the primary key", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const a = join(tmpRepo, "a.py");
      const b = join(tmpRepo, "b.py");
      // b.py's lines are deliberately lower than a.py's, to prove path is the primary key: b's line 1
      // must not sort ahead of a's line 9
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

  // ── added after review: ordering of same-name definitions from findSymbolDefinitions (a MEDIUM blind spot) ──
  it("findSymbolDefinitions: same-name definitions sort by path,line (the coarse-candidate contract)", () => {
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

  // ── added after review: the empty-input paths (a MEDIUM blind spot) ──
  it("empty symbols still registers the file, so a file with no top-level symbols counts for incrementality, and empty fingerprints clear the old ones", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      const fpath = join(tmpRepo, "empty.py");
      store.storeFileSymbols(fpath, "h1", [], 1);
      // no symbols but the file is registered: needsReindex false, indexed_files counts it, symbols 0
      expect(store.needsReindex(fpath, "h1")).toBe(false);
      expect(store.stats().indexed_files).toBe(1);
      expect(store.stats().symbols).toBe(0);
      // store non-empty fingerprints first, then clear them with an empty array (the executemany →
      // for-loop port makes an empty array equivalent to a no-op plus the DELETE)
      store.storeFileFingerprints(fpath, [{ name: "x", shape_hash: "S" }], [{ line: 1, fp_value: 9 }]);
      expect(store.stats().fingerprints).toBe(1);
      store.storeFileFingerprints(fpath, [], []);
      expect(store.stats().fingerprints).toBe(0);
    } finally {
      store.close();
    }
  });

  // ── added after review: the getMeta default branch, tested directly (a LOW blind spot) ──
  it("getMeta: the default branch, and reading back what was written", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      expect(store.getMeta("nonexistent")).toBeNull();
      expect(store.getMeta("nonexistent", "fallback")).toBe("fallback");
      expect(store.getMeta("schema_version")).toBe("3"); // written during open
      expect(store.getMeta("repo_path")).toBe(store.repoPath);
    } finally {
      store.close();
    }
  });

  // ── added after review: the known number-vs-float wire difference for integer REAL values, pinning
  //    the TypeScript behaviour ──
  it("an integer REAL last_indexed_at comes back as a number (the known wire difference from Python's float; see the edges note at the top of storage.ts)", () => {
    const store = ProjectStore.open(tmpRepo);
    try {
      store.storeFileSymbols(join(tmpRepo, "a.py"), "h", [sym("function", "f", 1, 2)], 2000);
      expect(store.stats().last_indexed_at).toBe(2000);
      // a JS number does not distinguish int from float, so JSON serializes it as "2000" (Python gives "2000.0")
      expect(JSON.stringify(store.stats().last_indexed_at)).toBe("2000");
    } finally {
      store.close();
    }
  });

  it("listIndexedProjects: lists healthy databases and marks a broken one with error, fail-soft", () => {
    // healthy database: tmpRepo really exists → path_exists true
    const s1 = ProjectStore.open(tmpRepo);
    const expectedRepo = s1.repoPath; // = resolve(tmpRepo), the repo_path stored in meta
    s1.storeFileSymbols(join(tmpRepo, "a.py"), "h1", [
      { kind: "function", name: "f", line: 1, end_line: 2, scope: "" },
    ], 1);
    s1.close();
    // broken database: write garbage into a .db file
    writeFileSync(join(tmpHome, "deadbeef.db"), "this is not a sqlite database");

    const projects = listIndexedProjects();
    // two entries expected: the healthy one and the broken one
    expect(projects.length).toBe(2);
    const good = projects.find((p) => p.repo_path)!;
    expect(good.repo_path).toBe(expectedRepo);
    expect(good.indexed_files).toBe(1);
    expect(good.symbols).toBe(1);
    expect(good.path_exists).toBe(true);
    const bad = projects.find((p) => p.error)!;
    expect(bad.error).toContain("failed to read database");
    expect(bad.project_key).toBe("deadbeef");
  });
});
