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

## -6. ⭐ SOTA gate — native-kernel 5a✅ 5b-i✅ 5b-ii✅ 完成（HEAD 83955e7，下一步 5c multiprocess）

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
- **當前 HEAD＝`83955e7`（refactor：share `revision::decode_bundle_ref` 消 UNIT_SEP 重複）＝5a✅ 5b-i✅ 5b-ii✅；worktree 乾淨。**（鏈：…c5f2ad3 T5a → 673e7f7 拆 5b plan note → 44ea8a3 T5b-i → 7c61269 T5b-ii coordinator → 83955e7 dedup）
- 跨越序（interlock：G0/G1 → quality T1-3 → native T1 → quality T4 → quality T5-9 → **native T2-12** → 回 quality T10-11）：
  - **G0-G1 Task 1-9**：`…a6ff73a`（foundation；`verify_g0.py`/`verify_g1.py` 綠。逐 task 摘要見 git log 與 `docs/.../g0-g1-foundation.md`）
  - **quality T1**＝`158c10b`（schema v5 source-class 分類）｜**T2**＝`7cb4f6a`（deterministic explainable ranking）｜**T3**＝`d70415f`（凍結 public Python + command registry）
  - **native T1**＝`7217766`（18 個 public-operation oracle adapters + 語料）
  - **quality T4**＝`fcb5d9e`（refresh base oracle；後因 harness evidence-invariant 修正，於 `fb16925` 重跑一次）
  - **quality T5**＝`9876220`+`1537dd4`（non-vacuous self-map 品質閘）｜**T6**＝`304c457`（完整 8-crate Rust workspace）｜**T7**＝`66233be`（從 operations.yaml 生 protocol/error 契約）｜**T8**＝`885c84e`（canonical envelopes + QueryService 邊界）｜**T9**＝`5fd3d5d`（thin CLI/MCP/HTTP adapters）
  - oracle harness 修正：`9318a47`（no-side-effect check 限縮 isolated run）+ `b272527`（evidence-commit invariant 允許 manifest+changed-golden subset）
  - **native T2**＝`731217c`（凍結 18-operation public oracle：manifest fmt v2 + golden，evidence-only）
  - **native T3**＝`7a2ba99`（native deterministic discovery + classification parity：no-follow directory-handle walker〔Windows windows-sys CreateFileW+GetFileInformationByHandleEx、reparse rejection、identity-swap retry〕、11-rule source-class 與 Python `source_class.py` byte-parity、in-scope-only ignore policy、state-root 非可覆蓋排除、BLAKE3 discovery digest、weighted byte-semaphore pipeline）
  - **native T4**＝`9eabd1b`（bundled 16-language tree-sitter parser registry；per-language Python-oracle parity〔symbols/comments/complexity/fingerprint〕、iterative bounded extraction + QueryCursor limits + PARSER_LIMIT、16 grammar 精確 pin）＋ `9fb8cb0`（reviewed plan change：go re-pin + kotlin carve-out 記錄）
- 綠證（本 session 2026-07-24/25，⛔ 主代理親自重跑非轉述子代理）：native T2 邊界 `oracle_snapshot.py`/`public_operation_oracle.py --verify` 皆 exit 0；**native T3**（7a2ba99）`discovery_parity` 兩次同 digest `7389bf4a…842`（各 2 passed）+ `discovery_security` 12 passed、commit 10 檔零 oracle-bound；**native T4**（9eabd1b）`cargo test -p codesextant-parser`＝language_registry 5 + parser_limits 14(+1 ignored) + python_oracle 2（含 carve-out guard test）全綠、clippy `-D warnings` exit 0、commit 13 檔零 frozen、`cargo tree -d` 恰 1 個 tree-sitter 0.25.8/go 0.25.0/kotlin-ng 1.1.0/無 fwcd。**native T5a**（c5f2ad3）33 store tests 全綠含 schema_authority 9；**native T5b-i**（44ea8a3，主代理親自重跑非轉述）：full store suite **44 tests 0 fail**（per-binary crash_recovery 10 / python_oracle 1 / schema_authority 9 逐一綠、破 cargo binary-level fail-fast 遮罩）、clippy `-D warnings` 兩 crate exit 0（乾淨捕捉非 pipe-masked）、`discovery_parity` 2 unregressed、`pytest test_schema_v5_python_rust.py` 1 passed、commit 10 檔零 frozen；python_oracle reconcile **誠實**（schema_version 兩側 scrub＝documented v5↔v6 divergence + `classified_symbols` 讀真 `files` 表 classification 非 hardcode、golden 未動、`SymbolRecord`/`get_symbols` 產品 API 未改）。**native T5b-ii**（7c61269，主代理親自重跑）：core suite 32（discovery_parity 2 / discovery_security 12 / +3 snapshot_wiring unit）+ full store suite 14 binaries 全綠（incremental_index 10 逐一綠、5a/5b-i 全 unregressed）+ clippy 兩 crate exit 0；trait-DI **無 core→parser|store 循環依賴**（parser/store 各 dep core、parser 僅 store dev-dep）；property-7 no-op budget **真實**（index.rs:169 no-op 路徑 return 在 begin_revision〔:334〕之前＝結構零寫入）；子代理注入 no_op=false bug→4 property 真 panic 證 assertion 非 vacuous。**dedup**（83955e7）store 14 binaries + clippy 再驗全綠。
- ⚠ native T3 已知邊界（非 blocker）：POSIX discovery path（rustix `open O_NOFOLLOW` sys 模組）本機 Windows-only toolchain **未編譯/未測**，Linux CI build 前別依賴；content-addressed spill / IndexReceipt / 完整 AccessScope threading de-scoped 到後續 task。
- ⚠ native T4 已知 carry-over（非 blocker）：① **kotlin `raw_token_hash` documented carve-out**（fwcd↔ng tokenization 合法差異；只碰 fingerprint col-11、語意欄位全 byte-parity；guard test `carveout_is_kotlin_raw_token_hash_only` 自證 15 語言零 masking + 防 stale；plan authority table 已記錄 commit `9fb8cb0`）② **`parser_limits::query_capture_explosion_trips_match_limit` `#[ignore]`**（match-limit gate 經 single-node query 結構性不可觸發、pre-existing；DoS fan-out 已由 capture-limit test 覆蓋；待 plan-owner 決：開 custom-query 測試 seam 或撤 gate）③ kotlin `block_comment` 修正僅 static 驗（corpus 無 kotlin 註解，MEDIUM-HIGH）。
- ⚠ native T5b-ii 已知 carry-over（非 blocker，主代理核實＝誠實 gap 非隱瞞）：① **O(changed·depth) snapshot-node sharing 未達**——5b-i `snapshot_nodes` 是 flat `(root,path)` map，新 root 每 discovered path 寫一 node row＝O(total-per-root)（非 plan Step-1 bullet 8 的 O(changed·depth)）；GC 保留 current+1 rollback+pinned 故 steady-state 有界（~2×files 常數因子非無限膨脹），但**確為 plan bullet 8 偏離**——fact bundle 層共享已達（`syntax_bundles` 只寫改動檔、實測 row-delta），缺的是 node 層 Merkle 子樹共享（需 hierarchical node schema，動 5b-i `snapshot_nodes` 表，宜獨立 sub-task 或併 5c/5d schema，⛔非能默默接受，plan-owner 可見項）。② **source bytes 從 live path 重讀**（discovery 丟 bytes、discovery.rs 出 scope）——BLAKE3 re-hash 不符即 `UnstableSource`〔保正確性〕；「immutable SourceBlob 單流不重開 live path」理想未達（本即 T3 已 de-scope 的 spill 邊界，非新債）。
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

### next_step — native-kernel Task 5c（5a✅ 5b-i✅ 5b-ii✅；syntax 層全鏈完成，剩 5c multiprocess + 5d semantic）

**現況**：Task 5 拆 5a-5d（plan note `31f3aff`）+ 5b 再拆 5b-i/5b-ii（`673e7f7`——binding boundary + python_oracle reconcile 判決全在 plan Task 5 blockquote）。syntax 層全鏈已完成並主代理親自重跑驗證（見上綠證段）：**5a**（`c5f2ad3` schema+migration）→ **5b-i**（`44ea8a3` crash-safe revision engine + ReaderEpoch + recover，10 crash tests）→ **5b-ii**（`7c61269` single-process IndexCoordinator：discovery→parse→store 首個 end-to-end 真接線，trait-DI `GraphStore`+`SyntaxAnalyzer` 零循環依賴，incremental_index 10）→ **dedup**（`83955e7`）。

**下一步 = 5c**（建議 exact-commit message `feat(store): add multiprocess revision publish with lease fencing`，依 plan Step 微調）：`crates/codesextant-store/tests/multiprocess_publish.rs`（new）launch **真 child processes**（非共用單一 connection 的 task）：兩 writer 從同 `base_published_revision` plan、deterministic barrier 反轉 publish 順序 → 恰一 pointer CAS 贏、輸家收 internal `PublishConflict`→abort staging root→IndexCoordinator 在固定 attempt budget + 原絕對 deadline 內 rediscover/replan 才可從新 base publish；`PublishConflict` **不跨** QueryService/transport，retry 耗盡→已宣告 public `INDEX_STALE`。額外 case：kill lease owner、PID-reuse（不同 process-start/boot identity）、resume paused old owner after takeover、concurrent GC、cancel writer——證 monotonic current content / permanent fencing / no stale overwrite / no leaked staging root / bounded lease recovery。**pointer CAS 即使持 lease 也必跑**。基座：5b-i 已有 single-process fencing epoch + `PublishConflict` + `writer_lease` 表（holder_uuid/pid/process_start/boot_id/heartbeat/expires/fencing_epoch）+ `BEGIN IMMEDIATE`；5c 擴跨進程 lease 取得/takeover/PID-reuse-safe `recover()`（可新增 `crates/codesextant-store/src/lease.rs`）。⚠ 難點：Windows 真 child-process + 真開檔 handle 跨 teardown（reap-before-delete）。從乾淨 `83955e7` 起、同紀律（red→green／exact-commit 恰列檔／`--locked`／⛔不碰 frozen〔golden/`codesextant/*.py|sql`/oracle tools/5a+5b-i+5b-ii 已綠 test〕／land-green-or-pristine／⛔不重啟 daemon／不碰 master）；派子代理前跑 `pytest tests/release/test_exact_task_commit.py` 綠 + dot-source `tools/exact_task_commit.ps1` + dispatch preamble。

**5c 後**：**5d**＝semantic-context bundles + invalidation（Task 6 resolver 後才能真斷言；`semantic_bundles` 表 + `AnalysisContract` semantic 分量 + `IndexPlan/Receipt::resolution_context_digest` 已留 named empty extension point 未 fake）併 Task 6｜**另立 sub-task**：O(changed·depth) Merkle node schema（見上 T5b-ii carry-over ①，動 `snapshot_nodes` 表）｜then Task 6-12。全綠仍非公開/發布/SOTA 授權。

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
