// Resolve TypeScript and JavaScript references through a Node subprocess.
//
// The Python side, codesextant/references.py, calls this over stdin JSON and reads stdout JSON.
// It gives TS/JS high-confidence import resolution (findReferences rules out same-name noise,
// which is what jedi does for Python).
//
// Two modes are available. Batch mode loads the project once and resolves each symbol
// without starting a separate Node process:
//   single  stdin {projectRoot, defFile, symbol}
//           stdout {symbol, definition, high_confidence:[...], engine, elapsed_ms}
//   batch   stdin {projectRoot, defFile, symbols:["A","B",...]}
//           stdout {batch:true, results:{A:{...}, B:{...}}, engine, elapsed_ms}
//   failure {error, high_confidence:[]}  The Python side falls back to name matching.
//
// Every reference carries is_reexport (whether it sits inside `export {X}` /
// `export {X} from './y'`), so the Python side marks a symbol that is only re-exported by a
// barrel file, with no real consumer, as REEXPORT_ONLY instead of misjudging it LIKELY_UNUSED.
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

// Whether a reference falls inside an export specifier (re-export / export, not real use).
// Both `export { X }` (exported from this file) and `export { X } from './y'` (barrel
// re-export) count, since both publish the symbol rather than use it; round 4 separates
// REEXPORT_ONLY on this basis.
function isReexportRef(node) {
  let n = node;
  while (n) {
    const k = n.getKind();
    if (k === SyntaxKind.ExportSpecifier) return true;
    if (k === SyntaxKind.SourceFile) break;  // stop at the file level, never walk up forever
    n = n.getParent();
  }
  return false;
}

try {
  const input = JSON.parse(await readStdin());
  const { projectRoot, defFile, symbol, symbols } = input;

  // Use the tsconfig compilerOptions when one exists (paths/baseUrl make import resolution
  // more accurate); always glob for files by hand (not limited to tsconfig include, so every
  // reference in the project is reachable).
  const tsconfig = path.join(projectRoot, "tsconfig.json");
  const project = fs.existsSync(tsconfig)
    ? new Project({ tsConfigFilePath: tsconfig, skipAddingFilesFromTsConfig: true })
    : new Project({ compilerOptions: { allowJs: true }, skipFileDependencyResolution: true });
  project.addSourceFilesAtPaths(
    `${projectRoot.replace(/\\/g, "/")}/**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs}`
  );

  // Resolve the definition and references of one symbol in one file (shared by single/batch).
  // Never throws: malformed input comes back as an object carrying error.
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
        if (ref.isDefinition()) continue;  // skip the definition site itself
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
    // Round-5 batch mode: one new Project (built above), then loop symbols calling findReferences.
    out.batch = true;
    out.results = {};
    for (const s of symbols) out.results[s] = resolveOne(defFile, s);
  } else {
    // Single mode (backward compatible with round 3's ts_morph_references)
    Object.assign(out, resolveOne(defFile, symbol));
  }
  out.elapsed_ms = Date.now() - t0;
  console.log(JSON.stringify(out));
} catch (e) {
  out.error = "ts-morph failed: " + (e && e.message ? e.message : String(e));
  if (!out.high_confidence) out.high_confidence = [];
  console.log(JSON.stringify(out));
  process.exit(0);  // never exit non-zero; the Python side decides fallback from the error field
}
