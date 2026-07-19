// CodeSextant C5b / 序4+序5 — ts-morph 找引用橋（Node 子進程）。
//
// Python 端 codesextant/references.py 透過 stdin JSON 呼叫，stdout 回 JSON。
// 給 TS/JS 高信心 import 解析（findReferences 排除同名干擾，等同 jedi 對 Python 的價值）。
//
// 兩種模式（同一支橋；batch 是序5 的核心提速——一次 new Project 載入整個專案後 loop 多符號，
// 取代「逐符號各 spawn 一次 node 各重載整個專案」的 N× 浪費）：
//   單一  stdin {projectRoot, defFile, symbol}
//         stdout {symbol, definition, high_confidence:[...], engine, elapsed_ms}
//   批量  stdin {projectRoot, defFile, symbols:["A","B",...]}
//         stdout {batch:true, results:{A:{...}, B:{...}}, engine, elapsed_ms}
//   失敗  {error, high_confidence:[]}  ← Python 端據此 fallback 回 C5a 名稱比對
//
// 序4：每個 reference 標 is_reexport（是否在 `export {X}` / `export {X} from './y'` 裡）——
// 讓 Python 端把「只被 barrel re-export、無真消費」的符號標 REEXPORT_ONLY 而非誤判 LIKELY_UNUSED。
import { Project, SyntaxKind } from "ts-morph";
import fs from "node:fs";
import path from "node:path";

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf-8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
  });
}

const t0 = Date.now();
const out = { engine: "ts-morph" };

// reference 是否落在 export specifier 內（re-export / 導出，非真消費）。
// `export { X }`（本檔導出）與 `export { X } from './y'`（barrel re-export）都算——
// 兩者都是「把符號公開」而非「使用符號」，序4 據此區分 REEXPORT_ONLY。
function isReexportRef(node) {
  let n = node;
  while (n) {
    const k = n.getKind();
    if (k === SyntaxKind.ExportSpecifier) return true;
    if (k === SyntaxKind.SourceFile) break;  // 到檔層就停，不無限上溯
    n = n.getParent();
  }
  return false;
}

try {
  const input = JSON.parse(await readStdin());
  const { projectRoot, defFile, symbol, symbols } = input;

  // 有 tsconfig 用它的 compilerOptions（paths/baseUrl 讓 import 解析更準）；
  // 一律手動 glob 收檔（不限 tsconfig include，確保整個專案引用都掃得到）。
  const tsconfig = path.join(projectRoot, "tsconfig.json");
  const project = fs.existsSync(tsconfig)
    ? new Project({ tsConfigFilePath: tsconfig, skipAddingFilesFromTsConfig: true })
    : new Project({ compilerOptions: { allowJs: true }, skipFileDependencyResolution: true });
  project.addSourceFilesAtPaths(
    `${projectRoot.replace(/\\/g, "/")}/**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs}`
  );

  // 解析「某檔內某符號」的定義與引用（單一/批量共用）。永不拋——畸形回帶 error 的物件。
  function resolveOne(df, sym) {
    const sf = project.getSourceFile(df);
    if (!sf) return { symbol: sym, error: `defFile not loaded: ${df}`, high_confidence: [] };
    const decl =
      sf.getFunction(sym) ?? sf.getClass(sym) ?? sf.getInterface(sym) ??
      sf.getTypeAlias(sym) ?? sf.getEnum(sym) ?? sf.getVariableDeclaration(sym);
    if (!decl) {
      return { symbol: sym, error: `declaration not found: ${sym} in ${df}`, high_confidence: [] };
    }
    const definition = {
      path: decl.getSourceFile().getFilePath(),
      line: decl.getStartLineNumber(),
    };
    const high = [];
    let reexportCount = 0;
    for (const rs of decl.findReferences()) {
      for (const ref of rs.getReferences()) {
        if (ref.isDefinition()) continue;  // 排除定義自身那一處
        const node = ref.getNode();
        const rx = isReexportRef(node);
        if (rx) reexportCount++;
        high.push({
          src_path: ref.getSourceFile().getFilePath(),
          line: node.getStartLineNumber(),
          column: node.getStart() - node.getStartLinePos(),
          confidence: "high",
          is_reexport: rx,
        });
      }
    }
    return { symbol: sym, definition, high_confidence: high, reexport_count: reexportCount };
  }

  if (Array.isArray(symbols)) {
    // 序5 批量模式：一次 new Project（上面已建），loop 多符號各自 findReferences。
    out.batch = true;
    out.results = {};
    for (const s of symbols) out.results[s] = resolveOne(defFile, s);
  } else {
    // 單一模式（向後相容序3 的 ts_morph_references）
    Object.assign(out, resolveOne(defFile, symbol));
  }
  out.elapsed_ms = Date.now() - t0;
  console.log(JSON.stringify(out));
} catch (e) {
  out.error = "ts-morph failed: " + (e && e.message ? e.message : String(e));
  if (!out.high_confidence) out.high_confidence = [];
  console.log(JSON.stringify(out));
  process.exit(0);  // 永不非零退出——讓 Python 端據 error 欄位決定 fallback
}
