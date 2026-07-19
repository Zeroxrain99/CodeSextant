# CodeSextant

> **一個常駐本機、零雲端零金鑰的代碼地圖服務——讓你所有 AI 代理共用同一份「真 import 解析」的全局關聯圖，用最少 token 秒懂任何程式碼庫。**

> 品牌＝package＝`codesextant`（全一致）。命名取 **sextant（六分儀）** 的「在代碼大海中定位航向」意象。

寫或改任何實質代碼前，先用它「看一眼全局」：這個符號被誰呼叫、改了會牽動誰、有沒有既有同類函數可重用。**不是讀碼的替代，是讀碼前的導航**——用最少 token 鎖定「該去讀哪幾處」。

---

## 為什麼（痛點）

AI 代理改碼最大的隱形成本是 **token**：不掌握全局就動手＝重寫造衝突、漏改呼叫點、重造已存在的函數。而 `grep`/名稱比對找引用會把所有同名符號當一個，給出高雜訊假關聯（實測在同名多的 repo 誤判率可達 **100%**）。CodeSextant 用 **真 import 解析**（不是文字比對）把這層雜訊濾掉，並把這張地圖做成**常駐單例服務、全代理共用**。

## 核心特色（差異化）

| 特色 | 說明 |
|---|---|
| **真 import 解析、非名稱比對** | Python 走 jedi（懂 import 鏈/scope）、TS/JS 走 ts-morph（findReferences 排除同名干擾）；標 high/low confidence，agent 只在高信心自動信任。 |
| **單例常駐 + 全代理共用 + 不混線** | 全機只一個 daemon（生命週期鎖＋exclusive socket＋探活冪等），所有 AI 代理（Claude/Sancio/Hermes…）連同一個；每專案 `sha1(repo 絕對路徑)` 分庫隔離。 |
| **多語言** | Python / JavaScript / TypeScript / TSX / Go / Rust（tree-sitter 抽符號；找引用 Python=jedi 高信心、TS/JS=ts-morph 高信心、其餘名稱比對誠實退低信心）。 |
| **中文友善面板** | daemon `GET /` 吐自包含中文 HTML（內嵌 CSS+原生 JS、零外部 CDN＝離線可用），給獨立殼／IDE webview 共用。 |
| **本機跑、零雲端、零金鑰** | 比「本機 LSP 工具」更徹底——完全不需任何 API key。 |
| **最少 token 掌握全局** | `get_map` 用 PageRank 給「token 預算內最重要的 N 個符號」。 |

## 快速開始

> 需求：Python 3.11、`pip install jedi tree-sitter tree-sitter-languages`（TS 高信心解析另需 Node + 在 `ts_bridge/` 跑一次 `npm install`，缺則自動退名稱比對、不會壞）。

```bash
# 命令列
python -m codesextant index   <專案路徑>                       # 建/增量更新索引
python -m codesextant map     <專案路徑> [--budget N]           # 全局最重要符號地圖
python -m codesextant references <專案路徑> <符號> [--src-root R] [--def-path D]  # 某符號被誰呼叫
python -m codesextant symbols <專案路徑> [--file F]             # 列某檔符號
python -m codesextant status  <專案路徑>                       # 索引狀態
# 任一命令加 --json 印原始 JSON
```

```bash
# 常駐 daemon（單例、全代理共用）
python -m codesextant.daemon ensure   # 冪等啟動：沒在跑才背景拉起
python -m codesextant.daemon ping     # 嚴格探活（/health brand 比對）
python -m codesextant.daemon stop     # 關掉本機 daemon
# 起來後瀏覽器開 http://127.0.0.1:8790/ 看中文面板
```

Windows 常駐與自癒（冪等，可重複執行）：

```powershell
& 'E:\ai-king\項目資料\CodeSextant\tools\register_windows_startup.ps1'
```

- daemon 以跨行程檔案鎖＋Windows exclusive listen socket 保證全機單例。
- `AIKing-CodeSextant` 排程執行隱藏 supervisor，每 5 秒探活；daemon 退出會自動拉回。supervisor 自身由合法上限 255 次失敗重啟＋每分鐘 heartbeat 雙保險拉回。
- 標準使用者權限建立「登入啟動」；以系統管理員 PowerShell 重跑同一支註冊腳本，會改成「系統開機＋登入啟動」。
- Skill/client 自身也會確保服務；若查詢途中遇到 transport 中斷（傳輸層斷線），會拉回 daemon 並只重試一次。HTTP 應用錯誤不重試。
- 大型 `map` 冷查使用 SQLite covering index（覆蓋索引）＋revision-checked UTF-8 JSON symbol snapshot；完整 map 小結果另存 digest-bound JSON，daemon 重啟後直接命中磁碟，再於程序內留 4 份裁切結果 LRU。快照都只是 cache，索引／參數／相關 env 一變即失效，SQLite 仍是唯一真相源。
- `map` 另有 60 秒冷查 deadline；一般查詢維持 client 自訂 timeout。逾時但 `/health` 仍正常時不重送同一份昂貴工作。

HTTP 端點（全帶 `project=<repo 絕對路徑>`）：`GET /health` `/get_symbols` `/get_map` `/status`（`?fresh=1` 才比對 git 新鮮度）`/projects`；`POST /find_references` `/reindex`。

> ⚠ Windows 傳中文路徑給 native exe（如 `python`）時要三通道全開：`chcp 65001`（argv）＋`$OutputEncoding=[Text.Encoding]::UTF8`（stdin）＋`[Console]::OutputEncoding=[Text.Encoding]::UTF8`（畫面）；PowerShell 讀文字檔另須明寫 `Get-Content -Encoding UTF8`。

## 架構（核心唯一、前端多個）

```
┌── CodeSextant daemon（Python，固定 port :8790，單例冪等、全代理共用）──┐
│   tree-sitter 抽符號 + jedi/ts-morph 真 import 解析                  │
│   + SQLite 增量(content hash + git HEAD sha freshness) + PageRank    │
│   專案隔離：sha1(repo 路徑) 分庫 ~/.codesextant/<key>.db                 │
│   HTTP API + GET / 吐自包含中文面板 HTML                             │
└──────────────────────────────────────────────────────────────────────┘
   ▲ 同一個 daemon、同一份面板，多種殼共用：
   ├ 獨立產品殼（iframe 載面板）   ├ IDE webview（內建）   └ 其他代理（HTTP/Skill 直打）
```

單例冪等保證不管誰先起、全機只一個 daemon——這同時是「全代理共用、不混線」與「企業版團隊共享」的同一個技術基礎。

## 設定 / 開關（環境變數）

| 環境變數 | 預設 | 作用 |
|---|---|---|
| `CODESEXTANT_HOME` | `~/.codesextant` | SQLite 庫目錄 |
| `CODESEXTANT_PORT` | `8790` | daemon port |
| `CODESEXTANT_SUPERVISOR_INTERVAL_SEC` | `5` | supervisor 嚴格探活間隔（秒，最低 1） |
| `CODESEXTANT_MAP_TIMEOUT_SEC` | `60` | `map` 冷查專屬 client deadline（秒；不影響一般查詢） |
| `CODESEXTANT_MAP_CACHE_SIZE` | `4` | daemon 內依 DB revision 保存幾份已裁切 map 結果 |
| `CODESEXTANT_NAMEGRAPH_MAX_FILES` | adaptive | 顯式覆寫 map/namegraph 掃描檔數；未設時依 symbol 數自適應 12~5000 |
| `CODESEXTANT_NAMEGRAPH_MAP_WORK_BUDGET` | `7000000` | 自適應檔數的工作預算分子 |
| `CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES` | `250000` | 單次 namegraph 唯一邊硬上限，防 generated code 吃光 RAM |
| `CODESEXTANT_WATCH_ENABLED` | on | file watcher 主動增量索引；關閉仍有查詢時 content-hash 兜底 |
| `CODESEXTANT_PKG_ROOT` | 內部路徑 | package 所在目錄（Skill wrapper 用） |
| `CODESEXTANT_TS_MORPH_DISABLED` | off | 停用 ts-morph、TS/JS 強制走名稱比對 |
| `CODESEXTANT_TS_MORPH_TIMEOUT` | 30 | ts-morph 子進程逾時（秒） |
| `CODESEXTANT_INFER_LANG_DISABLED` | off | 停用「查無候選定義時取樣推語言」的 fallback |
| `CODESEXTANT_INFER_LANG_SAMPLE_CAP` | 1000 | 取樣語言時掃幾個檔（≤0＝全掃） |
| `CODESEXTANT_INFER_LANG_MIN_RATIO` | 0.6 | 主導語言佔比門檻（未達回保守 jedi） |
| `CODESEXTANT_GIT_FRESHNESS_DISABLED` | off | 停用 git HEAD sha 新鮮度比對 |
| `CODESEXTANT_CSRF_GUARD` | on | POST 端點 CSRF Origin 防護（放行本機/Tauri/IDE webview、擋外部跨站） |

（所有布林開關 `1/true/yes/on` 皆 `.lower()` 容錯。）

## 商業模式：open-core（開放核心）

- **核心免費開源**：搶開發者心智、當多代理生態的內部基礎建設、開源引流（程式碼導航賽道的地板就是免費）。
- **企業版變現**（賣開源版不給的）：多人/多代理團隊共享同一張中央地圖、權限控管＋稽核日誌、私有部署、跨代理框架官方整合與支援。
- **不做**：一次買斷、純個人訂閱。

## 測試

```bash
python -m pytest tests/ -q   # 337 passed（2026-07-15；含 daemon／map 擴展性／snapshot 回歸）
```

## 已知限制 / 誠實邊界

- 找引用要指定對的 `--src-root`（import 根在子目錄的專案，如 `.../src`），否則漏高信心引用。
- 同名符號多時，不指定 `--def-path` 會用第一個候選定義，高信心可能為 0（會列出所有候選）。
- PageRank 品質取決於引用邊密度（`find_references` 按需累積）；冷索引後地圖會隨查詢變準。
- TS/JS 高信心解析需 `ts_bridge/` 跑過 `npm install`，否則自動退名稱比對（不會壞）。
- 索引更新靠 content hash 增量＋git HEAD sha 新鮮度；`status?fresh=1` 可查索引是否落後 HEAD。

---

*內部開發歷史與設計決策見 `交接_CodeSextant.md`、`使用日誌_2026-06-18.md` 與設計 SSOT。*
