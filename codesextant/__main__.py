"""命令列入口 — python -m codesextant <cmd> ... 可跑驗證。

子命令（一個對一個引擎 API，方便手動驗證 + 之後 C2 daemon 對照）：
  index        <path> [--force]
  symbols      <path> [--file F]
  references   <path> <symbol> [--src-root R] [--def-path D] [--no-low]
  map          <path> [--budget N]
  status       <path>

輸出預設人類可讀；加 --json 印原始 JSON（給程式/daemon 對照）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows console 印中文/emoji 不崩

from . import engine  # noqa: E402
from . import fieldread_lite as fl  # noqa: E402


def _emit(obj: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _out_budget(args) -> int:
    # queue 7 輸出壓縮預算：flag > env CODESEXTANT_OUTPUT_BUDGET > 預設 40
    if getattr(args, "output_budget", None) is not None:
        return args.output_budget
    try:
        return int(os.environ.get("CODESEXTANT_OUTPUT_BUDGET", "") or 40)
    except (TypeError, ValueError):
        return 40


def cmd_index(args) -> int:
    r = engine.index_project(args.path, force=args.force)
    if args.json:
        _emit(r, True)
    else:
        print(f"專案索引完成：{r['project_key'][:12]}…")
        print(f"  重算 {r['indexed']} 檔 / 跳過(cache hit) {r['skipped']} 檔 / "
              f"移除 {r['removed']} 檔 / 錯誤 {r['errors']} 檔")
        print(f"  符號總數 {r['symbols_total']}，耗時 {r['elapsed_sec']}s")
        print(f"  庫：{r['db_file']}")
        if r["errors"]:
            for ef in r["error_files"][:5]:
                print(f"    [錯誤] {ef['path']}: {ef['error']}")
    return 0


def cmd_symbols(args) -> int:
    r = engine.get_symbols(args.path, file=args.file)
    if args.json:
        _emit(r, True)
    else:
        print(f"符號數：{r['count']}（專案 {r['project_key'][:12]}…）")
        if r.get("note"):
            print(f"  注意：{r['note']}")
        for s in r["symbols"][:30]:
            scope = f"{s['scope']}." if s["scope"] else ""
            print(f"  [{s['kind']:8}] {scope}{s['name']:30} "
                  f"{s['path'].split(chr(92))[-1]}:{s['line']}")
        if r["count"] > 30:
            print(f"  …還有 {r['count'] - 30} 個")
    return 0


def cmd_references(args) -> int:
    r = engine.find_references(
        args.path, args.symbol,
        def_path=args.def_path, src_root=args.src_root,
        include_low_confidence=not args.no_low,
    )
    if args.json:
        _emit(r, True)
    else:
        print(f"找引用：'{r['symbol']}'")
        if r.get("error"):
            print(f"  ⚠ {r['error']}")
        d = r.get("definition")
        if d:
            print(f"  定義：{d['path']}:{d['line']}")
        hc = r["high_confidence"]
        print(f"  高信心引用（jedi 確認）：{len(hc)} 處")
        for ref in hc[:20]:
            print(f"    {ref['src_path']}:{ref['line']}:{ref['column']}")
        print(f"  名稱比對會框到 {r['name_match_file_count']} 個檔（對比基準）；"
              f"低信心（未經 jedi 確認）{len(r['low_confidence'])} 檔")
        cands = r.get("candidate_definitions", [])
        if len(cands) > 1:
            print(f"  ⚠ 同名定義有 {len(cands)} 個（名稱比對無法分辨，jedi 才行）：")
            for c in cands[:10]:
                print(f"    {c['path']}:{c['line']} (scope={c['scope'] or '模組頂層'})")
        # 序6：可靠度自評（low/medium 喊讀碼）
        rel = r.get("reliability") or {}
        if rel.get("level"):
            mark = "✅" if rel["level"] == "high" else "⚠"
            print(f"  {mark} 可靠度 {rel['level']}：{rel.get('advice')}")
    return 0


def cmd_map(args) -> int:
    r = engine.get_map(args.path, token_budget=args.budget)
    if args.json:
        _emit(r, True)
    else:
        print(f"代碼地圖（token 預算 {r['token_budget']} ≈ {r['approx_tokens']}，"
              f"取最重要 {r['count']} 個符號）")
        if r.get("note"):
            print(f"  注意：{r['note']}")
        # queue 7：符號已按 PageRank 排序，compress 截斷尾端低排名 + 麵包屑可展開
        cs = fl.compress([fl.Section("syms", "符號", list(r["symbols"]))],
                         budget=_out_budget(args), full=args.full)[0]
        for i, s in enumerate(cs.shown, 1):
            scope = f"{s['scope']}." if s["scope"] else ""
            print(f"  {i:3}. [{s['rank']:.4f}] [{s['kind']:8}] {scope}{s['name']:28} "
                  f"{s['path'].split(chr(92))[-1]}:{s['line']}")
        if cs.elided:
            print(f"  …（另 {cs.elided} 個較低排名符號省略，--full 看全部）")
    return 0


def cmd_status(args) -> int:
    r = engine.status(args.path)
    if args.json:
        _emit(r, True)
    else:
        if not r["indexed"]:
            print(f"專案尚未索引：{r['repo_path']}")
            print(f"  （庫位置會是 {r['db_file']}）")
        else:
            print(f"專案：{r['repo_path']}")
            print(f"  project_key：{r['project_key']}")
            print(f"  已索引 {r['indexed_files']} 檔 / {r['symbols']} 符號 / "
                  f"{r['refs']} 引用邊")
            print(f"  庫：{r['db_file']}")
    return 0


def cmd_deadcode(args) -> int:
    r = engine.find_deadcode(args.path, scope_file=args.file, lang=args.lang)
    if args.json:
        _emit(r, True)
    else:
        ui = r.get("unused_imports", {}) or {}
        if ui.get("available"):
            fs = ui.get("findings", []) or []
            print(f"未使用 import（linter={ui.get('linter')}）：{len(fs)} 處")
            for f in fs[:20]:
                print(f"  {f.get('path')}:{f.get('line')} [{f.get('code')}] {f.get('message')}")
        else:
            print(f"未使用 import = UNKNOWN（{ui.get('reason')}）")
        if r.get("scope_file"):
            print(f"孤兒符號分級（{r['scope_file']}）：")
            for o in r.get("orphans", []) or []:
                print(f"  {o.get('icon', '·')} {o.get('verdict')} {o.get('kind')} "
                      f"{o.get('name')} @line {o.get('line')} — {o.get('reason')}")
        s = r.get("summary", {}) or {}
        print(f"小結：unused={s.get('unused_import_count', 0)} "
              f"likely_unused={s.get('likely_unused', 0)} keep={s.get('keep', 0)} "
              f"unknown={s.get('unknown', 0)}")
        # 序6：工具盲區攤開（必須人工讀碼）
        for a in r.get("read_code_advisory", []) or []:
            print(f"  🔎 {a}")
    return 0


def cmd_ai_usage(args) -> int:
    r = engine.find_ai_usage(args.path, scope_file=args.file)
    if args.json:
        _emit(r, True)
    else:
        s = r.get("stats", {}) or {}
        print(f"AI 用量掃描（{s.get('files_scanned', 0)} 檔）：{s.get('providers_detected', 0)} 家 provider · "
              f"{s.get('consumer_files', 0)} 個消費端 · cli 合規 {s.get('cli_compliant', 0)} / "
              f"direct 違規 {s.get('dispatch_violations', 0)} / local 本地 {s.get('local', 0)}")
        for n in r.get("nodes", []):
            if n.get("type") == "file" and n.get("violation"):
                for st in n.get("sites", []):
                    if st.get("channel") == "direct":
                        print(f"  🔴 direct 違規 {n['path']}:{st['line']} [{st['provider']}] {st['snippet']}")
        for a in r.get("read_code_advisory", []) or []:
            print(f"  🔎 {a}")
        if r.get("verification_reminder"):
            print(f"  ℹ {r['verification_reminder']}")
    if getattr(args, "html", None):
        from . import ai_usage_html
        out = os.path.abspath(args.html)
        with open(out, "w", encoding="utf-8") as f:
            f.write(ai_usage_html.render_ai_usage(r))
        print(f"[codesextant] AI Usage HUD 已寫入：{out}", file=sys.stderr)
    return 0


def cmd_unwired(args) -> int:
    r = engine.find_unwired(args.path, max_fanout=args.max_fanout)
    if args.json:
        _emit(r, True)
    else:
        s = r.get("summary", {}) or {}
        print(f"未接線檢查（功能 A，名稱級全圖粗篩）：掃 {s.get('top_level_referenceable_scanned', 0)} "
              f"個頂層符號 → {s.get('unwired_candidates', 0)} 個未接線候選 / "
              f"{s.get('unknown_fanout', 0)} 個氾濫名不可判 / {s.get('exempt_entry_or_dunder', 0)} 個入口豁免")
        # queue 7：候選清單壓縮 + 麵包屑
        cands = list(r.get("candidates", []))
        cs = fl.compress([fl.Section("u", "未接線候選", cands, min_keep=5)],
                         budget=_out_budget(args), full=args.full)[0]
        for c in cs.shown:
            scope = f"{c['scope']}." if c.get("scope") else ""
            print(f"  {c.get('icon', '·')} {c.get('verdict'):16} [{c['kind']:8}] {scope}{c['name']:26} "
                  f"{c['path'].split(chr(92))[-1]}:{c['line']}")
        if cs.elided:
            print(f"  …（另 {cs.elided} 省略，--full 看全部）")
        # 誠實層：名稱級天花板 + 務必真解析複核
        for a in r.get("read_code_advisory", []) or []:
            print(f"  🔎 {a}")
        print(f"  ⚠ {r.get('verification_reminder', '')}")
    return 0


def cmd_health(args) -> int:
    r = engine.get_health(args.path)
    if args.json:
        _emit(r, True)
        return 0
    s = r.get("summary", {}) or {}
    print(f"代碼健康度（紀律轉美數值層 D1腫脹/D3複雜度/D5重複→health, D6死碼→dead）："
          f"{s.get('n_covered', 0)}/{s.get('n_nodes', 0)} 有評分"
          f"（覆蓋 {s.get('coverage', 0) * 100:.0f}%）· 未接線 {s.get('n_dead', 0)} · "
          f"重複碼弧 {len(s.get('clone_pairs', []))}")
    graded = sorted((n for n in r.get("symbols", []) if n.get("health") is not None),
                    key=lambda n: n["health"])
    topn = len(graded) if args.full else min(_out_budget(args), len(graded))
    for n in graded[:topn]:
        tag = "  💀未接線" if n.get("dead") else ""
        print(f"  health={n['health']:.3f}  [{n.get('kind', ''):8}] {n['name']:26} "
              f"{n['path'].split(chr(92))[-1]}:{n['line']}{tag}")
    if not args.full and len(graded) > topn:
        print(f"  …（另 {len(graded) - topn} 個較健康符號省略，--full 看全部）")
    print("  🔎 health 低=值得人工讀碼+build/CI 複核處、非「應刪」；UNKNOWN（無指紋/低信心語言）不評分")
    return 0


def cmd_comment_overview(args) -> int:
    r = engine.get_comment_overview(args.path, scope_file=args.file)
    if args.json:
        _emit(r, True)
    elif not r.get("indexed"):
        print(f"專案尚未索引：{r.get('note')}")
    else:
        cov = r["docstring_coverage"]
        print(f"docstring 覆蓋率（{'/'.join(cov['counted_kinds'])}，"
              f"skip_private={cov['skip_private']}）：{cov['overall_pct']}%")
        for k, v in cov["by_kind"].items():
            print(f"  {k:10} {v['documented']}/{v['total']} ({v['pct']}%)")
        if r["tag_counts"]:
            print(f"標記計數：{r['tag_counts']}")
        if r["density"]:
            dd = r["density"]
            print(f"密度：{dd['comment_lines']} 註解行 / {dd['code_lines']} 程式行 = {dd['ratio']}")
        for u in r["top_undocumented"][:10]:
            print(f"  ✗ {u['kind']} {u['name']} @ {u['path'].split(chr(92))[-1]}:{u['line']}")
        print(f"  🔎 {r['caveat']}")
    return 0


def cmd_comment_tags(args) -> int:
    tags = [t for t in args.tags.split(",") if t] if args.tags else None
    r = engine.find_comment_tags(args.path, tags=tags, scope_file=args.file)
    if args.json:
        _emit(r, True)
    elif not r.get("indexed"):
        print(r.get("note"))
    else:
        print(f"標記索引：{r['count_by_tag']}")
        cs = fl.compress([fl.Section("t", "標記", list(r["findings"]), min_keep=5)],
                         budget=_out_budget(args), full=args.full)[0]
        for f in cs.shown:
            print(f"  [{f['tag']}] {f['path'].split(chr(92))[-1]}:{f['line']} — {f['text']}")
        if cs.elided:
            print(f"  …（另 {cs.elided} 省略，--full）")
    return 0


def cmd_comments(args) -> int:
    r = engine.get_comments(args.path, file=args.file, scope=args.scope,
                            doc_only=args.doc_only, tag=args.tag)
    if args.json:
        _emit(r, True)
    else:
        print(f"註解數：{r['count']}")
        for c in r["comments"][:30]:
            mark = "/doc" if c["is_doc"] else ("/" + (c["tag"] or "") if c["tag"] else "")
            print(f"  L{c['line']} [{c['kind']}{mark}] {c['text'][:60]!r}")
    return 0


def cmd_duplicates(args) -> int:
    r = engine.find_duplicates(args.path, scope_file=args.file, near_global=args.near_global,
                               min_similarity=args.min_similarity, include_call_pattern=args.calls)
    if args.json:
        _emit(r, True)
    else:
        s = r["summary"]
        print(f"重複/類似偵測：掃 {s['total_units_scanned']} 單元 → EXACT {s['exact']} / "
              f"RENAMED {s['renamed']} / NEAR {s['structural_near']} / CALL {s['call_pattern']} / "
              f"壓制 {s['boilerplate_suppressed_groups']} 群（stage2_ran={s['stage2_ran']}）")
        cs = fl.compress([fl.Section("g", "群", list(r["groups"]), min_keep=5)],
                         budget=_out_budget(args), full=args.full)[0]
        for g in cs.shown:
            mem = ", ".join(f"{m['path'].split(chr(92))[-1]}:{m['line']} {m['name']}"
                            for m in g["members"])
            sim = f" sim={g['similarity']}" if g["similarity"] is not None else ""
            print(f"  {g['icon']} {g['verdict']}{sim}: {mem}")
        if cs.elided:
            print(f"  …（另 {cs.elided} 群省略，--full）")
        for a in r["read_code_advisory"]:
            print(f"  🔎 {a}")
        print(f"  ⚠ {r['verification_reminder']}")
    return 0


def cmd_callgraph(args) -> int:
    r = engine.call_hierarchy(args.path, args.symbol, direction=args.direction,
                              max_hops=args.max_hops, src_root=args.src_root,
                              def_path=args.def_path)
    if args.json:
        _emit(r, True)
    else:
        print(f"呼叫鏈：'{r['symbol']}' 方向={r['direction']} max_hops={r['max_hops']}")
        if r.get("error"):
            print(f"  ⚠ {r['error']}")
        budget = _out_budget(args)
        for key, title in (("callers", "被呼叫鏈(誰傳遞呼叫此符號)"),
                           ("callees", "呼叫鏈(此符號傳遞呼叫誰)")):
            if key in r:
                # queue 7：高信心淺層排前綴，compress 保前綴 + 麵包屑省尾端
                ordered = sorted(r[key] or [], key=lambda x: (
                    0 if x.get("confidence") == "high" else 1,
                    x.get("depth", 0), x.get("name", "")))
                cs = fl.compress([fl.Section(key, title, ordered, min_keep=3)],
                                 budget=budget, full=args.full)[0]
                head = f"  {title}：{cs.total} 個"
                if cs.elided:
                    head += f"（顯示 {len(cs.shown)}、另 {cs.elided} 省略，--full 看全部）"
                print(head)
                for c in cs.shown:
                    conf = "" if c.get("confidence") == "high" else " ⚠低"
                    fn = c["path"].split(chr(92))[-1]
                    print(f"    [L{c['depth']}] {c['name']} @ {fn}:{c['line']}{conf}")
        if r.get("note"):
            print(f"  ({r['note']})")
    return 0


def cmd_impact(args) -> int:
    r = engine.impact(args.path, args.symbol, max_hops=args.max_hops,
                      src_root=args.src_root, def_path=args.def_path)
    if args.json:
        _emit(r, True)
    else:
        s = r.get("summary", {}) or {}
        print(f"改動影響：改 '{r['symbol']}' 牽動 {s.get('total_confirmed_affected', 0)} 個"
              f"（直接 {s.get('direct', 0)}/傳遞 {s.get('transitive', 0)}）")
        print(f"  prod={s.get('prod', 0)} test={s.get('test', 0)} "
              f"entrypoint={s.get('entrypoint', 0)} high_importance={s.get('high_importance', 0)} "
              f"uncertain={s.get('uncertain', 0)}")
        # queue 7：高重要度受影響 min_keep 全留（最該看的不省）+ 麵包屑
        hi = r.get("high_importance_affected") or []
        cs = fl.compress([fl.Section("hi", "高重要度", list(hi), priority=10, min_keep=len(hi))],
                         budget=_out_budget(args), full=args.full)[0]
        for c in cs.shown:
            print(f"  ⭐ {c['name']} @ {c['path'].split(chr(92))[-1]}:{c['line']}")
        if cs.elided:
            print(f"  …（另 {cs.elided} 省略，--full）")
        if r.get("error"):
            print(f"  ⚠ {r['error']}")
    return 0


# 子命令 → (handler, 加參數的函數)，table-driven：加子命令只塞一筆
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="codesextant", description="代碼地圖純引擎（C1）")
    p.add_argument("--json", action="store_true", help="輸出原始 JSON")
    p.add_argument("--full", action="store_true",
                   help="（map/callgraph/impact）關閉輸出壓縮、印完整清單")
    p.add_argument("--output-budget", type=int, default=None,
                   help="（map/callgraph/impact）顯示條目預算，超過用麵包屑省略；"
                        "預設 env CODESEXTANT_OUTPUT_BUDGET 或 40")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("index", help="建/增量更新索引")
    pi.add_argument("path")
    pi.add_argument("--force", action="store_true", help="忽略 hash 全部重算")
    pi.set_defaults(func=cmd_index)

    ps = sub.add_parser("symbols", help="列出符號")
    ps.add_argument("path")
    ps.add_argument("--file", default=None, help="只看某個檔")
    ps.set_defaults(func=cmd_symbols)

    pr = sub.add_parser("references", help="找某符號被誰用（jedi 二段式）")
    pr.add_argument("path")
    pr.add_argument("symbol")
    pr.add_argument("--src-root", default=None, help="jedi.Project 根（預設=path）")
    pr.add_argument("--def-path", default=None, help="符號定義所在檔")
    pr.add_argument("--no-low", action="store_true", help="不回低信心候選")
    pr.set_defaults(func=cmd_references)

    pm = sub.add_parser("map", help="給最重要的 N 個符號（PageRank）")
    pm.add_argument("path")
    pm.add_argument("--budget", type=int, default=2000, help="token 預算")
    pm.set_defaults(func=cmd_map)

    pt = sub.add_parser("status", help="查專案索引狀態")
    pt.add_argument("path")
    pt.set_defaults(func=cmd_status)

    pd = sub.add_parser("deadcode", help="死碼線索（未使用 import + 孤兒符號分級）")
    pd.add_argument("path")
    pd.add_argument("--file", default=None,
                    help="只分析某檔的孤兒符號（不給只跑未使用 import 掃描）")
    pd.add_argument("--lang", default=None, help="覆寫語言推斷")
    pd.set_defaults(func=cmd_deadcode)

    pa = sub.add_parser("ai-usage", help="掃 repo 用了哪些 AI/LLM + dispatch_policy cli/direct/local 三通道")
    pa.add_argument("path")
    pa.add_argument("--file", default=None, help="只掃某檔（除錯用）")
    pa.add_argument("--html", default=None, help="輸出深色 HUD 關聯圖 HTML 到此路徑")
    pa.set_defaults(func=cmd_ai_usage)

    pu = sub.add_parser("unwired", help="未接線檢查（功能 A，名稱級全圖粗篩零外部引用符號）")
    pu.add_argument("path")
    pu.add_argument("--max-fanout", type=int, default=None,
                    help="同名 fan-out 上限（預設 env CODESEXTANT_NAMEGRAPH_MAX_FANOUT 或 20）")
    pu.set_defaults(func=cmd_unwired)

    ph = sub.add_parser("health", help="代碼健康度（紀律轉美數值層 D1腫脹/D3複雜度/D5重複→health, D6死碼）")
    ph.add_argument("path")
    ph.set_defaults(func=cmd_health)

    pco = sub.add_parser("comment-overview", help="repo 註解摘要（docstring 覆蓋率/TODO 計數/密度）")
    pco.add_argument("path")
    pco.add_argument("--file", default=None, help="只看某檔")
    pco.set_defaults(func=cmd_comment_overview)

    pct = sub.add_parser("comment-tags", help="TODO/FIXME 索引（逐行掃 marker 回真實行號）")
    pct.add_argument("path")
    pct.add_argument("--tags", default=None, help="逗號分隔標記（預設全部）")
    pct.add_argument("--file", default=None, help="只看某檔")
    pct.set_defaults(func=cmd_comment_tags)

    pcm = sub.add_parser("comments", help="精確取註解（只看該看的）")
    pcm.add_argument("path")
    pcm.add_argument("--file", default=None, help="只看某檔")
    pcm.add_argument("--scope", default=None, help="限某符號 scope")
    pcm.add_argument("--doc-only", action="store_true", help="只看 docstring")
    pcm.add_argument("--tag", default=None, help="只看含某標記的")
    pcm.set_defaults(func=cmd_comments)

    pdu = sub.add_parser("duplicates", help="重複/類似功能偵測（統一母版，結構指紋）")
    pdu.add_argument("path")
    pdu.add_argument("--file", default=None, help="限該檔範圍（stage-2/3 預設只此跑）")
    pdu.add_argument("--near-global", action="store_true", help="開全域近似 stage-2/3（大 repo 可能慢）")
    pdu.add_argument("--min-similarity", type=float, default=None, help="覆寫 STRUCTURAL_NEAR 門檻")
    pdu.add_argument("--calls", action="store_true", help="開 CALL_PATTERN 層（最低信心）")
    pdu.set_defaults(func=cmd_duplicates)

    pc = sub.add_parser("callgraph", help="傳遞呼叫鏈（call hierarchy）")
    pc.add_argument("path")
    pc.add_argument("symbol")
    pc.add_argument("--direction", default="both", choices=["up", "down", "both"],
                    help="up=誰呼叫此符號 / down=此符號呼叫誰 / both")
    pc.add_argument("--max-hops", type=int, default=None, help="傳遞鏈最多遞迴層數")
    pc.add_argument("--src-root", default=None, help="jedi.Project 根（建邊用）")
    pc.add_argument("--def-path", default=None, help="符號定義所在檔（同名衝突時指定）")
    pc.set_defaults(func=cmd_callgraph)

    pj = sub.add_parser("impact", help="改動影響 blast radius（改 X 牽動誰）")
    pj.add_argument("path")
    pj.add_argument("symbol")
    pj.add_argument("--max-hops", type=int, default=None, help="傳遞鏈最多遞迴層數")
    pj.add_argument("--src-root", default=None, help="jedi.Project 根（建邊用）")
    pj.add_argument("--def-path", default=None, help="符號定義所在檔（同名衝突時指定）")
    pj.set_defaults(func=cmd_impact)

    return p


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
