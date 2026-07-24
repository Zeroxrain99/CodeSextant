---
tier: 全文
type: 專案交接（三層交接之全文層）
喚起詞: 交接 CodeSextant / 交接 codesextant
updated: 2026-07-24
最後壓縮整理: 2026-07-19（-3 節逐檔改動移交 git log；-1 節 07-16 checkpoint 早已壓成 3 行）
設計SSOT: E:\ai-king\_AI_BRAIN\05_Planning\CodeSextant_自創代碼地圖神器_設計_2026-06-18.md
版本控制: ⭐ 2026-07-19 起有獨立 git（此前 9,395 行零回復點）。逐版史用 git log 查，⛔別再往本檔塞
---

# 交接 CodeSextant

## -6. ⭐ 2026-07-24 SOTA release gate 執行中（G0-G1 Task 4 已提交）

### §0 計畫路徑索引

- 設計 SSOT：`E:\ai-king\項目資料\CodeSextant\docs\superpowers\specs\2026-07-23-sota-open-source-release-gate-design.md`
- 目前執行計畫：`E:\ai-king\項目資料\CodeSextant\docs\superpowers\plans\2026-07-23-codesextant-g0-g1-foundation.md`
- 後續計畫：同目錄 `2026-07-23-codesextant-g2-*.md` 至 `g7-g8-publication-application.md`
- 執行 worktree：`E:\ai-king\項目資料\CodeSextant\.worktrees\codesextant-sota-gate`
- 執行分支：`codex/codesextant-sota-gate`

### 狀態總覽

- `master` 停在 `20252a1`（完整 release-gate 設計與七份實作計畫）。
- 執行分支目前停在乾淨 commit `87dd3e1 test: make untracked materialization check durable`。
- 已完成並提交：
  1. `df678bf`：Python 產品版本單一權威與精確提交工具。
  2. `e2c0c27`、`3162a95`、`8217715`：Rust kernel / Python oracle 架構裁決、TS-primary 降為 fixture/adapter 輸入。
  3. `9b6a404`：schema v4 抽為共用 resource。
  4. `a599471`：不可變 Python oracle 產生器、隔離環境 lock、deterministic corpus、manifest validator。
  5. `87dd3e1`：修正 Task 4 commit 後才暴露的假綠；untracked exclusion 改用 disposable Git repo 真測。
- Task 4 聚焦驗證：`38 passed in 20.81s`；Ruff 全綠；精確提交閘曾抓到 5 個檔尾空白，修正後才允許 commit。
- production daemon 未被重啟或切換：`http://127.0.0.1:8790/health` 於 2026-07-24 查得 `v0.16.0`、status ok、單一 listener。

### 鐵律／未解決

- ⛔ 不在 `master` 實作；所有 G0-G1 工作只在上述 worktree。
- ⛔ Python 0.16.0 仍是 production oracle；Rust parity 完成前不可切換。
- ⛔ G0-G7 全綠、獨立驗證與 user 明確授權前，不得建立公開 repo、發布 package/release、宣稱 SOTA 或送 Claude for Open Source。
- ⛔ 不讀／不複製競品 implementation source；研究邊界只到公開文件、論文、issue、benchmark protocol、documented interface。
- ⛔ production daemon 不因測試或交接重啟；磁碟最新碼不等於已部署。
- 計畫 Markdown checkbox 尚未回填，不能拿 `0 checked / 665 unchecked` 判進度；Git commits + clean worktree + 測試才是權威。

### next_step

1. 在乾淨 `87dd3e1` 上執行 G0-G1 **Task 5：Freeze the Python oracle in a separate commit**。
2. 生成兩份獨立 output root，比對 bytes，跑 `--verify-output-root ... --precommit`。
3. 只複製並精確提交三個 evidence 檔：`tests/fixtures/oracle-manifest.json`、`tests/parity/golden/python-engine-v1.json`、`python-store-v1.json`。
4. 驗證 evidence commit 的 first parent 正是 `87dd3e1`，再進 Task 6 Rust workspace。

## -4. ⭐ 2026-07-19 獨立產品化 + 技術債棘輪（5 個 commit·438 測試綠）

**起因**：user「concinno 相關用詞全拿掉 / CodeSextant 就是屬於自己 CodeSextant 的產品 /
整個做出來用 既然無法被取代 那就超越所有人 成為 SOTA」。

### ⭐ 最重要的一件事：建立版本控制

9,395 行產品碼、432 個測試，此前**零版本控制**——沒有任何「回到上一個好狀態」的點。
對一個目標是幫別人守住代碼紀律的工具，這是最不該有的缺口。已建獨立 git repo
（外層把 `項目資料/` 列入忽略，所以不影響外層）。本輪重構時字串手術打錯錨點、改壞
`find_deadcode`，**靠它救回來**——建好幾小時就派上用場。

### 競品調查改變了戰略判斷（⚠ 推翻先前結論）

| 專案 | Star | 建立 | 工具數 | 性質 |
|---|---:|---|---:|---|
| colbymchenry/codegraph | 60,803 | 2026-01（6 個月） | 8 | **全是導航** |
| DeusData/codebase-memory-mcp | 32,729 | 2026-02（5 個月） | 26 | **全是導航/記憶** |

（數字為 2026-07-19 親自 curl GitHub API 所得，非轉述子代理；曾懷疑刷星，查證後撤回
——ruff 的 star:watcher 451:1 與 codegraph 457:1 同量級。README 引文亦逐句比對屬實。）

**先前判斷「差異化在於會誠實聲明盲區」只對一半**——這兩個競品都做了盲區聲明，概念上
不再獨有。但兩者合計 34 個工具**沒有一個是紀律閘門**：它們回答「這東西在哪被用」，
CodeSextant ＋ discipline-audit 回答「有沒有東西偏離了我們宣告的規矩」。

→ **戰略結論**：通用代碼地圖賽道追不上（分發差兩個數量級、jedi 主攻 Python vs 158 語言）；
**代碼紀律強制**是空地，也正是 user 的原始目的（防屎山、反熵、工程管理）。

### 本輪落地

| 項目 | 內容 |
|---|---|
| **技術債棘輪** | 接進 discipline-audit：現況掃描是已接受基線的子集就過；長出基線沒有的 → exit 1。既有債（含誤報）進基線永久靜音，**不必先大掃除就能開始守紀律**（「要求先清乾淨」正是多數紀律工具推不動的原因）。契約 `.wiredo-audit.json` ＋ 基線 `.codesextant-baseline.json` |
| **獨立性** | 稽核路徑改成只讀環境變數 `CODESEXTANT_DISCIPLINE_LOG`；面板顯示服務回報的真實來源而非寫死路徑；原始碼外部品牌用詞零殘留 |
| **自己的規範** | 補 `[tool.ruff]`（此前沒有，外部工具拿 88 字元預設來評判，一次報 359 個假問題）。產品碼現在 ruff All checks passed |
| **結構** | `find_duplicates` 216 行／巢狀 6 層 → 拆成七個階段函式。四條路徑（預設／near_global／call_pattern／scope_file）輸出逐位元組相同 |
| **量測基線** | `tools/measure_coverage.py`：產品碼 Python 中位數解析率 **50.0%**、零高信心 44%、0.29 秒／符號。文件 `docs/量測基線_解析覆蓋率_2026-07-19.md` |

### ⛔ 本輪最貴的教訓（已沉澱 memory `prove-the-gate-fails-before-trusting-green`）

**棘輪第一版是結構性永遠綠的假閘門**：引擎的 subset 語意是「消費端 ⊆ 真相源」，我把
現況掃描放在真相源那一側，新債只會把真相源撐大、基線永遠是它的子集。連跑三次全綠
看起來像成功，是**注入真實新債**才揪出來。

配套三次同族錯誤：把測試的設定步驟輸出丟進 /dev/null，`/reindex` 不吃 GET 的失敗被
自己藏起來，稽核一路比對舊資料還回綠。→ **閘門要先證明它會紅，才信它的綠；測試腳本
裡的設定步驟絕不可靜音。**

量測工具亦然：同一份工具、同一份 repo，因測法不同數字從 2.0% → 4.3% → 50.0%，三次
都是測法錯不是工具變好。**發布任何數字前先證明測法本身對。**

### ⚠ 已知邊界（誠實記錄，非待修）

- `work_coordinator.py` 的 `SHARED_COORDINATOR` 是模組級單例，會被誤報成未接線；已收進
  基線並註明 **⛔不要去「修」這個沒壞的東西**
- deadcode 斷言暫撤：未用匯入實測為 0，兩側皆空會被 vacuous 守衛正確判為 SUSPECT。一條
  永遠 SUSPECT 的斷言會訓練人忽略 exit 2，反而更糟。ruff 的 F401 目前守著這塊
- 量測只量了自己；要跟別人比得在公認開源 repo 上跑同一套方法。TypeScript 每符號 25 秒
  （走 ts-morph 子行程），比 Python 慢兩個數量級

## -3. 2026-07-18 多代理併發根治（已上線·實測 155× 改善）

多代理同時打服務造成塞車。**⛔ 駁回「多開埠」方案**（會摧毀 single-flight 請求合併、
無狀態路由配有狀態工作有 75% 機率踩冷快取、逐字重演 07-15 的 watcher 模組級單例事故、
N 個進程寫同一個資料庫有損毀風險），改用 **per-project 分片 ＋ WAL**：塞車 74.8 秒
降到 0.48 秒。工人進程池方向對（唯一能解控制面 GIL 餓死），但 ⛔不可用標準庫的
ProcessPoolExecutor——它沒有單任務逾時，強殺工人會讓在途工作全部連坐失敗，把「一人
被擋」變成「全部被炸」。列第二順位，未做。

⚠ 未解：控制面 GIL 餓死。（supervisor 日誌裡的 pid=7 那幾行是測試污染、不是事故）

逐檔改動、紅藍全程與當時的 3 條 pre-existing 失敗記錄 → 用 git log 查，本檔不再留逐版史。


## -2. 🎉 2026-07-17 修復線收口（Ready YES·現役已換代·索引交付）

- **7 條紅隊 blocker 全修＋雙 reviewer 獨立 Ready YES**（Workflow wf_f00cdfef·9 agent）：#1 probe-vs-serve 原子 owner（probe timeout=unknown fail-closed）/#2 health lock-free snapshot（真占鎖紅測試）/#3 watcher generation key（突變法證明測試真抓 lost-update）/#4 watcher-disabled 不 import（含 `_require_project` 殘渣）/#5 coordinator 重入 fail-fast/#6 follower exception clone/#7 queue cap 8+follower cap 8（env `CODESEXTANT_HEAVY_QUEUE_CAP`/`CODESEXTANT_HEAVY_FOLLOWER_CAP`·注意 HEAVY_ 前綴）+`/health` 遙測+**supervisor stuck-recycle**（`CODESEXTANT_HEAVY_STUCK_SEC` 預設 1800·0 全關）+deadline 疊隊殘餘風險明文（work_coordinator docstring :11-28）。
- **全套 397 passed 零卡死**（含原卡死的 test_deadcode/test_watcher/test_daemon_reliability·雙 reviewer 各自重跑實證）。
- **現役已換代**（12:45）：停 task→殺舊 supervisor 12904/daemon 10364→重拉→新 supervisor **19424**/daemon **15744**·8790 唯一 listener·`/health` 含 heavy_work 遙測＝新碼證明·230s 真 reindex 期間 /health 29-206ms 秒答·>10min pid 零翻攪·log 零 spawn-timeout。
- **⚠排程 Last Result `0x800710E0`＝設計噪音非故障**（1 分鐘 keepalive 重複打在活 supervisor 上被 IgnoreNew 拒絕的記錄；真健康訊號＝pid 穩定；可選 cosmetic 改純 At-logon）。
- **⚠ops 教訓**：「Critical 未修前不得重啟現役」gate 擋不住重開機——At-logon 自啟會載入磁碟最新碼（今晨即已發生）。未來高風險改動落盤前先想「重開機=部署」。
- **順序索引交付**：兩 worktree 完成·報告 `E:\ai-king\項目資料\CodeSextant\_index_results_20260717.md`（11,862B·注入大師 B 線接手用：renderGameSettings 完整鏈/launch_gate/群組掛點/`brain_backend_*` refs 17）。⚠TS 檔 daemon 只名稱比對**實測漏報**（handleWebhook 漏 index.ts 真呼叫）——TS 部分以報告內 grep ground truth 為準。**附贈安全發現**：PF webhook 四平台 presence-only 弱檢查·強驗證器（line/wechat/discord）全未接線·驗不過仍回 200——交 psycheforge 線。
- **無 git 版控替代**：後修復備份+SHA-256 收據＝`E:\ai-king_backups\CodeSextant-post-critical-repair-20260717\SHA256-RECEIPT-20260717.txt`（6 關鍵檔）。
- **殘餘 minor（非 blocker）**：版本 SSOT 漂移 `__init__`=0.16.0 vs pyproject=0.15.0（ai-usage 線收口時同步）／`_get_watch_mgr` 無鎖（production 不可觸發）／pytest 測試會污染正式 supervisor.log（建議測試改 temp log 路徑）／cap 傳 0 falsy fallback 到 env。
- **下一步**：ai-usage 線收口版本號→TS rewrite 續行（namegraph.ts）。

## -1. 2026-07-16 contention 修復中繼點（歷史·已由 -2／-3 完全收口）

當時的 7 條 blocker（probe-vs-serve race／health 被 watcher lock 卡／watcher lost update／watcher 關閉仍載 engine／coordinator 重入死鎖／follower 共用 exception／queue 無上限）**已於 07-17 全修＋雙 reviewer Ready YES**，細節見 -2 節。回滾備份 `E:\ai-king_backups\CodeSextant-pre-daemon-contention-fix-20260716-164723`（⚠ 不可整包覆蓋，會吃掉並行的 ai-usage v0.16 線）。

⚠ 該節原記「fresh subprocess 約 14s」**已證實為誤**，校正見 -3 節數據校正第 1 條。

## 0. 一頁接手摘要（2026-07-15 歷史基線；現況以 -1 節為準）

- **現役真相**：Python 版 `v0.15.0` 是目前所有 Skill／代理實際使用的 production engine；本機 HTTP daemon 固定 `127.0.0.1:8790`。
- **2026-07-15 可靠性事故已修復**：原本 4 個 Python PID 同時 LISTEN 8790、各自掛 17 組 watcher；現在 daemon 本體有生命週期單例鎖、Windows exclusive socket、啟動競態鎖，實測只剩一個 listener。
- **2026-07-15 map 擴展性事故已修復**：`E:\ai-king` 索引為 570,651 symbols／33,064 files／DB 2.33 GB。舊版預設 map 超過 180 秒且逾時後殘留 4.5 GB worker；現版以稀疏 PageRank、重複邊 multiplicity、全 repo 分層取樣、250k 唯一邊硬上限、SQLite covering index、revision-checked symbol／final-map JSON snapshots 與 4-entry LRU 收斂。首次從零建圖實測 8.147~43.598 秒（60 秒 deadline 內）；有 map snapshot 後 daemon 重啟首查 wrapper 1.255 秒、直接 HTTP 0.025 秒。
- **雙層自癒已投產**：
  1. Skill/client 每次使用先 `ensure`；查詢途中遇到傳輸中斷會重拉 daemon 並只重試一次。
  2. Windows 排程 `AIKing-CodeSextant` 執行隱藏 supervisor，每 5 秒嚴格探活；daemon 退出自動拉回。supervisor 自身由合法上限 255 次失敗重啟＋每分鐘 heartbeat 雙保險拉回。
- **目前 Windows 權限邊界**：本輪是標準使用者權限，已註冊「登入即啟動」而非登入前的系統服務。以系統管理員 PowerShell 重跑同一註冊腳本，會自動改為「系統開機＋登入」雙 trigger。
- **watcher 現況**：HKCU `CODESEXTANT_WATCH_ENABLED=0` 是既有使用者環境設定，本輪未改；因此主動檔案監看目前關閉，但查詢時的 content-hash／git freshness 增量仍是兜底。
- **當前實機狀態**：Scheduled Task `AIKing-CodeSextant` 為 Running；daemon 自動復原後 PID `38544`，8790 只有一個 listener。Skill 單獨自癒與 supervisor 自癒已在本輪各重跑一次。
- **長線接手點**：全 TypeScript 重寫已完成 `symbols.ts`、`storage.ts`、`ranking.ts`；下一個尚未落地的核心模組是 `namegraph.ts`。達 parity 前不可把現役 Python 版切走。
- **版本庫現況**：`E:\ai-king\項目資料\CodeSextant` 本身不是獨立 git repository；本輪沒有可做的獨立 commit，交接與測試證據是回復點。

## 1. 2026-07-15 服務中斷事故

### 已坐實根因

1. `http.server.HTTPServer` 在 Python 3.11 的 `allow_reuse_address=1`；Windows 因此允許 4 個 PID 同綁 `127.0.0.1:8790`。這不是單純「殘留程序」，而是 socket 設定允許真正的多 listener 分流。
2. `ensure_running()` 原本是無鎖的 check-then-spawn；多代理同時看到服務未就緒時會一起 `Popen`。
3. 每個 daemon 都有自己的 `WatchManager`，所以 4 個 PID 同時重索引 `E:\ai-king`（約 33,051 檔）及其他 16 個已索引專案，造成高 CPU、SQLite 競爭與回應不穩。
4. Windows 原先沒有 CodeSextant Scheduled Task、service 或 Run entry；服務退出後無人持續拉回。
5. `CodesextantClient._get/_post` 直接 `urlopen`，服務在 `ensure` 後、真正查詢前退出就直接失敗。
6. 忙碌 daemon 的 `/health` 偶爾需 2.5~2.7 秒；舊 `ensure` 只等 0.6 秒就把同品牌 listener 誤判成 `port-conflict`。
7. `get_map` 每次 materialize 57 萬 symbols、重建全 definitions/namegraph，PageRank 每輪還掃全部孤立節點；同一行 occurrence 也先膨脹成重複邊。
8. client 對 map 與一般查詢共用 30 秒 timeout；外殼逾時後 server worker 仍繼續，曾留下 4.5 GB Python 程序。
9. `codesextant.client` 匯入時連 tree-sitter engine 一起 eager import，純 HTTP wrapper 也白花約 15 秒。

### 修復落點（單一真相源）

| 檔案 | 修復 |
|---|---|
| `E:\ai-king\項目資料\CodeSextant\codesextant\daemon.py` | `_InterprocessFileLock`（OS crash 自動釋放）、daemon 整段生命週期 instance lock、startup lock 內二次探活、`_ExclusiveThreadingHTTPServer` 禁 address/port reuse 並在 Windows 設 `SO_EXCLUSIVEADDRUSE`、非 CodeSextant 佔埠回 `port-conflict` 而非再綁。 |
| `E:\ai-king\項目資料\CodeSextant\codesextant\client.py` | 傳輸層錯誤時呼叫既有 `ensure_running` 後只重試一次；忙碌服務慢確認成功時不重送；map 專屬 60 秒 deadline。 |
| `E:\ai-king\項目資料\CodeSextant\codesextant\ranking.py` | 稀疏 active-node PageRank；孤立節點聚成一個 personalization scalar；multiplicity 保持原數學權重；top-N 用 heap、不再複製排序 57 萬 dict。 |
| `E:\ai-king\項目資料\CodeSextant\codesextant\namegraph.py` | 同 caller 行重複 occurrence 折邊；path normalization cache；大型 map 自適應 12~5000 檔、focus 優先＋全 repo 分層取樣、250k unique-edge 硬上限。 |
| `E:\ai-king\項目資料\CodeSextant\codesextant\storage.py` | schema v4 `idx_symbols_map` covering index；UTF-8 JSON symbol snapshot＋digest-bound final map snapshot（不合／損壞即忽略，SQLite 仍是 SSOT）。 |
| `E:\ai-king\項目資料\CodeSextant\codesextant\engine.py` | DB revision-aware 4-entry map LRU＋跨 daemon final-map disk cache；snapshot 背景建立與失效；回傳誠實 coverage／sampling／cache source metadata。 |
| `E:\ai-king\項目資料\CodeSextant\codesextant\__init__.py`、`daemon.py` | PEP 562／module proxy lazy import；純 client 不再載 engine，server 真命中端點才載重模組。 |
| `E:\ai-king\項目資料\CodeSextant\codesextant\supervisor.py` | 單例 watchdog；每 5 秒嚴格 `/health`，服務退出走同一個 `ensure_running` SSOT 拉回；失敗採最大 60 秒退避。 |
| `E:\ai-king\項目資料\CodeSextant\tools\register_windows_startup.ps1` | 冪等註冊／覆寫 `AIKing-CodeSextant`；標準使用者＝AtLogOn + Interactive，管理員＝AtStartup + AtLogOn + S4U；另有每分鐘 heartbeat；hidden、IgnoreNew、RestartCount=255（Task Scheduler schema 合法上限）、RestartInterval=PT1M。支援 `-Unregister`。 |
| `E:\ai-king\項目資料\CodeSextant\tests\test_daemon_reliability.py` | 12 項可靠性回歸；另有 ranking/namegraph 的稀疏等價、10 萬孤點、折邊、採樣、edge budget、LRU、snapshot revision 測試。 |
| `C:\Users\zerox\.agents\skills\codesextant\` | Codex 現役 Skill：文件已補自癒／啟動說明，wrapper 對任何非 `already-running/spawned` 的 ensure action 明確 exit 5。 |
| `C:\Users\zerox\.claude\skills\codesextant\` | Claude 相容鏡像，同步 wrapper 與可靠性說明。 |

### 真實驗證證據

- 事故現場：PID `2416`、`13680`、`17440`、`23676` 同時 LISTEN 8790；四者啟動時間皆為 2026-07-14 21:10:20，command line 都是 `...CodeSextant\codesextant\daemon.py serve`。
- 清理後冷啟：只剩 PID `23864` 一個 LISTEN 8790；再手動執行第二個 `serve`，新版以「duplicate ignored」退出，listener 仍只有一個。
- supervisor 實機 kill-recover：精準殺 PID `23864`，約 6 秒後自動拉回 PID `37948`，`supervisor.log` 寫入 `daemon recovered`。
- Skill 單獨自癒：先停止 Scheduled Task／確認 supervisor 不在，再殺 PID `37948`；直接跑現役 wrapper `--action status` 成功自動拉回 PID `39076` 並回傳索引狀態，之後重啟 Scheduled Task。
- 本輪 TDD 紅燈依序捕捉：slow health／重送／10053、multiplicity／10 萬孤點／折邊、自適應採樣／edge budget、LRU、lazy import、snapshot revision；不是先改後補自評。
- 完整 Python 回歸（final-map disk cache 落盤後最終重跑）：`C:\Python311\python.exe -m pytest tests -q --durations=10` → **337 passed in 114.28s**。
- supervisor 自身 kill-recover：精準殺 PID `39908`，25 秒內 Task Scheduler 以新 PID `3908` 拉回；task 回 `State=Running`。
- 當前 Task 設定（2026-07-15 驗證）：`State=Running`、`LogonType=Interactive`、2 triggers（AtLogOn＋每分鐘 heartbeat）、`RestartCount=255`、`RestartInterval=PT1M`、`MultipleInstances=IgnoreNew`。
- supervisor 當輪退出復原：PID `31864` 停止後 `5.619s` 拉回 PID `21388`；listener count=1。
- Skill 單獨自癒當輪重驗：先停 Task 至 Ready、停 PID `42192`，wrapper `--action status` 在 `4.021s` 以 `daemon=spawned` 拉起 PID `31864`；`finally` 復原 Task，listener count=1。
- map 性能證據：舊 cap=1 仍約 `57.7s`，預設 5000 檔超過 `180s`；symbol snapshot `100,949,730 bytes`、載入 `5.031s`。首次 final map 會依冷磁碟在 `8.147~43.598s` 建成 `25,823-byte` JSON；再重啟 daemon，wrapper 首查 `1.255s`，直接 HTTP `0.025s` 且 `cache_source=disk`。

## 2. 操作與排錯

### Skill 正常使用

```powershell
chcp 65001 > $null
$OutputEncoding = [Text.Encoding]::UTF8
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$S = "$env:USERPROFILE\.agents\skills\codesextant\scripts\codesextant_query.py"
C:\Python311\python.exe $S --project "E:\ai-king\項目資料\CodeSextant" --action status
```

Skill 入口本身會自動確保 daemon；不需要先手動啟服務。

### 註冊／修復 Windows 常駐

```powershell
& 'E:\ai-king\項目資料\CodeSextant\tools\register_windows_startup.ps1'
```

- 標準使用者：登入後最早啟動。
- 真正登入前開機啟動：用「以系統管理員身分執行」的 PowerShell 跑同一指令；腳本依權限自動選雙 trigger。
- 解除：同一路徑加 `-Unregister`。

### 觀測位置

- daemon：`C:\Users\zerox\.codesextant\daemon.log`
- supervisor：`C:\Users\zerox\.codesextant\supervisor.log`
- 健康：`http://127.0.0.1:8790/health`
- 面板：`http://127.0.0.1:8790/`

判斷「單例」要看 LISTEN 行，不要把 TIME_WAIT 當重複 listener：

```powershell
netstat -ano | Select-String ':8790 '
```

### 中文編碼硬閘

- PowerShell 讀文字：`Get-Content -Encoding UTF8`，禁止裸 `Get-Content`。
- 中文路徑傳給 native exe（python/node）：同時開 `chcp 65001`、`$OutputEncoding=UTF8`、`[Console]::OutputEncoding=UTF8`。

## 3. 現役架構

1. `codesextant/symbols.py`：16 語言 tree-sitter 抽符號。
2. `codesextant/references.py`：Python jedi、TS/JS ts-morph；其餘名稱級低信心 fallback。
3. `codesextant/storage.py`：`sha1(repo 絕對路徑)` 分 SQLite，不混專案；SQLite 是 SSOT，map covering index＋revision-checked JSON snapshot 只是可丟棄 cache。
4. `codesextant/engine.py`：index/map/refs/impact/call hierarchy/duplicates/comments 等 API。
5. `codesextant/daemon.py`：唯一 HTTP authority；所有殼、Skill、代理共用。
6. `codesextant/client.py`：所有 Skill 的 HTTP 與自癒入口。
7. `codesextant/supervisor.py`：Windows 長駐可靠性層，只呼叫 daemon SSOT，不另造啟動路徑。

## 4. 長線 TypeScript 重寫

- 權威藍圖：`E:\ai-king\項目資料\CodeSextant\docs\全TS重寫架構藍圖_2026-06-24.md`
- 已完成：
  - `E:\ai-king\項目資料\CodeSextant\ts\src\symbols.ts`
  - `E:\ai-king\項目資料\CodeSextant\ts\src\storage.ts`
  - `E:\ai-king\項目資料\CodeSextant\ts\src\ranking.ts`
- 下一步：先做 `ts\src\namegraph.ts` parity；之後才接 references／engine／daemon／client。
- `ts/package.json` 目前版本 `0.16.0-ts.0` 且 `private=true`。不可因檔案存在就宣稱 TS 已投產。
- Python 現役版與 TS 重寫是兩條線：可靠性修復已落在現役 Python；TS 達完整 parity、測試和真實 Skill 切換驗收前不可替換。

## 5. 已知邊界與下一步（07-15 歷史；07-16 以 -1 節為準）

1. ~~07-16 contention blocker~~ 已於 07-17 全修（-2 節）；併發架構已於 07-18 換代（-3 節）。**本節其餘各條仍有效**。
2. 若 user 要「登入前」即啟動，唯一剩餘動作是以管理員 PowerShell重跑註冊腳本；標準權限無法建立 AtStartup/S4U，不能假裝已做到。
3. `CODESEXTANT_WATCH_ENABLED=0` 是目前 HKCU 明確設定；若未來要恢復主動 watcher，先評估單 daemon 的 CPU／索引風暴，再由 user 明確同意改環境值。本輪不擅自改。
4. 若 8790 被非 CodeSextant 程式占用，新版會回 `port-conflict` 並停止，不再利用 address reuse 硬綁同埠。
5. 接續產品功能時，現役 Python 先維持；長線預設從 `namegraph.ts` 繼續。

## 6. 關鍵絕對路徑

- 專案：`E:\ai-king\項目資料\CodeSextant`
- 現役 package：`E:\ai-king\項目資料\CodeSextant\codesextant`
- 可靠性測試：`E:\ai-king\項目資料\CodeSextant\tests\test_daemon_reliability.py`
- 啟動註冊：`E:\ai-king\項目資料\CodeSextant\tools\register_windows_startup.ps1`
- Codex Skill：`C:\Users\zerox\.agents\skills\codesextant`
- Claude Skill：`C:\Users\zerox\.claude\skills\codesextant`
- 全域摘要索引：`C:\Users\zerox\.claude\HANDOFF.md`
