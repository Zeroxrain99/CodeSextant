---
tier: 全文
type: 專案交接（三層交接之全文層）
喚起詞: 交接 CodeSextant / 交接 codesextant
status: active
updated: 2026-07-24
last_updated: 2026-07-24
verified: 2026-07-24（HEAD 731217c；tools/oracle_snapshot.py 與 tools/public_operation_oracle.py --verify 皆 exit 0；worktree porcelain 空）
最後壓縮整理: 2026-07-24（Claude 接手核對 git ground truth，發現交接落後 ~14 commit；重建當前戰線 §-6，壓縮已解事故 §1/舊 CHECKPOINT 到 git-log 指針）
設計SSOT: E:\ai-king\_AI_BRAIN\05_Planning\CodeSextant_自創代碼地圖神器_設計_2026-06-18.md
版本控制: ⭐ 2026-07-19 起有獨立 git（項目資料/ 被外層 ignore，不影響外層）。逐版史用 git log 查，⛔別再往本檔塞
---

# 交接 CodeSextant

## -6. ⭐ 2026-07-24 SOTA gate — native-kernel Task 2 完成（HEAD 731217c，下一步 native Task 3）

### §0 計畫路徑索引

- 設計 SSOT：`E:\ai-king\項目資料\CodeSextant\docs\superpowers\specs\2026-07-23-sota-open-source-release-gate-design.md`
- 計畫檔（同目錄 `docs/superpowers/plans/`）：
  - `2026-07-23-codesextant-g0-g1-foundation.md`（G0-G1，Task 1-9 全綠）
  - `2026-07-23-codesextant-g2-g3-quality-contracts.md`（quality Task 1-11）
  - `2026-07-23-codesextant-g2-native-kernel-adapters.md`（native-kernel Task 1-12）← **當前戰線**
  - `2026-07-23-codesextant-g4-public-benchmark.md` … `g7-g8-publication-application.md`
- 執行 worktree：`E:\ai-king\項目資料\CodeSextant\.worktrees\codesextant-sota-gate`
- 執行分支：`codex/codesextant-sota-gate`（此線由 **Codex + superpowers `subagent-driven-development`** 驅動；Claude 接手時只當指揮官/驗收，實作照原 sub-skill 節奏）

### 狀態總覽（⛔ 進度權威＝git commit + clean worktree + oracle verifier 綠，非本檔文字、非 plan checkbox）

- `master` 只收本交接 checkpoint；產品實作全在上述 worktree 隔離分支。
- ⚠ plan Markdown checkbox 全空（0 checked / 665 unchecked 是假象，非進度）。commit↔task 以各 task 的 `Invoke-ExactTaskCommit -Message` 字串比對確認。
- **當前 HEAD＝`731217c test(oracle): freeze all public operation outputs`＝native-kernel Task 2 完成；worktree 乾淨。**
- 跨越序（interlock：G0/G1 → quality T1-3 → native T1 → quality T4 → quality T5-9 → **native T2-12** → 回 quality T10-11）：
  - **G0-G1 Task 1-9**：`…a6ff73a`（foundation；`verify_g0.py`/`verify_g1.py` 綠。逐 task 摘要見 git log 與 `docs/.../g0-g1-foundation.md`）
  - **quality T1**＝`158c10b`（schema v5 source-class 分類）｜**T2**＝`7cb4f6a`（deterministic explainable ranking）｜**T3**＝`d70415f`（凍結 public Python + command registry）
  - **native T1**＝`7217766`（18 個 public-operation oracle adapters + 語料）
  - **quality T4**＝`fcb5d9e`（refresh base oracle；後因 harness evidence-invariant 修正，於 `fb16925` 重跑一次）
  - **quality T5**＝`9876220`+`1537dd4`（non-vacuous self-map 品質閘）｜**T6**＝`304c457`（完整 8-crate Rust workspace）｜**T7**＝`66233be`（從 operations.yaml 生 protocol/error 契約）｜**T8**＝`885c84e`（canonical envelopes + QueryService 邊界）｜**T9**＝`5fd3d5d`（thin CLI/MCP/HTTP adapters）
  - oracle harness 修正：`9318a47`（no-side-effect check 限縮 isolated run）+ `b272527`（evidence-commit invariant 允許 manifest+changed-golden subset）
  - **native T2**＝`731217c`（凍結 18-operation public oracle：manifest fmt v2 + golden，evidence-only）← **HEAD**
- 綠證（本 session 2026-07-24 於同一乾淨 HEAD 實測）：`tools/oracle_snapshot.py --verify` exit 0、`tools/public_operation_oracle.py --verify` exit 0、`git status --porcelain` 空。
- production daemon 未動：`127.0.0.1:8790/health`＝engine `0.16.0`、status ok、單一 listener（pid 20028）。
- 8-crate Rust workspace（`.worktrees/codesextant-sota-gate/crates/`）：codesextant-core / -parser / -store / -protocol / -sidecar-protocol / -daemon / -cli / -mcp（＋ root `Cargo.toml`、`xtask/`）。`spec/operations.yaml`（23,967B）＝18-operation 唯一權威。

### 鐵律／未解決

- ⛔ 不在 `master` 實作產品碼；G2-G3 / native 全在 worktree。
- ⛔ Python 0.16.0 仍是 production oracle；Rust parity 完成前**不切換 production daemon**（不因測試/交接重啟；磁碟最新碼 ≠ 已部署，且 At-logon 自啟＝重開機就部署最新碼，高風險改動落盤前先想這點）。
- ⛔ quality T4 base freeze + native T2 public freeze 後：**不得再編輯任何 oracle-bound 路徑**（Python product / parity adapter / harness / oracle corpus/fixture / generator / 已凍 manifest+golden）。native T3+ 只加 Rust crate 碼與其 test，不碰凍結面。
- ⛔ 每個 implementation commit 用 `Invoke-ExactTaskCommit`（dot-source `tools/exact_task_commit.ps1`；僅 A/M、拒 D/R/C/T/重複/多檔/index mutation）。Cargo manifest 改動走**單一 lockfile window**：`cargo generate-lockfile` 一次 → 檢視完整 lock diff → 之後全走 `--locked`。
- ⛔ G0-G7 全綠 + 獨立驗證 + user 明確授權前：不建公開 repo、不發布 package/release、不宣稱 SOTA、不送 Claude for Open Source。
- ⛔ 不讀/不複製競品 implementation source；研究邊界＝公開文件 / 論文 / issue / benchmark protocol / documented interface。
- Rust 工具鏈：官方 rustup 鎖 `1.96.0` minimal（含 rustfmt/clippy）；Cargo 不在全域 PATH，可靠入口 `C:\Users\zerox\.cargo\bin\cargo.exe`。
- ⚠ 環境復原記錄：CodeSextant wrapper 曾遺失，已從 `E:\ai-king\ai-king-share\CodeSextant_v0.15.0_friend.zip` 機械還原至兩份 Skill scripts，SHA-256＝`8FAB4BEDBB574C520C15CBB90F8D65781CE54AE828AE42BF253013F55E4152A9`（只還原 wrapper，未複製任何 archived 產品碼進 repo）。

### next_step — native-kernel Task 3：Implement native deterministic discovery and classification parity

計畫：native plan 行 326-395。從乾淨 `731217c` 起，subagent-driven TDD：

1. **Step 1 先寫紅測**：`crates/codesextant-core/tests/discovery_parity.rs`（Python vs Rust discovery 比：normalized relative path / source class / classification rule ID / public API evidence / file length / content BLAKE3 / deterministic ordinal）＋ `discovery_security.rs`（traversal escape、symlink escape+loop、junction/file-ID/大小寫/Unicode alias、state-root（CODESEXTANT_HOME/DB/WAL/SHM/spill/snapshot）強制排除且 `!` 不可 reinclude、parent/symlinked/swap-after-load policy fail-closed、barrier swap 只允許「完整舊 revision 或 hash 一致新 revision」、byte-budget high-water、cancellation）。Step 2 跑紅確認 FAIL（native discovery 未存在）。
2. **Step 3 實作單一 no-follow directory-handle walker**：⛔禁 `ignore::WalkBuilder`/`walkdir`/任何 path-based recursive；本機 win32 → 走既有 **windows-sys** directory-handle 枚舉 + reparse rejection + file-identity（POSIX 才用 rustix openat）。in-scope policy 只用 `ignore::gitignore::GitignoreBuilder::add_line` 編譯**已捕捉的行**、ignore crate 不自行 walk/開 policy 檔；classification 重現 quality T1（`codesextant/source_class.py`）Python 精度、證據不足回 `unknown`；兩階段 producer/consumer + weighted byte semaphore + bounded channel + content-addressed spill；BLAKE3 discovery digest（policy blob tuples + 長度前綴 normalized path/class/blob-len/hash，ordinal 序）。
3. **Step 4 跑 parity 兩次**同 digest 全綠。**Step 5 exact commit** 檔案清單：`Cargo.toml`/`Cargo.lock`/`crates/codesextant-core/Cargo.toml`/`src/{discovery,ignore_policy,source_class,path}.rs`/`src/lib.rs`/`tests/{discovery_parity,discovery_security}.rs`；message＝`feat(core): add deterministic native discovery`。
4. 依賴：root Cargo.toml 只加 `ignore` / `blake3` / POSIX-only `rustix`（authority table：native plan 行 86-120，全 `=` pin，crate 內 `workspace = true` 無 local feature）。
5. Task 3 綠仍非公開 / 發布 / SOTA 宣稱 / Claude for Open Source 授權。

## -4. ⭐ 2026-07-19 獨立產品化 + 技術債棘輪（5 commit·438 測試綠）

**起因**：user「concinno 用詞全拿掉 / CodeSextant 屬於自己的產品 / 既然無法被取代那就超越所有人成為 SOTA」。

- ⭐ **建立版本控制**：9,395 行產品碼、432 測試此前零版控；已建獨立 git repo。本輪重構時字串手術打錯錨點改壞 `find_deadcode`，靠它救回。
- **競品調查推翻先前結論**（數字為 2026-07-19 親自 curl GitHub API）：colbymchenry/codegraph（60,803★，8 工具，全導航）、DeusData/codebase-memory-mcp（32,729★，26 工具，全導航/記憶）。兩者合計 34 工具**無一是紀律閘門**。→ **戰略**：通用代碼地圖賽道追不上（分發差兩個數量級）；**代碼紀律強制**是空地，也正是 user 原始目的（防屎山/反熵/工程管理）。
- **技術債棘輪**接進 discipline-audit：現況掃描是已接受基線子集就過、長出新債 → exit 1。既有債進基線永久靜音，不必先大掃除就能守紀律。契約 `.wiredo-audit.json` + 基線 `.codesextant-baseline.json`。
- **獨立性**：稽核路徑只讀 env `CODESEXTANT_DISCIPLINE_LOG`；補 `[tool.ruff]`（此前無，外部工具拿 88 字元預設報 359 個假問題）；產品碼現 ruff All checks passed。`find_duplicates` 216 行/巢狀 6 層拆成七階段函式（四路徑輸出逐位元組相同）。
- **量測基線**：`tools/measure_coverage.py`＝Python 中位數解析率 50.0%、零高信心 44%、0.29s/符號。TS 每符號 25s（走 ts-morph 子行程，慢兩個數量級）。
- ⛔ **最貴教訓**（memory `prove-the-gate-fails-before-trusting-green`）：棘輪第一版是結構性永遠綠的假閘門（把現況掃描放真相源側，新債只撐大真相源、基線永遠是子集）。連跑三次全綠像成功，注入真實新債才揪出。配套三同族錯誤：測試設定步驟輸出丟 /dev/null、`/reindex` GET 失敗自藏、稽核比對舊資料回綠。→ **閘門要先證明會紅才信它的綠；測試腳本裡的設定步驟絕不可靜音；發布任何數字前先證明測法本身對**（同工具同 repo 因測法不同 2.0%→4.3%→50.0%）。
- ⚠ 已知邊界（非待修）：`work_coordinator.py` 的 `SHARED_COORDINATOR` 模組級單例會被誤報未接線，已收基線並註「⛔不要去修這個沒壞的東西」；deadcode 斷言暫撤（未用匯入實測 0，兩側皆空 vacuous 守衛判 SUSPECT，改靠 ruff F401）。

## -3. 2026-07-18 多代理併發根治（已上線·實測 155× 改善）

多代理同時打服務塞車。⛔ 駁回「多開埠」（摧毀 single-flight 合併、冷快取 75% miss、重演 watcher 模組級單例事故、多進程寫同 DB 損毀）。改 **per-project 分片 + WAL**：塞車 74.8s → 0.48s。工人進程池方向對（唯一解控制面 GIL 餓死）但 ⛔不可用標準庫 `ProcessPoolExecutor`（無單任務逾時，強殺工人會全連坐）；列第二順位未做。⚠ 未解：控制面 GIL 餓死。逐檔改動/紅藍全程 → git log。

## -2. 🎉 2026-07-17 修復線收口（7 條紅隊 blocker 全修 + 雙 reviewer Ready YES）

Workflow wf_f00cdfef·9 agent：probe-vs-serve 原子 owner / health lock-free snapshot / watcher generation key / watcher-disabled 不 import / coordinator 重入 fail-fast / follower exception clone / queue+follower cap 8（env `CODESEXTANT_HEAVY_QUEUE_CAP`/`_FOLLOWER_CAP`）+ supervisor stuck-recycle（`CODESEXTANT_HEAVY_STUCK_SEC` 預設 1800）。全套 397 passed 零卡死；現役 12:45 換代（supervisor 19424 / daemon 15744，8790 唯一 listener）。⚠ 排程 Last Result `0x800710E0`＝keepalive 打在活 supervisor 被 IgnoreNew 拒的設計噪音非故障。**附贈安全發現**（交 psycheforge 線）：PF webhook 四平台 presence-only 弱檢查、強驗證器全未接線、驗不過仍回 200。

## -1. 2026-07-16 contention 中繼點（歷史·已由 -2/-3 完全收口）

7 條 blocker 已 07-17 全修（見 -2）。回滾備份 `E:\ai-king_backups\CodeSextant-pre-daemon-contention-fix-20260716-164723`（⚠ 不可整包覆蓋，會吃掉並行 ai-usage v0.16 線）。原記「fresh subprocess ~14s」已證實為誤。

## 0. 現役真相（2026-07-15 基線；現況以 §-6 為準）

- **現役** = Python `v0.15.0`（daemon 內部 report 0.16.0）＝所有 Skill/代理實際使用的 production engine；HTTP daemon 固定 `127.0.0.1:8790`。
- **雙層自癒已投產**：① Skill/client 每次先 `ensure`，查詢途中傳輸中斷重拉並只重試一次；② Windows 排程 `AIKing-CodeSextant` 跑隱藏 supervisor，每 5s 嚴格探活、daemon 退出自動拉回（supervisor 自身 255 次上限重啟 + 每分鐘 heartbeat 雙保險）。
- **watcher**：HKCU `CODESEXTANT_WATCH_ENABLED=0`（主動監看關；查詢時 content-hash / git freshness 增量兜底）。
- **權限邊界**：標準使用者＝AtLogOn；要「登入前開機啟動」需以系統管理員 PowerShell 重跑註冊腳本（自動改 AtStartup+S4U 雙 trigger）。標準權限無法建立，不可假裝已做到。

## 1. 2026-07-15 服務中斷事故（已修·壓縮為根因指針）

根因（9 條，全修落點見 git log 與下方修復表）：`HTTPServer` `allow_reuse_address=1` 讓 Windows 允許 4 PID 同綁 8790（真多 listener 非殘留）／`ensure_running()` 無鎖 check-then-spawn 多代理齊 Popen／每 daemon 各自 WatchManager 4 PID 同時重索引 33k 檔／無 Scheduled Task 無人拉回／client 直 urlopen 在 ensure 後查詢前退出即失敗／忙碌 `/health` 2.5s 但舊 ensure 只等 0.6s 誤判 port-conflict／`get_map` 每次 materialize 57 萬 symbols＋重建全圖／map 與一般查詢共用 30s timeout 逾時留 4.5GB 程序／client 匯入 eager import engine 白花 15s。修復落點（單一真相源）：`daemon.py`（interprocess file lock + 生命週期 instance lock + `SO_EXCLUSIVEADDRUSE` 禁 reuse + 非本品牌佔埠回 port-conflict）／`client.py`（傳輸層錯誤重試一次 + map 60s deadline）／`ranking.py`（稀疏 active-node PageRank + heap top-N）／`namegraph.py`（折邊 + path cache + 自適應 12~5000 檔 + 250k edge 硬上限）／`storage.py`（schema v4 covering index + digest-bound snapshot）／`engine.py`（revision-aware 4-entry LRU + cross-daemon disk cache + 誠實 coverage metadata）／`__init__.py`+`daemon.py`（PEP 562 lazy import）／`supervisor.py`（單例 watchdog）／`register_windows_startup.ps1`（冪等註冊）。

## 2. 操作與排錯

### Skill 正常使用

```powershell
chcp 65001 > $null
$OutputEncoding = [Text.Encoding]::UTF8
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$S = "$env:USERPROFILE\.agents\skills\codesextant\scripts\codesextant_query.py"
C:\Python311\python.exe $S --project "E:\ai-king\項目資料\CodeSextant" --action status
```

Skill 入口自動確保 daemon，不需先手動啟服務。

### 註冊/修復 Windows 常駐

```powershell
& 'E:\ai-king\項目資料\CodeSextant\tools\register_windows_startup.ps1'   # -Unregister 解除
```

標準使用者＝登入後最早啟動；要登入前開機啟動用「以系統管理員身分執行」跑同一指令（自動雙 trigger）。

### 觀測位置

- daemon log：`C:\Users\zerox\.codesextant\daemon.log`｜supervisor log：`C:\Users\zerox\.codesextant\supervisor.log`
- 健康：`http://127.0.0.1:8790/health`｜面板：`http://127.0.0.1:8790/`
- 判「單例」看 LISTEN 行、別把 TIME_WAIT 當重複：`netstat -ano | Select-String ':8790 '`

### 中文編碼硬閘

- PowerShell 讀文字：`Get-Content -Encoding UTF8`，禁裸 `Get-Content`。
- 中文路徑傳 native exe（python/node）：同開 `chcp 65001` + `$OutputEncoding=UTF8` + `[Console]::OutputEncoding=UTF8`。

## 3. 現役架構（Python production，§-6 的 Rust workspace 是平行重寫線）

1. `symbols.py`：16 語言 tree-sitter 抽符號。2. `references.py`：Python jedi、TS/JS ts-morph，其餘名稱級低信心 fallback。3. `storage.py`：`sha1(repo 絕對路徑)` 分 SQLite（SSOT；covering index + revision-checked JSON snapshot 只是可丟棄 cache）。4. `engine.py`：index/map/refs/impact/call hierarchy/duplicates/comments API。5. `daemon.py`：唯一 HTTP authority。6. `client.py`：所有 Skill 的 HTTP + 自癒入口。7. `supervisor.py`：Windows 長駐可靠性層（只呼叫 daemon SSOT）。

## 4. 長線 TypeScript 重寫（獨立於 §-6 Rust 線的較早探索）

- 藍圖：`E:\ai-king\項目資料\CodeSextant\docs\全TS重寫架構藍圖_2026-06-24.md`
- 已完成 `ts/src/`：`symbols.ts` / `storage.ts` / `ranking.ts`；下一 `namegraph.ts` parity。`ts/package.json`＝`0.16.0-ts.0`、`private=true`（⛔不可因檔案存在就宣稱 TS 已投產）。
- ⚠ 兩條 Rust 重寫線並存：`ts/`（06-24 TS 探索）與 `.worktrees/codesextant-sota-gate/crates/`（07-23 起 SOTA gate 的原生 Rust kernel）。SOTA gate 線是當前主戰線；TS 線是較早、未併入 gate 的探索，接手前先確認要推哪條（預設推 §-6 Rust 線）。

## 5. 已知邊界與下一步（07-15 歷史；現況以 §-6 為準）

- 登入前啟動＝管理員 PowerShell 重跑註冊腳本（標準權限做不到）。
- `CODESEXTANT_WATCH_ENABLED=0` 是現行 HKCU 明確設定；恢復主動 watcher 前先評估單 daemon CPU/索引風暴並由 user 明確同意。
- 8790 被非 CodeSextant 佔用時新版回 port-conflict 並停，不再 address-reuse 硬綁。

## 6. 關鍵絕對路徑

- 專案：`E:\ai-king\項目資料\CodeSextant`｜現役 package：`…\codesextant`｜SOTA worktree：`…\.worktrees\codesextant-sota-gate`
- 可靠性測試：`…\tests\test_daemon_reliability.py`｜啟動註冊：`…\tools\register_windows_startup.ps1`
- Codex Skill：`C:\Users\zerox\.agents\skills\codesextant`｜Claude Skill：`C:\Users\zerox\.claude\skills\codesextant`
- 全域摘要索引：`C:\Users\zerox\.claude\HANDOFF.md`
