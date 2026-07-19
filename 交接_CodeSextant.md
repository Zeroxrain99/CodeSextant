---
tier: 全文
type: 專案交接（三層交接之全文層）
喚起詞: 交接 CodeSextant / 交接 codesextant
updated: 2026-07-18
最後壓縮整理: 2026-07-18（-1 節 07-16 checkpoint 已壓成 3 行；併發根治收於 -3 節）
設計SSOT: E:\ai-king\_AI_BRAIN\05_Planning\CodeSextant_自創代碼地圖神器_設計_2026-06-18.md
---

# 交接 CodeSextant

## -3. 🎉 2026-07-18 多代理併發根治（已換代上線·實測 155× 改善）

**起因**：user「現在很多進程都會同時用這服務 看是否要多開幾個服務埠 或怎樣 根治這問題」。

### 裁決：⛔ 不多開埠（方案 A 駁回）

派紅藍 Opus 各一（皆完成報告），指揮官逐條重算後裁定：

| 方案 | 裁決 | 決定性理由（皆有實測） |
|---|---|---|
| **A 多開 N 個埠** | **駁回** | ① 摧毀 single-flight 合併（實測仍在生效：4 個相同請求只算 1 次）② 無狀態路由 × 有狀態工作＝N=4 時 75% 機率踩冷快取（冷啟 map 曾 523.9s）③ 逐字重演 07-15 事故（`_WATCH_MGR` 是模組級單例＝每 daemon 一個 watcher）④ N 個進程寫同一個 .db＋無鎖 snapshot sidecar＝資料損毀風險 |
| **B 工人進程池** | **接受但降級·改選型·排第二順位** | 方向對（唯一能解控制面 GIL 餓死），但 ⛔**不可用 stdlib `ProcessPoolExecutor`**（無單任務逾時、強殺工人→`BrokenProcessPool`→**在途工作全部連坐失敗**＝把「一人被擋」變「全部被炸」）。前置件已補（見下）。 |
| **C 預建快取** | **接受但降級** | 消費者是「一直在改碼的 AI 代理」，每次 Edit 就失效，且既有 snapshot 是 revision 不合就整份丟＝命中率結構性受限。僅 `/projects` 清單快取值得單做。 |
| **★ 新增第一刀（紅隊提案）** | **接受·升 P0·已上線** | 重工作道是**全機全專案共用一條**＝跨專案隊頭阻塞。改 per-project 分片。 |

### 已上線的改動（4 檔 + 3 個新測試檔·全套 420 綠）

| 檔案 | 改動 |
|---|---|
| `codesextant/work_coordinator.py` | 新增 `ShardedHeavyWork`：per-project FIFO 車道 + 全域併發上限（預設 2）。保留 single-flight 合併與 owner-thread 重入防護。`snapshot()` 聚合時回報**跨分片最久**的工作，維持 supervisor stuck-detection 契約。 |
| `codesextant/daemon.py` | `_route_work_key` 改回 `(key, shard)`；`_execute_route` 傳 `shard=`；`_HEAVY_COORDINATOR` 指向 `SHARED_SHARDED`。 |
| `codesextant/watcher.py` | ⚠**接線半套 bug（WIREDO 閘擋下才發現）**：watcher 的增量重索引原本還走舊 `SHARED_COORDINATOR`＝**第二個互相看不見的權威**——它會逃過全域上限，且跟 HTTP `/reindex` **不再合併**，同一 repo 可能同時跑兩份完整重索引（正是 07-16 修好的「watcher 共用 lane」被改壞）。已遷到 `SHARED_SHARDED` 並傳 `shard`。**`SHARED_COORDINATOR` 單例已整個移除**（留著就是讓後人接錯的陷阱），`HeavyWorkCoordinator` 僅作為分片內部的車道實作。 |
| `codesextant/storage.py` | 新增 `apply_connection_pragmas()`（WAL + busy_timeout + synchronous=NORMAL，三個 env 開關）接到**兩處**裸 connect（`:264`/`:551`，原交接只記一處）；新增 `ProjectStore.open_readonly()`（走 `PRAGMA query_only`，⛔非 `mode=ro`——WAL 庫需建 `-shm`、`mode=ro` 開不起來）。 |
| `tests/conftest.py`（新） | autouse session fixture 把 `CODESEXTANT_HOME` 指到 tmp。**修掉測試污染生產 `supervisor.log`**（見數據校正）。 |
| `tests/test_storage_concurrency.py`（新 7 測） | WAL / busy_timeout / 寫入中讀者不被擋 / 開關可關 |
| `tests/test_storage_readonly.py`（新 6 測） | 唯讀連線拒寫 / 不建庫 / 寫入交易中仍可讀快照 |
| `tests/test_heavy_sharding.py`（新 9 測） | 跨專案不互卡 / 同專案仍序列化 / 全域上限生效 / 合併仍在 / supervisor 契約 / 分片可關 |
| `tests/test_sharded_wiring.py`（新 8 測） | watcher 與 HTTP 共用同一權威 / 舊單例不得復活 / 顯式 0 不得掉回環境預設 / 節流可觀測 / **日誌真的到得了 daemon 檔案處理器** |
| `tools/bench_contention.py`（新·**保留工具非拋棄式腳本**） | 跨專案塞車可複現量測。交接說「先觀察一週」＝接手的人要能跑出同一組數字比對。⚠**中文路徑當參數必走 PowerShell 三通道**（`chcp 65001`＋`$OutputEncoding`＋`[Console]::OutputEncoding`），從 Bash 傳中文 argv 會靜默無輸出（已踩）。用法：`python tools/bench_contention.py --busy <大專案> --idle <小專案>` |
| `tests/test_bench_contention.py`（新 4 測） | 釘住膨脹倍數算式（50.32×／0.77×）＋單次失敗不得中斷＋除零不得編造比值 |

### 實測前後對比（同機同測試·只差程式碼）

| 指標 | 舊碼（pid 15332） | 新碼（pid 42756） |
|---|---|---|
| 小專案便宜查詢（單獨） | 1,486 ms | 624 ms |
| 小專案便宜查詢（**別的專案忙碌中**） | **74,772 ms** | **482 ms** |
| 膨脹倍數 | **50.3×** | 0.8×（無膨脹） |
| `/status`（全日平均 → 換代後實測） | 5,474 ms | 62 ms |

換代程序：停排程 → `python codesextant/daemon.py stop`（優雅停）→ 重啟排程。驗證：8790 恰好一個 listener（pid 42756）、supervisor 43092、功能正確（`/get_symbols` 回 1466 真符號）、single-flight 合併仍在（4 請求 wall 1129ms、彼此差 19ms）。

### ✅ WIREDO 交付閘：四個誤判都已根治（不是繞過，是把閘修對）

原本此閘對本專案報 `code(wired,extensible,defended,observable)` 全數失敗。**四條全部已修在 concinno 源碼裡**（不是把 CodeSextant 改成迎合 regex）。修完實測：六維 **W/I/E/D/O 全 PASS**（22 個本 session 檔案，`wiredo_full_check` 真入口跑出來的）。

| 維度 | 原判定 | 現況 |
|---|---|---|
| **observable** | 真缺陷 | ✅ **已修**：`work_coordinator.py` 零日誌，已補「全域上限擋下」「重工作完成（>10s）」兩行，生產落檔 `重工作完成 /get_health（分片 ...concinno）耗時 116.1s`。⚠ 修的過程犯過**假可觀測**：起初用 `logging.getLogger("codesextant.admission")`＝daemon logger 的**兄弟**、沒處理器、訊息全靜默丟棄，而閘照樣給過（它只看原始碼有沒有 logging 呼叫）。正解＝取名**子代** `codesextant.daemon.admission`。已加 `test_admission_log_reaches_the_daemon_log_handler` 釘住。 |
| **wired** | 「結構性誤判·勿追」 | ✅ **已修（原判定作廢）**：根因是閘刻意不加 `--no-ignore`（怕大工作區逾時），而 `項目資料/` 在 `.gitignore:207`＝整個專案對它隱形。修法＝**全工作區掃到零筆時，改用該檔自己的專案子樹重掃一次並加 `--no-ignore`**（範圍縮到單一專案所以不會逾時）。`wiredo._project_scope_for()` + 兩趟式 `_is_wired_grep`。**同族 bug 一併修**：`orphan.py` 的批次掃描路徑也漏了 `--no-ignore`（單符號路徑有、批次沒有＝自己跟自己不一致）。 |
| **extensible** | 「誤判」 | ✅ **已修**：`DEFAULT_PORT = 8790` 是具名常數＋`CODESEXTANT_PORT` 環境變數覆寫（`daemon.py:250`）＝**教科書上正確的可配置寫法**，卻被判違規。改成逐行判讀 + 三種豁免（行尾註解／上一行區塊註解／同檔有環境變數讀取）。⚠ 順手抓到原本 `(?!\s*#)` 註解逃生口**從來沒生效過**（`\d+` 會回溯成只吃 `3`，lookahead 看到的是 `0`）。另修：`f(timeout=0.0)` 是呼叫端傳參數不是宣告設定，已用 `^` 錨定排除。 |
| **defended** | 「本設定下不可能過·勿偽造」 | ✅ **已修（原判定是錯的）**：證據通道不是被開關 #51 關掉，是**寫入端和讀取端路徑對不上**。寫入端落在 `.concinno_cache/sentinel/sentinel/`（`StateStore` 基底已含 `sentinel`，`record_outcome` 又加一層命名空間），`wiredo` 卻讀 `.concinno_cache/sentinel/`＝沒人寫的空目錄。**疊了三個 bug**：①路徑錯位 ②`record_outcome` 沒寫 `bash_pfx`＝指令身分整個遺失（實測 10 筆全空）③ `calls` 是 10 筆滾動窗，測試跑完再做幾件事就被擠掉。三個都修了，現在生產實測 `has_test_evidence: True`、黏性證據 `{"cmd": "...python.exe -m pytest tests/test_handoff_claim_g", "ts": ...}`。**⛔ 舊交接寫的「不可能過」是我上一輪的錯誤結論，別再引用。** |

**修的過程另外挖出兩個同族真 bug**（都是「查不出來」被折成「確定沒有」＝憑空指控）：

- `wiredo._is_wired_grep` 第二趟回 `None`（工具缺席／逾時）被 `bool()` 折成 `False`＝判定孤島。逾時是間歇的，同一支檔會時好時壞。
- `orphan._batch_check_imported_rg` 例外被靜默吞掉後回全空 dict，而 `has_rg` 只問「rg 執行檔在不在」→ 走訪退路被跳過 → **整批符號全被判成孤島**，且沒有任何一行日誌說掃描其實沒跑完。已改成回 `None` + `_log.warning`。

**效能改良（`c879a20`）**：閘的總時間 **6,145ms → 1,006ms（6.1×）**。瓶頸量出來全在 W 維（佔 99.8%，其他五維加起來 55ms）——它**每個檔各自跑一次 rg**，25 個檔就把整個工作區的目錄樹走 10 遍（每趟 621ms；熱 5.8s、冷 33.6s）。⚠ 誠實記：上面那個兩趟式 gitignore 修法**讓它更慢**（零命中的檔多付一趟）。修法＝抄 `orphan._batch_check_imported_rg` 既有母版（⛔不另造第二套）：一次搜尋全部 stem→只讀命中的檔→純 Python 比對，第二趟也按專案分組批次。25 檔搜尋次數 10→2、判定不變。`test_wired_batch.py` 釘住搜尋次數，防日後悄悄退回逐檔掃。⚠ 量測注意：冷快取 33.6s vs 熱 5.8s 差 6 倍，**別拿冷啟數字當基準**（我第一次差點就據此下錯結論）。

**查證後推翻的假設**（留著省下一個人重查）：曾懷疑 `_is_wired` 的 `"{stem}"` 這條 pattern 太寬、會把「log 訊息裡剛好提到模組名」誤判成已接線＝漏報孤島。**實測不成立**——pattern 要求的是**帶雙引號**的 `"engine"`，`print("starting engine subsystem")` 並不匹配，孤島照樣正確報出。此條無需修改。

**這輪不追的**：R 維「nested loop」對 `for a in A: for b in a.x:`（走訪巢狀資料＝O(總數)）誤判——已改成看內層迭代對象是否來自外層迴圈變數，攤平不報、真的相乘才報。

### ⚠ 數據校正（舊交接與 brief 的錯誤，已坐實）

1. **「fresh subprocess 約 14s」是錯的**（-1 節第 4 條）。實測 `import codesextant.engine` 子進程完整牆鐘 **0.5–1.5 秒**（`-X importtime` 累計 0.33s；純 python 啟動 0.198s）。紅隊獨立測得 0.81/1.35/1.52s。推測原數字量於 07-16 多 daemon 重索引、CPU 打滿時——**它本身就是餓死現象的症狀**，不是 import 固有成本。
2. **`supervisor.log` 裡的 `heavy job stuck ... pid=7 ... active_for_sec=5400.0 -> recycling daemon` 全部是測試污染**，不是生產事故。字面值出自 `tests/test_daemon_reliability.py:1164,1168`，而 `supervisor.py:31` 把 log 寫死在 `default_db_dir()/supervisor.log`。已用 `tests/conftest.py` 根治（跑全套前後 byte 完全不變＝零污染實證）。**既有 11 行假告警保留未刪（刪日誌＝破壞性），讀 log 時請忽略所有 `pid=7` 行。**
3. **推論**：因此「supervisor stuck-recycle 生產可用」**沒有生產證據**——單元測試綠燈，但 `stop_running` 在測試中被 monkeypatch，生產從未真正觸發過。
4. **busy_timeout 原本不是 0 而是 5000**（Python `sqlite3.connect` 預設 `timeout=5.0`）。原描述「未設 busy_timeout」易誤導成「沒有逾時保護」。
5. **藍隊主張「`C:\Python311` 缺 tree_sitter、`/find_duplicates` 靜默降級」＝駁回**。實測 `tree_sitter` 在 `C:\Python311\Lib\site-packages\tree_sitter\`，`clones`/`engine` 匯入正常。

### ⛔ 回滾程序（WAL 是資料庫持久屬性，碼回滾不會回滾它）

程式碼回滾後**必須**另外把已轉檔的庫轉回，否則舊碼會對著 WAL 庫跑：

```powershell
# 1) 碼回滾後，逐庫轉回 rollback journal
Get-ChildItem "$env:USERPROFILE\.codesextant\*.db" | ForEach-Object {
  C:\Python311\python.exe -c "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute('PRAGMA journal_mode=DELETE');c.close()" $_.FullName
}
# 2) 或不改碼、只關開關（不需重轉檔，新碼相容兩種模式）
#    CODESEXTANT_SQLITE_WAL=0 / CODESEXTANT_HEAVY_SHARDING=0
```

WAL 是**惰性轉換**（該庫被新碼開過才轉）。2026-07-18 換代後實測：125MB 庫已轉 `wal`，2.2GB 等尚未被碰的仍是 `delete`。

### 新增開關（皆 env·對齊 L0 鐵律 #6）

`CODESEXTANT_HEAVY_SHARDING=0`（回單一車道舊行為）｜`CODESEXTANT_HEAVY_GLOBAL_CAP`（全域併發，預設 2）｜`CODESEXTANT_HEAVY_QUEUE_CAP`（**現為每分片**，預設 8）｜`CODESEXTANT_HEAVY_FOLLOWER_CAP`（8）｜`CODESEXTANT_SQLITE_WAL=0`｜`CODESEXTANT_SQLITE_BUSY_TIMEOUT_MS`（5000）｜`CODESEXTANT_SQLITE_SYNC_NORMAL=0`

另有 `CODESEXTANT_HEAVY_SLOW_LOG_SEC`（預設 10）＝超過幾秒的重工作才寫一行完成日誌（免得便宜查詢刷版）、`CODESEXTANT_WATCH_STOP_JOIN_SEC`（預設 2）＝關閉時等監看執行緒收工的上限。

**調 `GLOBAL_CAP` 的依據**（新增遙測，`/health` → `heavy_work`）：`global_waiting`＝此刻純粹卡在全域上限的請求數、`global_throttled_total`＝累計被上限擋過的次數。持續 >0 ＝上限是瓶頸可考慮調高；恆為 0 ＝上限沒在綁，調高無意義。⛔ 別靠端到端延遲猜。另可直接看日誌：`grep -E "全域上限擋下|重工作完成" ~/.codesextant/daemon.log`。

### ⬜ 未解決（誠實列，勿當已完成）

1. ⬜ **控制面 GIL 餓死未解**。分片**沒有**把 CPU 工作移出進程；「135s reindex → `/health` 23,646ms」那條因果鏈仍可能重演。換代後看到的 `/health` <31ms 是因為當時的重查詢偏 I/O，**不可當成已修的證據**。真解＝工人子進程（方案 B），且⛔須自管子進程 + 單任務逾時 + 工人隔離重啟，**不可用 `ProcessPoolExecutor`**。前置件 `open_readonly()` 已備好。
2. ⬜ **全域上限預設 2 可能微幅加劇 GIL 爭用**（舊碼是嚴格 1）。實測 4 執行緒對 CPU 工作是 **0.64×**（比循序更慢；藍隊獨立測得 0.78×），4 進程才 1.53×（藍隊 2.02×）。若觀察到控制面變差，先降 `CODESEXTANT_HEAVY_GLOBAL_CAP=1`。
3. ⬜ **單次查詢仍是分鐘級**：`/find_duplicates` 320s、`/find_unwired` 320s、`/get_symbols` 152s、`/impact` 137s。分片只解「排錯隊」，不解「算太久」。
4. ⬜ **`/projects` 19.3s 且不在重工作道**——I/O 綁定（開 37 個庫含 2.2GB），工人進程救不了它，需獨立的清單快取。
5. ⬜ **B 的 pickle 邊界未量**：結果跨進程反序列化是在父進程持 GIL 做的，可能把 CPU 請回父進程。緩解方向＝工人直接回 JSON bytes、父進程只轉發不反序列化。動工前必量。
6. ⬜ **`RotatingFileHandler` 非多進程安全**——走方案 B 前必須先解決工人的 log 通道。
7. ⬜ 版本 SSOT 漂移：`__init__`=0.16.0 vs `pyproject`=0.15.0（ai-usage 線收口時同步）。
8. ⬜ `_get_watch_mgr` 無鎖（production 不可觸發）。

**以下 3 條在 concinno 那條線、不是 CodeSextant**（07-18 修 WIREDO 閘時順手發現，本輪未動——不是我造成的，也不敢猜原作者意圖）：

**全套實測基線（2026-07-18·排除下述 2 個卡死檔）＝`9188 passed / 72 failed / 57 errors`，13 分 25 秒。** 72 條裡只有 3 條是我造成的（`test_wired_check.py`，已修，見下）；其餘 69 條**證實與本輪無關**——那 12 個失敗檔的模組圖全部載不到我改的 4 個模組（`delivery/{wiredo,orphan,artifact_pipeline}.py`＋`sentinel.py`），且改動前的那一輪同樣是 72 failed。**接手時請以這組數字當基線**，別把既有失敗算到自己頭上。既有失敗的兩大族：①品牌改名（測試還期待 `[Concinno: ...]`，程式已輸出 `[AI King: ...]`）②相容殼分歧（如 `concinno.core.subprocess_safe` 自帶一份與 `aiking_core` **不同**的 `_inject_flags`，⛔這是兩份真相源、要挑哪份得原作者定奪）。

- ⬜ **concinno 全套在本機跑不完——3 個測試會走訪真實機器而卡死**（同一族，非我造成）：①`test_auto_update_tier2.py::TestIsInUse::test_returns_sane_tuple` → `psutil.Process.open_files()` 列舉**所有活行程**的檔案握柄 ②`test_destruction_guard.py` → `backup_targets()` 對整棵目錄樹 `os.stat` ③某測試呼叫 `importlib.metadata.packages_distributions()` 掃全部已安裝套件的 metadata。三者都在「讀真實檔案系統／行程表」時停住（雲端同步佔位檔會讓 `os.stat` 阻塞——就是 `_SEARCH_TIMEOUT_S` 註解裡寫的那個坑）。**都是測試設計問題**（想驗回傳值形狀卻要掃整台機器），不是功能壞掉。**替代驗證法**：跑「你改到的檔＋其相關測試」而非全套——本輪即用此法拿到 374 passed。
- ⬜ **`tests/test_a2a_attacks.py::TestPiBenchPolicyCompliance::test_ignore_system_prompt` 失敗**（`blocked=False`，期望 True）。已證與本輪修改無關：`GuardAgent` 匯入的 60 個 concinno 模組**沒有一個**是我改過的。疑似與守門員白名單收斂（開關 #51）有關，未確認。
- ⬜ **`tests/test_profile_fail_mode_overrides.py` 2 條 + `test_preset_cascade.py` 1 條失敗**。這 8 個測試檔原本**整個無法載入**（`concinno.feature_config` 是指向 `aiking_core` 的反向殼，而 `from X import *` 不會匯出底線開頭的私有名字）。已把私有匯入改指向 `aiking_core.*`，**救回 121 個原本完全跑不到的測試**；剩下這 3 條是 rebrand 後的**行為**變更（驗證器不再拋 `ValueError`），需要原作者確認是不是故意的。

### 下一步

先觀察一週分片在真實多代理負載下的表現（看 `daemon.log` 是否還有跨專案等待、`/health` 是否出現 >1s）；確認穩定後再評估是否真的需要方案 B——若控制面餓死不再出現，B 可以不做（96 次重查詢／10.4 小時的真實負載下，B 的 1.5–2× 並行收益不見得值那個複雜度）。TS 重寫線（`namegraph.ts`）不受本次影響。

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
