"""Persist each project's CodeSextant index in SQLite.

Projects are isolated by a hash of their absolute path. File content hashes drive
incremental updates, so unchanged files remain cache hits. The default database
location is ``~/.codesextant/<project_key>.db``.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

from . import cache_lease

# Database schema version (bump on schema change; future migrations can key off this).
# ``open()`` creates missing tables and ``_ensure_columns()`` adds missing columns.
# The reported schema version does not gate migrations. Type changes and removals
# still require a dedicated migration.
SCHEMA_VERSION = 9
_INDEX_GENERATION_KEY = "index_generation"
_COCHANGE_HEAD_KEY = "cochange_head"
_SYMBOL_SNAPSHOT_FORMAT = 1
_MAP_SNAPSHOT_FORMAT = 2


def project_key(repo_path: str) -> str:
    """Per-project isolation key = sha1(absolute repo path).

    Computed from the (normalized) absolute path, so the same project always maps
    to the same key and the same database, no matter what relative path it was
    reached through.
    """
    abs_path = os.path.normcase(os.path.abspath(repo_path))
    return hashlib.sha1(abs_path.encode("utf-8")).hexdigest()


def default_db_dir() -> Path:
    """Default database directory ~/.codesextant/. Overridable via env var CODESEXTANT_HOME (handy for test isolation)."""
    home = os.environ.get("CODESEXTANT_HOME")
    base = Path(home) if home else (Path.home() / ".codesextant")
    return base


def db_path_for(repo_path: str) -> Path:
    """The SQLite database file path for a given project."""
    return default_db_dir() / f"{project_key(repo_path)}.db"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def sqlite_wal_is_safe(version_info=None) -> bool:
    """Return whether this SQLite runtime contains the WAL-reset fix."""
    raw = sqlite3.sqlite_version_info if version_info is None else version_info
    try:
        version = tuple(int(part) for part in raw[:3])
    except (TypeError, ValueError):
        return False
    if len(version) != 3:
        return False
    if version >= (3, 51, 3):
        return True
    if version[:2] == (3, 50):
        return version[2] >= 7
    if version[:2] == (3, 44):
        return version[2] >= 6
    return False


def is_busy_index_error(error_type: str, message: str) -> bool:
    """Whether an error means "the index is busy right now" rather than "it is broken".

    SQLite reports lock contention as OperationalError with a message naming a lock or a
    busy database, after busy_timeout has already been waited out. On a daemon shared by
    several agents, a reindex holding the write lock is an ordinary condition with an
    ordinary remedy -- retry -- so it belongs with the other overload responses rather
    than with internal failures.
    """
    if error_type != "OperationalError":
        return False
    text = message.lower()
    return "locked" in text or "database is busy" in text


def sqlite_runtime_status() -> dict:
    """Describe the SQLite version and the journal policy selected for it."""
    wal_safe = sqlite_wal_is_safe()
    unsafe_override = _env_flag("CODESEXTANT_SQLITE_UNSAFE_WAL", False)
    wal_requested = _env_flag("CODESEXTANT_SQLITE_WAL", True)
    return {
        "version": sqlite3.sqlite_version,
        "wal_safe": wal_safe,
        "unsafe_wal_override": unsafe_override,
        "wal_requested": wal_requested,
        "wal_allowed": wal_requested and (wal_safe or unsafe_override),
    }


def apply_connection_pragmas(conn: sqlite3.Connection) -> None:
    """Set the connection-level PRAGMAs that let "many readers + one writer" coexist.

    Local clients share the same daemon. WAL permits concurrent readers, but affected
    SQLite releases can corrupt a database during a rare WAL reset race. Safe releases
    use WAL by default; affected releases fail closed to the rollback journal.

    Environment switches:
      CODESEXTANT_SQLITE_WAL=0              -> force the classic rollback journal
      CODESEXTANT_SQLITE_UNSAFE_WAL=1       -> force WAL on an affected SQLite runtime
      CODESEXTANT_SQLITE_BUSY_TIMEOUT_MS    -> max wait under contention (default 5000ms)
      CODESEXTANT_SQLITE_SYNC_NORMAL=0      -> fall back to synchronous=FULL

    synchronous=NORMAL under WAL is still safe against a process crash; it can only
    lose the last few transactions on a power loss. This database is a rebuildable
    index cache (SQLite is the index's source of truth, but the index itself can be
    rebuilt from source), so write speed is prioritized.
    """
    busy_ms = max(0, _env_int("CODESEXTANT_SQLITE_BUSY_TIMEOUT_MS", 5000))
    conn.execute(f"PRAGMA busy_timeout={busy_ms}")
    runtime = sqlite_runtime_status()
    current_mode = None
    try:
        row = conn.execute("PRAGMA journal_mode").fetchone()
        current_mode = str(row[0]).lower() if row else None
    except sqlite3.DatabaseError:
        pass
    if runtime["wal_allowed"]:
        # Not fatal on failure (e.g. the database lives on a network drive without WAL support):
        # keep running on whatever journal mode is already in effect.
        if current_mode != "wal":
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:
                pass
    else:
        # Journal mode persists in the database file. Explicitly leave WAL so a
        # database created by a different runtime cannot keep an unsafe mode.
        # Avoid setting the already-active mode because that requests an
        # unnecessary exclusive lock and can stall readers behind a writer.
        if current_mode != "delete":
            conn.execute("PRAGMA journal_mode=DELETE")
    if _env_flag("CODESEXTANT_SQLITE_SYNC_NORMAL", True):
        conn.execute("PRAGMA synchronous=NORMAL")


def symbol_snapshot_path(db_file: str | Path) -> Path:
    """Symbol snapshot dedicated to `map` (a cache, not the source of truth); ignored outright on a revision mismatch."""
    return Path(f"{db_file}.symbols-v{_SYMBOL_SNAPSHOT_FORMAT}.json")


def _acquire_cache_lease_for_db(
        db_file: str | Path) -> cache_lease.ProjectLease:
    """Protect one managed database group during direct artifact access."""
    path = Path(db_file)
    if path.suffix != ".db":
        raise cache_lease.LeaseUnsafeError(
            "managed cache database must use the .db suffix")
    return cache_lease.acquire_shared(path.stem, home=path.parent)


def write_symbol_snapshot(db_file: str | Path, revision: tuple,
                          symbols: list[dict]) -> Path:
    """Atomically write a UTF-8 JSON snapshot; not pickle, so on-disk content can't execute arbitrary Python."""
    target = symbol_snapshot_path(db_file)
    with _acquire_cache_lease_for_db(db_file):
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(
            f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with open(temp, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({
                    "format": _SYMBOL_SNAPSHOT_FORMAT,
                    "revision": list(revision),
                }, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
                json.dump(symbols, handle, ensure_ascii=False, separators=(",", ":"))
            os.replace(temp, target)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
    return target


def map_snapshot_path(db_file: str | Path) -> Path:
    """Each project keeps only the full map result for its most recent parameter combination; the daemon's LRU is what keeps several."""
    return Path(f"{db_file}.map-v{_MAP_SNAPSHOT_FORMAT}.json")


def write_map_snapshot(db_file: str | Path, key_digest: str,
                       result: dict) -> Path:
    """Atomically write a map JSON tied to a revision/parameter digest; any index or env change misses immediately."""
    target = map_snapshot_path(db_file)
    with _acquire_cache_lease_for_db(db_file):
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(
            f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with open(temp, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({
                    "format": _MAP_SNAPSHOT_FORMAT,
                    "key_digest": key_digest,
                    "result": result,
                }, handle, ensure_ascii=False, separators=(",", ":"))
            os.replace(temp, target)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
    return target


def load_map_snapshot(db_file: str | Path, key_digest: str) -> dict | None:
    """Return the map only when the digest matches exactly; on corruption or a stale revision, fail-soft into a recompute."""
    with _acquire_cache_lease_for_db(db_file):
        try:
            with open(map_snapshot_path(db_file), encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None
    if (payload.get("format") != _MAP_SNAPSHOT_FORMAT
            or payload.get("key_digest") != key_digest
            or not isinstance(payload.get("result"), dict)):
        return None
    return payload["result"]


def file_content_hash(path: str) -> str:
    """sha256 of file content (the invalidation key for incremental updates)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


_SCHEMA = """
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
-- get_map hot path: covers all six SELECT columns and directly satisfies ORDER BY path,line,
-- avoiding a table lookup + temp sort on large databases.
CREATE INDEX IF NOT EXISTS idx_symbols_map
ON symbols(path,line,kind,name,end_line,scope);

-- Reference edges: which line of which file uses a given defined symbol
-- (backs both persisted find-references results and PageRank graph construction).
CREATE TABLE IF NOT EXISTS refs (
    src_path    TEXT NOT NULL,   -- file where the reference occurs (the call site)
    src_line    INTEGER NOT NULL,
    symbol_name TEXT NOT NULL,   -- name of the referenced symbol
    def_path    TEXT,            -- file jedi resolved the definition to (None = unresolved)
    def_line    INTEGER,
    confidence  TEXT NOT NULL    -- "high" (resolved-import) / "low" (name-match)
);
CREATE INDEX IF NOT EXISTS idx_refs_symbol ON refs(symbol_name);
CREATE INDEX IF NOT EXISTS idx_refs_def ON refs(def_path);

-- Duplicate detection: a structural fingerprint per executable unit (function/method).
-- shape_hash = normalized AST shape (identifiers/literals erased, control-flow
-- structure kept); raw_token_hash = unnormalized raw token stream (only counts as EXACT_DUP when
-- this also matches); call_hash = the set of called names. GROUP BY shape_hash finds duplicate
-- groups in a single O(n) SQL query.
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
    cognitive        INTEGER,            -- cognitive complexity, or NULL when unsupported
    FOREIGN KEY(path) REFERENCES files(path)
);
CREATE INDEX IF NOT EXISTS idx_fp_shape ON fingerprints(shape_hash);
CREATE INDEX IF NOT EXISTS idx_fp_call  ON fingerprints(call_hash);
CREATE INDEX IF NOT EXISTS idx_fp_path  ON fingerprints(path);

-- Winnowing k-gram fingerprint inverted index for Type-3 near-duplicates.
-- fp_value -> {symbol, line}; only entries sharing a fingerprint get compared.
CREATE TABLE IF NOT EXISTS fingerprint_index (
    path     TEXT NOT NULL,
    line     INTEGER,
    fp_value INTEGER,
    FOREIGN KEY(path) REFERENCES files(path)
);
CREATE INDEX IF NOT EXISTS idx_fpidx_val  ON fingerprint_index(fp_value);
CREATE INDEX IF NOT EXISTS idx_fpidx_path ON fingerprint_index(path);

-- Comment index: one row per comment node, source line, and owning symbol.
-- is_doc=1 = docstring (owner_line points at the owning symbol's
-- definition line, used by the coverage JOIN); tag = TODO/FIXME marker (NULL if none).
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
-- Co-change counts mined from version-control history: how often each file changed,
-- and how often each pair changed together. Paths are repository-relative, as Git
-- reports them, because these describe the repository rather than one checkout.
-- Counts rather than rules: a rule is a threshold applied to counts, counts add and
-- rules do not, so a new commit costs a commit rather than a re-derivation.
-- _COCHANGE_HEAD_KEY records the commit the totals were last brought up to.
CREATE TABLE IF NOT EXISTS cochange_count (
    path    TEXT PRIMARY KEY,
    changes INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cochange_pair (
    path      TEXT NOT NULL,
    companion TEXT NOT NULL,
    support   INTEGER NOT NULL,
    PRIMARY KEY (path, companion)
);
CREATE INDEX IF NOT EXISTS idx_cochange_pair_path ON cochange_pair(path);

-- The same coupling keyed by a symbol rather than a whole file. "engine.py changes
-- with storage.py" is true and nearly useless on two thousand lines; the coupling of
-- the function actually being edited is what a caller can act on. Mined per file, on
-- demand, because reading full diffs for a whole repository does not scale.
-- cochange_symbol_state records which commit each file's rows describe.
CREATE TABLE IF NOT EXISTS cochange_symbol (
    path       TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    companion  TEXT NOT NULL,
    support    INTEGER NOT NULL,
    changes    INTEGER NOT NULL,
    confidence REAL NOT NULL,
    PRIMARY KEY (path, symbol, companion)
);
CREATE INDEX IF NOT EXISTS idx_cochange_symbol ON cochange_symbol(path, symbol);

CREATE TABLE IF NOT EXISTS cochange_symbol_state (
    path TEXT PRIMARY KEY,
    head TEXT NOT NULL
);

-- Which optional analyses have been computed for a file, and for what content.
-- Clone fingerprints and comment extraction are not needed to navigate code, so they
-- are materialized when something asks for them rather than for every file at index
-- time. A row here means "this kind is up to date for this exact content hash"; no row
-- means it has to be computed. Absence of derived rows cannot say this on its own,
-- because a file with no comments and a file whose comments were never extracted both
-- have zero rows.
CREATE TABLE IF NOT EXISTS derived_state (
    path         TEXT NOT NULL,
    kind         TEXT NOT NULL,   -- 'fingerprints' | 'comments' | 'refs:<symbol>'
    content_hash TEXT NOT NULL,
    PRIMARY KEY (path, kind)
);

CREATE INDEX IF NOT EXISTS idx_comments_path ON comments(path);
CREATE INDEX IF NOT EXISTS idx_comments_tag  ON comments(tag);
CREATE INDEX IF NOT EXISTS idx_comments_doc  ON comments(is_doc);
"""


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Migration hook for adding columns to an existing database (CREATE TABLE IF NOT EXISTS does not add columns to an existing table).

    Add-column-only, idempotent, reversible (ALTER ADD COLUMN doesn't disturb existing rows;
    the new column defaults to NULL). Changing a column's type or dropping one is out of scope.
    """
    expected = {
        "fingerprints": [("cognitive", "INTEGER")],  # NULL when cognitive complexity is unsupported
    }
    for table, cols in expected.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, decl in cols:
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


class ProjectStore:
    """Facade over one project's SQLite index database.

    Usage:
        store = ProjectStore.open(repo_path)
        try:
            ...
        finally:
            store.close()
    Or as a context manager: `with ProjectStore.open(repo) as store: ...`
    """

    def __init__(self, conn: sqlite3.Connection, repo_path: str, db_file: Path,
                 *, lease: cache_lease.ProjectLease,
                 read_only: bool = False):
        self.conn = conn
        self.repo_path = os.path.abspath(repo_path)
        self.project_key = project_key(repo_path)
        self.db_file = db_file
        self.read_only = read_only
        self._cache_lease = lease
        self._close_lock = threading.Lock()
        self._closed = False

    # ── open / close ──
    @classmethod
    def open_readonly(cls, repo_path: str, *,
                      busy_timeout_ms: int | None = None,
                      lease_timeout_sec: float | None = None) -> ProjectStore:
        """Open a connection that is guaranteed not to write, for query-only worker processes / read-only endpoints.

        Why this is needed: every `open()` call writes (executescript creates tables,
        backfills columns, writes two meta rows, commits). That's correct for the sole
        writer, but query paths shouldn't go through the write path, and future worker
        subprocesses definitely shouldn't have the ability to corrupt the index.

        Why `PRAGMA query_only` instead of SQLite's `mode=ro` URI: a database in WAL
        mode needs to create a `-shm` shared-memory index file to be readable, and a
        `mode=ro` connection lacks permission to create it, so it simply fails to open
        when no other connection is already open. `query_only` doesn't have this
        problem, and equally raises OperationalError on any write attempt.

        This guards against accidental cross-project access, not a malicious local
        process. The same connection can still run `PRAGMA query_only=0` to lift it.
        The real isolation boundary is the process, not this PRAGMA.

        Raises FileNotFoundError when the database doesn't exist (rather than silently
        creating an empty one, which would swallow the "not indexed yet" error and turn
        it into an empty query result).
        """
        db_file = db_path_for(repo_path)
        lease = cache_lease.acquire_shared(
            project_key(repo_path),
            home=db_file.parent,
            timeout_sec=(
                5.0 if lease_timeout_sec is None
                else max(0.0, float(lease_timeout_sec))
            ),
        )
        conn: sqlite3.Connection | None = None
        try:
            if not db_file.exists():
                raise FileNotFoundError(
                    f"CodeSextant: project not indexed yet, no read-only database to open ({db_file})")
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            busy_ms = max(0, (
                _env_int("CODESEXTANT_SQLITE_BUSY_TIMEOUT_MS", 30000)
                if busy_timeout_ms is None else int(busy_timeout_ms)
            ))
            conn.execute(f"PRAGMA busy_timeout={busy_ms}")
            conn.execute("PRAGMA query_only=1")
            return cls(
                conn, repo_path, db_file, lease=lease, read_only=True)
        except BaseException:
            if conn is not None:
                # Do not unregister until SQLite proves its handle is closed.
                conn.close()
            lease.close()
            raise

    @classmethod
    def open(cls, repo_path: str) -> ProjectStore:
        """Open (or create) a project's database. Creates the database directory automatically if it doesn't exist."""
        db_file = db_path_for(repo_path)
        lease = cache_lease.acquire_shared(
            project_key(repo_path), home=db_file.parent)
        conn: sqlite3.Connection | None = None
        try:
            db_file.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            apply_connection_pragmas(conn)
            conn.executescript(_SCHEMA)
            _ensure_columns(conn)
            store = cls(conn, repo_path, db_file, lease=lease)
            store._set_meta("schema_version", str(SCHEMA_VERSION))
            store._set_meta("repo_path", store.repo_path)
            conn.execute(
                "INSERT OR IGNORE INTO meta(key,value) VALUES(?,?)",
                (_INDEX_GENERATION_KEY, "0"),
            )
            conn.commit()
            return store
        except BaseException:
            if conn is not None:
                # A close failure keeps the lease live until process exit.
                conn.close()
            lease.close()
            raise

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self.conn.close()
            self._cache_lease.close()
            self._closed = True

    def __enter__(self) -> ProjectStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── meta ──
    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value "
            "WHERE meta.value <> excluded.value",
            (key, value),
        )

    def get_meta(self, key: str, default=None):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def record_git_sha(self, sha: str) -> None:
        """Record the repository's Git HEAD SHA for freshness comparisons."""
        self._set_meta("git_head_sha", sha)
        self.conn.commit()

    def index_generation(self) -> int:
        """Return the source-graph generation used to fence reference writes."""
        raw = self.get_meta(_INDEX_GENERATION_KEY, "0")
        try:
            generation = int(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"invalid {_INDEX_GENERATION_KEY} metadata: {raw!r}"
            ) from exc
        if generation < 0:
            raise RuntimeError(
                f"invalid {_INDEX_GENERATION_KEY} metadata: {raw!r}"
            )
        return generation

    def _bump_index_generation(self) -> int:
        """Advance the source-graph generation inside the caller's transaction."""
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "value=CAST(meta.value AS INTEGER)+1",
            (_INDEX_GENERATION_KEY, "1"),
        )
        return self.index_generation()

    # ── Incremental core: decide whether a file needs recomputing ──
    def needs_reindex(self, path: str, current_hash: str) -> bool:
        """Content hash changed (or the file isn't in the database yet) -> needs recomputing."""
        row = self.conn.execute(
            "SELECT content_hash FROM files WHERE path=?", (path,)
        ).fetchone()
        return (row is None) or (row["content_hash"] != current_hash)

    def has_indexed_file(self, path: str) -> bool:
        """Return whether one exact file path is present in the index."""
        row = self.conn.execute(
            "SELECT 1 FROM files WHERE path=? LIMIT 1", (path,)
        ).fetchone()
        return row is not None

    def store_file_symbols(self, path: str, content_hash: str, symbols: list[dict],
                           indexed_at: float) -> None:
        """Persist after a recompute: clear the file's old symbols, write the new ones, update the hash. The whole batch is one transaction."""
        cur = self.conn
        with cur:
            # A changed file invalidates edges it emitted and edges that pointed at definitions
            # inside it. Reference resolution is on demand, so keeping stale edges would be worse
            # than temporarily having fewer edges until the affected symbol is queried again.
            cur.execute("DELETE FROM refs WHERE src_path=? OR def_path=?", (path, path))
            cur.execute("DELETE FROM symbols WHERE path=?", (path,))
            cur.executemany(
                "INSERT INTO symbols(path,kind,name,line,end_line,scope) "
                "VALUES(?,?,?,?,?,?)",
                [(path, s["kind"], s["name"], s["line"], s["end_line"],
                  s.get("scope", "")) for s in symbols],
            )
            cur.execute(
                "INSERT INTO files(path,content_hash,indexed_at) VALUES(?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET "
                "content_hash=excluded.content_hash, indexed_at=excluded.indexed_at",
                (path, content_hash, indexed_at),
            )
            self._bump_index_generation()

    def store_file_index(self, path: str, content_hash: str, symbols: list[dict],
                         indexed_at: float) -> None:
        """Replace the navigation rows for one source file atomically.

        Extraction happens before this method is called. If any statement fails,
        SQLite rolls the entire replacement back, including the files-table hash,
        so the next incremental pass still sees that the source needs indexing.

        Clone fingerprints and comments are dropped rather than rewritten: they are
        materialized on demand, and this file's content just changed, so whatever was
        computed for the previous content is stale. Clearing derived_state is what makes
        the next reader recompute them.
        """
        cur = self.conn
        with cur:
            # A changed definition invalidates both edges emitted by this file
            # and edges from other files that resolved into it.
            cur.execute("DELETE FROM refs WHERE src_path=? OR def_path=?", (path, path))
            cur.execute("DELETE FROM symbols WHERE path=?", (path,))
            cur.execute("DELETE FROM comments WHERE path=?", (path,))
            cur.execute("DELETE FROM fingerprints WHERE path=?", (path,))
            cur.execute("DELETE FROM fingerprint_index WHERE path=?", (path,))
            cur.execute("DELETE FROM derived_state WHERE path=?", (path,))
            cur.execute(
                "INSERT INTO files(path,content_hash,indexed_at) VALUES(?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET "
                "content_hash=excluded.content_hash, indexed_at=excluded.indexed_at",
                (path, content_hash, indexed_at),
            )
            cur.executemany(
                "INSERT INTO symbols(path,kind,name,line,end_line,scope) "
                "VALUES(?,?,?,?,?,?)",
                [(path, s["kind"], s["name"], s["line"], s["end_line"],
                  s.get("scope", "")) for s in symbols],
            )
            self._bump_index_generation()

    def store_file_fingerprints(self, path: str, fingerprints: list[dict],
                                winnow_index: list[dict],
                                *, content_hash: str | None = None) -> None:
        """Replace a file's structural fingerprints and winnowing index.

        This method does not touch the files table; content_hash is owned by the indexer.
        Pass ``content_hash`` to record in derived_state that fingerprints are current for
        that exact content, which is what lets a later reader skip the work.
        """
        cur = self.conn
        cur.execute("DELETE FROM fingerprints WHERE path=?", (path,))
        cur.execute("DELETE FROM fingerprint_index WHERE path=?", (path,))
        cur.executemany(
            "INSERT INTO fingerprints(path,name,kind,line,end_line,scope,shape_hash,"
            "raw_token_hash,call_hash,node_count,nstmts,has_control_flow,cognitive) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(path, f.get("name"), f.get("kind"), f.get("line"), f.get("end_line"),
              f.get("scope", ""), f.get("shape_hash"), f.get("raw_token_hash"),
              f.get("call_hash"), f.get("node_count"), f.get("nstmts"),
              1 if f.get("has_control_flow") else 0, f.get("cognitive")) for f in fingerprints],
        )
        cur.executemany(
            "INSERT INTO fingerprint_index(path,line,fp_value) VALUES(?,?,?)",
            [(path, w.get("line"), w.get("fp_value")) for w in winnow_index],
        )
        if content_hash is not None:
            self._mark_derived(path, "fingerprints", content_hash)
        cur.commit()

    def store_file_comments(self, path: str, comments: list[dict],
                            *, content_hash: str | None = None) -> None:
        """Replace a file's indexed comments; see store_file_fingerprints on content_hash."""
        cur = self.conn
        cur.execute("DELETE FROM comments WHERE path=?", (path,))
        cur.executemany(
            "INSERT INTO comments(path,line,end_line,kind,is_doc,tag,scope,owner_line,text) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            [(path, c.get("line"), c.get("end_line", c.get("line")), c.get("kind", "line"),
              1 if c.get("is_doc") else 0, c.get("tag"), c.get("scope", ""),
              c.get("owner_line"), c.get("text", "")) for c in comments],
        )
        if content_hash is not None:
            self._mark_derived(path, "comments", content_hash)
        cur.commit()

    def cochange_head(self) -> str | None:
        """The commit the stored co-change rules describe, or None if never mined."""
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key=?", (_COCHANGE_HEAD_KEY,)).fetchone()
        return row["value"] if row else None

    def symbol_cochange_head(self, path: str) -> str | None:
        """The commit this file's symbol-level rules describe, or None if never mined."""
        row = self.conn.execute(
            "SELECT head FROM cochange_symbol_state WHERE path=?", (path,)).fetchone()
        return row["head"] if row else None

    def store_symbol_cochange(self, path: str, rules: list[dict],
                              head_sha: str | None) -> None:
        """Replace one file's symbol-level rules and record the commit they describe.

        Scoped to the file rather than the whole table: each file is mined separately,
        so clearing more than the file being replaced would discard work another query
        already paid for.
        """
        with self.conn:
            self.conn.execute("DELETE FROM cochange_symbol WHERE path=?", (path,))
            self.conn.executemany(
                "INSERT INTO cochange_symbol(path,symbol,companion,support,changes,"
                "confidence) VALUES(?,?,?,?,?,?)",
                [(path, r["symbol"], r["companion"], int(r["support"]),
                  int(r["changes"]), float(r["confidence"])) for r in rules],
            )
            self.conn.execute(
                "INSERT INTO cochange_symbol_state(path,head) VALUES(?,?) "
                "ON CONFLICT(path) DO UPDATE SET head=excluded.head",
                (path, head_sha or ""),
            )

    def symbol_cochange_for(self, path: str, symbol: str,
                            *, limit: int = 20) -> list[dict]:
        """Companions of one symbol in one file, most reliable first."""
        rows = self.conn.execute(
            "SELECT companion,support,changes,confidence FROM cochange_symbol "
            "WHERE path=? AND symbol=? "
            "ORDER BY confidence DESC, support DESC, companion LIMIT ?",
            (path, symbol, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_cochange_counts(self, changes: dict, pairs: dict,
                            head_sha: str | None) -> None:
        """Add one batch of commits' counts to the running totals.

        Addition, not replacement: the stored totals describe every commit read so far,
        and an update describes only the ones since. Pairs are stored under both
        orderings so a lookup by either side is one indexed read.
        """
        with self.conn:
            self.conn.executemany(
                "INSERT INTO cochange_count(path,changes) VALUES(?,?) "
                "ON CONFLICT(path) DO UPDATE SET changes=changes+excluded.changes",
                [(path, int(n)) for path, n in changes.items()],
            )
            rows = []
            for (left, right), support in pairs.items():
                rows.append((left, right, int(support)))
                rows.append((right, left, int(support)))
            self.conn.executemany(
                "INSERT INTO cochange_pair(path,companion,support) VALUES(?,?,?) "
                "ON CONFLICT(path,companion) DO UPDATE SET support=support+excluded.support",
                rows,
            )
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_COCHANGE_HEAD_KEY, head_sha or ""),
            )

    def clear_cochange_counts(self) -> None:
        """Forget the totals, for when the window they describe is no longer the wanted one."""
        with self.conn:
            self.conn.execute("DELETE FROM cochange_count")
            self.conn.execute("DELETE FROM cochange_pair")

    def cochange_rules_for(self, path: str, *, min_support: int, min_confidence: float,
                           limit: int = 20) -> list[dict]:
        """Companions of one path that clear the thresholds, most reliable first.

        The thresholds are applied here rather than when the counts were stored, so
        changing one takes effect immediately and without re-reading any history.
        """
        rows = self.conn.execute(
            "SELECT p.companion AS companion, p.support AS support, "
            "       c.changes AS changes, "
            "       CAST(p.support AS REAL) / c.changes AS confidence "
            "FROM cochange_pair p JOIN cochange_count c ON c.path = p.path "
            "WHERE p.path = ? AND p.support >= ? AND c.changes > 0 "
            "  AND CAST(p.support AS REAL) / c.changes >= ? "
            "ORDER BY confidence DESC, support DESC, companion LIMIT ?",
            (path, int(min_support), float(min_confidence), int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def _mark_derived(self, path: str, kind: str, content_hash: str) -> None:
        """Record that ``kind`` is materialized for this file at this content hash."""
        self.conn.execute(
            "INSERT INTO derived_state(path,kind,content_hash) VALUES(?,?,?) "
            "ON CONFLICT(path,kind) DO UPDATE SET content_hash=excluded.content_hash",
            (path, kind, content_hash),
        )

    def symbol_references_resolved(self, path: str, symbol: str, digest: str) -> bool:
        """Whether ``symbol``'s references were resolved against exactly this evidence.

        The distinction this records is the one preflight could not otherwise make:
        an empty blast radius because nobody calls the symbol, versus an empty blast
        radius because nobody has looked.

        ``digest`` is a fingerprint of every file that names the symbol, from
        references.name_sweep -- not the defining file's content hash. Keying it to
        the definition would be wrong in a way that is hard to notice: a new caller
        appears in some *other* file, the definition is untouched, and the stale
        marker keeps reporting a "measured absence" that stopped being true.
        """
        row = self.conn.execute(
            "SELECT content_hash FROM derived_state WHERE path=? AND kind=?",
            (path, f"refs:{symbol}")).fetchone()
        return row is not None and row["content_hash"] == digest

    def mark_symbol_references_resolved(self, path: str, symbol: str,
                                        digest: str) -> None:
        """Record that resolution ran for this symbol against this exact evidence.

        Marked even when resolution found nothing: "no callers" is a result worth
        keeping, and re-deriving it on every call is what would make preflight too
        expensive to call every time.
        """
        with self.conn:
            self._mark_derived(path, f"refs:{symbol}", digest)

    def paths_missing_derived(self, kind: str,
                              paths: list[str] | None = None) -> list[tuple[str, str]]:
        """Indexed files whose ``kind`` has not been materialized for their current content.

        Returns [(path, content_hash), ...]. A file counts as missing when it has no
        derived_state row for the kind, or when that row records a different content hash
        than the file's current one.
        """
        query = ("SELECT f.path AS path, f.content_hash AS content_hash FROM files f "
                 "LEFT JOIN derived_state d ON d.path = f.path AND d.kind = ? "
                 "WHERE (d.content_hash IS NULL OR d.content_hash <> f.content_hash)")
        params: list = [kind]
        if paths is not None:
            if not paths:
                return []
            placeholders = ",".join("?" for _ in paths)
            query += f" AND f.path IN ({placeholders})"
            params.extend(paths)
        return [(r["path"], r["content_hash"])
                for r in self.conn.execute(query, params).fetchall()]

    def remove_file(self, path: str) -> None:
        """A file was deleted -> remove it from the index: symbols + the file record + reference
        edges it emitted (src_path = it) + reference edges pointing at it (def_path = it, to avoid
        leaving stale edges pointing at a deleted definition file) and related index rows.
        """
        changed = 0
        with self.conn:
            changed += self.conn.execute(
                "DELETE FROM symbols WHERE path=?", (path,)).rowcount
            changed += self.conn.execute(
                "DELETE FROM files WHERE path=?", (path,)).rowcount
            changed += self.conn.execute(
                "DELETE FROM refs WHERE src_path=? OR def_path=?", (path, path)).rowcount
            changed += self.conn.execute(
                "DELETE FROM fingerprints WHERE path=?", (path,)).rowcount
            changed += self.conn.execute(
                "DELETE FROM fingerprint_index WHERE path=?", (path,)).rowcount
            changed += self.conn.execute(
                "DELETE FROM comments WHERE path=?", (path,)).rowcount
            self.conn.execute("DELETE FROM derived_state WHERE path=?", (path,))
            if changed:
                self._bump_index_generation()

    # ── Queries ──
    def get_symbols(self, file_path: str | None = None) -> list[dict]:
        """Fetch symbols. Pass file_path to fetch only that file, otherwise fetches the whole project."""
        if file_path is not None:
            rows = self.conn.execute(
                "SELECT path,kind,name,line,end_line,scope FROM symbols "
                "WHERE path=? ORDER BY line", (file_path,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT path,kind,name,line,end_line,scope FROM symbols "
                "ORDER BY path,line"
            ).fetchall()
        return [dict(r) for r in rows]

    def symbol_revision(self) -> tuple[int, int, str]:
        """A cheap revision tied only to the symbols table; a refs update shouldn't invalidate the symbol snapshot."""
        row = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM symbols) AS symbol_count, "
            "COUNT(*) AS file_count, COALESCE(MAX(indexed_at), 0) AS max_indexed "
            "FROM files"
        ).fetchone()
        return (
            int(row["symbol_count"]), int(row["file_count"]),
            format(float(row["max_indexed"]), ".9f"),
        )

    def load_symbol_snapshot(self, revision: tuple | None = None) -> list[dict] | None:
        """Load the JSON cache only when the revision matches; a missing/truncated/corrupt file always returns None and lets SQLite take over."""
        expected = tuple(revision or self.symbol_revision())
        path = symbol_snapshot_path(self.db_file)
        try:
            with open(path, encoding="utf-8") as handle:
                header = json.loads(handle.readline())
                if (header.get("format") != _SYMBOL_SNAPSHOT_FORMAT
                        or tuple(header.get("revision") or ()) != expected):
                    return None
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(payload, list) or len(payload) != expected[0]:
            return None
        return payload

    def find_symbol_definitions(self, name: str) -> list[dict]:
        """Find all definitions of a given name (feeds the first stage of two-stage find-references: coarse candidate filtering)."""
        rows = self.conn.execute(
            "SELECT path,kind,name,line,end_line,scope FROM symbols "
            "WHERE name=? ORDER BY path,line", (name,)
        ).fetchall()
        return [dict(r) for r in rows]

    def all_indexed_files(self) -> list[str]:
        rows = self.conn.execute("SELECT path FROM files ORDER BY path").fetchall()
        return [r["path"] for r in rows]

    # ── Reference edges ──
    def replace_refs_for_symbol(
            self, src_path: str, symbol_name: str, edges: list[dict], *,
            expected_generation: int) -> bool:
        """Replace one source and symbol edge set if the source graph is unchanged.

        The immediate transaction serializes writers before the generation check.
        Deleting only the requested tuple prevents concurrent symbol lookups in the
        same source file from replacing each other's rows.
        """
        rows = []
        for edge in edges:
            if (edge.get("src_path") != src_path
                    or edge.get("symbol_name") != symbol_name):
                raise ValueError(
                    "reference edge does not match its source and symbol scope"
                )
            rows.append((
                src_path,
                edge["src_line"],
                symbol_name,
                edge.get("def_path"),
                edge.get("def_line"),
                edge["confidence"],
            ))

        if self.conn.in_transaction:
            raise RuntimeError(
                "replace_refs_for_symbol requires an idle database connection"
            )
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            if self.index_generation() != int(expected_generation):
                self.conn.rollback()
                return False
            self.conn.execute(
                "DELETE FROM refs WHERE src_path=? AND symbol_name=?",
                (src_path, symbol_name),
            )
            self.conn.executemany(
                "INSERT INTO refs(src_path,src_line,symbol_name,def_path,def_line,confidence) "
                "VALUES(?,?,?,?,?,?)",
                rows,
            )
        except BaseException:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()
            return True

    def replace_refs_for(self, src_path: str, edges: list[dict]) -> None:
        """Persist the reference edges a file emits (clear the file's old edges first, then write, to keep a single source of truth)."""
        self.conn.execute("DELETE FROM refs WHERE src_path=?", (src_path,))
        self.conn.executemany(
            "INSERT INTO refs(src_path,src_line,symbol_name,def_path,def_line,confidence) "
            "VALUES(?,?,?,?,?,?)",
            [(e["src_path"], e["src_line"], e["symbol_name"],
              e.get("def_path"), e.get("def_line"), e["confidence"]) for e in edges],
        )
        self.conn.commit()

    def all_refs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT src_path,src_line,symbol_name,def_path,def_line,confidence FROM refs"
        ).fetchall()
        return [dict(r) for r in rows]

    def traverse_call_graph(self, symbol: str, def_path: str, *, direction: str,
                            max_hops: int = 5) -> list[dict]:
        """Run a recursive CTE over the persisted refs edges to compute the transitive call chain (call hierarchy, absorbed from competitor backlog item 1).

        The refs table is itself a set of directed edges (line X of file `src` references symbol
        Y defined in file `def`). Using the symbols table's [line, end_line] range, a "reference
        site src_line" maps to "the symbol that contains it (the caller)", and a "symbol's body
        range" maps to "the references inside it (the callees)", and together these form the call
        chain.

        direction='up'   finds callers: who (transitively) calls this symbol.
        direction='down' finds callees: what this symbol (transitively) calls.
        max_hops caps depth (CTE depth < max_hops) to prevent infinite recursion on a call cycle;
        UNION dedupes rows.
        Confidence propagation: if any edge along a chain has confidence='low', that path is
        downgraded to low; a node's confidence is "does at least one all-high path exist to it".

        Returns [{name, path, line, depth, confidence}], with distinct nodes keeping their
        minimum depth.
        An empty refs table (find_references was never run to build edges) -> returns []
        (the caller's note should prompt building edges first).
        """
        def_path = os.path.abspath(def_path)
        if direction == "up":
            # Recursion: who references the current symbol (r.symbol_name=c.name and
            # r.def_path=c.path pin down this exact definition) -> which symbol's body
            # does the reference site src_line fall inside = the caller
            join = ("JOIN refs r ON r.symbol_name = c.name AND r.def_path = c.path "
                    "JOIN symbols s ON s.path = r.src_path "
                    "AND s.line <= r.src_line AND r.src_line <= s.end_line")
        elif direction == "down":
            # Recursion: references inside the current symbol's body range (src falls within
            # c's [line, end_line]) -> the referenced symbol's definition = the callee
            join = ("JOIN refs r ON r.src_path = c.path "
                    "AND r.src_line >= c.line AND r.src_line <= c.end_line "
                    "JOIN symbols s ON s.path = r.def_path AND s.name = r.symbol_name")
        else:
            raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")

        cte = f"""
        WITH RECURSIVE chain(name, path, line, end_line, depth, min_conf) AS (
            SELECT name, path, line, end_line, 0, 'high'
            FROM symbols WHERE name = ? AND path = ?
            UNION
            SELECT s.name, s.path, s.line, s.end_line, c.depth + 1,
                   CASE WHEN r.confidence = 'low' OR c.min_conf = 'low'
                        THEN 'low' ELSE 'high' END
            FROM chain c
            {join}
            WHERE c.depth < ? AND NOT (s.name = c.name AND s.path = c.path)
        )
        SELECT name, path, MIN(line) AS line, MIN(depth) AS depth,
               MAX(CASE WHEN min_conf = 'high' THEN 1 ELSE 0 END) AS has_high_path
        FROM chain WHERE depth > 0
        GROUP BY name, path
        ORDER BY depth, name
        """
        rows = self.conn.execute(cte, (symbol, def_path, max_hops)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["confidence"] = "high" if d.pop("has_high_path") else "low"
            out.append(d)
        return out

    # ── Stats (for status / panel use) ──
    def stats(self, *, deadline: float | None = None) -> dict:
        """Return project counts, interrupting SQLite when a deadline expires."""
        c = self.conn
        handler_installed = deadline is not None

        def deadline_expired() -> bool:
            return deadline is not None and time.monotonic() >= deadline

        def scalar(query: str):
            if deadline_expired():
                raise sqlite3.OperationalError(
                    "status stats interrupted by deadline")
            return c.execute(query).fetchone()[0]

        if handler_installed:
            c.set_progress_handler(lambda: int(deadline_expired()), 1000)
        try:
            n_files = scalar("SELECT COUNT(*) FROM files")
            n_symbols = scalar("SELECT COUNT(*) FROM symbols")
            n_refs = scalar("SELECT COUNT(*) FROM refs")
            # Keep stats to cheap COUNT queries. Duplicate groups require aggregation and
            # would slow down every dashboard refresh.
            n_fingerprints = scalar("SELECT COUNT(*) FROM fingerprints")
            n_comments = scalar("SELECT COUNT(*) FROM comments")
            last_indexed = scalar("SELECT MAX(indexed_at) FROM files")
            result = {
                "project_key": self.project_key,
                "repo_path": self.repo_path,
                "db_file": str(self.db_file),
                "indexed_files": n_files,
                "symbols": n_symbols,
                "refs": n_refs,
                "fingerprints": n_fingerprints,
                "comments": n_comments,
                "last_indexed_at": last_indexed,
                "schema_version": int(self.get_meta("schema_version", "0")),
                "indexed_git_sha": self.get_meta("git_head_sha"),
            }
            if deadline_expired():
                raise sqlite3.OperationalError(
                    "status stats interrupted by deadline")
            return result
        finally:
            if handler_installed:
                c.set_progress_handler(None, 0)


def list_indexed_projects() -> list[dict]:
    """Scan the database directory for every `*.db` and reverse-look-up each one's repo_path (meta table) + stats.

    Backs the panel's "list all locally indexed projects" feature. This is the sole source of
    that data. Mirror image of ProjectStore.open: that path computes the database file from
    repo_path; this path reads repo_path back from the database file.
    A broken database (unreadable / missing tables) is skipped and flagged with an error, so one
    bad database doesn't blow up the whole listing (fail-soft for listing; fail-loud is reserved
    for single-project operations).
    """
    db_dir = default_db_dir()
    out: list[dict] = []
    if not db_dir.is_dir():
        return out
    for db_file in sorted(db_dir.glob("*.db")):
        try:
            # closing: also covers connect() so an exception from setting row_factory still
            # guarantees close() (on Windows, an unclosed connection locks the .db file handle
            # and blocks a later reindex/delete).
            # The overview is a read-only operation. Applying the normal writer
            # PRAGMAs here attempts to switch journal mode and can block behind an
            # active indexer for minutes even though the COUNT queries are cheap.
            with cache_lease.acquire_shared(
                    db_file.stem, home=db_dir):
                uri = db_file.resolve().as_uri() + "?mode=ro"
                with closing(sqlite3.connect(
                        uri, uri=True, timeout=1.0)) as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA busy_timeout=1000")
                    conn.execute("PRAGMA query_only=1")
                    row = conn.execute(
                        "SELECT value FROM meta WHERE key='repo_path'"
                    ).fetchone()
                    repo_path = row["value"] if row else None
                    n_files = conn.execute(
                        "SELECT COUNT(*) FROM files").fetchone()[0]
                    n_symbols = conn.execute(
                        "SELECT COUNT(*) FROM symbols").fetchone()[0]
                    n_refs = conn.execute(
                        "SELECT COUNT(*) FROM refs").fetchone()[0]
                    last_indexed = conn.execute(
                        "SELECT MAX(indexed_at) FROM files"
                    ).fetchone()[0]
            out.append({
                "project_key": db_file.stem,
                "repo_path": repo_path,
                "db_file": str(db_file),
                "indexed_files": n_files,
                "symbols": n_symbols,
                "refs": n_refs,
                "last_indexed_at": last_indexed,
                # Whether the repo path still exists (lets a hand-off agent see at a glance which
                # databases correspond to projects that have been moved or deleted).
                "path_exists": bool(repo_path and os.path.isdir(repo_path)),
            })
        except Exception as exc:
            # Fail-soft at the listing layer: any database read error (sqlite / OSError /
            # permissions / non-.db directory) just skips that database and flags an error,
            # instead of one bad database blowing up all of /projects (fail-loud is reserved
            # for single-project operations).
            out.append({
                "project_key": db_file.stem,
                "db_file": str(db_file),
                "error": f"Failed to read database: {exc}",
            })
    return out
