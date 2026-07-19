// 索引存儲模組 — SQLite 落盤 + content hash 增量 + 專案隔離（全 TS 重寫 P1，平移自 Python codesextant/storage.py）。
//
// 設計來源（PoC 已坐實）：
//   - 每專案一個 SQLite 庫，project_key = sha1(repo 絕對路徑)（不混線）。
//   - 用檔案 content hash(sha256) 當失效 key：改一檔只重算一檔，其餘 cache hit 跳過。
//
// 職責（單一）：管一個專案的 SQLite 庫——開庫、建表、查/寫檔案 hash、存/取符號、存/取引用邊、
// 給統計。不碰 tree-sitter、不碰 ts-morph。預設庫位置：~/.codesextant/<project_key>.db。
//
// 與 Python 版的刻意差異（不影響輸出/落盤 parity）：
//   - project_key：Python 用 os.path.normcase(os.path.abspath())；TS 用 path.resolve() + normcaseAbs
//     對齊（小寫化 + 統一反斜線 + 元件尾點尾空格剝除），確保同一專案 TS/Python 算出相同 sha1、共用同一個 .db。
//   - better-sqlite3 預設 autocommit（無顯式 BEGIN 時每句各自 commit），故 Python 的 conn.commit()
//     多數可省；但「先 DELETE 再批次 INSERT」想原子者一律用 db.transaction() 包，保持與 Python 一致。
//   - better-sqlite3 不接受 undefined 作為綁定值 → Python 的 dict.get(k)（缺則 None）平移為 v ?? null。
//
// 已知邊界（producer 不觸發、故不影響實務 parity，標記在此避免日後誤判）：
//   - dict.get(k, D)（D 非 None，如 comments 的 kind→"line"/scope→""）：Python 只在「key 缺席」回退 D，
//     對「key 存在但值 None」直接存 None（NOT NULL 欄 → fail-loud IntegrityError）；TS 的 v ?? D 對
//     「undefined 或 null」都回退 D（fail-soft）。兩版對「缺 key」與「給數字」路徑一致——comments 產出端
//     恆填值、永不發顯式 null，故實務落盤一致；唯「顯式給 null」這條不可達髒輸入分歧（TS fail-soft）。
//   - REAL 欄整數值（indexed_at/last_indexed_at）：Python sqlite3 取 REAL 恆回 float（2000→2000.0、
//     JSON 序列化 "2000.0"），better-sqlite3 回 JS number（JSON.stringify 成 "2000"）。重寫期 Python 凍結、
//     TS 達 parity 才切，不會同時對外服務同一庫，故 wire 不需同時 parity；消費端勿對 REAL 做精確字串比較。
import DatabaseConstructor from "better-sqlite3";
import { createHash } from "node:crypto";
import { readFileSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { resolve, join } from "node:path";
import type { SymbolDef } from "./symbols.js";

/** better-sqlite3 的 Database 實例型別（namespace 型別，配合 esModuleInterop default import）。 */
type DB = DatabaseConstructor.Database;

// 庫的綱要版本（schema 改了就 +1，未來可據此做遷移）。
// ⚠ 遷移機制誠實：open() 跑 exec(CREATE TABLE IF NOT EXISTS) 冪等補表 + ensureColumns() 純加欄 hook。
// 無條件覆寫 meta.schema_version——version 號僅 stats 回報、不 gate 任何遷移。對「加表/加欄」安全。
export const SCHEMA_VERSION = 3; // v0.11.x P3：fingerprints 加 cognitive 欄；v2=功能 B 三表

/** 一筆已落盤符號（= SymbolDef + 所屬檔路徑）。 */
export interface SymbolRow extends SymbolDef {
  path: string;
}

/** 一條引用邊（呼叫端某行用到了某個被定義的符號）。 */
export interface RefEdge {
  src_path: string;
  src_line: number;
  symbol_name: string;
  def_path?: string | null;
  def_line?: number | null;
  confidence: string; // "high"(resolved-import) / "low"(name-match)
}

/** 功能 B：一個可執行單元的結構指紋（給重複偵測 GROUP BY shape_hash）。 */
export interface Fingerprint {
  name?: string | null;
  kind?: string | null;
  line?: number | null;
  end_line?: number | null;
  scope?: string | null;
  shape_hash?: string | null;
  raw_token_hash?: string | null;
  call_hash?: string | null;
  node_count?: number | null;
  nstmts?: number | null;
  has_control_flow?: boolean | number | null;
  cognitive?: number | null; // P3 D3：高信心語言 int / 其餘語言 null=UNKNOWN
}

/** 功能 B：winnowing k-gram 倒排索引一筆。 */
export interface WinnowEntry {
  line?: number | null;
  fp_value?: number | null;
}

/** 功能 B：一個 comment 節點 + 行號 + 歸屬符號。 */
export interface CommentRow {
  line?: number | null;
  end_line?: number | null;
  kind?: string | null;
  is_doc?: boolean | number | null;
  tag?: string | null;
  scope?: string | null;
  owner_line?: number | null;
  text?: string | null;
}

/** 呼叫鏈一個節點（call hierarchy 遞迴 CTE 結果）。 */
export interface CallGraphNode {
  name: string;
  path: string;
  line: number;
  depth: number;
  confidence: string;
}

/** 單專案統計（給 status / 面板）。 */
export interface ProjectStats {
  project_key: string;
  repo_path: string;
  db_file: string;
  indexed_files: number;
  symbols: number;
  refs: number;
  fingerprints: number;
  comments: number;
  last_indexed_at: number | null;
  schema_version: number;
  indexed_git_sha: string | null;
}

/** 列舉本機所有已索引專案一筆。 */
export interface IndexedProject {
  project_key: string;
  db_file: string;
  repo_path?: string | null;
  indexed_files?: number;
  symbols?: number;
  refs?: number;
  last_indexed_at?: number | null;
  path_exists?: boolean;
  error?: string;
}

/** 複刻 Python os.path.normcase(os.path.abspath()) 的複合效果（win32）：
 *  - abspath/GetFullPathName：剝除路徑元件結尾的點/空格（Windows 檔名語義；path.resolve 不做這步）。
 *    ⚠ 實測 GetFullPathName 細則（_dbg 坐實）：尾「點」所有元件都剝（'foo.'→'foo'）；尾「空格」
 *    只剝 basename（最後元件），中間元件的尾空格保留（'E:\\專案 \\Foo.'→'e:\\專案 \\foo'）。
 *  - normcase：小寫化 + 統一反斜線。POSIX 全程 no-op（保留大小寫與正斜線）。
 *  ⚠ 此剝除是 project_key 命脈：user 手誤多打尾點/尾空格（'E:\\foo. '）時，實體目錄是 'E:\\foo'，
 *  TS/Python 須算出同一把 key、共用同一個 .db。病態混合路徑（如中間元件 'foo. '）不保證完美複刻。 */
function normcaseAbs(resolved: string): string {
  if (process.platform !== "win32") return resolved;
  const parts = resolved.replace(/\//g, "\\").split("\\");
  const last = parts.length - 1;
  const stripped = parts.map((seg, i) => {
    if (i === 0) return seg; // drive（'E:'）或 UNC 起始空段，不剝
    if (i === last) return seg.replace(/[. ]+$/, ""); // basename：尾點 + 尾空格都剝
    return seg.replace(/\.+$/, ""); // 中間元件：只剝尾點，尾空格保留（對齊 GetFullPathName）
  });
  return stripped.join("\\").toLowerCase();
}

/** 專案隔離鍵 = sha1(規範化的 repo 絕對路徑)。複刻 Python normcase(abspath())，確保同專案任何相對/
 *  大小寫/正反斜線/尾點尾空格寫法進來都對應同一把 key、共用同一個 .db（不混線命脈）。 */
export function projectKey(repoPath: string): string {
  const abs = normcaseAbs(resolve(repoPath));
  return createHash("sha1").update(abs, "utf-8").digest("hex");
}

/** 對齊 Python os.path.normcase(os.path.abspath(p)) 的單一真相源——給 ranking/namegraph 等模組
 *  做路徑配對用（引用邊的 def_path/src_path 與符號 path 必須走同一正規化才對得上同一節點）。
 *  ⚠ 與 projectKey 共用同一個 normcaseAbs，避免兩份 normcase 邏輯漂移。空字串由呼叫端自理
 *  （此處不擋空：normPath("") 會回 cwd，與 Python abspath("") 行為一致）。 */
export function normPath(p: string): string {
  return normcaseAbs(resolve(p));
}

/** 預設庫目錄 ~/.codesextant/。可用環境變數 CODESEXTANT_HOME 覆寫（方便測試隔離）。 */
export function defaultDbDir(): string {
  const home = process.env["CODESEXTANT_HOME"];
  return home ? home : join(homedir(), ".codesextant");
}

/** 某專案對應的 SQLite 庫檔路徑。 */
export function dbPathFor(repoPath: string): string {
  return join(defaultDbDir(), `${projectKey(repoPath)}.db`);
}

/** 檔案內容 sha256（增量的失效 key）。 */
export function fileContentHash(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS files (
    path         TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    indexed_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS symbols (
    path     TEXT NOT NULL,
    kind     TEXT NOT NULL,
    name     TEXT NOT NULL,
    line     INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    scope    TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(path) REFERENCES files(path)
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols(path);

CREATE TABLE IF NOT EXISTS refs (
    src_path    TEXT NOT NULL,
    src_line    INTEGER NOT NULL,
    symbol_name TEXT NOT NULL,
    def_path    TEXT,
    def_line    INTEGER,
    confidence  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refs_symbol ON refs(symbol_name);
CREATE INDEX IF NOT EXISTS idx_refs_def ON refs(def_path);

CREATE TABLE IF NOT EXISTS fingerprints (
    path             TEXT NOT NULL,
    name             TEXT,
    kind             TEXT,
    line             INTEGER,
    end_line         INTEGER,
    scope            TEXT,
    shape_hash       TEXT,
    raw_token_hash   TEXT,
    call_hash        TEXT,
    node_count       INTEGER,
    nstmts           INTEGER,
    has_control_flow INTEGER DEFAULT 0,
    cognitive        INTEGER,
    FOREIGN KEY(path) REFERENCES files(path)
);
CREATE INDEX IF NOT EXISTS idx_fp_shape ON fingerprints(shape_hash);
CREATE INDEX IF NOT EXISTS idx_fp_call  ON fingerprints(call_hash);
CREATE INDEX IF NOT EXISTS idx_fp_path  ON fingerprints(path);

CREATE TABLE IF NOT EXISTS fingerprint_index (
    path     TEXT NOT NULL,
    line     INTEGER,
    fp_value INTEGER,
    FOREIGN KEY(path) REFERENCES files(path)
);
CREATE INDEX IF NOT EXISTS idx_fpidx_val  ON fingerprint_index(fp_value);
CREATE INDEX IF NOT EXISTS idx_fpidx_path ON fingerprint_index(path);

CREATE TABLE IF NOT EXISTS comments (
    path       TEXT NOT NULL,
    line       INTEGER NOT NULL,
    end_line   INTEGER NOT NULL,
    kind       TEXT NOT NULL,
    is_doc     INTEGER NOT NULL DEFAULT 0,
    tag        TEXT,
    scope      TEXT NOT NULL DEFAULT '',
    owner_line INTEGER,
    text       TEXT NOT NULL,
    FOREIGN KEY(path) REFERENCES files(path)
);
CREATE INDEX IF NOT EXISTS idx_comments_path ON comments(path);
CREATE INDEX IF NOT EXISTS idx_comments_tag  ON comments(tag);
CREATE INDEX IF NOT EXISTS idx_comments_doc  ON comments(is_doc);
`;

/** 既有庫加欄位的 migration hook（CREATE TABLE IF NOT EXISTS 不會對既有表加欄）。純加欄、冪等、可逆。 */
function ensureColumns(db: DB): void {
  const expected: Record<string, [string, string][]> = {
    fingerprints: [["cognitive", "INTEGER"]], // P3 D3：高信心語言 int / 其餘 NULL
  };
  for (const [table, cols] of Object.entries(expected)) {
    const have = new Set(
      (db.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[]).map(
        (r) => r.name,
      ),
    );
    for (const [col, decl] of cols) {
      if (!have.has(col)) {
        db.exec(`ALTER TABLE ${table} ADD COLUMN ${col} ${decl}`);
      }
    }
  }
}

/** 一個專案的 SQLite 索引庫門面。用法：const store = ProjectStore.open(repo); try { ... } finally { store.close(); } */
export class ProjectStore {
  readonly db: DB;
  readonly repoPath: string;
  readonly projectKey: string;
  readonly dbFile: string;

  private constructor(db: DB, repoPath: string, dbFile: string) {
    this.db = db;
    this.repoPath = resolve(repoPath);
    this.projectKey = projectKey(repoPath);
    this.dbFile = dbFile;
  }

  // ── 開 / 關 ──
  static open(repoPath: string): ProjectStore {
    const dbFile = dbPathFor(repoPath);
    mkdirSync(defaultDbDir(), { recursive: true });
    const db = new DatabaseConstructor(dbFile);
    // ⚠ 對齊 Python sqlite3 預設：foreign_keys OFF。better-sqlite3 預設 ON，但 Python 版整個設計
    // （storeFileSymbols 先 INSERT symbol 後 UPSERT file 的順序）假設 FK 不強制——schema 裡的
    // FOREIGN KEY 宣告只是文件、Python 版從不強制。關掉以保持落盤/操作順序 parity。
    db.pragma("foreign_keys = OFF");
    db.exec(SCHEMA);
    ensureColumns(db); // 既有庫補新欄（migration hook）
    const store = new ProjectStore(db, repoPath, dbFile);
    store.setMeta("schema_version", String(SCHEMA_VERSION));
    store.setMeta("repo_path", store.repoPath);
    return store;
  }

  close(): void {
    this.db.close();
  }

  // ── meta ──
  private setMeta(key: string, value: string): void {
    this.db
      .prepare(
        "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
      )
      .run(key, value);
  }

  getMeta(key: string): string | null;
  getMeta(key: string, defaultValue: string): string;
  getMeta(key: string, defaultValue: string | null = null): string | null {
    const row = this.db.prepare("SELECT value FROM meta WHERE key=?").get(key) as
      | { value: string }
      | undefined;
    return row ? row.value : defaultValue;
  }

  /** 坑6：記錄本次索引時 repo 的 git HEAD sha（freshness 比對用）。 */
  recordGitSha(sha: string): void {
    this.setMeta("git_head_sha", sha);
  }

  // ── 增量核心：判斷某檔要不要重算 ──
  needsReindex(path: string, currentHash: string): boolean {
    const row = this.db
      .prepare("SELECT content_hash FROM files WHERE path=?")
      .get(path) as { content_hash: string } | undefined;
    return row === undefined || row.content_hash !== currentHash;
  }

  /** 重算後落盤：清掉該檔舊符號，寫入新符號，更新 hash。整批一個 transaction。 */
  storeFileSymbols(
    path: string,
    contentHash: string,
    symbols: SymbolDef[],
    indexedAt: number,
  ): void {
    const delSym = this.db.prepare("DELETE FROM symbols WHERE path=?");
    const insSym = this.db.prepare(
      "INSERT INTO symbols(path,kind,name,line,end_line,scope) VALUES(?,?,?,?,?,?)",
    );
    const upsertFile = this.db.prepare(
      "INSERT INTO files(path,content_hash,indexed_at) VALUES(?,?,?) " +
        "ON CONFLICT(path) DO UPDATE SET content_hash=excluded.content_hash, indexed_at=excluded.indexed_at",
    );
    const tx = this.db.transaction(() => {
      delSym.run(path);
      for (const s of symbols) {
        insSym.run(path, s.kind, s.name, s.line, s.end_line, s.scope ?? "");
      }
      upsertFile.run(path, contentHash, indexedAt);
    });
    tx();
  }

  /** 功能 B：落盤某檔的結構指紋 + winnowing 倒排（先清該檔舊的再寫）。content_hash 由 storeFileSymbols 管。 */
  storeFileFingerprints(
    path: string,
    fingerprints: Fingerprint[],
    winnowIndex: WinnowEntry[],
  ): void {
    const delFp = this.db.prepare("DELETE FROM fingerprints WHERE path=?");
    const delIdx = this.db.prepare("DELETE FROM fingerprint_index WHERE path=?");
    const insFp = this.db.prepare(
      "INSERT INTO fingerprints(path,name,kind,line,end_line,scope,shape_hash," +
        "raw_token_hash,call_hash,node_count,nstmts,has_control_flow,cognitive) " +
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
    );
    const insIdx = this.db.prepare(
      "INSERT INTO fingerprint_index(path,line,fp_value) VALUES(?,?,?)",
    );
    const tx = this.db.transaction(() => {
      delFp.run(path);
      delIdx.run(path);
      for (const f of fingerprints) {
        insFp.run(
          path,
          f.name ?? null,
          f.kind ?? null,
          f.line ?? null,
          f.end_line ?? null,
          f.scope ?? "",
          f.shape_hash ?? null,
          f.raw_token_hash ?? null,
          f.call_hash ?? null,
          f.node_count ?? null,
          f.nstmts ?? null,
          f.has_control_flow ? 1 : 0,
          f.cognitive ?? null,
        );
      }
      for (const w of winnowIndex) {
        insIdx.run(path, w.line ?? null, w.fp_value ?? null);
      }
    });
    tx();
  }

  /** 功能 B：落盤某檔的註解（先清該檔舊的再寫）。content_hash 同上由 storeFileSymbols 管。 */
  storeFileComments(path: string, comments: CommentRow[]): void {
    const delC = this.db.prepare("DELETE FROM comments WHERE path=?");
    const insC = this.db.prepare(
      "INSERT INTO comments(path,line,end_line,kind,is_doc,tag,scope,owner_line,text) " +
        "VALUES(?,?,?,?,?,?,?,?,?)",
    );
    const tx = this.db.transaction(() => {
      delC.run(path);
      for (const c of comments) {
        insC.run(
          path,
          c.line ?? null,
          c.end_line ?? c.line ?? null,
          c.kind ?? "line",
          c.is_doc ? 1 : 0,
          c.tag ?? null,
          c.scope ?? "",
          c.owner_line ?? null,
          c.text ?? "",
        );
      }
    });
    tx();
  }

  /** 檔被刪了 → 從索引移除：符號 + 檔記錄 + 它發出/指向它的引用邊 + 功能 B 三表。 */
  removeFile(path: string): void {
    const tx = this.db.transaction(() => {
      this.db.prepare("DELETE FROM symbols WHERE path=?").run(path);
      this.db.prepare("DELETE FROM files WHERE path=?").run(path);
      this.db
        .prepare("DELETE FROM refs WHERE src_path=? OR def_path=?")
        .run(path, path);
      this.db.prepare("DELETE FROM fingerprints WHERE path=?").run(path);
      this.db.prepare("DELETE FROM fingerprint_index WHERE path=?").run(path);
      this.db.prepare("DELETE FROM comments WHERE path=?").run(path);
    });
    tx();
  }

  // ── 查詢 ──
  /** 取符號。給 filePath 只取該檔，否則取全專案。 */
  getSymbols(filePath?: string): SymbolRow[] {
    if (filePath !== undefined) {
      return this.db
        .prepare(
          "SELECT path,kind,name,line,end_line,scope FROM symbols WHERE path=? ORDER BY line",
        )
        .all(filePath) as SymbolRow[];
    }
    return this.db
      .prepare(
        "SELECT path,kind,name,line,end_line,scope FROM symbols ORDER BY path,line",
      )
      .all() as SymbolRow[];
  }

  /** 找某名稱的所有定義（給找引用二段式第一段——粗篩候選用）。 */
  findSymbolDefinitions(name: string): SymbolRow[] {
    return this.db
      .prepare(
        "SELECT path,kind,name,line,end_line,scope FROM symbols WHERE name=? ORDER BY path,line",
      )
      .all(name) as SymbolRow[];
  }

  allIndexedFiles(): string[] {
    return (
      this.db.prepare("SELECT path FROM files ORDER BY path").all() as {
        path: string;
      }[]
    ).map((r) => r.path);
  }

  // ── 引用邊 ──
  /** 落盤某檔發出的引用邊（先清該檔的舊邊再寫，保持單一真相）。 */
  replaceRefsFor(srcPath: string, edges: RefEdge[]): void {
    const delR = this.db.prepare("DELETE FROM refs WHERE src_path=?");
    const insR = this.db.prepare(
      "INSERT INTO refs(src_path,src_line,symbol_name,def_path,def_line,confidence) VALUES(?,?,?,?,?,?)",
    );
    const tx = this.db.transaction(() => {
      delR.run(srcPath);
      for (const e of edges) {
        insR.run(
          e.src_path,
          e.src_line,
          e.symbol_name,
          e.def_path ?? null,
          e.def_line ?? null,
          e.confidence,
        );
      }
    });
    tx();
  }

  allRefs(): RefEdge[] {
    return this.db
      .prepare(
        "SELECT src_path,src_line,symbol_name,def_path,def_line,confidence FROM refs",
      )
      .all() as RefEdge[];
  }

  /** 在落盤 refs 邊上跑遞迴 CTE 算傳遞呼叫鏈（call hierarchy）。
   *  direction='up' 找 callers（誰傳遞地呼叫此符號）；'down' 找 callees（此符號傳遞地呼叫誰）。
   *  max_hops 限深度防環；信心傳播：鏈中任一邊 low 則該路徑降 low、節點取是否存在全 high 路徑。
   *  回 [{name,path,line,depth,confidence}]，DISTINCT 節點取最小 depth；refs 表為空 → 回 []。 */
  traverseCallGraph(
    symbol: string,
    defPath: string,
    direction: "up" | "down",
    maxHops = 5,
  ): CallGraphNode[] {
    const absDefPath = resolve(defPath);
    let joinClause: string;
    if (direction === "up") {
      // 誰引用了當前符號（r.symbol_name=c.name 且 r.def_path=c.path）→ 引用點 src_line 落在哪個符號 body = caller
      joinClause =
        "JOIN refs r ON r.symbol_name = c.name AND r.def_path = c.path " +
        "JOIN symbols s ON s.path = r.src_path " +
        "AND s.line <= r.src_line AND r.src_line <= s.end_line";
    } else if (direction === "down") {
      // 當前符號 body 範圍內的引用（src 在 c 的 [line,end_line]）→ 被引用符號定義 = callee
      joinClause =
        "JOIN refs r ON r.src_path = c.path " +
        "AND r.src_line >= c.line AND r.src_line <= c.end_line " +
        "JOIN symbols s ON s.path = r.def_path AND s.name = r.symbol_name";
    } else {
      throw new Error(`direction 必須是 'up' 或 'down'，收到 ${direction as string}`);
    }

    const cte = `
        WITH RECURSIVE chain(name, path, line, end_line, depth, min_conf) AS (
            SELECT name, path, line, end_line, 0, 'high'
            FROM symbols WHERE name = ? AND path = ?
            UNION
            SELECT s.name, s.path, s.line, s.end_line, c.depth + 1,
                   CASE WHEN r.confidence = 'low' OR c.min_conf = 'low'
                        THEN 'low' ELSE 'high' END
            FROM chain c
            ${joinClause}
            WHERE c.depth < ? AND NOT (s.name = c.name AND s.path = c.path)
        )
        SELECT name, path, MIN(line) AS line, MIN(depth) AS depth,
               MAX(CASE WHEN min_conf = 'high' THEN 1 ELSE 0 END) AS has_high_path
        FROM chain WHERE depth > 0
        GROUP BY name, path
        ORDER BY depth, name
        `;
    const rows = this.db.prepare(cte).all(symbol, absDefPath, maxHops) as {
      name: string;
      path: string;
      line: number;
      depth: number;
      has_high_path: number;
    }[];
    return rows.map((r) => ({
      name: r.name,
      path: r.path,
      line: r.line,
      depth: r.depth,
      confidence: r.has_high_path ? "high" : "low",
    }));
  }

  // ── 統計（給 status / 面板用） ──
  stats(): ProjectStats {
    const c = this.db;
    const count = (sql: string): number =>
      (c.prepare(sql).get() as { n: number }).n;
    const nFiles = count("SELECT COUNT(*) AS n FROM files");
    const nSymbols = count("SELECT COUNT(*) AS n FROM symbols");
    const nRefs = count("SELECT COUNT(*) AS n FROM refs");
    // 功能 B：便宜的 COUNT(*) 放 stats；⛔ dup_groups（要 GROUP BY shape_hash HAVING）絕不放 stats。
    const nFingerprints = count("SELECT COUNT(*) AS n FROM fingerprints");
    const nComments = count("SELECT COUNT(*) AS n FROM comments");
    const lastIndexed = (
      c.prepare("SELECT MAX(indexed_at) AS m FROM files").get() as {
        m: number | null;
      }
    ).m;
    return {
      project_key: this.projectKey,
      repo_path: this.repoPath,
      db_file: this.dbFile,
      indexed_files: nFiles,
      symbols: nSymbols,
      refs: nRefs,
      fingerprints: nFingerprints,
      comments: nComments,
      last_indexed_at: lastIndexed,
      schema_version: parseInt(this.getMeta("schema_version", "0"), 10),
      indexed_git_sha: this.getMeta("git_head_sha"), // 坑6：索引時的 sha
    };
  }
}

/** 掃庫目錄下所有 *.db，反查各自的 repo_path（meta 表）+ 統計。給中文面板「列出本機所有已索引專案」用。
 *  壞庫（讀不了/缺表）跳過並標 error，不讓單一壞庫炸掉整個列舉（fail-soft 列舉、fail-loud 留給單專案操作）。 */
export function listIndexedProjects(): IndexedProject[] {
  const dbDir = defaultDbDir();
  const out: IndexedProject[] = [];
  let entries: string[];
  try {
    entries = readdirSync(dbDir)
      .filter((f) => f.endsWith(".db"))
      .sort();
  } catch {
    return out; // 目錄不存在 → 空列舉
  }
  for (const fname of entries) {
    const dbFile = join(dbDir, fname);
    const stem = fname.replace(/\.db$/, "");
    let conn: DB | undefined;
    try {
      conn = new DatabaseConstructor(dbFile, { readonly: true });
      const row = conn
        .prepare("SELECT value FROM meta WHERE key='repo_path'")
        .get() as { value: string } | undefined;
      const repoPath = row ? row.value : null;
      const cnt = (sql: string): number =>
        (conn!.prepare(sql).get() as { n: number }).n;
      const nFiles = cnt("SELECT COUNT(*) AS n FROM files");
      const nSymbols = cnt("SELECT COUNT(*) AS n FROM symbols");
      const nRefs = cnt("SELECT COUNT(*) AS n FROM refs");
      const lastIndexed = (
        conn.prepare("SELECT MAX(indexed_at) AS m FROM files").get() as {
          m: number | null;
        }
      ).m;
      let pathExists = false;
      if (repoPath) {
        try {
          pathExists = statSync(repoPath).isDirectory();
        } catch {
          pathExists = false;
        }
      }
      out.push({
        project_key: stem,
        repo_path: repoPath,
        db_file: dbFile,
        indexed_files: nFiles,
        symbols: nSymbols,
        refs: nRefs,
        last_indexed_at: lastIndexed,
        path_exists: pathExists,
      });
    } catch (exc) {
      // 列舉層 fail-soft：任何讀庫錯誤都只跳過該庫並標 error。
      out.push({
        project_key: stem,
        db_file: dbFile,
        error: `讀庫失敗: ${exc instanceof Error ? exc.message : String(exc)}`,
      });
    } finally {
      conn?.close();
    }
  }
  return out;
}
