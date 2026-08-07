# CodeSextant 資產登記表（⛔ 刪除任何一項前先讀完本檔）

> 建立於 2026-08-07。本目錄是 CodeSextant **所有非程式碼資產的唯一集中地**。
> 站長指令（2026-08-07）：「資產保護好，要放一起，不要又被清道夫刪除，東西不要亂放，最好統一放在 項目資料/CodeSextant 裡面」。

## ⛔ 先讀這段：本目錄**沒有版控**，刪掉就永久消失

整個 `_assets/` 被 `.gitignore` 排除（理由見下表各項）。這代表：

- ⛔ **沒有 `git checkout` 可以救回來**，沒有 remote 備份，沒有回收桶保證。
- ⛔ **「gitignored」不等於「可拋棄」** —— 這裡每一份都是**證據級產物**，不是快取。
- ⭐ 真正的保護只有這份登記表：想刪的人會先撞到它，看到每份的重建成本與依賴。

## 資產清單

| 目錄 | 體積 | 是什麼 | 能重建嗎 | 刪除後果 |
|---|---|---|---|---|
| `adjudication/` | 150 MB · 659 檔 | G4.3 外部審查證據 —— reviewer/custodian 的 candidates 與 2-of-3 裁決輸出（`candidates-reset-v2-1`…`v4-1`、`custodian-reset-v4r1-k` 等） | ⚠ 理論上可重跑，但需重新跑完整 adjudication 流程；revision-4r1 的 4,249 rows 是**已定案的否證證據**，重跑不保證得到同一批 | G4.3「H1 已被證偽」失去原始證據，結論退回未驗證 |
| `holdout/` | 672 KB · 6 檔 | 正式 holdout 資料集（`impact/map/miswires/navigation/references/symbols.jsonl`） | ⛔ **不能** —— 這是盲測答案 | 整條 G4 benchmark 失去評分基準；⛔ 這是本目錄**最不可替代**的一份 |
| `wip-snapshots/` | 382 KB | worktree 未提交變更的時點快照（見下節） | ⛔ 不能（原檔本身就未提交） | 見下節 |

### `holdout/` 的額外禁令（來自交接 §3）

- ⛔ **產品/root 實作者不得開啟** 這裡的 case JSONL —— 只能看聚合值與 digest。開了就污染盲測。
- ⛔ **不得進 git、不得上 GitHub** —— 產品 repo 有 public remote（`Zeroxrain99/CodeSextant`），推上去等於把答案公開。
- ⚠ 交接 §3 另註：正式 `benchmarks/ground_truth/holdout-manifest.json` **並不存在**；本目錄不是已封存的 manifest。

### `wip-snapshots/codesextant-sota-gate-20260807-1546/`

worktree `codesextant-sota-gate` 在 2026-08-07 15:46 的 **8 項未提交變更**副本（含 `benchmarks/adjudication.py` 48 KB、`tests/benchmarks/test_adjudication.py`、`benchmarks/ground_truth/`）。

- **為什麼存在**：那 8 項在原 worktree 裡是 modified/untracked 狀態，**未提交＝無任何版控保護**，一個 `git checkout .` 或 `git clean` 就永久消失。交接 §3 又明令不得 reset/stash/checkout/`git add -A`，所以只能複製、不能提交。
- ⛔ **這是副本不是真相源**。真相源是 worktree 本身。要改就改 worktree，⛔ 不要改這份快照，也⛔ 不要拿它覆蓋回去（會蓋掉之後的進展）。
- 快照當下的 branch / HEAD / `git status` 全記在同目錄 `_SNAPSHOT_PROVENANCE.txt`。

## 索引資料庫**不在這裡**（刻意的）

CodeSextant 的 SQLite 索引在 `~/.codesextant/<sha1(repo絕對路徑)>.db`，**不搬進來**，因為 `storage.py:49 db_path_for()` 是用 repo 絕對路徑算 sha1 定位的，搬走等於讓程式找不到（除非設 `CODESEXTANT_HOME` 環境變數）。

現況（2026-08-07）：

| 檔 | 對應 repo | 體積 |
|---|---|---|
| `8c24fd8362c9…db` | `E:\ai-king\項目資料\CodeSextant\.worktrees\codesextant-sota-gate` | 133 MB |
| `ae7dc3bc1cbc…db` | ⚠ 來源不明（sha1 不可逆，未對上任何已知路徑） | 98 KB |
| `dc29d092eac3…db` | ⚠ 來源不明 | 938 KB |

- ⭐ **索引可重建**（re-index 即可），所以它是本專案唯一「真的能當快取看待」的資產。
- ⚠ 但重建要數小時。交接 P1 第一條「Re-index first」講的 570,651 symbols / 2.33 GB 版本目前**確實不在**（現存最大的只有 133 MB）。
- ⚠ **路徑一改，sha1 就變，舊索引會「查不到」而不是「被刪」** —— 診斷「索引不見了」時先正算 sha1 比對檔名，別直接重跑。

## ⛔ 澄清：清道夫（scavenger）不是兇手（2026-08-07 查證）

站長懷疑資產是被清道夫刪的。逐項查證後**否證**：

- `scavenger` 排程 **2026-07-02 就已停用**（`schedule_config.json` → `"enabled": false`，理由是連日 budget-exceeded）。⛔ 該註記還明寫「別重新 enable、別重新註冊」。
- 接手的 `deep-clean`（週六 Opus 四段）刪除範圍**只有** `E:\ai-king` 底下的 `_temp_*` / `*.bak` / `*backup*`，且要求逐一確認無活躍引用。
- `daily-tidy` 完全沒有刪除動作。
- **沒有任何排程掃得到** `E:\codesextant-*` 或 `~/.codesextant`。

⭐ 所以真正的機制不是「被排程刪」，是**這些資產從來就沒有任何版控或備份**，任何人（含 AI 代理、含手滑）誤刪即永久消失。本登記表是針對這個真實機制的對策，⛔ 不是針對清道夫。

## 搬遷紀錄

| 時間 | 原位置 | 現位置 | 驗證 |
|---|---|---|---|
| 2026-08-07 15:55 | `E:\codesextant-adjudication` | `_assets/adjudication/` | 659 檔 / 155,614,331 B 搬前搬後一致 |
| 2026-08-07 15:55 | `E:\codesextant-holdout` | `_assets/holdout/` | 6 檔 / 673,560 B 搬前搬後一致 |
| 2026-08-07 15:46 | worktree 未提交變更（複製，原檔未動） | `_assets/wip-snapshots/…-1546/` | 16 檔 / 382 KB；原 worktree 仍為 8 項變更 |

引用這些路徑的文件（搬遷後已更新指針）：`_AI_BRAIN/06_Handoffs/codesextant/交接_2026-07-24.md` §4、`交接_archive.md`、`_AI_BRAIN/05_Planning/codesextant_g43_*.md` ×2。
產品程式碼、`benchmarks/`、`tools/`、worktree 內**均無**硬寫死這兩個路徑（2026-08-07 掃過）。
