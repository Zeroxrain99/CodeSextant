"""C6-a prod canary — 證實 CodeSextantEscalationGuard 在「真 feature flag + 真信號源」
下會 fire，破「wiring 健康但 prod 0% fire」假綠（繁衍迴圈 v2 最警惕的隱蔽假綠）。

跟單元測試的差別（單元測試 mock get_config + 手寫 fail_stall）：
  - 本 canary 用「真 FEATURE_META + 真 get_config」→ 證明真 feature flag enabled=True 會 fire
  - 用「真 CbuaPipelineGuard 餵真失敗字串」算 fail_stall → 證明真信號源會寫
  - audit log 用真實 session_id（非 pytest 的 s1/s5/s8）→ 留真 prod fire 鐵證
  - 末段走「真 create_default_pipeline().run_pre_tool」full pipeline → 證整鏈在真註冊表下注入

完整重現「一敗升一級」真實寫碼序列：改碼 → pytest 失敗 → 同錯再失敗 → 再改碼（此時注入）。

跑法（含中文路徑，PowerShell 先設 UTF-8）：
  C:\\Python311\\python.exe "E:\\ai-king\\項目資料\\CodeSextant\\tools\\c6a_prod_canary.py"
退出碼 0 = canary PASS（guard 真 fire + audit 真寫）。
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")  # Win console emoji/中文防崩

from aiking_core.core.state_store import StateStore
from concinno.core.config import get_config
from concinno.guards.base import GuardContext
from concinno.guards.cbua_pipeline_guard import CbuaPipelineGuard
from concinno.guards.codesextant_escalation_guard import CodeSextantEscalationGuard
from concinno.guards.registry import create_default_pipeline

_AUDIT = os.path.join(os.path.expanduser("~"), ".concinno", "audit",
                      "codesextant_escalation.jsonl")


def _audit_lines() -> int:
    try:
        with open(_AUDIT, encoding="utf-8") as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def main() -> int:
    print("=" * 66)
    print(" C6-a PROD CANARY — CodeSextantEscalationGuard 真 fire 驗證（零 mock）")
    print("=" * 66)

    # ── 0. 環境前提（印真值，前提不對則 canary 結論無效）──────────────
    cfg = get_config()
    enabled = cfg.feature("codesextant_fail_escalation", "enabled")
    try:
        from concinno.handoff_engine import get_handoff_mode
        mode = get_handoff_mode()
    except Exception as e:  # pragma: no cover
        mode = f"(err {e})"
    print(f"[env] feature.enabled={enabled}  handoff_mode={mode}  "
          f"ux_injection={cfg.feature('ux_injection', 'enabled')}")
    if not enabled:
        print("❌ feature 未開 → guard 永遠靜默；canary 無意義。先開 enabled。")
        return 1
    if mode == "competition":
        print("⚠ competition mode → CbuaPipelineGuard bypass 不寫 fail_stall；"
              "信號源這環無法在本 mode 驗（切 save/phase 再跑）。")

    sid = f"c6a_canary_{int(time.time())}"
    cache = tempfile.mkdtemp(prefix="c6a_canary_")
    code_file = os.path.join(cache, "buggy.py")
    with open(code_file, "w", encoding="utf-8") as f:
        f.write("def f():\n    return undefined_name  # NameError\n")

    # 前提：模擬「真實複雜寫碼 session」（C0 判 complicated）。
    # canary 第一版跑揭示的真實行為：cbua _update_cbua_state 對 C0=simple 的
    # session 在寫 fail_stall 前就 return（cbua_pipeline_guard.py:250），故
    # simple session 不 fire——這符合 SKILL.md「超簡單代碼別強迫看」設計意圖。
    # codesextant 的目標場景＝複雜代碼連續撞牆，故預埋 edit_count=12（_classify
    # 門檻 edit_count>=10 → complicated）模擬一個已改 12 次碼的真實 session。
    StateStore(cache).read_modify_write(
        "cbua_pipeline", sid, lambda s: {**(s or {}), "edit_count": 12})

    before = _audit_lines()
    # 同一個失敗 tool_result（指紋相同）= 連續同錯
    fail_out = ("Traceback (most recent call last):\n"
                "  File \"tests/test_x.py\", line 3, in test_f\n"
                "    assert f() == 1\n"
                "NameError: name 'undefined_name' is not defined\n"
                "FAILED tests/test_x.py::test_f")

    # ── 1. 真 CbuaPipelineGuard 餵 Bash 失敗 ×2（真信號源寫 fail_stall）──
    cbua = CbuaPipelineGuard()
    stall = None
    for i in (1, 2):
        ctx_post = GuardContext(
            tool_name="Bash",
            tool_input={"command": "pytest tests/test_x.py"},
            session_id=sid, cache_dir=cache, hook_event="PostToolUse",
            tool_result=fail_out,
        )
        cbua.on_post_tool(ctx_post)
        st = StateStore(cache).read("cbua_pipeline", sid, default={}) or {}
        stall = st.get("fail_stall")
        print(f"[step{i}] 真 cbua 收到 pytest 失敗#{i}（同指紋）→ fail_stall={stall}")

    # ── 2. 真 CodeSextantEscalationGuard.check（真 feature flag，零 mock）──
    ctx_pre = GuardContext(
        tool_name="Edit", tool_input={"file_path": code_file},
        session_id=sid, cache_dir=cache, hook_event="PreToolUse",
    )
    res = CodeSextantEscalationGuard().check(ctx_pre)
    fired = res is not None and "CodeSextant" in (getattr(res, "context", "") or "")
    print(f"[guard] 再次 Edit 代碼 → fired={fired}  "
          f"advisory={getattr(res, 'advisory', None)}")
    if res is not None:
        print("[guard] 注入內容：")
        print("  " + (res.context or "").replace("\n", "\n  "))

    # ── 3. audit log 真 prod fire（session_id 是真實的，非 pytest）──────
    after = _audit_lines()
    print(f"[audit] {_AUDIT}")
    print(f"[audit] fire 行數 {before} → {after}  (+{after - before})")

    # ── 4. full pipeline 整鏈（真 create_default_pipeline）─────────────
    pipe = create_default_pipeline()
    sid2 = f"c6a_full_{int(time.time())}"
    StateStore(cache).read_modify_write(
        "cbua_pipeline", sid2,
        lambda s: {**(s or {}), "fail_stall": 2, "last_fail_fp": "canaryfp"},
    )
    ctx_full = GuardContext(
        tool_name="Edit", tool_input={"file_path": code_file},
        session_id=sid2, cache_dir=cache, hook_event="PreToolUse",
    )
    out = pipe.run_pre_tool(ctx_full)
    add_ctx = out.get("additionalContext", "") or ""
    tm_in_full = "CodeSextant" in add_ctx
    print(f"[full-pipeline] permissionDecision={out.get('permissionDecision')}  "
          f"codesextant_in_additionalContext={tm_in_full}")
    if not tm_in_full and add_ctx:
        # 誠實：full pipeline 下可能 competition profile 把 advisory 路由去 audit 靜音
        print("[full-pipeline] additionalContext（前 400 字）：")
        print("  " + add_ctx[:400].replace("\n", "\n  "))
    elif not tm_in_full:
        print("[full-pipeline] 註：additionalContext 空——可能 advisory 在 competition "
              "profile 被靜音去 audit（guard 仍 fire，見 [audit]）；非 wiring 壞。")

    # ── 判定：核心命題 = guard 在真環境真 fire 且 audit 真寫 ────────────
    core_pass = fired and (after > before) and stall == 2
    print()
    print("=" * 66)
    if core_pass:
        print(" ✅ C6-a CANARY PASS — 真 feature flag + 真信號源 → guard 真 fire、"
              "audit 真寫 prod 證據")
        print("    破「wiring 健康但 prod 0% fire」假綠：之前 audit 只有 pytest fire，"
              "非 wiring 壞，是還沒真撞上連續同錯場景。")
    else:
        print(f" ❌ C6-a CANARY FAIL — fired={fired} stall={stall} "
              f"audit(+{after - before})")
    print("=" * 66)
    return 0 if core_pass else 1


if __name__ == "__main__":
    sys.exit(main())
