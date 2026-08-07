// Symbol extraction module: a fast whole-file symbol table across languages via tree-sitter (full
// TypeScript rewrite, P1; ported from Python codesextant/symbols.py).
//
// Porting rules (checked against the Python version's golden-test ground truth):
//   - The 16-language LANGUAGE_SPECS table is 1:1 with the Python version (the tree-sitter node type
//     strings are identical and can be copied verbatim).
//   - The walk logic (is_named filter + the always/scope_only/vars/py_assignment branches) is ported
//     statement by statement.
//   - Output fields keep snake_case (kind/name/line/end_line/scope) to match the Python version's JSON.
//
// Deliberate differences from the Python version (no effect on output parity):
//   - Python reads names from bytes with byte slicing; TypeScript reads node.text (a string) from
//     web-tree-sitter directly, and takes line numbers from node.startPosition.row + 1 (row is
//     0-based). ASCII and non-ASCII identifiers, and line numbers, come out the same either way.
//   - The tree-sitter parse API: web-tree-sitter is async (Parser.init + Language.load(wasm)), so the
//     outward parse path is async; the walk itself is plain synchronous code.
//   - wasm filename mapping: of the 16 languages only csharp has a wasm file named
//     tree-sitter-c_sharp.wasm (every other grammar name matches its wasm filename), so the spec
//     records the middle part of the wasm filename in its grammar field. ⛔ Measured, don't guess.
//
// Single responsibility: take a file path or a piece of source, return that file's symbol definitions
// (functions/classes/methods/types/module-level variables + line numbers + owning scope). It does not
// touch SQLite, does not find references via ts-morph, and does not rank; those belong to other modules.
import { Parser, Language, type Tree, type Node } from "web-tree-sitter";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, extname } from "node:path";

/** One symbol definition. Field names match the Python version's output so storage and the daemon can
 *  serialize them straight to JSON. */
export interface SymbolDef {
  /** "function" / "class" / "method" / "interface" / "type" / "enum" / "struct" / "trait"
   *  / "module" / "protocol" / "constructor" / "property" / "variable", depending on the language. */
  kind: string;
  /** The symbol name. Returns "<anon>" when no name can be read, never a silent null. */
  name: string;
  /** First and last line of the definition (1-based). */
  line: number;
  end_line: number;
  /** Owning scope, e.g. "MyClass" means the method sits inside MyClass; "" means module top level. */
  scope: string;
}

/** Per-language spec (table-driven: adding a language is adding one entry). */
interface LangSpec {
  /** The middle part of the tree-sitter-wasms filename (the wasm path is tree-sitter-<grammar>.wasm). */
  grammar: string;
  /** File extensions (lowercase, with the dot). */
  exts: string[];
  /** {tree-sitter node type: symbol kind}. Structural definitions, collected at any nesting depth,
   *  each one pushing itself onto the scope. */
  always: Record<string, string>;
  /** {node type: kind}. Variable definitions, collected only at module top level (empty scope), to
   *  keep local-variable noise out. */
  vars: Record<string, string>;
  /** Container nodes (such as Rust impl_item): push the named field onto the scope, but do not count
   *  the container itself as a symbol. */
  scopeOnly?: Record<string, string>;
  /** Naming strategy for nodes that have no name field (c_declarator for C/C++, child:<type> for Kotlin). */
  nameRules?: Record<string, string>;
  /** Python special case: a module-level assignment.left becomes a variable (assignment has no name field). */
  pyAssignment?: boolean;
}

// ── 16 language specs (1:1 with the Python LANGUAGE_SPECS; node types and name fields were all
//    measured with _probe) ──
export const LANGUAGE_SPECS: Record<string, LangSpec> = {
  python: {
    grammar: "python",
    exts: [".py", ".pyi"],
    always: { function_definition: "function", class_definition: "class" },
    vars: {}, // Python variables go through the assignment special case
    pyAssignment: true,
  },
  javascript: {
    grammar: "javascript",
    exts: [".js", ".jsx", ".mjs", ".cjs"],
    always: {
      function_declaration: "function",
      class_declaration: "class",
      method_definition: "method",
    },
    vars: { variable_declarator: "variable" },
  },
  typescript: {
    grammar: "typescript",
    exts: [".ts", ".mts", ".cts"],
    always: {
      function_declaration: "function",
      class_declaration: "class",
      abstract_class_declaration: "class", // abstract class Foo
      method_definition: "method",
      abstract_method_signature: "method", // abstract m(): void
      interface_declaration: "interface",
      type_alias_declaration: "type",
      enum_declaration: "enum",
    },
    vars: { variable_declarator: "variable" },
  },
  tsx: {
    grammar: "tsx",
    exts: [".tsx"],
    always: {
      function_declaration: "function",
      class_declaration: "class",
      abstract_class_declaration: "class",
      method_definition: "method",
      abstract_method_signature: "method",
      interface_declaration: "interface",
      type_alias_declaration: "type",
      enum_declaration: "enum",
    },
    vars: { variable_declarator: "variable" },
  },
  go: {
    grammar: "go",
    exts: [".go"],
    always: {
      function_declaration: "function",
      method_declaration: "method",
      type_spec: "type",
    },
    vars: { var_spec: "variable", const_spec: "variable" },
  },
  rust: {
    grammar: "rust",
    exts: [".rs"],
    always: {
      function_item: "function",
      function_signature_item: "function",
      struct_item: "struct",
      enum_item: "enum",
      trait_item: "trait",
    },
    vars: { const_item: "variable", static_item: "variable" },
    // An impl block is not a symbol itself, but its target type is pushed onto the scope so the
    // functions inside show what they belong to.
    scopeOnly: { impl_item: "type" },
  },
  csharp: {
    grammar: "c_sharp", // ⚠ the wasm file is tree-sitter-c_sharp.wasm, the only one differing from its langKey
    exts: [".cs"],
    always: {
      class_declaration: "class",
      struct_declaration: "struct",
      interface_declaration: "interface",
      enum_declaration: "enum",
      record_declaration: "class", // a record is close enough to a class
      delegate_declaration: "type",
      method_declaration: "method",
      constructor_declaration: "constructor",
      property_declaration: "property",
    },
    vars: {}, // no top-level variables (fields live inside a class and have no name field)
  },
  java: {
    grammar: "java",
    exts: [".java"],
    always: {
      class_declaration: "class",
      interface_declaration: "interface",
      enum_declaration: "enum",
      record_declaration: "class",
      annotation_type_declaration: "interface", // @interface
      method_declaration: "method",
      constructor_declaration: "constructor",
    },
    vars: {},
  },
  c: {
    grammar: "c",
    exts: [".c", ".h"], // .h defaults to C (C++ headers use .hpp/.hh/.hxx)
    always: {
      function_definition: "function", // the name is buried in the declarator chain → c_declarator
      struct_specifier: "struct",
      enum_specifier: "enum",
      union_specifier: "struct", // union folds into the struct kind
    },
    vars: {},
    nameRules: { function_definition: "c_declarator" },
  },
  cpp: {
    grammar: "cpp",
    exts: [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"],
    always: {
      function_definition: "function", // Widget::doIt → c_declarator takes the last segment, doIt
      class_specifier: "class",
      struct_specifier: "struct",
      enum_specifier: "enum",
    },
    vars: {},
    nameRules: { function_definition: "c_declarator" },
  },
  kotlin: {
    grammar: "kotlin",
    // ⚠ Definition nodes in the Kotlin grammar have no name field (the name sits in a
    //    type_identifier/simple_identifier child), so they all go through the child:<type> strategy
    //    in name_rules. Confirmed with _probe.
    exts: [".kt", ".kts"],
    always: {
      class_declaration: "class", // enum class and data class are both class_declaration
      object_declaration: "class",
      function_declaration: "function", // functions inside a class get kind=function, with scope naming the class
    },
    vars: {},
    nameRules: {
      class_declaration: "child:type_identifier",
      object_declaration: "child:type_identifier",
      function_declaration: "child:simple_identifier",
    },
  },
  swift: {
    grammar: "swift",
    // ⚠ The Swift grammar parses enum/struct/class/actor all as class_declaration and offers no way
    //    to tell them apart, so everything is labelled class. Recording the limitation rather than
    //    hiding it. Confirmed with _probe.
    exts: [".swift"],
    always: {
      class_declaration: "class",
      protocol_declaration: "protocol",
      protocol_function_declaration: "method",
      function_declaration: "function",
      init_declaration: "constructor",
      property_declaration: "property",
    },
    vars: {},
  },
  php: {
    grammar: "php",
    exts: [".php"],
    always: {
      class_declaration: "class",
      interface_declaration: "interface",
      trait_declaration: "trait",
      enum_declaration: "enum",
      function_definition: "function",
      method_declaration: "method",
    },
    vars: {},
  },
  ruby: {
    grammar: "ruby",
    exts: [".rb"],
    always: {
      module: "module",
      class: "class",
      method: "method",
      singleton_method: "method", // def self.x
    },
    vars: {},
  },
  bash: {
    grammar: "bash",
    exts: [".sh", ".bash"],
    always: { function_definition: "function" }, // both explicit_fn() and function explicit_fn are this type
    vars: {}, // a top-level variable's name field is not an identifier, so the walk skips it; left empty on purpose
  },
  lua: {
    grammar: "lua",
    exts: [".lua"],
    // ⚠ The lua grammar in tree-sitter-wasms (the Azganoth fork) uses different node types from the
    //    tree-sitter-language-pack the Python version uses: a function definition is
    //    function_definition_statement / local_function_definition_statement, not language-pack's
    //    function_declaration. tree-sitter-wasms wins here (measured with probeLang).
    //    global, local and M.method all have a name field and use the default naming; the SymbolDef
    //    that comes out matches the Python version.
    always: {
      function_definition_statement: "function",
      local_function_definition_statement: "function",
    },
    vars: {},
  },
};

// Extension → lang key reverse lookup, used by the engine when scanning and when deciding a file's
// language during reference finding.
const EXT_TO_LANG: Record<string, string> = {};
for (const [name, spec] of Object.entries(LANGUAGE_SPECS)) {
  for (const ext of spec.exts) EXT_TO_LANG[ext] = name;
}
export const SUPPORTED_EXTENSIONS: ReadonlySet<string> = new Set(Object.keys(EXT_TO_LANG));

// ── Locate the wasm directory. createRequire resolves the package's package.json then goes to out/,
//    so the answer does not depend on how deep src/ or dist/ sits. ──
const nodeRequire = createRequire(import.meta.url);
const WASM_DIR = join(dirname(nodeRequire.resolve("tree-sitter-wasms/package.json")), "out");

function wasmPath(grammar: string): string {
  return join(WASM_DIR, `tree-sitter-${grammar}.wasm`);
}

// ── One-shot guard around Parser.init + a lazy cache of Language objects, so each language is loaded
//    once and shared. ──
let parserReady: Promise<void> | null = null;
function ensureInit(): Promise<void> {
  if (parserReady === null) parserReady = Parser.init();
  return parserReady;
}

const langCache = new Map<string, Language>();
async function loadLanguage(grammar: string): Promise<Language> {
  let lang = langCache.get(grammar);
  if (lang === undefined) {
    await ensureInit();
    lang = await Language.load(readFileSync(wasmPath(grammar)));
    langCache.set(grammar, lang);
  }
  return lang;
}

/** Extension → language key. Returns null for unsupported extensions. */
export function languageForFile(filePath: string): string | null {
  return EXT_TO_LANG[extname(filePath).toLowerCase()] ?? null;
}

/** Parse a piece of source into a tree-sitter tree. An unsupported lang_key throws.
 *  Addresses red-team L4-MEDIUM: the indexer parses each file once and symbols, comments and
 *  fingerprints all share that one tree. */
export async function parseSource(source: string, langKey: string): Promise<Tree> {
  const spec = LANGUAGE_SPECS[langKey];
  if (spec === undefined) throw new Error(`parseSource: unsupported language '${langKey}'`);
  const lang = await loadLanguage(spec.grammar);
  const parser = new Parser();
  parser.setLanguage(lang);
  const tree = parser.parse(source);
  parser.delete(); // the tree outlives the parser and stays usable after this; avoids leaking WASM parsers
  if (tree === null) throw new Error(`parseSource: tree-sitter returned null for '${langKey}'`);
  return tree;
}

/** Read the name out of a definition node (its name child). Returns "<anon>" when there is none,
 *  never a silent null. */
function nameOf(node: Node): string {
  const nameNode = node.childForFieldName("name");
  return nameNode === null ? "<anon>" : nameNode.text;
}

// The C/C++ declarator chain: a function_definition's name is not in a name field, it is buried in
// (pointer/reference/...) → function_declarator → identifier/qualified_identifier (take the last segment).
const C_DECLARATOR_WRAPPERS: ReadonlySet<string> = new Set([
  "function_declarator", "pointer_declarator", "reference_declarator",
  "parenthesized_declarator", "array_declarator",
]);

/** C/C++ function_definition: descend through the declarator wrappers to the function_declarator and
 *  take the declared name (for a qualified_identifier such as Widget::doIt, the last segment).
 *  Returns "<anon>" when nothing is found. */
function cDeclaratorName(node: Node): string {
  // find the first-level declarator wrapper
  let decl: Node | null = null;
  for (const c of node.children) {
    if (c !== null && C_DECLARATOR_WRAPPERS.has(c.type)) {
      decl = c;
      break;
    }
  }
  // walk through pointer/reference and similar wrappers until reaching function_declarator
  let seen = 0;
  while (decl !== null && decl.type !== "function_declarator" && seen < 8) {
    seen += 1;
    let nxt: Node | null = null;
    for (const c of decl.children) {
      if (c !== null && C_DECLARATOR_WRAPPERS.has(c.type)) {
        nxt = c;
        break;
      }
    }
    decl = nxt;
  }
  if (decl === null) return "<anon>";
  // the first child of function_declarator that is not a parameter_list is the declared name
  for (const c of decl.children) {
    if (c === null) continue;
    if (c.type === "parameter_list") continue;
    if (c.type === "qualified_identifier") {
      // namespace::name → take the last identifier/field_identifier segment
      const kids = c.children;
      for (let i = kids.length - 1; i >= 0; i -= 1) {
        const q = kids[i];
        if (q != null && (q.type === "identifier" || q.type === "field_identifier" || q.type === "destructor_name")) {
          return q.text;
        }
      }
    }
    if (c.type === "identifier" || c.type === "field_identifier" || c.type === "destructor_name" || c.type === "operator_name") {
      return c.text;
    }
  }
  return "<anon>";
}

/** Read a definition node's name according to its name_rules strategy. rule=undefined falls back to
 *  childForFieldName("name").
 *  "child:<type>" → the text of the first direct child of that type (Kotlin).
 *  "c_declarator"  → the C/C++ declarator chain. */
function extractName(node: Node, rule: string | undefined): string {
  if (rule === undefined) return nameOf(node);
  if (rule.startsWith("child:")) {
    const want = rule.slice("child:".length);
    for (const c of node.children) {
      if (c !== null && c.type === want) return c.text;
    }
    return "<anon>";
  }
  if (rule === "c_declarator") return cDeclaratorName(node);
  return nameOf(node);
}

/** The plain synchronous core: walk an already-parsed tree and extract symbols. This is the logic the
 *  golden tests compare against. */
function walkSymbols(root: Node, spec: LangSpec): SymbolDef[] {
  const { always, vars: varkinds } = spec;
  const scopeOnly = spec.scopeOnly ?? {};
  const nameRules = spec.nameRules ?? {};
  const pyAssignment = spec.pyAssignment ?? false;
  const symbols: SymbolDef[] = [];

  const walk = (node: Node, scopeParts: string[]): void => {
    const nodeType = node.type;
    let childScope = scopeParts;

    // tree-sitter keywords and punctuation are unnamed tokens, and their type can collide with a
    // definition node's type (a Ruby `module`/`class` keyword token has the same type as the
    // definition node). Only is_named nodes are real symbol definitions, which keeps keyword tokens
    // from being collected as <anon>.
    if (node.isNamed && Object.hasOwn(always, nodeType)) {
      const name = extractName(node, nameRules[nodeType]);
      symbols.push({
        kind: always[nodeType]!,
        name,
        line: node.startPosition.row + 1,
        end_line: node.endPosition.row + 1,
        scope: scopeParts.join("."),
      });
      // on the way into a definition, push it onto the scope so methods and nested functions show
      // what they belong to
      childScope = [...scopeParts, name];
    } else if (Object.hasOwn(scopeOnly, nodeType)) {
      // Container nodes (such as Rust impl_item): push the named field onto the scope, but do not
      // count the container itself as a symbol.
      const fieldNode = node.childForFieldName(scopeOnly[nodeType]!);
      if (fieldNode !== null) childScope = [...scopeParts, fieldNode.text];
    } else if (Object.hasOwn(varkinds, nodeType) && scopeParts.length === 0) {
      // Variables are collected only at module top level, and the name has to be a single
      // identifier: a destructuring `const {a,b}=…` has an object_pattern/array_pattern as its name
      // field, and skipping it avoids emitting junk symbol names like "{a, b}".
      const nameNode = node.childForFieldName("name");
      if (nameNode !== null && nameNode.type === "identifier") {
        symbols.push({
          kind: varkinds[nodeType]!,
          name: nameNode.text,
          line: node.startPosition.row + 1,
          end_line: node.endPosition.row + 1,
          scope: "",
        });
      }
    } else if (pyAssignment && nodeType === "assignment" && scopeParts.length === 0) {
      // Python special case: a module-level assignment to an identifier counts as a variable
      // (assignment has no name field)
      const left = node.childForFieldName("left");
      if (left !== null && left.type === "identifier") {
        symbols.push({
          kind: "variable",
          name: left.text,
          line: node.startPosition.row + 1,
          end_line: node.endPosition.row + 1,
          scope: "",
        });
      }
    }

    for (const child of node.children) {
      if (child !== null) walk(child, childScope);
    }
  };

  walk(root, []);
  return symbols;
}

/** Extract the symbol definitions from a piece of source.
 *
 * @param source   The file's source text.
 * @param langKey  Language key (a key of LANGUAGE_SPECS; defaults to "python" for compatibility).
 * @param opts.filePath  Used only in error messages and labels; no file is read.
 * @param opts.tree      An already-parsed tree (the indexer shares one to avoid parsing twice); when
 *                       omitted, this function parses asynchronously itself.
 *
 * Fails loud: a non-string source throws TypeError, an unsupported langKey throws Error.
 */
export async function extractSymbolsFromSource(
  source: string,
  langKey = "python",
  opts: { filePath?: string; tree?: Tree } = {},
): Promise<SymbolDef[]> {
  const { filePath = "<memory>", tree: providedTree } = opts;
  if (typeof source !== "string") {
    throw new TypeError(
      `extractSymbolsFromSource expects a string, got ${typeof source} (filePath=${filePath})`,
    );
  }
  const spec = LANGUAGE_SPECS[langKey];
  if (spec === undefined) {
    throw new Error(
      `extractSymbolsFromSource: unsupported language '${langKey}' (filePath=${filePath}). ` +
        `Available: ${Object.keys(LANGUAGE_SPECS).sort().join(", ")}`,
    );
  }

  const ownTree = providedTree === undefined;
  const tree = providedTree ?? (await parseSource(source, langKey));
  try {
    return walkSymbols(tree.rootNode, spec);
  } finally {
    if (ownTree) tree.delete(); // delete a tree we parsed ourselves to save WASM memory; a providedTree is left alone
  }
}

/** Read a source file, pick the language from its extension, and extract the symbol definitions. This
 *  is the main entry point. An unsupported extension throws; an unreadable file throws. */
export async function extractSymbols(filePath: string): Promise<SymbolDef[]> {
  const langKey = languageForFile(filePath);
  if (langKey === null) {
    throw new Error(
      `symbol extraction failed: unsupported extension ${filePath} ` +
        `(supported: ${[...SUPPORTED_EXTENSIONS].sort().join(", ")})`,
    );
  }
  let source: string;
  try {
    source = readFileSync(filePath, "utf-8");
  } catch (exc) {
    throw new Error(`symbol extraction failed: cannot read file ${filePath} (${String(exc)})`);
  }
  return extractSymbolsFromSource(source, langKey, { filePath });
}
