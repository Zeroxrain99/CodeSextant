// Index storage module: SQLite persistence + content-hash incrementality + project isolation
// (full TypeScript rewrite, P1; ported from Python codesextant/storage.py).
//
// Design, as settled by the PoC:
//   - One SQLite database per project, project_key = sha1(absolute repo path), so projects never
//     cross-talk.
//   - The file content hash (sha256) is the invalidation key: edit one file and only that file is
//     recomputed, everything else is a cache hit.
//
// Single responsibility: own one project's SQLite database (open it, create tables, read/write file
// hashes, store and fetch symbols, store and fetch reference edges, report statistics). It touches
// neither tree-sitter nor ts-morph. Default database location: ~/.codesextant/<project_key>.db.
//
// Deliberate differences from the Python version (none affect output or persistence parity):
//   - project_key: Python uses os.path.normcase(os.path.abspath()); TypeScript uses path.resolve()
//     plus normcaseAbs (lowercase, unify backslashes, strip trailing dots and spaces from components)
//     to match it, so both compute the same sha1 for a project and share one .db.
//   - better-sqlite3 autocommits by default (without an explicit BEGIN every statement commits on its
//     own), so most of Python's conn.commit() calls drop out; anything that wants "DELETE then batch
//     INSERT" to be atomic is wrapped in db.transaction(), matching Python.
//   - better-sqlite3 rejects undefined as a bound value, so Python's dict.get(k) (None when absent)
//     ports to v ?? null.
//
// Known edges. The producers never trigger these, so practical parity is unaffected; they are
// recorded here so nobody misreads them later:
//   - dict.get(k, D) where D is not None (e.g. comments kind→"line" / scope→""): Python falls back to
//     D only when the key is absent, and stores None when the key exists with value None (a NOT NULL
//     column then fails loud with IntegrityError); TypeScript's v ?? D falls back for undefined and
//     null alike (fail-soft). Both versions agree on the "key absent" and "value given" paths: the
//     comments producer always fills a value and never emits an explicit null, so what lands on disk
//     is identical. Only the unreachable "explicit null" dirty input diverges, where TypeScript is
//     fail-soft.
//   - Integer values in REAL columns (indexed_at/last_indexed_at): Python's sqlite3 always returns a
//     float for REAL (2000 → 2000.0, serialized as "2000.0"); better-sqlite3 returns a JS number
//     (JSON.stringify gives "2000"). During the rewrite the Python version is frozen and the switch
//     only happens once TypeScript reaches parity, so the two never serve the same database at the
//     same time and the wire format needs no simultaneous parity. Consumers must not compare a REAL
//     as an exact string.
import DatabaseConstructor from "better-sqlite3";
import { createHash } from "node:crypto";
import { readFileSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { resolve, join } from "node:path";
import type { SymbolDef } from "./symbols.js";

/** The better-sqlite3 Database instance type (a namespace type, paired with the esModuleInterop default import). */
type DB = DatabaseConstructor.Database;

// Schema version of the database (bump by one whenever the schema changes; future migrations can key
// off it).
// ⚠ Be honest about what the migration mechanism is: open() runs exec(CREATE TABLE IF NOT EXISTS) to
// add missing tables idempotently, plus the add-column-only ensureColumns() hook. meta.schema_version
// is overwritten unconditionally; the number is only reported in stats and gates no migration. That
// is safe for "add a table" and "add a column" changes.
export const SCHEMA_VERSION = 3; // v0.11.x P3: fingerprints gained the cognitive column; v2 = the three feature-B tables

/** One persisted symbol (= SymbolDef + the path of the file it lives in). */
export interface SymbolRow extends SymbolDef {
  path: string;
}

/** One reference edge (some line at a call site uses a defined symbol). */
export interface RefEdge {
  src_path: string;
  src_line: number;
  symbol_name: string;
  def_path?: string | null;
  def_line?: number | null;
  confidence: string; // "high"(resolved-import) / "low"(name-match)
}

/** Feature B: the structural fingerprint of one executable unit (duplicate detection groups by shape_hash). */
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
  cognitive?: number | null; // P3 D3: an int for high-confidence languages, null = UNKNOWN for the rest
}

/** Feature B: one entry in the winnowing k-gram inverted index. */
export interface WinnowEntry {
  line?: number | null;
  fp_value?: number | null;
}

/** Feature B: one comment node + its line number + the symbol it belongs to. */
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

/** One node in a call chain (a row from the call-hierarchy recursive CTE). */
export interface CallGraphNode {
  name: string;
  path: string;
  line: number;
  depth: number;
  confidence: string;
}

/** Statistics for one project (used by status and the panel). */
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

/** One entry when listing every indexed project on this machine. */
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

/** Reproduces the combined effect of Python's os.path.normcase(os.path.abspath()) on win32:
 *  - abspath/GetFullPathName: strips trailing dots and spaces from path components (Windows filename
 *    semantics; path.resolve does not do this).
 *    ⚠ Measured GetFullPathName behaviour (confirmed with _dbg): a trailing dot is stripped from every
 *    component ('foo.' → 'foo'); a trailing space is stripped only from the basename (the last
 *    component), and intermediate components keep theirs ('E:\\Proj \\Foo.' → 'e:\\proj \\foo').
 *  - normcase: lowercase + unify backslashes. A no-op throughout on POSIX (case and forward slashes
 *    are kept).
 *  ⚠ This stripping is load-bearing for project_key: when the user mistypes a trailing dot or space
 *  ('E:\\foo. ') the real directory is 'E:\\foo', and TypeScript and Python have to compute the same
 *  key and share one .db. Pathological mixed paths (an intermediate component like 'foo. ') are not
 *  guaranteed to reproduce exactly. */
function normcaseAbs(resolved: string): string {
  if (process.platform !== "win32") return resolved;
  const parts = resolved.replace(/\//g, "\\").split("\\");
  const last = parts.length - 1;
  const stripped = parts.map((seg, i) => {
    if (i === 0) return seg; // drive ('E:') or the empty leading segment of a UNC path, never stripped
    if (i === last) return seg.replace(/[. ]+$/, ""); // basename: strip both trailing dots and trailing spaces
    return seg.replace(/\.+$/, ""); // intermediate component: strip trailing dots only, keep spaces (matches GetFullPathName)
  });
  return stripped.join("\\").toLowerCase();
}

/** Project isolation key = sha1(normalized absolute repo path). Reproduces Python's
 *  normcase(abspath()) so that any relative, differently-cased, slash-flipped or
 *  trailing-dot-or-space spelling of the same project maps to one key and one shared .db, which is
 *  what keeps projects from crossing wires. */
export function projectKey(repoPath: string): string {
  const abs = normcaseAbs(resolve(repoPath));
  return createHash("sha1").update(abs, "utf-8").digest("hex");
}

/** The single source of truth matching Python's os.path.normcase(os.path.abspath(p)), used by
 *  modules such as ranking and namegraph for path matching (a reference edge's def_path/src_path and
 *  a symbol's path must go through the same normalization to land on the same node).
 *  ⚠ Shares one normcaseAbs with projectKey so the two normalizations cannot drift apart. Empty
 *  strings are the caller's business (not guarded here: normPath("") returns cwd, matching Python's
 *  abspath("")). */
export function normPath(p: string): string {
  return normcaseAbs(resolve(p));
}

/** Default database directory ~/.codesextant/. Override it with the CODESEXTANT_HOME environment
 *  variable, which is what test isolation uses. */
export function defaultDbDir(): string {
  const home = process.env["CODESEXTANT_HOME"];
  return home ? home : join(homedir(), ".codesextant");
}

/** The SQLite database file path for a given project. */
export function dbPathFor(repoPath: string): string {
  return join(defaultDbDir(), `${projectKey(repoPath)}.db`);
}

/** File content sha256: the invalidation key for incremental indexing. */
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

/** Migration hook that adds columns to an existing database, since CREATE TABLE IF NOT EXISTS never
 *  adds a column to a table that already exists. Add-only, idempotent, reversible. */
function ensureColumns(db: DB): void {
  const expected: Record<string, [string, string][]> = {
    fingerprints: [["cognitive", "INTEGER"]], // P3 D3: an int for high-confidence languages, NULL for the rest
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

/** Facade over one project's SQLite index. Usage: const store = ProjectStore.open(repo); try { ... } finally { store.close(); } */
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

  // ── open / close ──
  static open(repoPath: string): ProjectStore {
    const dbFile = dbPathFor(repoPath);
    mkdirSync(defaultDbDir(), { recursive: true });
    const db = new DatabaseConstructor(dbFile);
    // ⚠ Match the Python sqlite3 default: foreign_keys OFF. better-sqlite3 defaults to ON, but the
    // whole Python design (storeFileSymbols inserts symbols before upserting the file row) assumes
    // foreign keys are not enforced: the FOREIGN KEY declarations in the schema are documentation
    // that the Python version never enforced. Turn it off to keep persistence and ordering parity.
    db.pragma("foreign_keys = OFF");
    db.exec(SCHEMA);
    ensureColumns(db); // add new columns to an existing database (migration hook)
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

  /** Pitfall 6: record the repo's git HEAD sha at index time, for freshness comparison. */
  recordGitSha(sha: string): void {
    this.setMeta("git_head_sha", sha);
  }

  // ── incremental core: decide whether a file needs recomputing ──
  needsReindex(path: string, currentHash: string): boolean {
    const row = this.db
      .prepare("SELECT content_hash FROM files WHERE path=?")
      .get(path) as { content_hash: string } | undefined;
    return row === undefined || row.content_hash !== currentHash;
  }

  /** Persist after recomputing: drop the file's old symbols, write the new ones, update the hash.
   *  The whole batch is one transaction. */
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

  /** Feature B: persist one file's structural fingerprints + winnowing inverted index, clearing that
   *  file's old rows first. content_hash is owned by storeFileSymbols. */
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

  /** Feature B: persist one file's comments, clearing that file's old rows first. content_hash is
   *  likewise owned by storeFileSymbols. */
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

  /** A file was deleted, so remove it from the index: its symbols, its file row, the reference edges
   *  it emits or that point at it, and the three feature-B tables. */
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

  // ── queries ──
  /** Fetch symbols. With filePath, only that file; without it, the whole project. */
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

  /** Find every definition of a name: stage one of two-stage reference finding, the coarse candidate filter. */
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

  // ── reference edges ──
  /** Persist the reference edges a file emits, clearing that file's old edges first so there is one
   *  source of truth. */
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

  /** Run a recursive CTE over the persisted refs edges to compute the transitive call chain (call
   *  hierarchy).
   *  direction='up' finds callers (who transitively calls this symbol); 'down' finds callees (whom
   *  this symbol transitively calls).
   *  max_hops caps the depth to guard against cycles. Confidence propagates: one low edge anywhere in
   *  a chain drops that path to low, and a node counts as high if any all-high path reaches it.
   *  Returns [{name,path,line,depth,confidence}], one row per distinct node at its smallest depth; an
   *  empty refs table gives []. */
  traverseCallGraph(
    symbol: string,
    defPath: string,
    direction: "up" | "down",
    maxHops = 5,
  ): CallGraphNode[] {
    const absDefPath = resolve(defPath);
    let joinClause: string;
    if (direction === "up") {
      // who references the current symbol (r.symbol_name=c.name and r.def_path=c.path) → whichever
      // symbol body contains src_line is the caller
      joinClause =
        "JOIN refs r ON r.symbol_name = c.name AND r.def_path = c.path " +
        "JOIN symbols s ON s.path = r.src_path " +
        "AND s.line <= r.src_line AND r.src_line <= s.end_line";
    } else if (direction === "down") {
      // references inside the current symbol's body (src within c's [line,end_line]) → the referenced
      // symbol's definition is the callee
      joinClause =
        "JOIN refs r ON r.src_path = c.path " +
        "AND r.src_line >= c.line AND r.src_line <= c.end_line " +
        "JOIN symbols s ON s.path = r.def_path AND s.name = r.symbol_name";
    } else {
      throw new Error(`direction must be 'up' or 'down', got ${direction as string}`);
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

  // ── statistics (for status and the panel) ──
  stats(): ProjectStats {
    const c = this.db;
    const count = (sql: string): number =>
      (c.prepare(sql).get() as { n: number }).n;
    const nFiles = count("SELECT COUNT(*) AS n FROM files");
    const nSymbols = count("SELECT COUNT(*) AS n FROM symbols");
    const nRefs = count("SELECT COUNT(*) AS n FROM refs");
    // Feature B: a cheap COUNT(*) belongs in stats; ⛔ dup_groups (which needs GROUP BY shape_hash
    // HAVING) must never go in stats.
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
      indexed_git_sha: this.getMeta("git_head_sha"), // pitfall 6: the sha at index time
    };
  }
}

/** Scan every *.db under the database directory and look up each one's repo_path (from the meta
 *  table) plus its statistics. This is what backs the panel's "list every indexed project on this
 *  machine".
 *  A broken database (unreadable, or missing tables) is skipped and marked with error, so one bad
 *  database cannot blow up the whole listing. Listing is fail-soft; fail-loud is reserved for
 *  single-project operations. */
export function listIndexedProjects(): IndexedProject[] {
  const dbDir = defaultDbDir();
  const out: IndexedProject[] = [];
  let entries: string[];
  try {
    entries = readdirSync(dbDir)
      .filter((f) => f.endsWith(".db"))
      .sort();
  } catch {
    return out; // directory does not exist → empty listing
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
      // Fail-soft at the listing layer: any read error just skips that database and records error.
      out.push({
        project_key: stem,
        db_file: dbFile,
        error: `failed to read database: ${exc instanceof Error ? exc.message : String(exc)}`,
      });
    } finally {
      conn?.close();
    }
  }
  return out;
}
