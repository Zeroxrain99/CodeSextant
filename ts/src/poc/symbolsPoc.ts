// P0 hard gate PoC: prove web-tree-sitter can extract symbols across languages under Node
// (the core assumption behind the full TypeScript rewrite).
// Extracts function/class/method from Python/TypeScript/Go and prints name + line number.
// Passing means the TypeScript route holds up.
// Usage: npm run poc:symbols
import { Parser, Language, type Node } from "web-tree-sitter";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const wasmDir = join(here, "..", "..", "node_modules", "tree-sitter-wasms", "out");

interface LangSpec {
  wasm: string;
  code: string;
  defTypes: string[]; // structural definition node types (the `always` set in Python symbols.py LANGUAGE_SPECS)
}

const samples: Record<string, LangSpec> = {
  python: {
    wasm: "tree-sitter-python.wasm",
    code: `class Animal:\n    def speak(self):\n        return "woof"\n\ndef top_level(x):\n    return x\n`,
    defTypes: ["class_definition", "function_definition"],
  },
  typescript: {
    wasm: "tree-sitter-typescript.wasm",
    code: `export class Service {\n  run(): void {}\n}\nfunction helper(): number { return 1; }\n`,
    defTypes: ["class_declaration", "function_declaration", "method_definition"],
  },
  go: {
    wasm: "tree-sitter-go.wasm",
    code: `package main\nfunc Hello() {}\ntype T struct{}\nfunc (t T) M() {}\n`,
    defTypes: ["function_declaration", "type_declaration", "method_declaration"],
  },
};

async function main(): Promise<void> {
  await Parser.init();
  let totalFound = 0;
  for (const [lang, spec] of Object.entries(samples)) {
    const bytes = readFileSync(join(wasmDir, spec.wasm));
    const language = await Language.load(bytes);
    const parser = new Parser();
    parser.setLanguage(language);
    const tree = parser.parse(spec.code);
    if (!tree) {
      console.log(`[${lang}] ❌ parse returned null`);
      continue;
    }
    const found: string[] = [];
    const walk = (node: Node): void => {
      if (spec.defTypes.includes(node.type)) {
        const nameNode = node.childForFieldName("name");
        found.push(`${node.type} '${nameNode?.text ?? "<anon>"}' @L${node.startPosition.row + 1}`);
      }
      for (const child of node.children) {
        if (child) walk(child);
      }
    };
    walk(tree.rootNode);
    totalFound += found.length;
    console.log(`\n[${lang}] extracted ${found.length} symbols:`);
    for (const f of found) console.log("  " + f);
  }
  console.log(`\n=== P0 PoC result: ${totalFound} symbols across 3 languages ===`);
  if (totalFound < 8) {
    console.log("⚠ fewer than expected (8): check the node types / grammar");
    process.exit(1);
  }
  console.log("✅ web-tree-sitter extracts symbols across languages under Node; the full TypeScript route holds");
}

main().catch((e) => {
  console.error("❌ PoC failed:", e);
  process.exit(1);
});
