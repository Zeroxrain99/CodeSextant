"""索引存儲模組 — SQLite 落盤 + content hash 增量 + 專案隔離。

設計來源（PoC 已坐實）：
  - 每專案一個 SQLite 庫，project_key = sha1(repo 絕對路徑)（不混線）。
  - 用檔案 content hash(sha256) 當失效 key：改一檔只重算一檔，其餘 cache hit 跳過。

職責（單一）：管一個專案的 SQLite 庫——開庫、建表、查/寫檔案 hash、
存/取符號、存/取引用邊、給統計。不碰 tree-sitter、不碰 jedi。

預設庫位置：~/.codesextant/<project_key>.db（對齊設計文件 §3③）。
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

# 庫的綱要版本（schema 改了就 +1，未來可據此做遷移）
# ⚠ 遷移機制誠實（設計 §⑦）：open() 跑 executescript(CREATE TABLE IF NOT EXISTS) 冪等補表
# ＋ _ensure_columns() 純加欄 migration hook（CREATE TABLE IF NOT EXISTS 對既有表不會加欄）。
# 無條件覆寫 meta.schema_version——version 號僅 stats 回報、**不 gate 任何遷移**。對「加表/加欄」安全；
# 若未來改欄型別/刪欄（非加）仍需另寫 migration。
SCHEMA_VERSION = 4  # v4：symbols map 覆蓋索引；v3=fingerprints cognitive；v2=功能 B 三表
_SYMBOL_SNAPSHOT_FORMAT = 1
_MAP_SNAPSHOT_FORMAT = 1


def project_key(repo_path: str) -> str:
    """專案隔離鍵 = sha1(repo 絕對路徑)。

    用絕對路徑（normalize 過）算，確保同一專案不管用什麼相對路徑進來
    都對應同一把 key、同一個庫。
    """
    abs_path = os.path.normcase(os.path.abspath(repo_path))
    return hashlib.sha1(abs_path.encode("utf-8")).hexdigest()


def default_db_dir() -> Path:
    """預設庫目錄 ~/.codesextant/。可用環境變數 CODESEXTANT_HOME 覆寫（方便測試隔離）。"""
    home = os.environ.get("CODESEXTANT_HOME")
    base = Path(home) if home else (Path.home() / ".codesextant")
    return base


def db_path_for(repo_path: str) -> Path:
    """某專案對應的 SQLite 庫檔路徑。"""
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


def apply_connection_pragmas(conn: sqlite3.Connection) -> None:
    """設定讓「多讀者 + 單寫者」能共存的連線層 PRAGMA。

    整台機器所有 AI 代理共用同一個 daemon，未來還會加唯讀工人子進程；預設的
    rollback journal 會讓寫入者在 commit 時把所有讀者擋在門外。WAL（預寫日誌）
    改成寫入者寫側檔、讀者續讀最後一份已提交快照，兩邊不互卡。

    三個開關（皆走 env，對齊 L0 鐵律 #6）：
      CODESEXTANT_SQLITE_WAL=0             → 退回舊 rollback journal
      CODESEXTANT_SQLITE_BUSY_TIMEOUT_MS   → 忙碌時退讓上限（預設 5000ms）
      CODESEXTANT_SQLITE_SYNC_NORMAL=0     → 退回 synchronous=FULL

    synchronous=NORMAL 在 WAL 下對「程式崩潰」仍安全，只在斷電時可能丟掉最後
    幾筆交易；本庫是可重建的索引快取（SQLite 是索引的 SSOT，但索引本身能由原始碼
    重建），故以寫入速度優先。
    """
    busy_ms = max(0, _env_int("CODESEXTANT_SQLITE_BUSY_TIMEOUT_MS", 5000))
    conn.execute(f"PRAGMA busy_timeout={busy_ms}")
    if _env_flag("CODESEXTANT_SQLITE_WAL", True):
        # 失敗不致命（例如庫放在不支援 WAL 的網路磁碟）：保持既有 journal 續跑。
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
    if _env_flag("CODESEXTANT_SQLITE_SYNC_NORMAL", True):
        conn.execute("PRAGMA synchronous=NORMAL")


def symbol_snapshot_path(db_file: str | Path) -> Path:
    """map 專用符號快照（cache，不是真相源）；revision 不合就完全忽略。"""
    return Path(f"{db_file}.symbols-v{_SYMBOL_SNAPSHOT_FORMAT}.json")


def write_symbol_snapshot(db_file: str | Path, revision: tuple,
                          symbols: list[dict]) -> Path:
    """原子寫 UTF-8 JSON 快照；不用 pickle，磁碟內容不可執行任意 Python。"""
    target = symbol_snapshot_path(db_file)
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
    """每專案只留最近一次參數組合的完整 map 小結果；daemon LRU 才保多組。"""
    return Path(f"{db_file}.map-v{_MAP_SNAPSHOT_FORMAT}.json")


def write_map_snapshot(db_file: str | Path, key_digest: str,
                       result: dict) -> Path:
    """原子寫 revision/參數 digest 綁定的 map JSON；索引或 env 一變即不命中。"""
    target = map_snapshot_path(db_file)
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
    """只在 digest 完全相符時回 map；損壞／舊 revision fail-soft 到重算。"""
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
    """檔案內容 sha256（增量的失效 key）。"""
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
-- get_map 熱路徑：涵蓋 SELECT 六欄且直接滿足 ORDER BY path,line，避免大型 DB 回表 + temp sort。
CREATE INDEX IF NOT EXISTS idx_symbols_map
ON symbols(path,line,kind,name,end_line,scope);

-- 引用邊：哪個檔的哪行用到了某個被定義的符號（供找引用結果落盤 + PageRank 建圖）
CREATE TABLE IF NOT EXISTS refs (
    src_path    TEXT NOT NULL,   -- 引用發生在哪個檔（呼叫端）
    src_line    INTEGER NOT NULL,
    symbol_name TEXT NOT NULL,   -- 被引用的符號名
    def_path    TEXT,            -- jedi 解析出的定義所在檔（None=未解析）
    def_line    INTEGER,
    confidence  TEXT NOT NULL    -- "high"(resolved-import) / "low"(name-match)
);
CREATE INDEX IF NOT EXISTS idx_refs_symbol ON refs(symbol_name);
CREATE INDEX IF NOT EXISTS idx_refs_def ON refs(def_path);

-- 功能 B 重複偵測：每個可執行單元（function/method）的結構指紋（設計 §3.A.4）。
-- shape_hash=正規化 AST 形狀(抹 ID/LIT、保留控制流結構)；raw_token_hash=未正規化原始 token
-- (只有它也相同才配 EXACT_DUP)；call_hash=呼叫名集合。GROUP BY shape_hash 一句 SQL 找重複群＝O(n)。
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
    cognitive        INTEGER,            -- P3 D3 認知複雜度（高信心語言 int / 其餘語言 NULL=UNKNOWN）
    FOREIGN KEY(path) REFERENCES files(path)
);
CREATE INDEX IF NOT EXISTS idx_fp_shape ON fingerprints(shape_hash);
CREATE INDEX IF NOT EXISTS idx_fp_call  ON fingerprints(call_hash);
CREATE INDEX IF NOT EXISTS idx_fp_path  ON fingerprints(path);

-- 功能 B：winnowing k-gram 指紋倒排索引（抓 Type-3 近似重複）。fp_value→{符號,行}，同指紋才比對。
CREATE TABLE IF NOT EXISTS fingerprint_index (
    path     TEXT NOT NULL,
    line     INTEGER,
    fp_value INTEGER,
    FOREIGN KEY(path) REFERENCES files(path)
);
CREATE INDEX IF NOT EXISTS idx_fpidx_val  ON fingerprint_index(fp_value);
CREATE INDEX IF NOT EXISTS idx_fpidx_path ON fingerprint_index(path);

-- 功能 B 註解管理：每個 comment 節點 + 行號 + 歸屬符號（設計 §3.B.3）。
-- is_doc=1＝docstring(owner_line 指所屬符號定義行，覆蓋率 JOIN 用)；tag=TODO/FIXME 標記(無則 NULL)。
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
"""


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """既有庫加欄位的 migration hook（CREATE TABLE IF NOT EXISTS 不會對既有表加欄）。

    純加欄、冪等、可逆（ALTER ADD COLUMN 不破壞既有列、新欄預設 NULL）。改欄型別/刪欄不在此列。
    """
    expected = {
        "fingerprints": [("cognitive", "INTEGER")],  # P3 D3：高信心語言 int / 其餘 NULL
    }
    for table, cols in expected.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, decl in cols:
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


class ProjectStore:
    """一個專案的 SQLite 索引庫門面。

    用法：
        store = ProjectStore.open(repo_path)
        try:
            ...
        finally:
            store.close()
    或當 context manager：`with ProjectStore.open(repo) as store: ...`
    """

    def __init__(self, conn: sqlite3.Connection, repo_path: str, db_file: Path,
                 read_only: bool = False):
        self.conn = conn
        self.repo_path = os.path.abspath(repo_path)
        self.project_key = project_key(repo_path)
        self.db_file = db_file
        self.read_only = read_only

    # ── 開 / 關 ──
    @classmethod
    def open_readonly(cls, repo_path: str) -> ProjectStore:
        """開一個「保證不會寫」的連線 —— 給查詢用的工人進程／唯讀端點。

        為何需要它：`open()` 每次開啟都會寫（executescript 建表、補欄、寫兩筆
        meta、commit）。那對唯一寫者是對的，但查詢端不該走寫入路徑，未來的工人
        子進程更不該有能力弄壞索引。

        為何用 `PRAGMA query_only` 而不是 SQLite 的 `mode=ro` URI：WAL 模式的庫
        需要建立 `-shm` 共享記憶體索引檔才能讀，而 `mode=ro` 連線沒權限建它，
        在沒有其他連線同時開著時會直接開不起來。`query_only` 沒這個問題，且一樣
        會讓任何寫入拋 OperationalError。

        ⚠ 誠實邊界：這是「防手滑」不是「防惡意」——同一個連線仍可執行
        `PRAGMA query_only=0` 解除。真正的隔離邊界是進程，不是這個 PRAGMA。

        庫不存在時拋 FileNotFoundError（而非默默建一個空庫，那會讓「尚未索引」
        的錯誤被吞掉、變成查到空結果）。
        """
        db_file = db_path_for(repo_path)
        if not db_file.exists():
            raise FileNotFoundError(
                f"CodeSextant：專案尚未索引，無唯讀庫可開（{db_file}）")
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        busy_ms = max(0, _env_int("CODESEXTANT_SQLITE_BUSY_TIMEOUT_MS", 30000))
        conn.execute(f"PRAGMA busy_timeout={busy_ms}")
        conn.execute("PRAGMA query_only=1")
        return cls(conn, repo_path, db_file, read_only=True)

    @classmethod
    def open(cls, repo_path: str) -> ProjectStore:
        """開（或建）某專案的庫。庫目錄不存在會自動建。"""
        db_file = db_path_for(repo_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        apply_connection_pragmas(conn)
        conn.executescript(_SCHEMA)
        _ensure_columns(conn)  # 既有庫補新欄（migration hook）
        store = cls(conn, repo_path, db_file)
        store._set_meta("schema_version", str(SCHEMA_VERSION))
        store._set_meta("repo_path", store.repo_path)
        conn.commit()
        return store

    def close(self) -> None:
        self.conn.close()

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
        """坑6：記錄本次索引時 repo 的 git HEAD sha（freshness 比對用）。"""
        self._set_meta("git_head_sha", sha)
        self.conn.commit()

    # ── 增量核心：判斷某檔要不要重算 ──
    def needs_reindex(self, path: str, current_hash: str) -> bool:
        """content hash 變了（或庫裡沒這檔）→ 要重算。"""
        row = self.conn.execute(
            "SELECT content_hash FROM files WHERE path=?", (path,)
        ).fetchone()
        return (row is None) or (row["content_hash"] != current_hash)

    def store_file_symbols(self, path: str, content_hash: str, symbols: list[dict],
                           indexed_at: float) -> None:
        """重算後落盤：清掉該檔舊符號，寫入新符號，更新 hash。整批一個 transaction。"""
        cur = self.conn
        cur.execute("DELETE FROM symbols WHERE path=?", (path,))
        cur.executemany(
            "INSERT INTO symbols(path,kind,name,line,end_line,scope) "
            "VALUES(?,?,?,?,?,?)",
            [(path, s["kind"], s["name"], s["line"], s["end_line"], s.get("scope", ""))
             for s in symbols],
        )
        cur.execute(
            "INSERT INTO files(path,content_hash,indexed_at) VALUES(?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "content_hash=excluded.content_hash, indexed_at=excluded.indexed_at",
            (path, content_hash, indexed_at),
        )
        cur.commit()

    def store_file_fingerprints(self, path: str, fingerprints: list[dict],
                                winnow_index: list[dict]) -> None:
        """功能 B：落盤某檔的結構指紋 + winnowing 倒排（先清該檔舊的再寫，保持單一真相）。

        content_hash 由 store_file_symbols 管（index_project 同一逐檔迴圈內先抽符號），此處不碰
        files 表——增量天然複用 needs_reindex（content hash 沒變整檔 skip，指紋也不重算）。
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
        cur.commit()

    def store_file_comments(self, path: str, comments: list[dict]) -> None:
        """功能 B：落盤某檔的註解（先清該檔舊的再寫）。content_hash 同上由 store_file_symbols 管。"""
        cur = self.conn
        cur.execute("DELETE FROM comments WHERE path=?", (path,))
        cur.executemany(
            "INSERT INTO comments(path,line,end_line,kind,is_doc,tag,scope,owner_line,text) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            [(path, c.get("line"), c.get("end_line", c.get("line")), c.get("kind", "line"),
              1 if c.get("is_doc") else 0, c.get("tag"), c.get("scope", ""),
              c.get("owner_line"), c.get("text", "")) for c in comments],
        )
        cur.commit()

    def remove_file(self, path: str) -> None:
        """檔被刪了 → 從索引移除：符號 + 檔記錄 + 它發出的引用邊（src_path=它）
        + 指向它的引用邊（def_path=它，避免留下指向已刪定義檔的 stale 邊）+ 功能 B 三表。
        """
        self.conn.execute("DELETE FROM symbols WHERE path=?", (path,))
        self.conn.execute("DELETE FROM files WHERE path=?", (path,))
        self.conn.execute("DELETE FROM refs WHERE src_path=? OR def_path=?", (path, path))
        self.conn.execute("DELETE FROM fingerprints WHERE path=?", (path,))
        self.conn.execute("DELETE FROM fingerprint_index WHERE path=?", (path,))
        self.conn.execute("DELETE FROM comments WHERE path=?", (path,))
        self.conn.commit()

    # ── 查詢 ──
    def get_symbols(self, file_path: str | None = None) -> list[dict]:
        """取符號。給 file_path 只取該檔，否則取全專案。"""
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
        """只綁 symbols 真相的便宜 revision；refs 更新不必讓符號快照失效。"""
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
        """revision 相符才載 JSON cache；缺檔/截斷/損壞一律回 None 讓 SQLite 接手。"""
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
        """找某名稱的所有定義（給找引用的二段式第一段——粗篩候選用）。"""
        rows = self.conn.execute(
            "SELECT path,kind,name,line,end_line,scope FROM symbols "
            "WHERE name=? ORDER BY path,line", (name,)
        ).fetchall()
        return [dict(r) for r in rows]

    def all_indexed_files(self) -> list[str]:
        rows = self.conn.execute("SELECT path FROM files ORDER BY path").fetchall()
        return [r["path"] for r in rows]

    # ── 引用邊 ──
    def replace_refs_for(self, src_path: str, edges: list[dict]) -> None:
        """落盤某檔發出的引用邊（先清該檔的舊邊再寫，保持單一真相）。"""
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
        """在落盤 refs 邊上跑遞迴 CTE 算傳遞呼叫鏈（call hierarchy，競品吸收 queue 1）。

        refs 表本身就是有向邊集合（src 檔某行引用了 def 檔的某符號）。靠 symbols 表的
        [line,end_line] 範圍，把「引用點 src_line」映射到「包含它的符號（caller）」、把
        「符號 body 範圍」映射到「內部引用（callee）」，即成呼叫鏈。

        direction='up'   找 callers：誰（傳遞地）呼叫此符號。
        direction='down' 找 callees：此符號（傳遞地）呼叫誰。
        max_hops 限深度（CTE depth<max_hops）防呼叫環無限遞迴；UNION 去重 row。
        信心傳播：鏈中任一邊 confidence='low' 則該路徑降 low；節點取「是否存在全 high 路徑」。

        回 [{name, path, line, depth, confidence}]，DISTINCT 節點取最小 depth。
        refs 表為空（沒跑過 find_references 建邊）→ 回 []（呼叫端 note 提示先建邊）。
        """
        def_path = os.path.abspath(def_path)
        if direction == "up":
            # 遞迴：誰引用了當前符號（r.symbol_name=c.name 且 r.def_path=c.path 鎖定此定義）→
            # 引用點 src_line 落在哪個符號 body = caller
            join = ("JOIN refs r ON r.symbol_name = c.name AND r.def_path = c.path "
                    "JOIN symbols s ON s.path = r.src_path "
                    "AND s.line <= r.src_line AND r.src_line <= s.end_line")
        elif direction == "down":
            # 遞迴：當前符號 body 範圍內的引用（src 在 c 的 [line,end_line]）→ 被引用符號定義 = callee
            join = ("JOIN refs r ON r.src_path = c.path "
                    "AND r.src_line >= c.line AND r.src_line <= c.end_line "
                    "JOIN symbols s ON s.path = r.def_path AND s.name = r.symbol_name")
        else:
            raise ValueError(f"direction 必須是 'up' 或 'down'，收到 {direction!r}")

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

    # ── 統計（給 status / 面板用） ──
    def stats(self) -> dict:
        c = self.conn
        n_files = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        n_symbols = c.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        n_refs = c.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
        # 功能 B：便宜的 COUNT(*) 放 stats；⛔ dup_groups（要 GROUP BY shape_hash HAVING）
        # 絕不放 stats（設計 FIX-4 lens-3：那不是一行 COUNT，會拖慢每次面板渲染）。
        n_fingerprints = c.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
        n_comments = c.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        last_indexed = c.execute("SELECT MAX(indexed_at) FROM files").fetchone()[0]
        return {
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
            "indexed_git_sha": self.get_meta("git_head_sha"),  # 坑6：索引時的 sha
        }


def list_indexed_projects() -> list[dict]:
    """掃庫目錄下所有 `*.db`，反查各自的 repo_path（meta 表）＋統計。

    給中文面板「列出本機所有已索引專案」用——這是唯一資料來源。
    與 ProjectStore.open 相反：那邊由 repo_path 算出庫檔，這邊由庫檔讀回 repo_path。
    壞庫（讀不了 / 缺表）跳過並標 error，不讓單一壞庫炸掉整個列舉（fail-soft 列舉、
    fail-loud 留給單專案操作）。
    """
    db_dir = default_db_dir()
    out: list[dict] = []
    if not db_dir.is_dir():
        return out
    for db_file in sorted(db_dir.glob("*.db")):
        try:
            # closing：connect 也納入保護，row_factory 設定若拋例外也保證 close
            # （Windows 上未 close 的連線會鎖住 .db 檔 handle，擋後續 reindex/刪庫）。
            with closing(sqlite3.connect(str(db_file))) as conn:
                conn.row_factory = sqlite3.Row
                apply_connection_pragmas(conn)
                row = conn.execute(
                    "SELECT value FROM meta WHERE key='repo_path'"
                ).fetchone()
                repo_path = row["value"] if row else None
                n_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
                n_symbols = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
                n_refs = conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
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
                # repo 路徑是否還在（接手代理一眼看出哪些庫對應已搬走/刪掉的專案）
                "path_exists": bool(repo_path and os.path.isdir(repo_path)),
            })
        except Exception as exc:
            # 列舉層 fail-soft：任何讀庫錯誤（sqlite / OSError / 權限 / 非 .db 目錄）
            # 都只跳過該庫並標 error，不讓單一壞庫炸掉整個 /projects（fail-loud 留給單專案操作）。
            out.append({
                "project_key": db_file.stem,
                "db_file": str(db_file),
                "error": f"讀庫失敗: {exc}",
            })
    return out
