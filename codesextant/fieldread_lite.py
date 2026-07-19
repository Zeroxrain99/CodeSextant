"""FieldRead-lite — CodeSextant 的輸出壓縮層（MIT、零依賴自持實作）。

緣起：CodeSextant 的長輸出（callgraph 傳遞鏈／impact 一堆 caller／map 一堆符號）會吃 token。
採用的壓縮思路來自 **FieldRead**：「按語意命名空間分比例配預算 ＋ 超預算的部分用
麵包屑（breadcrumb，只留一行路徑摘要）省略、需要時再展開」。

為何自己實作一份，而不是相依於既有的 FieldRead 套件（2026-06-19 定案）：
  - 授權會傳染：該套件是 **AGPL-3.0**（強傳染式開源授權），相依會把 CodeSextant
    從 MIT 一路傳染成 AGPL，直接打死「任何人／任何 agent 都能拿去用」的定位——
    AGPL 會卡住商用與閉源整合。
  - 依賴會爆肥：它連帶要求兩家 LLM SDK ＋ 一整套 web 框架。一個代碼地圖工具
    不該為了「把輸出變短」而扛這些。
  - 演算法本身很簡單（純字串／條目處理），自持一份的成本遠低於上面兩個代價。

⛔ 這裡的取捨對後人的一般化教訓：借「想法」不會傳染授權，借「程式碼」會。
   工具型專案想保持任何人都能用，相依清單就是它的定位聲明。

⛔ 不抄 aider TreeContext（只壓代碼顯示）；用 FieldRead 的「語意分區」思路，但分區是**代碼語意**
（high 信心／low／test／prod／entrypoint／UNKNOWN）。純顯示層壓縮——engine 仍回完整 dict，
--json/--full 拿全部，壓的只是給人看的摘要。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Section:
    """一個語意分區的待壓內容。

    priority 高＝優先保留 + 分更多預算；min_keep＝至少保留幾個（重要分區設高，確保不被擠掉）。
    """
    name: str
    label: str
    items: list
    priority: int = 1
    min_keep: int = 0


@dataclass
class CompressedSection:
    name: str
    label: str
    shown: list
    elided: int   # 省略幾個（麵包屑）
    total: int


def compress(sections: list[Section], *, budget: int, full: bool = False) -> list[CompressedSection]:
    """按語意分區比例預算壓縮 + 麵包屑可展開（FieldRead-lite 核心）。

    full=True 或總條目 <= budget → 全給不壓。否則：
      ① 各分區先給 min_keep（保證重要分區不被擠掉）；
      ② 剩餘預算按 priority×剩餘量 加權分給各分區（高 priority 先吃、分更多）；
      ③ 超分配的截斷、記 elided（麵包屑「…另 N 個省略」）。
    回 list[CompressedSection]（維持原分區順序）。budget<=0 視為只留 min_keep。
    """
    secs = list(sections)
    total = sum(len(s.items) for s in secs)
    if full or total <= max(0, budget):
        return [CompressedSection(s.name, s.label, list(s.items), 0, len(s.items)) for s in secs]

    alloc: dict[str, int] = {s.name: 0 for s in secs}

    # ① min_keep 先保（硬下限——即使撐破 budget 也保重要分區；min_keep 是「絕對要看到」的保證）
    for s in secs:
        alloc[s.name] = min(s.min_keep, len(s.items))
    remaining = budget - sum(alloc.values())

    # ② 剩餘按 priority×剩餘量 加權分配（高 priority 先吃）
    while remaining > 0:
        hungry = [s for s in secs if alloc[s.name] < len(s.items)]
        if not hungry:
            break
        wsum = sum(s.priority * (len(s.items) - alloc[s.name]) for s in hungry) or 1
        progressed = False
        for s in sorted(hungry, key=lambda x: -x.priority):
            if remaining <= 0:
                break
            want = max(1, round(remaining * s.priority * (len(s.items) - alloc[s.name]) / wsum))
            give = min(want, len(s.items) - alloc[s.name], remaining)
            if give > 0:
                alloc[s.name] += give
                remaining -= give
                progressed = True
        if not progressed:
            break

    out: list[CompressedSection] = []
    for s in secs:
        k = alloc[s.name]
        out.append(CompressedSection(s.name, s.label, list(s.items[:k]),
                                     len(s.items) - k, len(s.items)))
    return out


def render(sections: list[Section], *, budget: int, full: bool = False,
           item_fmt=str, indent: str = "  ") -> list[str]:
    """壓縮 + 渲染成文字行（各分區標題 + 條目 + 麵包屑）。回 list[str]。

    item_fmt：把單個條目轉成顯示字串的函數（預設 str）。空分區（total=0）不印。
    """
    lines: list[str] = []
    for cs in compress(sections, budget=budget, full=full):
        if cs.total == 0:
            continue
        head = f"{indent}{cs.label}：{cs.total} 個"
        if cs.elided:
            head += f"（顯示 {len(cs.shown)}、另 {cs.elided} 省略，--full 看全部）"
        lines.append(head)
        for it in cs.shown:
            lines.append(f"{indent}  {item_fmt(it)}")
    return lines
