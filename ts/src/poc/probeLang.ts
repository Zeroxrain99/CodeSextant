// Probe tool: print the named node types and AST shape a tree-sitter-wasms grammar produces
// for one file. Used to pin down where tree-sitter-wasms grammars differ in node type from the
// tree-sitter-language-pack grammars the Python version uses.
// Usage (from ts/, keep argv paths ASCII and relative to dodge non-ASCII encoding trouble):
//   npx tsx src/poc/probeLang.ts lua test/fixtures/samples/sample.lua
import { Parser, Language, type Node } from "web-tree-sitter";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const nodeRequire = createRequire(import.meta.url);
const wasmDir = join(dirname(nodeRequire.resolve("tree-sitter-wasms/package.json")), "out");

async function main(): Promise<void> {
  const grammar = process.argv[2];
  const file = process.argv[3];
  if (grammar === undefined || file === undefined) {
    console.error("usage: probeLang <grammar> <relative-file>");
    process.exit(1);
  }
  await Parser.init();
  const lang = await Language.load(readFileSync(join(wasmDir, `tree-sitter-${grammar}.wasm`)));
  const parser = new Parser();
  parser.setLanguage(lang);
  const tree = parser.parse(readFileSync(file, "utf-8"));
  if (tree === null) {
    console.error("parse returned null");
    process.exit(1);
  }
  const types = new Set<string>();
  const print = (n: Node, depth: number): void => {
    if (n.isNamed) {
      types.add(n.type);
      const nameNode = n.childForFieldName("name");
      console.log(
        "  ".repeat(depth) + n.type +
        (nameNode ? ` [name=${nameNode.text}]` : "") +
        ` @L${n.startPosition.row + 1}`,
      );
    }
    for (const c of n.children) if (c !== null) print(c, depth + (n.isNamed ? 1 : 0));
  };
  print(tree.rootNode, 0);
  console.log("\n=== named node types (deduped) ===");
  console.log([...types].sort().join("  "));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
