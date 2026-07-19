# CodeSextant 星圖「美＝全面 Clean Code 品質」加分項 — 紅藍 CBUA 最佳解（權威 SSOT）

> tier: 全文
> 狀態：紅藍對抗收口完成 + **user 已拍板（2026-06-22）**：①產品定位＝**A 結構健康星圖**（D12 變數收斂/D13 UDT 不擴引擎、誠實標「需 data-flow/語意、超純靜態鐵律、不進視覺」）②權重＝**preset 三檔（嚴格/平衡/寬鬆）+ 各維度 enabled 開關 + panel 顯原始分**③產品哲學＝星圖診斷地圖 + panel 逐項診斷（採納）。
> ⚠ 落地起點＝§4 的 **P0.5 join 地基**（後端 health 落盤、驗 fingerprint 覆蓋率、不上視覺）→ P1 sat → P2 alpha → P3 複雜度。D12/D13 整條不做。
> 真檔已親讀核對（symbols.py / clones.py / ranking.py / engine.py / group_in_box_v3.py / graph-common.js / poc-a-webgl2.html / poc-b-webgpu-tsl.html，逐行驗證紅藍引用無誤）
> ⛔ 禁推翻基底（前序紅藍 + PoC 已落地）：美=模組化 smoothstep 連續閘、結構決定形狀 spectral 確定性、group-in-a-box + per-社群 beauty、singleton 帶、tidy/spiral、左旋手性 opt-in。

---

## §0 一句話總結

**位置永遠只吃結構（modularity，最可信通道、物理上最不可 game）；clean-code 品質只能往「醜」方向、走末位感知通道（飽和/透明）、復合成單一 health 後映射、honest UNKNOWN 一律中性；用戶最想要的兩維（變數收斂 D12／UDT D13）誠實標「靜態算不到、零輸入、不進視覺」，產品宣稱因此須誠實降級為「結構健康星圖」或評 CP 值另立 data-flow 引擎擴充提案——絕不可宣稱「美＝全面 clean code」又把用戶兩核心訴求踢出視覺。**

---

## §1 總裁判裁決摘要

### 1.1 命門去重後的真實規模

紅隊跨 4 lens（可行性／Goodhart／視覺過載／確定性效能）+ 藍隊 3 視角，原始 findings 約 40 條，但**同一根因被多 lens 重複計分嚴重通膨**。去重後 distinct 命門 **約 13 條**，且**全部是 need_change（明確工作項）或回拋拍板，無一條能 reject 整個設計**。基底（美=模組化 smoothstep + spectral 確定性 + per-社群 beauty）完全成立，用戶願景合理。

藍隊揭穿的紅隊嚴重度通膨（採信）：
- 同一個「point-sprite 渲染器畫不出 per-node 幾何/紋理」根因，被當 4-5 個獨立 FATAL（形狀刺狀/裂紋、虛胖暈、不規則邊）→ 合併為**單一裁決：刪除所有需 per-node 程序化紋理/幾何的視覺通道**。
- 同一個「health join 缺失」根因散在多 lens → 合併為**單一 Phase 0.5 地基工作**。

### 1.2 逐條 FATAL/MAJOR 裁決（5態 + framing + 證據）

| # | 命門（去重後） | 嚴重度 | 5態裁決 | framing + 證據 |
|---|---|---|---|---|
| **C1** | **D12 變數收斂零輸入**：symbols.py 連函數內區域變數都不抽（`not scope_parts` 硬 gate），panel 降級也是 vapor | FATAL | **接受（改寫為「未實作能力非降級」）** | 場景前提真實。親驗 symbols.py:423 `elif node_type in varkinds and not scope_parts`、:436 `and not scope_parts` — 變數只在模組頂層抽，函數體零區域變數輸入。草案§8#1「降級為 panel 弱提示」假設輸入存在=事實錯誤。非天花板、是**能力缺口**。→ D12 標「零輸入、需從零建區域變數抽取層」，拆成獨立引擎擴充提案，不混進交付。 |
| **C2** | **health join 缺失**：symbol_id 4部鍵 vs fingerprint 2部鍵無 1:1、小符號無指紋→多數節點 health=UNKNOWN=滿分=vapor | FATAL | **接受（補 Phase 0.5 地基）** | 親驗 ranking.py:88 `f"{path}::{scope}::{name}::{line}"`(4部) vs engine.py:1199 `{(m["path"],m["line"]):m}`(2部)；clones.py:299 `min_node_count=15`、:313 只對 function/method 抽指紋 → 小 getter/dataclass/re-export 無指紋列。草案§2「UNKNOWN→0」使這些節點 health=1 滿分=加分項感知有效性歸零。**這是 health 上線與否的最上游地基**，非無解=補 join 層即可。 |
| **C3** | **形狀/紋理通道 point-sprite 物理做不到**：刺狀/裂紋/重複紋理需 per-node shader 或換 instanced mesh=渲染管線重寫 | FATAL | **接受（刪除整個形狀連續通道）** | 鐵證：poc-b-webgpu-tsl.html:109 設計者自己血淚註解「Points 無 sprite uv attribute（uv() 警告 not found on geometry）→ 圓點做不出」；poc-a:72 `gl_PointSize` point sprite；v2/v3-stunning.html:160/180 「sizeNode 在 WebGPU 無效＝全 1px」issue #30612。雙 PoC 連圓點都畫不出。草案當「P2 加 shape buffer」=把物理不可能包裝成 roadmap=switch#27/#28 vapor 前例。 |
| **C4** | **拆假函數 game 緩解被公式證偽**：「拆函數→Q降→位置糊」依賴的因果反向（緊密小函數同社群→qc 反升→位置更美） | FATAL→降 MAJOR | **接受（刪除失效緩解、複雜度移出 sat 只進 panel）** | 親驗 group_in_box_v3.py:60 `per_comm_modularity` qc=e_in/m-(deg_sum/2m)²、:51 louvain seed42 互呼叫歸同社群、:90 `R_ci=R_GLOBAL*strength*(0.12+0.83*beauty)`。拆出 trivial 小函數緊密互呼叫→e_in↑→qc↑→beauty↑→半徑推遠（位置更美）=health 升+位置美雙贏 game。降 MAJOR 因藍隊正確攻回：複雜度仍是 SOTA 有效信號（SonarSource cognitive complexity），命門在「走哪個通道」非「該不該量」。 |
| **C5** | **D2/D3/D4 複雜度=從零造跨語言控制流子系統**，非「填一欄」；且 `_CONTROL_FLOW` 白名單已自承 Go switch 系統性誤判 | FATAL→降 MAJOR | **接受（重標獨立子系統 + per-language 信心降級 + 三選一只留 D3）** | 親驗 clones.py:197-211 `_metadata` 只有 node_count/nstmts/has_cf 單 bool、無深度狀態無分支計數；:52-53 設計者紅隊註解「Go 普通 switch 解成 expression_switch_statement…has_control_flow=False 被當 boilerplate 系統性誤壓制」、:60 事後補列證明白名單脆弱。cognitive complexity 需帶深度狀態遞迴 walker。降 MAJOR：先只對 jedi/ts-morph(Python/TS-JS) PoC 驗 CP 值，其餘語言該維度 UNKNOWN 中性。 |
| **C6** | **D3 用戶 D12/D13 算不到 vs 「美=全面 clean code」承諾落差** | FATAL（deviates_from_user_intent，永不入 pruned） | **反問態 → commander_flagged_for_human** | 反漂移錨：用戶 prompt #1#2 明確點名兩維恰是純靜態鐵律下最算不到的（D12 需 def-use+alias/points-to/SSA、動態語言 undecidable；D13 需語意）。技術裁決「不進視覺」正確（SOTA frama-c conservative may-alias、USPTO 10127133 possibly redundant 背書），但宣稱「美=全面」又踢出核心訴求=承諾落差。**舉證可行性：擴 data-flow 層技術可行但 CP 值未知、且必對合法條件式（SSA φ-join）誤報。回拋 user 二擇一拍板**（見§7）。 |
| **C7** | **sat+alpha 雙載 D6 死碼**：又灰又透明=過度懲罰、死碼隱形喪失「該被看見去刪」診斷價值、與「分通道不互搶」自相矛盾 | MAJOR | **接受（D6 只走 alpha + 下限、sat 排除 D6）** | 草案§2 sat=health(含 w_dead=0.25 D6)+alpha=D6=同一指標跨兩通道累加。非盤點 R4「冗餘編碼強化辨識」（那是同度量同向提升正確率 color+shape 88% vs 純 color 66%），是當兩個獨立扣分源。死碼 alpha 設下限≥0.3-0.35 保「可見但脫團」。 |
| **C8** | **size 子通道腫脹**：與 size=rank 語意衝突（大≠重要）+ size×sat 半整合壓制 + 正當大型協調節點被誤標腫脹 + 虛胖暈同屬 vapor | MAJOR | **接受（size 純留 rank、腫脹併入 sat 復合分量）** | 親驗 graph-common.js:80 `siz[k]=(isAux?2.4:4.5)+(n.rank||0)*(isAux?6.0:20.0)` 純 PageRank。盤點 R4 size+color 半整合（大球壓制小球顏色辨識）。核心 dispatcher rank 高+node_count 大會被誤標腫脹醜=假陽性 + 誘導拆協調器（又一拆假函數誘因）。 |
| **C9** | **D1 分位數相對基準破壞局部確定性 + 絕對品質語意**：加無關檔改全圖、屎山裡爛碼反顯乾淨、反向 game（塞大檔推 P95） | MAJOR | **接受（改絕對閾值 smoothstep(T_lo,T_hi)）** | 草案§1 D1=clip((node_count-P50)/(P95-P50))。與用戶願景「漂亮=乾淨（絕對品質）」直接對立：同 200 行函數在屎山顯瘦、塞 vendored 大檔推高 P95→既有中等函數變鮮豔=讓專案更爛能讓既有碼顯美。雖同 sha 仍確定但破壞 per-file 可歸因（星圖核心用途）。 |
| **C10** | **P0「sat 算進 col 既有 buffer」污染社群 hue 基底**：health 有多缺陷、算錯直接污染已驗證社群配色（基底禁推翻） | MAJOR（確定性/整合 lens 升 FATAL） | **接受（P0 改獨立 sat buffer 或純後端落盤、永不碰 col）** | 親驗 graph-common.js:43 `hslToRgb(hue,0.85,0.62)`、:76-77 `col[k*3]=c[0]…` col=nodeColor=社群 hue 唯一載體、:130 `return {N,E,C,pos,col,siz,lpos,lcol}` 無 sat buffer。基底鐵律 hue 留社群身分禁推翻。既然 C3/C7 證形狀/alpha 遲早動 shader，P0 一次把 sat 獨立做對反省 P0→P1 返工。 |
| **C11** | **權重拍腦袋 + 暴露 switch 兩難**：user 可調權重把差維度調 0 顯漂亮=把 Goodhart 防護開關交給被測者 | MAJOR | **接受但降級（preset 非自由調參 + 落盤審計）→ needs_user_decision** | 草案§2 w_dup=0.25 等全建議值、§7#8 自承糾結 L0 鐵律#6。藍隊正確：市場（CodeScene 官方預設+可選 metric）證明非死結。解：per-dimension enabled 可關（誠實降級非 game）+ weights 用離散 preset（嚴格/平衡/寬鬆，無法精準歸零單維）+ 落盤進 graph JSON meta + 截圖浮水印顯權重組 + panel 永遠顯原始未加權各維分數（堵 game 後門）。對齊 L0#6 須 user 拍板例外。 |
| **C12** | **canary synth 設計者手挑爛碼=自證預言**：只驗符合設計者直覺非真捕捉 clean code | MAJOR | **接受（改外部 ground truth）** | 草案§6 破口6.2 自承。違反 CBUA「外部信號非自評」鐵律（MEMORY feedback-cbua-rearch-external-ground-truth）。改用公認乾淨庫（requests/flask）vs 已知 bug 密度/CVE 史/code-smell 標註屎山庫，外部 ground truth 當裁判。synth 保留當回歸測試（同 sha 同視覺）不當「美=乾淨」真驗收。 |
| **C13** | **D9 instability 粒度錯配**：模組層級指標套符號節點、社群層已被 modularity 佔=無正確落點 | MINOR | **駁回（直接砍出路線、housekeeping 非設計分叉）** | 草案§7#1 自承「可能根本不該做」卻仍排 P3 + §1 信心標「中」=自相矛盾。instability I=Ce/(Ce+Ca) 是 package metric（wikipedia software_package_metrics）。砍出設計，§1 表標「無正確視覺落點、不做」，§6 移除 P3 的 D9。 |

### 1.3 降級/駁回的 framing 修正（防雙向偏袒）

| 紅隊主張 | 裁決 | 理由 |
|---|---|---|
| R3(可行性) test 節點「NaN 退原點(0,0,0) 卻帶鮮豔色」FATAL | **降 MAJOR** | 藍隊親驗證偽：group_in_box_v3.py:44 prod 排除 is_test、但 :102-111 test 節點收進專屬測試帶外圈 R_GLOBAL*1.45、:113 `assert np.isfinite(coords).all()` 全圖通過（**非 NaN**）；graph-common.js:51 已硬寫 `Ltest→[0.30,0.32,0.38]` 暗藍灰、:79-80 isAux 縮小。test「中性灰」現狀已做到。真殘留只剩一行 guard（health sat 疊加別覆寫既有 Ltest/Lsingleton 灰）→ 收進 C7 同批處理。 |
| R1(Goodhart) 「把品質做成可看見的美=Goodhart 最上游、measure 變 target、自毀」FATAL | **降為產品定位 note（needs_user_decision）** | 過度上綱用戶願景本身。基底已物理鎖死：位置（Cleveland-McGill 最高精度通道）永遠只吃 modularity、clean-code 只能用末位 sat/alpha → **無法只靠調 clean-code 維度把結構爛的圖變第一眼漂亮**（位置已被結構鎖死）。R1 真貢獻=UX 收口（panel 優先/軟通道低強度/文案明說美是副產品），全採納為產品定位決策、非設計阻斷。 |
| R5/R8 「往醜扣分=往美加分=數學等價=話術」 | **降級措辭、非命門** | 邏輯對但結論過頭。攻的是從未承擔主防護責任的子原則2。真主防護=子原則1（位置不吃 clean-code 分數，消最強座標 game 梯度，SOTA Cleveland-McGill 背書）+子原則3（多指標復合無單一清晰梯度）未被駁。單向扣分降格為「降低（非消除）灌水相對收益」輔助效果。 |
| R7(確定性) 「多軟指標復合 sat 可診斷性歸零」MAJOR | **降為 UX 增強** | 是已知設計取捨（防 Goodhart 無個體梯度 vs 可診斷性，草案§7#10 自承）非 bug，panel 已是 fix。採 R7 好建議：hover/點節點時顏色高亮「該節點最差的單一主導 smell」（非全復合），星圖答 where 髒、panel 答 why 髒。 |
| R11(確定性) 「position 鎖結構→漂亮=乾淨有感知天花板」needs_user_decision | **降為誠實告知（基底必然推論）** | position 鎖結構是用戶禁推翻的基底之必然，非缺陷。且與 R1 Goodhart 防護**正向互補**：clean-code 用弱通道恰好讓它無法成搶眼 game 信號。§7 誠實標：第一眼由模組化主導、clean-code 是第二層感知。 |

### 1.4 Pruned 復活清單（抽驗誤殺）

抽驗 4 條 pruned（紅隊自剪 + 對抗篩選），**無一誤殺，全部正確降級且建議已被吸收**：

| Pruned | 原判 | 抽驗結論 |
|---|---|---|
| R11(Goodhart) canary 獨立性 | downgraded by gate2_market_norm | ✅ 正確。建議（第三方庫對照+數值門檻）已吸收進 C12 fix。屬「要求更嚴謹的市場驗收標準」=閘2 只降不 DROP，且與既有破口6.2 高度重疊。 |
| R9(確定性) 「往醜扣分=話術」核心原則指控 | downgraded by gate4 | ✅ 正確。框架性指控部分臆測（草案已自承等價並補實質差別「乾淨碼預設滿分不需灌水」）；D7 移出視覺的有效建議已吸收進 C7 鄰近的 D7 處理。 |
| R9(整合) D9 「無落點該砍非延後」 | downgraded by gate4 | ✅ 正確。閘4 部分不成立：instability 在「檔/模組層級」有正確落點（CodeScene/CodeCity 先例），是「落點需對齊」非「無落點」。最終裁決仍砍出星圖視覺（C13），但保留「若做只在裝盒/檔層級或 panel」的誠實選項。 |
| R10(整合) canary 真實屎山 | downgraded by gate4 | ✅ 正確。重述設計者已內建 caveat（§6破口6.2/§7#9/§8），建議已併入 C12。 |

⚠ 特別抽驗：無任何 pruned 帶 `sota_unverified`/`weak_evidence`/不可逆 flag 被誤殺。`weak_evidence` 的 R5/R12 均已正確保留為 MINOR/輔助、非 DROP。

---

## §2 最終設計（追溯用戶期許 + 量化公式 + 通道 + 誠實標 + Goodhart 防護）

### 2.0 設計總綱：三子原則（紅藍收口後修訂版）

> **位置＝結構真相（只吃 modularity）；其餘 clean-code 品質一律往醜扣、走末位感知通道、復合 health、honest UNKNOWN 中性。**

1. **通道分權（主防護·SOTA 背書）**：位置（Cleveland-McGill 最高精度通道）永遠只由 modularity/spectral 驅動。clean-code 只能用次要通道。**這是物理上消除最強 game 梯度的根本機制**——你無法只靠調 clean-code 維度把結構爛的圖變第一眼漂亮。
3. **復合 health（主防護）**：所有 per-node 軟指標加權復合成單一 `health∈[0,1]` 再映射，多指標互有張力、game 一個被另一個扣回、無對單一條優化的清晰梯度。
2. **單向扣分（輔助·非主防護）**：clean-code 只往「醜」作用。**誠實措辭**：真效果是「乾淨碼=預設中性滿分、不需主動維護分數」=降低（非消除，與往美加分數學等價）灌水相對收益。不宣稱它消除 game 誘因。

### 2.1 各紀律維度：量化 + 靜態可算性（誠實標）+ 最終去向

| # | 維度 | 量化公式（收口後） | 靜態可算性 | 信心 | 最終去向（紅藍收口） |
|---|---|---|---|---|---|
| D1 | 函數腫脹 | **絕對閾值** `bloat=smoothstep(T_lo,T_hi,node_count)`，T_lo=80/T_hi=200（env `CODESEXTANT_BLOAT_LO/HI`） | ✅ node_count 已落盤（**僅 function/method**） | 高（function）/ **class/variable=UNKNOWN 中性**（C2 衍生：clones.py:313 只對 function/method 抽指紋） | **sat 復合分量**；分位數降為 panel 相對參考 |
| D2 | cyclomatic | `1+Σ分支`，需新跨語言控制流 taxonomy | ⚠ 子系統待建 | 中 | **panel only**（C5 三選一不選） |
| D3 | cognitive | SonarSource 巢狀加權，帶深度狀態遞迴 walker | ⚠ 子系統待建、per-language 信心降級 | 中（僅 jedi/ts-morph，其餘 UNKNOWN） | **sat 復合分量（唯一複雜度代表）** |
| D4 | 巢狀深度 | max_nesting AST walk | ⚠ 子系統待建 | 高 | **panel only**（C5） |
| D5 | 重複碼 DRY | `dup=1 EXACT/RENAMED / 0.5 STRUCTURAL / 0` | ✅ clones 已落盤 | 高（結構非語意） | **sat 復合分量 + 既有連線弧線連孿生（零渲染器改動）** |
| D6 | 死碼 | verdict→ LIKELY_UNUSED=0.7 等；UNKNOWN_*=中性 | ✅ jedi/ts-morph 真解析 | 高（其餘 UNKNOWN） | **僅走 alpha（下限 0.3-0.35）、從 health 移除**（C7） |
| D7 | 文檔覆蓋 | per-symbol has_doc | ✅ 已算 | 高 | **移出 health、panel only**（C7 鄰近裁決：清晰 game 梯度+0.05 灰度人眼看不出） |
| D8 | 命名規範 | _well_named × 氾濫名懲罰 | ✅ 已算 | 中 | **移出 health、panel only**（氾濫名懲罰**反向**用戶#1 訴求，見 2.2） |
| D9 | instability | I=Ce/(Ce+Ca) | ✅ 聚合可算 | 中（檔層級） | **砍出星圖視覺**（C13 粒度錯配） |
| D10 | 長參數/primitive obsession | param_count；prim_ratio | ✅ param 可算；型別需 annotation walk | 低 | **sat 弱分量（param_count）/ panel（prim_ratio）** |
| D11 | 內聚 LCOM4 | method×field 連通分量 | ⚠ 需 field-access 邊，破壞「一檔一parse共用tree」鐵律 | 低 | **不進視覺**（gate-0 先驗不破壞鐵律才議） |
| D12 | **變數收斂（用戶#1）** | def-use+alias | ⛔ **零輸入**（symbols.py:423/436 連區域變數都不抽） | 無 | **不進視覺、不進 panel；獨立引擎擴充提案**（C1/C6） |
| D13 | **UDT（用戶#2）** | 領域語意判斷 | ⛔ 語意算不到 | 無 | **不進視覺；D10 線索進 panel**（C6） |

### 2.2 對用戶兩個明確新維度的誠實裁決（追溯用戶期許）

**D12 變數收斂/單一身分**：用戶期許＝「同一身分只用一個變數名，搜 A 全出來、改 A 不漏改」（可操作精確，非氛圍）。
- ⛔ **零輸入**（不是「降級為弱信號」）：親驗 symbols.py:34「變數只在模組頂層收」、:423 `elif node_type in varkinds and not scope_parts`、:436 `and not scope_parts` — 兩條變數抽取路徑都硬 gate 在模組頂層，函數體內**零區域變數抽取**。而別名分裂問題 100% 發生在函數體內。
- 嚴格判定需 def-use chain + alias/points-to/SSA；動態語言**不可判定（undecidable）**（frama-c 只給保守 may-alias 上界、USPTO 10127133 只能標 possibly redundant）；合法例外（條件式賦值＝SSA φ-join）純名稱比對**必誤報**。
- **裁決**：不進視覺、**不進 panel**（連 panel 都是 vapor，因零輸入）。標「未實作能力、非降級」，拆成**獨立引擎擴充提案**（CP 值另議，回拋 user 見§7）。

**D13 UDT/primitive obsession**：「UDT 是否真表達領域概念」是語意判斷，靜態算不到。
- **裁決**：不進視覺。唯一可數的 D10（長參數列/多 primitive 簽名＝線索）進 health 弱分量（param_count）+ panel（prim_ratio）。「該不該升型」永留人類判斷。

### 2.3 health 復合公式（收口後）

```
health = 1 - clip( Σ wᵢ · penaltyᵢ , 0, 1 )

penalty 分量（皆 0..1，UNKNOWN/N-A 一律剔除並對剩餘權重 renormalize，不洗成滿分）：
  w_dup   * D5_dup          # 重複碼        preset「平衡」=0.30
  w_cog   * D3_cognitive    # 認知複雜度    preset「平衡」=0.30（僅 jedi/ts-morph 計權，其餘 UNKNOWN）
  w_bloat * D1_bloat        # 函數腫脹      preset「平衡」=0.25（絕對閾值；class/variable=N-A）
  w_param * D10_param       # 長參數弱分量  preset「平衡」=0.15
  ⛔ D6 死碼不在 health（只走 alpha）
  ⛔ D7 文檔/D8 命名不在 health（panel only）

per-語言正規化（C2/C8 衍生·防多語言假可比）：
  penalty 只在「該語言該維度有效」時計入，health 顯示為「基於 N 個有效維度」，
  panel 標每節點 health 的有效維度集合（讓 user 知 Rust 區塊只反映 2 維）。
  小符號(node_count<15 或無 body)：D1/D3 視為 N-A 中性不計權（不洗滿分），D5 仍可算 → 動態 renormalize。

視覺映射（純函數，零隨機）：
  saturation = 0.85 * (0.45 + 0.55 * health)   # health=0→sat≈0.38 灰、=1→0.85 鮮（獨立 sat buffer，不碰 col 的 hue）
  alpha      = clip(0.35 + 0.65 * D6_health_alpha, 0.35, 1.0)  # 只吃 D6 死碼、下限 0.35 保可見
  ⛔ size 永遠只給 rank，不疊腫脹
```

### 2.4 Goodhart 防護總表（逐維度·收口後）

| 維度 | 風險 | 收口後緩解 |
|---|---|---|
| D3 複雜度 | 高（拆 trivial 函數搬家+同社群 Q 反升雙贏 game，C4 證實） | **移出有座標梯度的位置通道、只進 sat 末位通道**（消最強梯度）；誠實標「拆函數搬家複雜度本系統無法被位置懲罰」=殘留風險不假裝有緩解；canary 主動測 game 抵抗（乾淨碼故意拆緊密小函數驗視覺不變美） |
| D7 文檔 | 高（灌假 docstring 歸零 penalty） | **移出 health、panel only**（清晰梯度+0.05 灰度無視覺價值） |
| D8 命名 | **反向**（氾濫名懲罰誘導把同名拆成 a_user/b_user 製造別名分裂，恰反用戶#1） | **氾濫名懲罰移出 health**；命名信號在 D12 能力到位前一律不進視覺 |
| D1 腫脹 | 中（拆小衝低）+反向（塞大檔推 P95，C9） | 絕對閾值（非分位數）；併 sat 非 size 子通道 |
| D6 死碼 | 低（刪死碼=真改善） | 安全；只走 alpha 保可見；unwired 名稱級誤報對外 API→UNKNOWN 中性 |
| D5 重複 | 低（消重=真改善） | 安全；⛔永不出「應合併」決策（clones 鐵律③） |
| 權重 | 災難（user 調權重把差維度歸零，C11） | preset 非自由調參+panel 顯原始分+落盤審計+non_canonical 浮水印 |

**四條總緩解**：①位置不吃任何 clean-code 分數（主）②多指標復合無清晰單一梯度（主）③honest UNKNOWN/N-A 中性 renormalize ④canary 用外部 ground truth 主動測 game 抵抗。

---

## §3 視覺通道分配總表（位置/色/大小/亮度/形狀各給誰）

| 視覺通道 | 感知精度 | 載什麼 | 方向 | 收口裁決 |
|---|---|---|---|---|
| **位置 pos** | 最高 | 結構 modularity（基底） | — | ⛔鎖死。任何 clean-code 分數都不准動座標 |
| **色相 hue** | 中 | community 身分（基底，170°→290°） | — | ⛔鎖死。clean-code 不換 hue |
| **大小 size** | 高 | PageRank rank（重要度） | — | **純留 rank**（C8：腫脹不疊 size，避免大≠重要語意衝突+半整合壓制） |
| **飽和 saturation** | 末位 | **health 復合**（D5/D3/D1/D10，排除 D6/D7/D8） | health↓→褪色發灰 | **獨立 sat buffer**（C10：不碰 col 的 hue，shader 端 hsl 合成） |
| **透明 alpha** | 低 | **D6 死碼**（獨立、非雙載） | LIKELY_UNUSED→半透明、下限 0.35 | C7：從 health 移除 D6、設下限保「可見但脫團」 |
| **連線亮度** | 已用 | 群內/跨群（基底）+ **D5 clone 暗債弧線** | clone 孿生連暗弧 | **複用既有 lpos/lcol buffer（零渲染器改動）** |
| **形狀/紋理** | 最低 | ~~刺狀/裂紋/重複紋理~~ | — | ⛔**整個刪除**（C3：point-sprite 物理做不到）。離散旗標降級 panel 文字或顏色外環 |

**test/singleton 節點**（C7/R3 修正）：health 視覺通道對 `community∈{Ltest,Lsingleton}` 直接 skip，維持既有灰（graph-common.js:51-52），不被 health sat 覆寫。

**節點集對齊**（C2/R3）：health 節點集 = 佈局 prod 節點集（group_in_box_v3.py:44）。test fixture 節點 health 通道一律中性。

---

## §4 分階段落地（canary-first 防 vapor）

> **✅ 落地實況（2026-06-22，PoC 層 `_poc_graph_c\`）**：P0.5+P1+P2 已實作驗證。
> - **P0.5✅**：`code_health.py`（D1 腫脹 smoothstep80→200 + D5 重複 shape_hash>1 + D6 未接線 find_unwired，UNKNOWN renormalize 不洗滿分）；接進 `build_repo_graph.py`（⚠ 須 `index_project(force=True)` 否則增量 skip 致 fingerprints 表空 health 0%）。CodeSextant 自身 **health 覆蓋 69%**（剩 class/變數無指紋＝UNKNOWN 中性）。數據真實性驗證：最褪色 health=0.455 全是真重複碼（PoC 裡複製貼上的 `_smoothstep`/`_hash_unit`/`apd`）。
> - **P1✅**：`graph-common.js` nodeColor 加 health→去飽和（保 hue、UNKNOWN 中性）。matplotlib 鐵證 `plot_cs_health.png` 雙維度（社群 vs health）。互動星圖已接線（bloom 下 sat 弱＝符合「末位通道」設計）。
> - **P2✅**：`code_health` 算 clone_pairs（同 shape star 連接）→ `build_repo_graph` 存 `clone_edges`（獨立於佈局 edges）；`graph-common.js` 加 alpha buffer（死碼半透明下限0.4）+ clone 暗弧 buffer（暗紅）；`v3-stunning.html` 渲染（alphaN×opacityNode + clone LineSegments）。CodeSextant 自身 **63 條重複碼弧 + 6 死碼**，matplotlib 鐵證紅弧連孿生。
> - **無頭截圖**：`shoot_v3.py` 改 headless=True + SwiftShader flags（不開真視窗）；能力沉澱進 `/playwright` skill（`shot.mjs --webgpu`）。
> - **⏳ P3/P4/D12 未做**：P3 認知複雜度子系統＝SSOT 標獨立大工程（cognitive complexity walker 跨語言、UNKNOWN-heavy），建議乾淨脈絡做。外部 ground truth 對照（屎山庫 vs 乾淨庫）canary 未跑（CodeSextant 自身太乾淨 health 0.455~1、無極爛碼，自我展示對比弱）。

每 phase 先在「**外部 ground truth 對照**」（requests/flask 乾淨庫 vs 已知 bug 密度/CVE 屎山庫，C12）+ real598 雙圖 playwright 截圖，人工驗「漂亮星圖＝乾淨碼」直覺成立才推。

| Phase | 內容 | 信號來源 | 動 shader | 硬節點（canary 過才推） |
|---|---|---|---|---|
| **P0.5（地基·新增）** | **建 symbol_id↔(path,line) 反查 join 層**（ranking symbols 全集當權威 node 鍵，撞 line 用 end_line/scope tie-break）+ 小符號 N-A 動態 renormalize + **後端 health 計算落盤、離線數值對照驗正確性、不上視覺** | join 層 | ❌ | **fingerprint 覆蓋率% 報告**，覆蓋率過低直接判未過（杜絕「少數大函數變灰肉眼誤判成立」假 canary） |
| **P1** | 獨立 sat buffer + shader hsl 合成（hue 純社群、sat 純 health）：D5 clone + D1 腫脹(絕對閾值) → health → sat | 已落盤 | ✅ sat（一次做對省返工） | 外部對照：屎山庫 sat 明顯灰 vs 乾淨庫鮮豔，截圖直覺成立 |
| **P2** | alpha buffer：D6 死碼→半透明（下限 0.35）+ clone 暗債弧線（複用連線 buffer） | deadcode + 既有 lpos/lcol | ✅ alpha | 死碼節點朦朧脫團但仍可見，與基底 beauty 低→中心糊不衝突（test/singleton skip） |
| **P3** | 跨語言控制流子系統 PoC（**僅 jedi/ts-morph**）：D3 cognitive → health；per-language 信心降級 + `_CONTROL_FLOW` 覆蓋率自測 fixture | 新 AST 子系統 | ❌（沿用 sat） | 複雜函數視覺臃腫 + **game 抵抗測試**（乾淨碼拆緊密小函數驗視覺不變美，C4）；Go switch fixture 不被顯成乾淨（C5） |
| **P4（可選/評 CP 值）** | D11 LCOM4（先 gate-0 驗不破壞一檔一parse鐵律）；D9 若做只在裝盒/檔層級 panel | 新分析層 | ⚠ | 視 P0.5-P3 效果再定，標 UNKNOWN-heavy |
| **獨立提案（回拋 user）** | D12 變數收斂 data-flow 引擎擴充（區域變數抽取層 + jedi/ts-morph scope-aware use→def + φ-join 白名單）；**永不扣美、confidence=low、panel only** | 全新引擎 | — | CP 值 + 必誤報合法條件式的接受度，user 拍板（§7） |

⛔ 形狀/紋理通道：若未來真要，須先獨立雙 PoC（WebGL2+WebGPU instanced mesh/sprite atlas）驗證可行當 gate-0，當獨立大工程，**不混進本設計**。

---

## §5 關鍵接線檔案（絕對路徑）

| 角色 | 絕對路徑 | 改動 |
|---|---|---|
| 佈局骨架 | `E:\ai-king\項目資料\CodeSextant\_poc_graph_c\group_in_box_v3.py` | ⛔不動骨架（位置/beauty/prod-test 分離）；只讀 prod 節點集對齊 health |
| 前端通道 | `E:\ai-king\項目資料\CodeSextant\_poc_graph_c\graph-common.js` | buildBuffers 新增獨立 sat/alpha buffer（不碰 col line 76-77）；Ltest/Lsingleton skip health；clone 暗弧複用 lpos/lcol |
| WebGL2 渲染器 | `E:\ai-king\項目資料\CodeSextant\_poc_graph_c\poc-a-webgl2.html` | fragment shader hsl 合成 sat + alpha 輸出（P1/P2） |
| WebGPU 渲染器 | `E:\ai-king\項目資料\CodeSextant\_poc_graph_c\poc-b-webgpu-tsl.html` | TSL 同步 sat/alpha（維持雙 PoC 公平對照）；⛔形狀紋理不做（:109 自承做不到） |
| 靜態引擎-符號 | `E:\ai-king\項目資料\CodeSextant\codesextant\symbols.py` | D12 區域變數抽取層（獨立提案，非本期）；:423/:436 是零輸入鐵證 |
| 靜態引擎-指紋/複雜度 | `E:\ai-king\項目資料\CodeSextant\codesextant\clones.py` | D3 cognitive 子系統 + `_CONTROL_FLOW` 覆蓋率自測（:52-60 脆弱白名單）；D1 node_count 既有(僅 function/method) |
| 靜態引擎-排名/join | `E:\ai-king\項目資料\CodeSextant\codesextant\ranking.py` | :88 4部鍵 symbol_id（join 層權威 node 鍵來源） |
| 索引/落盤 | `E:\ai-king\項目資料\CodeSextant\codesextant\engine.py` | :166 一檔一parse共用tree 算 health 落盤；:1199 2部鍵 meta（join 層對接點） |
| 死碼/註解 | `E:\ai-king\項目資料\CodeSextant\codesextant\{deadcode.py,comments.py}` | D6 alpha 分量 / D7 panel only |
| 本 SSOT | `E:\ai-king\項目資料\CodeSextant\docs\星圖美=全面CleanCode品質_紅藍CBUA最佳解_2026-06-22.md` | — |

---

## §6 token 帳

- 本次收口：研究盤點 5 份 + 設計草案 + 紅隊 4 lens（~40 findings 去重至 13）+ 紅隊 pruned 4 + 藍隊 3 視角 + 真檔親驗 8 檔 7 次 grep。
- 真檔驗證成本：7 次 grep（symbols/clones/ranking+engine/group_in_box/graph-common/poc），確認所有紅藍引用行號無誤、無幻覺。
- 產出：本 SSOT 全文（單一真相源，後續落地直接讀此，免重跑紅藍）。

---

## §7 commander_flagged_for_human（✅ user 已於 2026-06-22 全數拍板）

> **拍板結果**：1=**A 誠實降級「結構健康星圖」**（D12/D13 不擴引擎、不進視覺）｜2=**preset 三檔 + 各維度開關 + panel 顯原始分**｜3=產品哲學採納。下方為原始決策脈絡（保留供日後重議）。

**1. 【C6·deviates_from_user_intent·反漂移錨】產品宣稱二擇一**：
用戶 prompt 願景「美＝全面 clean code」，但用戶最想要的 D12（變數收斂）/D13（UDT）恰是純靜態鐵律下零輸入/算不到。技術裁決「不進視覺」正確（已舉證可行性：擴 data-flow 層技術可行但必對合法條件式誤報、CP 值未知），但宣稱「全面」又踢出核心訴求=承諾落差。**二擇一**：
- **(A) 誠實降級宣稱**：產品定位改為「**結構健康星圖**」（不宣稱全面 clean code）。D12/D13 明標「需 data-flow/語意、超出純靜態鐵律、不進視覺」。**推薦**（對齊純靜態零依賴鐵律 + honest UNKNOWN）。
- **(B) 評 CP 值破例擴引擎**：為 D12 建獨立 data-flow 層（僅 jedi/ts-morph 高信心子集、必標 confidence=low、永不扣美、panel only）。接受「必誤報合法條件式」的代價。

**2. 【C11·L0 鐵律#6】權重 preset vs 自由調參**：採「per-dimension enabled + 離散 preset（嚴格/平衡/寬鬆）+ 落盤審計 + panel 顯原始分」同時過 L0#6 與防 game。**須 user 拍板此例外**（對齊 switches.md ZIQ vs 手動 cosmetic/UX 例外邏輯）。

**3. 【R1/R11·產品定位 note】星圖定位**：確認「星圖=診斷地圖（看了去讀碼，where 髒）+ panel=逐項診斷（why 髒+file:line）」，UX 強制 panel 視覺權重 ≥ 整團印象、首屏文案明說「美是結構/品質的副產品、真相在 panel」、clean-code 軟通道預設低強度。**須 user 確認此產品哲學**（影響首屏 UX）。

---

## §8 一句話總結

把「寫碼整潔紀律」轉成星圖視覺美的最佳解＝**位置鎖結構（物理上消除最強 game 梯度）、clean-code 走獨立 sat 末位通道復合 health（D6 死碼走 alpha 設下限、D1 改絕對閾值、複雜度只留 D3 且 per-language 降級、D7/D8/D9 移出視覺只進 panel）、形狀紋理通道因 point-sprite 物理做不到而整刪、canary 改外部 ground truth、先建 join 地基（P0.5）再上視覺**；而用戶最想要的變數收斂（D12）/UDT（D13）誠實標「零輸入/算不到、不進視覺」，逼出產品宣稱二擇一回拋 user 拍板——絕不可宣稱「美＝全面 clean code」又把用戶兩核心訴求踢出視覺。
