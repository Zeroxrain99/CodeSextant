// P0 硬前置閘 PoC：驗證 web-tree-sitter 在 Node 能跨語言抽符號（全 TS 重寫路線的核心假設）。
// 對 Python/TypeScript/Go 各抽 function/class/method，印出名+行號。通過＝TS 路線坐實。
// 跑法：npm run poc:symbols
import { Parser, Language, type Node } from "web-tree-sitter";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const wasmDir = join(here, "..", "..", "node_modules", "tree-sitter-wasms", "out");

interface LangSpec {
  wasm: string;
  code: string;
  defTypes: string[]; // 結構定義節點型別（對應 Python symbols.py LANGUAGE_SPECS 的 always）
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
      console.log(`[${lang}] ❌ parse 回 null`);
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
    console.log(`\n[${lang}] 抽到 ${found.length} 個符號：`);
    for (const f of found) console.log("  " + f);
  }
  console.log(`\n=== P0 PoC 結果：3 語言共抽 ${totalFound} 個符號 ===`);
  if (totalFound < 8) {
    console.log("⚠ 少於預期(8)，需檢查節點型別/grammar");
    process.exit(1);
  }
  console.log("✅ web-tree-sitter 在 Node 跨語言抽符號可行 — 全 TS 路線坐實");
}

main().catch((e) => {
  console.error("❌ PoC 失敗：", e);
  process.exit(1);
});
