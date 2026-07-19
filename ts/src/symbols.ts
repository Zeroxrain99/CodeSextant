// 符號抽取模組 — tree-sitter 多語言全量快速符號表（全 TS 重寫 P1，平移自 Python codesextant/symbols.py）。
//
// 平移原則（對照 Python 版黃金測試 ground truth）：
//   - LANGUAGE_SPECS 16 語言 table 與 Python 版 1:1（tree-sitter 節點型別字串完全相同，可照抄）。
//   - walk 邏輯（is_named 過濾 + always/scope_only/vars/py_assignment 四分支）逐句平移。
//   - 輸出欄位沿用 snake_case（kind/name/line/end_line/scope）以對齊 Python 版 JSON 輸出。
//
// 與 Python 版的刻意差異（不影響輸出 parity）：
//   - Python 用 bytes + byte-slice 取名；TS 用 web-tree-sitter 的 node.text（string）直接取，
//     行號用 node.startPosition.row + 1（0-based row）。ASCII / 非 ASCII 識別字、行號皆一致。
//   - tree-sitter parse API：web-tree-sitter 是 async（Parser.init + Language.load(wasm)），
//     故對外 parse 路徑為 async；walk 本身純同步。
//   - wasm 檔名映射：16 語言中唯 csharp 的 wasm 檔名是 tree-sitter-c_sharp.wasm（其餘 grammar
//     名與 wasm 檔名一致），故 spec 用 grammar 欄記錄 wasm 檔名中段（實測坐實，⛔別腦推）。
//
// 職責（單一）：吃一個檔路徑或一段原始碼，吐出該檔的符號定義清單（函數/類別/方法/型別/模組層級變數
// + 行號 + 所屬範圍）。不碰 SQLite、不碰 ts-morph 找引用、不碰排序——那些是別的模組的事。
import { Parser, Language, type Tree, type Node } from "web-tree-sitter";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, extname } from "node:path";

/** 一筆符號定義（欄位名對齊 Python 版輸出，給 storage / daemon 直接轉 JSON）。 */
export interface SymbolDef {
  /** "function" / "class" / "method" / "interface" / "type" / "enum" / "struct" / "trait"
   *  / "module" / "protocol" / "constructor" / "property" / "variable"（依語言）。 */
  kind: string;
  /** 符號名稱（抓不到名字回 "<anon>"，不靜默 null）。 */
  name: string;
  /** 定義起訖行號（1-based）。 */
  line: number;
  end_line: number;
  /** 所屬範圍（如 "MyClass" 表示 method 在 MyClass 內；"" 表示模組頂層）。 */
  scope: string;
}

/** per-language spec（table-driven，加語言只加一筆）。 */
interface LangSpec {
  /** tree-sitter-wasms 的 wasm 檔名中段（wasm 路徑＝tree-sitter-<grammar>.wasm）。 */
  grammar: string;
  /** 副檔名（小寫、含點）。 */
  exts: string[];
  /** {tree-sitter 節點型別: 符號 kind}——結構定義，不論巢狀深度一律收，並 push 自己進 scope。 */
  always: Record<string, string>;
  /** {節點型別: kind}——變數定義，只在模組頂層（scope 為空）收，避免區域變數噪音。 */
  vars: Record<string, string>;
  /** 容器節點（如 Rust impl_item）：用指定 field 當 scope 名 push 下去、自己不算符號。 */
  scopeOnly?: Record<string, string>;
  /** 無 name field 節點的取名策略（C/C++ 的 c_declarator、Kotlin 的 child:<type>）。 */
  nameRules?: Record<string, string>;
  /** Python 特例：模組層級 assignment.left → variable（assignment 無 name field）。 */
  pyAssignment?: boolean;
}

// ── 16 語言 spec（與 Python 版 LANGUAGE_SPECS 1:1；節點型別/name field 皆 _probe 實測坐實）──
export const LANGUAGE_SPECS: Record<string, LangSpec> = {
  python: {
    grammar: "python",
    exts: [".py", ".pyi"],
    always: { function_definition: "function", class_definition: "class" },
    vars: {}, // Python 變數走 assignment 特例
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
    // impl 區塊本身不算符號，但要把目標型別 push 進 scope，讓內部 fn 標出歸屬。
    scopeOnly: { impl_item: "type" },
  },
  csharp: {
    grammar: "c_sharp", // ⚠ wasm 檔名是 tree-sitter-c_sharp.wasm（唯一與 langKey 不同者）
    exts: [".cs"],
    always: {
      class_declaration: "class",
      struct_declaration: "struct",
      interface_declaration: "interface",
      enum_declaration: "enum",
      record_declaration: "class", // record 語意近 class
      delegate_declaration: "type",
      method_declaration: "method",
      constructor_declaration: "constructor",
      property_declaration: "property",
    },
    vars: {}, // 頂層無變數（field 在 class 內、無 name field）
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
    exts: [".c", ".h"], // .h 預設歸 C（C++ header 走 .hpp/.hh/.hxx）
    always: {
      function_definition: "function", // 名字埋在 declarator 鏈 → c_declarator
      struct_specifier: "struct",
      enum_specifier: "enum",
      union_specifier: "struct", // union 併入 struct kind
    },
    vars: {},
    nameRules: { function_definition: "c_declarator" },
  },
  cpp: {
    grammar: "cpp",
    exts: [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"],
    always: {
      function_definition: "function", // Widget::doIt → c_declarator 取末段 doIt
      class_specifier: "class",
      struct_specifier: "struct",
      enum_specifier: "enum",
    },
    vars: {},
    nameRules: { function_definition: "c_declarator" },
  },
  kotlin: {
    grammar: "kotlin",
    // ⚠ Kotlin grammar 的定義節點「無 name field」（名字在 type_identifier/simple_identifier
    //    子節點），故全走 name_rules 的 child:<type> 策略（_probe 坐實）。
    exts: [".kt", ".kts"],
    always: {
      class_declaration: "class", // enum class / data class 都是 class_declaration
      object_declaration: "class",
      function_declaration: "function", // 類內函數 kind=function、scope 標出類名歸屬
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
    // ⚠ Swift grammar 把 enum/struct/class/actor 全 parse 成 class_declaration（無法細分）→
    //    一律標 class，誠實記錄此限制（_probe 坐實）。
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
    always: { function_definition: "function" }, // explicit_fn() 與 function explicit_fn 皆此型別
    vars: {}, // 頂層變數 name field 非 identifier、walk 不收（誠實留空）
  },
  lua: {
    grammar: "lua",
    exts: [".lua"],
    // ⚠ tree-sitter-wasms 的 lua grammar（Azganoth fork）節點型別與 Python 版 tree-sitter-language-pack
    //    不同：函數定義是 function_definition_statement / local_function_definition_statement
    //    （非 language-pack 的 function_declaration）。以 tree-sitter-wasms 為準（probeLang 實測坐實）。
    //    global/local/M.method 皆有 name field、走預設取名；輸出 SymbolDef 與 Python 版一致。
    always: {
      function_definition_statement: "function",
      local_function_definition_statement: "function",
    },
    vars: {},
  },
};

// 副檔名 → lang key（反查表），給 engine 掃描 / 找引用判語言用。
const EXT_TO_LANG: Record<string, string> = {};
for (const [name, spec] of Object.entries(LANGUAGE_SPECS)) {
  for (const ext of spec.exts) EXT_TO_LANG[ext] = name;
}
export const SUPPORTED_EXTENSIONS: ReadonlySet<string> = new Set(Object.keys(EXT_TO_LANG));

// ── wasm 目錄定位（createRequire resolve 套件 package.json → out/，不受 src/dist 深度影響）──
const nodeRequire = createRequire(import.meta.url);
const WASM_DIR = join(dirname(nodeRequire.resolve("tree-sitter-wasms/package.json")), "out");

function wasmPath(grammar: string): string {
  return join(WASM_DIR, `tree-sitter-${grammar}.wasm`);
}

// ── Parser.init 一次性 guard + Language 物件 lazy cache（各語言只載一次共享）──
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

/** 副檔名 → 語言 key（不支援回 null）。 */
export function languageForFile(filePath: string): string | null {
  return EXT_TO_LANG[extname(filePath).toLowerCase()] ?? null;
}

/** parse 一段原始碼成 tree-sitter tree。lang_key 不支援 → Error。
 *  紅隊 L4-MEDIUM 對齊：給 index 一檔 parse 一次、symbols/comments/fingerprints 共用同一 tree。 */
export async function parseSource(source: string, langKey: string): Promise<Tree> {
  const spec = LANGUAGE_SPECS[langKey];
  if (spec === undefined) throw new Error(`parseSource 不支援的語言 '${langKey}'`);
  const lang = await loadLanguage(spec.grammar);
  const parser = new Parser();
  parser.setLanguage(lang);
  const tree = parser.parse(source);
  parser.delete(); // tree 獨立於 parser、可在 parser 刪除後續用；省 WASM parser 洩漏
  if (tree === null) throw new Error(`parseSource: tree-sitter 對 '${langKey}' parse 回 null`);
  return tree;
}

/** 從定義節點抓名字（name 子節點）。抓不到回 "<anon>"（不靜默 null）。 */
function nameOf(node: Node): string {
  const nameNode = node.childForFieldName("name");
  return nameNode === null ? "<anon>" : nameNode.text;
}

// C/C++ declarator 鏈：function_definition 名字不在 name field，埋在
// (pointer/reference/...) → function_declarator → identifier/qualified_identifier（取末段）。
const C_DECLARATOR_WRAPPERS: ReadonlySet<string> = new Set([
  "function_declarator", "pointer_declarator", "reference_declarator",
  "parenthesized_declarator", "array_declarator",
]);

/** C/C++ function_definition：往下穿過 declarator wrapper 找 function_declarator，取被宣告名
 *  （qualified_identifier 如 Widget::doIt 取末段）。抓不到回 "<anon>"。 */
function cDeclaratorName(node: Node): string {
  // 找第一層 declarator wrapper
  let decl: Node | null = null;
  for (const c of node.children) {
    if (c !== null && C_DECLARATOR_WRAPPERS.has(c.type)) {
      decl = c;
      break;
    }
  }
  // 穿過 pointer/reference 等 wrapper 直到 function_declarator
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
  // function_declarator 的第一個非 parameter_list 子 = 被宣告名
  for (const c of decl.children) {
    if (c === null) continue;
    if (c.type === "parameter_list") continue;
    if (c.type === "qualified_identifier") {
      // namespace::name → 取最後一段 identifier/field_identifier
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

/** 依 name_rules 策略取定義節點的名字。rule=undefined → 預設 childForFieldName("name")。
 *  "child:<type>" → 取第一個該型別的直接子節點文字（Kotlin）。
 *  "c_declarator"  → C/C++ declarator 鏈。 */
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

/** 純同步核心：走訪已 parse 的 tree 抽符號（黃金測試對照的就是這段邏輯）。 */
function walkSymbols(root: Node, spec: LangSpec): SymbolDef[] {
  const { always, vars: varkinds } = spec;
  const scopeOnly = spec.scopeOnly ?? {};
  const nameRules = spec.nameRules ?? {};
  const pyAssignment = spec.pyAssignment ?? false;
  const symbols: SymbolDef[] = [];

  const walk = (node: Node, scopeParts: string[]): void => {
    const nodeType = node.type;
    let childScope = scopeParts;

    // tree-sitter 關鍵字/標點是 unnamed token，其 type 可能與定義節點型別撞名
    // （Ruby `module`/`class` keyword token 的 type == 定義節點 type），
    // 只有 is_named 的節點才是真正的符號定義 → 擋掉 keyword token 誤收成 <anon>。
    if (node.isNamed && Object.hasOwn(always, nodeType)) {
      const name = extractName(node, nameRules[nodeType]);
      symbols.push({
        kind: always[nodeType]!,
        name,
        line: node.startPosition.row + 1,
        end_line: node.endPosition.row + 1,
        scope: scopeParts.join("."),
      });
      // 進到定義內部時把自己加進 scope，讓 method/巢狀函數標出歸屬
      childScope = [...scopeParts, name];
    } else if (Object.hasOwn(scopeOnly, nodeType)) {
      // 容器節點（如 Rust impl_item）：用指定 field 當 scope 名 push 下去、自己不算符號。
      const fieldNode = node.childForFieldName(scopeOnly[nodeType]!);
      if (fieldNode !== null) childScope = [...scopeParts, fieldNode.text];
    } else if (Object.hasOwn(varkinds, nodeType) && scopeParts.length === 0) {
      // 變數只收模組頂層，且名字必須是單一識別字——解構 `const {a,b}=…` 的 name field
      // 是 object_pattern/array_pattern，跳過免吐 "{a, b}" 這種垃圾符號名。
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
      // Python 特例：模組層級 identifier 賦值當變數（assignment 無 name field）
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

/** 從一段原始碼抽出符號定義清單。
 *
 * @param source   檔案原始碼（string）。
 * @param langKey  語言 key（LANGUAGE_SPECS 的鍵；預設 "python" 保持相容）。
 * @param opts.filePath  僅用於錯誤訊息與標記，不會讀檔。
 * @param opts.tree      已 parse 的 tree（index 共用省重複 parse）；未給則內部 async parse。
 *
 * fail-loud：source 非 string → TypeError；langKey 不支援 → Error。
 */
export async function extractSymbolsFromSource(
  source: string,
  langKey = "python",
  opts: { filePath?: string; tree?: Tree } = {},
): Promise<SymbolDef[]> {
  const { filePath = "<memory>", tree: providedTree } = opts;
  if (typeof source !== "string") {
    throw new TypeError(
      `extractSymbolsFromSource 需要 string，收到 ${typeof source}（filePath=${filePath}）`,
    );
  }
  const spec = LANGUAGE_SPECS[langKey];
  if (spec === undefined) {
    throw new Error(
      `extractSymbolsFromSource 不支援的語言 '${langKey}'（filePath=${filePath}）。` +
        `可用：${Object.keys(LANGUAGE_SPECS).sort().join(", ")}`,
    );
  }

  const ownTree = providedTree === undefined;
  const tree = providedTree ?? (await parseSource(source, langKey));
  try {
    return walkSymbols(tree.rootNode, spec);
  } finally {
    if (ownTree) tree.delete(); // 自己 parse 的 tree 用完即刪、省 WASM 記憶體；providedTree 不刪
  }
}

/** 讀一個原始碼檔，按副檔名選語言、抽出符號定義清單（對外主要入口）。
 *  副檔名不支援 → Error；檔讀不到 → Error。 */
export async function extractSymbols(filePath: string): Promise<SymbolDef[]> {
  const langKey = languageForFile(filePath);
  if (langKey === null) {
    throw new Error(
      `抽符號失敗：不支援的副檔名 ${filePath}` +
        `（支援：${[...SUPPORTED_EXTENSIONS].sort().join(", ")}）`,
    );
  }
  let source: string;
  try {
    source = readFileSync(filePath, "utf-8");
  } catch (exc) {
    throw new Error(`抽符號失敗：讀不到檔 ${filePath}（${String(exc)}）`);
  }
  return extractSymbolsFromSource(source, langKey, { filePath });
}
