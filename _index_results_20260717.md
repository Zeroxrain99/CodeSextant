# 兩 worktree 順序索引＋refs/impact 查詢結果（2026-07-17）

> 交接 §-1 步驟 8 產出。給注入大師 B 線接手用：每個查詢的真 refs/impact 清單。
> 執行方式＝codesextant wrapper（`C:\Users\zerox\.claude\skills\codesextant\scripts\codesextant_query.py`）對現役 production daemon（pid 15744·port 8790·engine 0.16.0）查詢；**全程未重啟 daemon**（交接鐵律遵守）。
> Daemon 健康軌跡：4 次 `/health` 全 200 ok、同 pid 15744（基線 uptime 613s → 收尾 1352s，重工作下無中斷）。

---

## ① E:\ai-king\_worktrees\addonmaster-federation-v1（注入大師）

**索引狀態**：已索引 ✅ 68 檔 / 7213 符號 / project_key `3c79cd4420b28b3e5f910255eaa8b9b3f77e26ed`。增量 reindex：0 檔變動（索引與磁碟同步·0.202s）。

### 1a. renderGameSettings（⚠ JS-in-HTML·codesextant 無法解析，以下為 grep+讀碼補全）

codesextant refs 正式回報：`在 src_root 內找不到 'renderGameSettings' 的 def/class 定義行`（exit 7）——它是嵌在 Python HTML 字串裡的 JavaScript 函數，jedi/tree-sitter 都抽不到（`dist\index.html` 符號數＝0）。以下呼叫鏈為 grep 逐點確認：

**定義（雙份·dist 由 `_make_dist.py` 從 gui.py 生成）**：
- `E:\ai-king\_worktrees\addonmaster-federation-v1\addon_master_gui.py:7453`（權威源）
- `E:\ai-king\_worktrees\addonmaster-federation-v1\dist\index.html:2835`（生成物·⛔別直接改）

**上游（誰呼叫它）**：
- 唯一呼叫點：`openGameSettings()` @ addon_master_gui.py:7442（函數本體 7437-7444）；dist 對應 index.html:2824
- `openGameSettings` 的接線：modbar「⚙ 遊戲設定」按鈕 onclick @ addon_master_gui.py:5798
- 視圖歸屬：`gameSettingsView` div @ gui.py:6125；view 切換 @ 7207；返回/快捷鍵分支 @ 8827

**下游（它牽動誰）**：
- 狀態：`_gsGame` @ 7436（寫入 @ 7454）；GTA5 gate＝inline `_gsGame === 'gta5'` @ 7461（⚠ 計畫 Task 5 說要用 `_isGtaGame(g)`——**該符號目前不存在**，是待新增項）
- DOM：gsBrainCard/gsNoAiCard/gsVoiceCard/gsModFeatCard @ 7456-7459；gsMfAmbientTg/gsMfPoliceTg/gsMfGangTg/gsMfPropTg @ 7472-7475；gsAutoInjectTg @ 7479/7488；gsBrainAutostartTg @ 7500
- 協力 JS 函數：`_renderGsBrain` @ 7445、`_renderGsVoice`（7480/7489 呼叫）
- 後端 API 橋（api.xxx → Tauri 殼 POST /api/xxx → addon_server.HttpApi）：`get_mod_features` @ 7468、`game_settings_get` @ 7484、`settings_get` @ 7497；鄰接 toggle：`toggleBrainAutostart` @ 7508（settings_set/brain_start）、`toggleModFeature` @ 7525

### 1b. group membership 相關（Task 9 遊戲群組聯邦）

**現狀＝零代碼符號**。`group_membership`/`groupMembership` 全 worktree 只出現在 `.superpowers\sdd\progress.md` 與計畫文件。Task 9 待新增檔：`services/conversation_authority.py`、`services/game_groups.py`、`services/local_group_store.py`＋改 `addon_server.py`（見計畫 `docs\superpowers\plans\2026-07-15-addonmaster-b-git-c.md` Task 9）。

**既有掛點（exactly-once 建群要接的 launch 成功路徑）·codesextant 實測**：

- `launch_game` 雙定義：GUI `Api.launch_game` @ addon_master_gui.py:4172、HTTP facade `HttpApi.launch_game` @ addon_server.py:770。
  - impact（addon_server.py 定義）：確定受影響 3（全測試）＝`AddonServerPortIntegrationTests` @ tests\test_addon_server_ports.py:16、`test_gta_launcher_honors_stable_activation_lock` @ :65、`test_pending_incompatible_update_blocks_gta_launch` @ :51。
  - ⚠ prod 呼叫是動態派發（前端 JS `api.launch_game(...)` @ gui.py:9131、9808 → HTTP → HttpApi 反射 dispatch），靜態 impact 看不到——這是真消費者，改簽章時必須同步前端。
- `launch_gate` 雙定義：gui.py:4094（Api）、addon_server.py:760（HttpApi）。refs（addon_server def）：高信心 1 處＝tests\test_addon_server_ports.py:109；contract 登記 @ services\http_api_contract.py:54；名稱比對 22 命中經 jedi 精解只 1 真引用（誤判率 95.5%）。
- 真正 launch 執行體：巢狀函數 `_do_launch` @ addon_master_gui.py:4183（`Api.launch_game` 內背景緒；launch 成功點＝Task 9 建群掛點）。`_LAUNCH` 全域狀態 @ 4178-4182。

### 1c. webhook verification 相關

**本 worktree 無 webhook 代碼**（grep `webhook` 只中計畫/設計文件）；webhook fail-closed 是 PF 側 Task 7（見 ② 節）。本 worktree 最接近的「verification」既有面＝Task 1 本機橋接認證（已實作於 addon_server.py）·codesextant 實測：

- `_trusted_local_origin` @ addon_server.py:999 — refs 高信心 3 處（✅ 可靠度高）：addon_server.py:1023、:1045、:1129。
- `_authorized` @ addon_server.py:1029 — impact：prod 2＝`Handler` @ addon_server.py:1020、`do_POST` @ addon_server.py:1122。
- 相關：`_bind_http_server(candidates, api_token)` @ addon_server.py:1177；CORS `Authorization` header @ :1027；測試 `tests\test_local_bridge_auth.py`。

### 1d. brain_backend_*（⚠ 實際住在本 worktree、非 PF——見 ② 的查無結論）

檔案：`brain\brain_backend.py`（97 符號）、`brain\brain_backend_options.py`（18 符號）。import 根＝`E:\ai-king\_worktrees\addonmaster-federation-v1\brain`（flat `import brain_backend`）。

**消費者（import 層·grep 確認）**：brain\brain_server.py:198（`import brain_backend as _brain_backend`）、brain\brain_detect.py:55、brain\brain_selftest.py（30+ 處）、brain\brain_backend_options.py:272（反向 import `_resolve_key`）、tests\test_bundled_brain_selftest.py:553；brain_backend_options 消費者＝brain_server.py:1411/1418/1660。

**`dispatch_think`（主入口）@ brain_backend.py:1645 — refs 高信心 17 處（✅ 可靠度高·jedi 從 33 名稱命中精解出 17 真引用）**：
- prod：brain\brain_server.py:524（`chat_think` 內·brain_server.py:504 起）
- selftest：brain\brain_selftest.py:1007/1024/1046/1077/1082/1088/1100/1125/1247/1256/1278/1284/1291/1386/2307/2349

impact：確定受影響 11（`chat_think` @ brain_server.py:504 ＋ selftest 10 個 test 函數：test_backend_rule_echo_passthrough:999、test_backend_mock_normal:1016、test_backend_timeout_falls_to_echo:1033、test_backend_consecutive_error_cooldown:1056、test_backend_cooldown_disabled:1109、test_persona_scope_enforced_in_dispatch:1225、test_persona_scope_rule_echo_path:1267、test_backend_illegal_action_gate:1373、test_2b_never_attacks_player:2287、test_anti_jailbreak_fail_closed:2317）。⚠ daemon 把 brain_selftest.py 歸類 prod（路徑不在 tests\ 下）——實質是自測。

**`brain_status` @ brain_backend.py:240 — refs 高信心 3 處**：brain_backend.py:1829、brain_selftest.py:1479、brain_server.py:1640。（低信心 18 處多為同名 method 干擾·⚠ 可靠度中）

**brain_backend.py 關鍵符號（給 B 線任務 3 供應商 service 對照）**：`dispatch_think`:1645、`brain_status`:240、`_ADAPTERS` 表:1624、`call_deepseek`:1238、`call_openai_compatible_direct`:1274、`call_anthropic`:1363、`call_pod_gemma`:1418、`call_bridge`:1457、`call_king_router`:1485、`call_custom_endpoint`:1501、`call_persona_api`:1520、`call_psyche_sdk`:1538、`call_psyche_console`:1560、`call_mock`:1609、`should_skip_backend`:210、`set_context_builder`:1803、`_resolve_key`:306、`_custom_endpoint_ssrf_guard`:439。

**brain_backend_options.py 關鍵符號**：`handle_backend_options`:268、`resolve_key`:274、`handle_backend_switch`:290、`handle_backend_config_set`:310、`_live_models`:160、`_CATALOG`:31。

---

## ② E:\ai-king\_worktrees\psycheforge-federation-v1（PsycheForge）

**索引狀態**：已索引 ✅ 1227 檔 / 19875 符號 / project_key `e3d501307e684f896f92f8e34859cace08544411`。增量 reindex：0 檔變動（1.006s）。

### 2a. brain_backend_* — **查無（正式結論）**

codesextant refs 正式回報：定義未在索引庫（958 檔名稱比對 0 次命中）；grep（含大小寫變體 `brain[_-]?backend`/`brainBackend`）同樣 0 命中。**`brain_backend_*` 不存在於 PF worktree——它住在 worktree ①的 `brain\` 目錄**（見 1d，已補跑完整 refs/impact）。B 線接手時別在 PF 找這族符號。

### 2b. webhook verification（Task 7 item 2 的真實既有面·PF 是 TS→codesextant 退名稱比對低信心，以下以 grep+讀碼為準）

**管線核心**：`handleWebhook` @ src\pipeline\webhook-handler.ts:350（export async function；後端聊天統一母版）。呼叫端（grep ground truth）：
- src\index.ts:51（import）、:1073（直呼）、:2113（注入 task-consumer cfg）
- src\router\task-consumer.ts:135、:266、:381（`cfg.handleWebhook`；:66 註明「三處呼叫裸奔無鎖」既有 B-掃描發現）
- 自遞迴 @ webhook-handler.ts:402
- ⚠ daemon TS name-match 只回 console\src\lib\api.ts:966 一筆＝**漏報**（TS 無 ts-morph 真解析引擎·勿信 daemon 的 TS refs 清單，以本節 grep 為準）。

**簽章驗證接線（Task 7「Webhook fail closed」的現場）**：
- 契約：`PlatformAdapter.verifyWebhook(headers, body)` @ src\adapters\types.ts:102
- 唯一 runtime 呼叫點：src\api\platform-webhook-routes.ts:136（route `POST /webhook/:platform/:character` @ :124，註冊函數 `registerPlatformWebhookRoutes` @ :119）
- 實作（四平台全是「presence-only」弱檢查）：line-adapter.ts:169（只驗 header 存在·:174 `return signature.length > 0`）、wechat-adapter.ts:93、telegram-adapter.ts:112（`_headers` 直接忽略）、discord-adapter.ts:88（只驗兩 header 存在）
- **強驗證器已寫但零接線（未接線＝Task 7 要收口的核心）**：`LineAdapter.verifySignature`（HMAC-SHA256）@ line-adapter.ts:181、`WeChatAdapter.verifySignature`（SHA1）@ wechat-adapter.ts:104、`DiscordAdapter.verifyEd25519` @ discord-adapter.ts:99——grep 全 repo（排 node_modules）無任何呼叫點（packages\infinite-agent 的同名 `verifySignature` 是另一符號·agent-comm.ts:162·勿混淆）。
- **fail-closed 缺口二**：platform-webhook-routes.ts:135 `rawBody = JSON.stringify(request.body)`——用重新序列化的 body 當「raw」＝**非原始 bytes**，與計畫 Task 7「驗 raw bytes/signature」直接對應；且 :143 驗不過仍回 200 `{status:'ok'}`（吞掉不拒）。
- 另一入口：src\pipeline\sdk-handler.ts（`handleSdkChat` 薄殼→handleWebhook；見 `_設計_聊天統一母版_世界私人AI_2026-06-13.md:20`）。

### 2c. group membership 相關既有符號（供 Task 7 item 4「Native group」對照）

PF 尚無 `tenant/platform/group` namespaced group store（待新增）。既有鄰接面：
- `src\cognition\faction-service.ts`（faction membership·AI 世界行為用·「── Membership ──」段 @ :132）
- `src\api\community-routes.ts`（`GET /api/community/:id/is-member` @ :110）
- 這兩者是「社群/派系」語意，**不是** Task 7 的群組權威——別直接挪用，但新 group store 落地時要檢查與它們的命名/路由衝突。

---

## 查詢方法與信心標註（誠實邊界）

- Python 側（worktree ①）＝jedi 真解析·高信心清單可直接信任（各查詢誤判率對比已列）。
- TS 側（worktree ②）＝daemon 無 ts-morph→名稱比對低信心且**實測漏報**（handleWebhook 案例）；本報告 TS 部分一律以 grep+讀碼 ground truth 為準。
- JS-in-HTML（renderGameSettings）＝兩引擎都抽不到符號；grep 補全。
- impact 的 prod/測試分類是路徑法（brain_selftest.py 被算 prod）；靜態鏈看不到 HTTP 反射派發（HttpApi）與動態呼叫——改簽章前仍須讀受影響處＋跑 pytest。
- Daemon 全程健康：4 次 /health 皆 200 ok·pid 15744 未變（未重啟 production daemon·遵守交接鐵律）。
