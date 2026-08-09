"""Command-line interface for CodeSextant.

Commands cover indexing, symbol and reference lookup, code maps, change impact,
and repository checks. Output is human-readable by default; ``--json`` prints
JSON for scripts and integrations.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Preserve paths and symbols on Windows.

from . import engine  # noqa: E402
from . import fieldread_lite as fl  # noqa: E402


def _emit(obj: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _out_budget(args) -> int:
    # Output compression budget: the flag wins, then env CODESEXTANT_OUTPUT_BUDGET, then 40.
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
        print(f"Project indexed: {r['project_key'][:12]}…")
        print(f"  {r['indexed']} file(s) recomputed / {r['skipped']} skipped (cache hit) / "
              f"{r['removed']} removed / {r['errors']} with errors")
        print(f"  {r['symbols_total']} symbols total, {r['elapsed_sec']}s elapsed")
        print(f"  Database: {r['db_file']}")
        if r["errors"]:
            for ef in r["error_files"][:5]:
                print(f"    [error] {ef['path']}: {ef['error']}")
    return 0


def cmd_symbols(args) -> int:
    r = engine.get_symbols(args.path, file=args.file)
    if args.json:
        _emit(r, True)
    else:
        print(f"Symbols: {r['count']} (project {r['project_key'][:12]}…)")
        if r.get("note"):
            print(f"  Note: {r['note']}")
        for s in r["symbols"][:30]:
            scope = f"{s['scope']}." if s["scope"] else ""
            print(f"  [{s['kind']:8}] {scope}{s['name']:30} "
                  f"{s['path'].split(chr(92))[-1]}:{s['line']}")
        if r["count"] > 30:
            print(f"  … and {r['count'] - 30} more")
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
        print(f"References to '{r['symbol']}'")
        if r.get("error"):
            print(f"  Warning: {r['error']}")
        d = r.get("definition")
        if d:
            print(f"  Definition: {d['path']}:{d['line']}")
        hc = r["high_confidence"]
        print(f"  High-confidence references (confirmed by jedi): {len(hc)}")
        for ref in hc[:20]:
            print(f"    {ref['src_path']}:{ref['line']}:{ref['column']}")
        print(f"  Name matching would sweep in {r['name_match_file_count']} file(s) (the baseline "
              f"for comparison); {len(r['low_confidence'])} file(s) are low confidence, not "
              f"confirmed by jedi")
        cands = r.get("candidate_definitions", [])
        if len(cands) > 1:
            print(f"  Warning: {len(cands)} definitions share this name (name matching cannot tell them "
                  f"apart; only jedi can):")
            for c in cands[:10]:
                print(f"    {c['path']}:{c['line']} (scope={c['scope'] or 'module top level'})")
        # Report the resolver's confidence and any follow-up advice.
        rel = r.get("reliability") or {}
        if rel.get("level"):
            print(f"  Reliability {rel['level']}: {rel.get('advice')}")
    return 0


def cmd_map(args) -> int:
    r = engine.get_map(args.path, token_budget=args.budget)
    if args.json:
        _emit(r, True)
    else:
        print(f"Code map (token budget {r['token_budget']} ≈ {r['approx_tokens']}, "
              f"the {r['count']} most important symbols)")
        if r.get("note"):
            print(f"  Note: {r['note']}")
        # Symbols are already PageRank-ordered, so compress truncates the low-ranked tail
        # and leaves an expandable breadcrumb.
        cs = fl.compress([fl.Section("syms", "Symbols", list(r["symbols"]))],
                         budget=_out_budget(args), full=args.full)[0]
        for i, s in enumerate(cs.shown, 1):
            scope = f"{s['scope']}." if s["scope"] else ""
            print(f"  {i:3}. [{s['rank']:.4f}] [{s['kind']:8}] {scope}{s['name']:28} "
                  f"{s['path'].split(chr(92))[-1]}:{s['line']}")
        if cs.elided:
            print(f"  … ({cs.elided} lower-ranked symbol(s) elided; use --full to see all)")
    return 0


def cmd_status(args) -> int:
    r = engine.status(args.path)
    if args.json:
        _emit(r, True)
    else:
        if not r["indexed"]:
            print(f"Project not indexed yet: {r['repo_path']}")
            print(f"  (its database would be at {r['db_file']})")
        else:
            print(f"Project: {r['repo_path']}")
            print(f"  project_key: {r['project_key']}")
            print(f"  {r['indexed_files']} file(s) indexed / {r['symbols']} symbol(s) / "
                  f"{r['refs']} reference edge(s)")
            print(f"  Database: {r['db_file']}")
    return 0


def cmd_cache(args) -> int:
    from . import cache_gc

    result = cache_gc.inventory()
    if args.json:
        _emit(result, True)
    else:
        mib = result["managed_bytes"] / (1024 * 1024)
        print(
            f"Managed cache: {result['project_count']} project(s), "
            f"{mib:.1f} MiB")
        for project in result["projects"][:20]:
            size = project["bytes"] / (1024 * 1024)
            print(
                f"  {project['project_key'][:12]}  {size:9.1f} MiB  "
                f"repo={project['repo_state']}  "
                f"artifacts={project['artifact_count']}")
        if result["project_count"] > 20:
            print(f"  ... and {result['project_count'] - 20} more")
        if result["issues"]:
            print(
                f"  {len(result['issues'])} cache group issue(s) were preserved "
                "instead of pruned")
    return 0


def cmd_install_skill(args) -> int:
    from .skill_install import install_skill

    results = install_skill(args.target, force=args.force)
    if args.json:
        _emit({"skills": results}, True)
    else:
        for result in results:
            print(f"Agent Skill {result['action']}: {result['path']}")
    return 0


def cmd_gui(args) -> int:
    import webbrowser

    from .client import CodesextantClient

    project = os.path.abspath(args.path)
    client = CodesextantClient(project=project)
    started = client.ensure()
    if started.get("action") not in ("already-running", "spawned"):
        print(f"Could not start the CodeSextant daemon: {started.get('action')}", file=sys.stderr)
        return 1

    state = client.status()
    if not state["indexed"]:
        print(f"Indexing {project} for the first time...")
        client.reindex()

    url = client.dashboard_url()
    opened = False
    if not args.no_browser:
        opened = bool(webbrowser.open_new_tab(url))
        if not opened:
            print("The default browser could not be opened. Use the URL below.", file=sys.stderr)
    print(f"Dashboard: {client.base + '/' if opened else url}")
    return 0


def cmd_deadcode(args) -> int:
    r = engine.find_deadcode(args.path, scope_file=args.file, lang=args.lang)
    if args.json:
        _emit(r, True)
    else:
        ui = r.get("unused_imports", {}) or {}
        if ui.get("available"):
            fs = ui.get("findings", []) or []
            print(f"Unused imports (linter={ui.get('linter')}): {len(fs)}")
            for f in fs[:20]:
                print(f"  {f.get('path')}:{f.get('line')} [{f.get('code')}] {f.get('message')}")
        else:
            print(f"Unused imports = UNKNOWN ({ui.get('reason')})")
        if r.get("scope_file"):
            print(f"Orphan symbol grades ({r['scope_file']}):")
            for o in r.get("orphans", []) or []:
                print(f"  {o.get('icon', '·')} {o.get('verdict')} {o.get('kind')} "
                      f"{o.get('name')} @line {o.get('line')}: {o.get('reason')}")
        s = r.get("summary", {}) or {}
        print(f"Summary: unused={s.get('unused_import_count', 0)} "
              f"likely_unused={s.get('likely_unused', 0)} keep={s.get('keep', 0)} "
              f"unknown={s.get('unknown', 0)}")
        for a in r.get("read_code_advisory", []) or []:
            print(f"  Review: {a}")
    return 0


def cmd_ai_usage(args) -> int:
    r = engine.find_ai_usage(args.path, scope_file=args.file)
    if args.json:
        _emit(r, True)
    else:
        s = r.get("stats", {}) or {}
        print(f"AI usage scan ({s.get('files_scanned', 0)} file(s)): {s.get('providers_detected', 0)} "
              f"provider(s) · {s.get('consumer_files', 0)} consumer(s) · "
              f"{s.get('cli_compliant', 0)} cli (compliant) / "
              f"{s.get('dispatch_violations', 0)} direct (violation) / {s.get('local', 0)} local")
        for n in r.get("nodes", []):
            if n.get("type") == "file" and n.get("violation"):
                for st in n.get("sites", []):
                    if st.get("channel") == "direct":
                        print(f"  Policy violation: direct API call {n['path']}:{st['line']} "
                              f"[{st['provider']}] {st['snippet']}")
        for a in r.get("read_code_advisory", []) or []:
            print(f"  Review: {a}")
        if r.get("verification_reminder"):
            print(f"  Note: {r['verification_reminder']}")
    if getattr(args, "html", None):
        from . import ai_usage_html
        out = os.path.abspath(args.html)
        with open(out, "w", encoding="utf-8") as f:
            f.write(ai_usage_html.render_ai_usage(r))
        print(f"[codesextant] AI usage report written to: {out}", file=sys.stderr)
    return 0


def cmd_unwired(args) -> int:
    r = engine.find_unwired(args.path, max_fanout=args.max_fanout)
    if args.json:
        _emit(r, True)
    else:
        s = r.get("summary", {}) or {}
        print(f"Unwired check (name-level graph): scanned "
              f"{s.get('top_level_referenceable_scanned', 0)} top-level symbol(s) → "
              f"{s.get('unwired_candidates', 0)} unwired candidate(s) / "
              f"{s.get('unknown_fanout', 0)} undecidable (flooded name) / "
              f"{s.get('exempt_entry_or_dunder', 0)} entrypoint exemption(s)")
        # Compress the candidate list and leave a breadcrumb.
        cands = list(r.get("candidates", []))
        cs = fl.compress([fl.Section("u", "Unwired candidates", cands, min_keep=5)],
                         budget=_out_budget(args), full=args.full)[0]
        for c in cs.shown:
            scope = f"{c['scope']}." if c.get("scope") else ""
            print(f"  {c.get('icon', '·')} {c.get('verdict'):16} [{c['kind']:8}] {scope}{c['name']:26} "
                  f"{c['path'].split(chr(92))[-1]}:{c['line']}")
        if cs.elided:
            print(f"  … ({cs.elided} more elided; use --full to see all)")
        # Explain the limits of name-level analysis and the need to
        # cross-check with real resolution.
        for a in r.get("read_code_advisory", []) or []:
            print(f"  Review: {a}")
        print(f"  Note: {r.get('verification_reminder', '')}")
    return 0


def cmd_health(args) -> int:
    r = engine.get_health(args.path)
    if args.json:
        _emit(r, True)
        return 0
    s = r.get("summary", {}) or {}
    print(f"Code health (bloat, complexity, and duplication; unwired evidence is separate): "
          f"{s.get('n_covered', 0)}/{s.get('n_nodes', 0)} scored "
          f"({s.get('coverage', 0) * 100:.0f}% coverage) · {s.get('n_dead', 0)} unwired · "
          f"{len(s.get('clone_pairs', []))} duplicate arc(s)")
    graded = sorted((n for n in r.get("symbols", []) if n.get("health") is not None),
                    key=lambda n: n["health"])
    topn = len(graded) if args.full else min(_out_budget(args), len(graded))
    for n in graded[:topn]:
        tag = "  unwired" if n.get("dead") else ""
        print(f"  health={n['health']:.3f}  [{n.get('kind', ''):8}] {n['name']:26} "
              f"{n['path'].split(chr(92))[-1]}:{n['line']}{tag}")
    if not args.full and len(graded) > topn:
        print(f"  … ({len(graded) - topn} healthier symbol(s) elided; use --full to see all)")
    print("  Review: Low health marks a place worth inspecting and checking with build/CI. It is "
          "not a 'should be deleted' verdict. UNKNOWN (no fingerprint, or a low-confidence "
          "language) is left unscored.")
    return 0


def cmd_comment_overview(args) -> int:
    r = engine.get_comment_overview(args.path, scope_file=args.file)
    if args.json:
        _emit(r, True)
    elif not r.get("indexed"):
        print(f"Project not indexed yet: {r.get('note')}")
    else:
        cov = r["docstring_coverage"]
        print(f"Docstring coverage ({'/'.join(cov['counted_kinds'])}, "
              f"skip_private={cov['skip_private']}): {cov['overall_pct']}%")
        for k, v in cov["by_kind"].items():
            print(f"  {k:10} {v['documented']}/{v['total']} ({v['pct']}%)")
        if r["tag_counts"]:
            print(f"Tag counts: {r['tag_counts']}")
        if r["density"]:
            dd = r["density"]
            print(f"Density: {dd['comment_lines']} comment line(s) / {dd['code_lines']} code line(s) = {dd['ratio']}")
        for u in r["top_undocumented"][:10]:
            print(f"  ✗ {u['kind']} {u['name']} @ {u['path'].split(chr(92))[-1]}:{u['line']}")
        print(f"  Note: {r['caveat']}")
    return 0


def cmd_comment_tags(args) -> int:
    tags = [t for t in args.tags.split(",") if t] if args.tags else None
    r = engine.find_comment_tags(args.path, tags=tags, scope_file=args.file)
    if args.json:
        _emit(r, True)
    elif not r.get("indexed"):
        print(r.get("note"))
    else:
        print(f"Tag index: {r['count_by_tag']}")
        cs = fl.compress([fl.Section("t", "Tags", list(r["findings"]), min_keep=5)],
                         budget=_out_budget(args), full=args.full)[0]
        for f in cs.shown:
            print(f"  [{f['tag']}] {f['path'].split(chr(92))[-1]}:{f['line']}: {f['text']}")
        if cs.elided:
            print(f"  … ({cs.elided} more elided; use --full)")
    return 0


def cmd_comments(args) -> int:
    r = engine.get_comments(args.path, file=args.file, scope=args.scope,
                            doc_only=args.doc_only, tag=args.tag)
    if args.json:
        _emit(r, True)
    else:
        print(f"Comments: {r['count']}")
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
        print(f"Duplicate/near-duplicate detection: scanned {s['total_units_scanned']} unit(s) → "
              f"EXACT {s['exact']} / RENAMED {s['renamed']} / NEAR {s['structural_near']} / "
              f"CALL {s['call_pattern']} / {s['boilerplate_suppressed_groups']} group(s) suppressed "
              f"(stage2_ran={s['stage2_ran']})")
        cs = fl.compress([fl.Section("g", "Groups", list(r["groups"]), min_keep=5)],
                         budget=_out_budget(args), full=args.full)[0]
        for g in cs.shown:
            mem = ", ".join(f"{m['path'].split(chr(92))[-1]}:{m['line']} {m['name']}"
                            for m in g["members"])
            sim = f" sim={g['similarity']}" if g["similarity"] is not None else ""
            print(f"  {g['icon']} {g['verdict']}{sim}: {mem}")
        if cs.elided:
            print(f"  … ({cs.elided} more group(s) elided; use --full)")
        for a in r["read_code_advisory"]:
            print(f"  Review: {a}")
        print(f"  Note: {r['verification_reminder']}")
    return 0


def cmd_callgraph(args) -> int:
    r = engine.call_hierarchy(args.path, args.symbol, direction=args.direction,
                              max_hops=args.max_hops, src_root=args.src_root,
                              def_path=args.def_path)
    if args.json:
        _emit(r, True)
    else:
        print(f"Call chain for '{r['symbol']}' direction={r['direction']} max_hops={r['max_hops']}")
        if r.get("error"):
            print(f"  Warning: {r['error']}")
        budget = _out_budget(args)
        for key, title in (("callers", "Callers (who transitively calls this symbol)"),
                           ("callees", "Callees (who this symbol transitively calls)")):
            if key in r:
                # High-confidence, shallow entries sort to the front, so compress keeps
                # that prefix and elides the tail behind a breadcrumb.
                ordered = sorted(r[key] or [], key=lambda x: (
                    0 if x.get("confidence") == "high" else 1,
                    x.get("depth", 0), x.get("name", "")))
                cs = fl.compress([fl.Section(key, title, ordered, min_keep=3)],
                                 budget=budget, full=args.full)[0]
                head = f"  {title}: {cs.total}"
                if cs.elided:
                    head += f" (showing {len(cs.shown)}, {cs.elided} elided; use --full to see all)"
                print(head)
                for c in cs.shown:
                    conf = "" if c.get("confidence") == "high" else " [low confidence]"
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
        print(f"Change impact: editing '{r['symbol']}' affects {s.get('total_confirmed_affected', 0)} "
              f"symbol(s) ({s.get('direct', 0)} direct / {s.get('transitive', 0)} transitive)")
        print(f"  prod={s.get('prod', 0)} test={s.get('test', 0)} "
              f"entrypoint={s.get('entrypoint', 0)} high_importance={s.get('high_importance', 0)} "
              f"uncertain={s.get('uncertain', 0)}")
        # High-importance affected symbols get min_keep = all of them: the entries that most
        # need to be seen are never elided. Everything else keeps its breadcrumb.
        hi = r.get("high_importance_affected") or []
        cs = fl.compress([fl.Section("hi", "High importance", list(hi), priority=10, min_keep=len(hi))],
                         budget=_out_budget(args), full=args.full)[0]
        for c in cs.shown:
            print(f"  High importance: {c['name']} @ {c['path'].split(chr(92))[-1]}:{c['line']}")
        if cs.elided:
            print(f"  … ({cs.elided} more elided; use --full)")
        if r.get("error"):
            print(f"  Warning: {r['error']}")
    return 0


# Subcommand → (handler, argument-adding function), table-driven: adding a subcommand
# means adding one entry.
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="codesextant",
        description="Local code navigation and change-impact analysis",
    )
    p.add_argument("--json", action="store_true", help="print raw JSON")
    p.add_argument("--full", action="store_true",
                   help="(map/callgraph/impact) turn off output compression and print the full list")
    p.add_argument("--output-budget", type=int, default=None,
                   help="(map/callgraph/impact) how many entries to display; anything beyond that "
                        "is elided behind a breadcrumb. Defaults to env CODESEXTANT_OUTPUT_BUDGET, or 40")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("index", help="build or incrementally update the index")
    pi.add_argument("path")
    pi.add_argument("--force", action="store_true", help="ignore hashes and recompute everything")
    pi.set_defaults(func=cmd_index)

    ps = sub.add_parser("symbols", help="list symbols")
    ps.add_argument("path")
    ps.add_argument("--file", default=None, help="restrict to one file")
    ps.set_defaults(func=cmd_symbols)

    pr = sub.add_parser("references", help="find references to a symbol")
    pr.add_argument("path")
    pr.add_argument("symbol")
    pr.add_argument("--src-root", default=None, help="jedi.Project root (defaults to path)")
    pr.add_argument("--def-path", default=None, help="the file the symbol is defined in")
    pr.add_argument("--no-low", action="store_true", help="omit low-confidence candidates")
    pr.set_defaults(func=cmd_references)

    pm = sub.add_parser("map", help="return the N most important symbols (PageRank)")
    pm.add_argument("path")
    pm.add_argument("--budget", type=int, default=2000, help="token budget")
    pm.set_defaults(func=cmd_map)

    pt = sub.add_parser("status", help="check a project's index status")
    pt.add_argument("path")
    pt.set_defaults(func=cmd_status)

    pc = sub.add_parser("cache", help="show managed local index cache usage")
    pc.set_defaults(func=cmd_cache)

    psi = sub.add_parser("install-skill", help="install the bundled Agent Skill")
    psi.add_argument(
        "--target",
        action="append",
        default=None,
        help="agent skill root; repeat for multiple agents (auto-detected when omitted)",
    )
    psi.add_argument(
        "--force", action="store_true", help="replace an existing modified CodeSextant skill"
    )
    psi.set_defaults(func=cmd_install_skill)

    pg = sub.add_parser("gui", help="index a project and open the local dashboard")
    pg.add_argument("path", nargs="?", default=".", help="project path (defaults to current directory)")
    pg.add_argument(
        "--no-browser",
        action="store_true",
        help="start the dashboard without opening a browser",
    )
    pg.set_defaults(func=cmd_gui)

    pd = sub.add_parser("deadcode", help="dead-code clues (unused imports + orphan symbol grading)")
    pd.add_argument("path")
    pd.add_argument("--file", default=None,
                    help="analyse orphan symbols in one file only (omit it to run the unused-import scan alone)")
    pd.add_argument("--lang", default=None, help="override language inference")
    pd.set_defaults(func=cmd_deadcode)

    pa = sub.add_parser("ai-usage", help="scan AI/LLM provider calls and access channels")
    pa.add_argument("path")
    pa.add_argument("--file", default=None, help="scan one file only (for debugging)")
    pa.add_argument("--html", default=None, help="write the interactive relationship graph HTML to this path")
    pa.set_defaults(func=cmd_ai_usage)

    pu = sub.add_parser(
        "unwired",
        help="find top-level symbols with no name-level external references",
    )
    pu.add_argument("path")
    pu.add_argument("--max-fanout", type=int, default=None,
                    help="fan-out cap for same-name definitions (defaults to env CODESEXTANT_NAMEGRAPH_MAX_FANOUT, or 20)")
    pu.set_defaults(func=cmd_unwired)

    ph = sub.add_parser(
        "health",
        help="score code health from bloat, complexity, and duplication evidence",
    )
    ph.add_argument("path")
    ph.set_defaults(func=cmd_health)

    pco = sub.add_parser("comment-overview", help="repo comment summary (docstring coverage / TODO counts / density)")
    pco.add_argument("path")
    pco.add_argument("--file", default=None, help="restrict to one file")
    pco.set_defaults(func=cmd_comment_overview)

    pct = sub.add_parser("comment-tags", help="TODO/FIXME index (scans line by line for markers and reports real line numbers)")
    pct.add_argument("path")
    pct.add_argument("--tags", default=None, help="comma-separated tags (default: all of them)")
    pct.add_argument("--file", default=None, help="restrict to one file")
    pct.set_defaults(func=cmd_comment_tags)

    pcm = sub.add_parser(
        "comments",
        help="retrieve comments with file, scope, docstring, and tag filters",
    )
    pcm.add_argument("path")
    pcm.add_argument("--file", default=None, help="restrict to one file")
    pcm.add_argument("--scope", default=None, help="restrict to one symbol scope")
    pcm.add_argument("--doc-only", action="store_true", help="docstrings only")
    pcm.add_argument("--tag", default=None, help="only comments carrying a given tag")
    pcm.set_defaults(func=cmd_comments)

    pdu = sub.add_parser("duplicates", help="find structural duplicates and near-duplicates")
    pdu.add_argument("path")
    pdu.add_argument("--file", default=None, help="restrict to this file (stage 2/3 run here only by default)")
    pdu.add_argument("--near-global", action="store_true", help="enable global near-duplicate stage 2/3 (can be slow on a large repo)")
    pdu.add_argument("--min-similarity", type=float, default=None, help="override the STRUCTURAL_NEAR threshold")
    pdu.add_argument("--calls", action="store_true", help="enable the CALL_PATTERN layer (lowest confidence)")
    pdu.set_defaults(func=cmd_duplicates)

    pc = sub.add_parser("callgraph", help="transitive call chain (call hierarchy)")
    pc.add_argument("path")
    pc.add_argument("symbol")
    pc.add_argument("--direction", default="both", choices=["up", "down", "both"],
                    help="up = who calls this symbol / down = who this symbol calls / both")
    pc.add_argument("--max-hops", type=int, default=None, help="maximum recursion depth of the transitive chain")
    pc.add_argument("--src-root", default=None, help="jedi.Project root (used when building edges)")
    pc.add_argument("--def-path", default=None, help="the file the symbol is defined in (specify it when names collide)")
    pc.set_defaults(func=cmd_callgraph)

    pj = sub.add_parser("impact", help="estimate change impact through caller relationships")
    pj.add_argument("path")
    pj.add_argument("symbol")
    pj.add_argument("--max-hops", type=int, default=None, help="maximum recursion depth of the transitive chain")
    pj.add_argument("--src-root", default=None, help="jedi.Project root (used when building edges)")
    pj.add_argument("--def-path", default=None, help="the file the symbol is defined in (specify it when names collide)")
    pj.set_defaults(func=cmd_impact)

    return p


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
