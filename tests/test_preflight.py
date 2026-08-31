"""What a caller must be told before editing, and how strong the evidence is.

preflight exists because three failures kept happening in spite of there already being a
query for each: a second implementation of something that existed, a companion change
nothing in the source mentions, and callers somewhere else. These tests pin the parts
that decide whether it earns being called every time -- that it is cheap, that it says
how strong each claim is, and that no single section can take the answer down with it.
"""
from __future__ import annotations

import os
import subprocess
import textwrap

import pytest

from codesextant import cochange, engine, render, storage


def _run(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "proj"
    root.mkdir()
    _run(root, "init", "-q")
    _run(root, "config", "user.email", "test@example.com")
    _run(root, "config", "user.name", "Test")
    return root


def _write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


def _commit(root, message, files):
    for rel, content in files.items():
        _write(root, rel, content)
    _run(root, "add", "-A")
    _run(root, "commit", "-q", "-m", message)


# The obligation nobody wrote down.

def test_co_change_finds_an_obligation_absent_from_the_source(repo):
    """version.py and packaging.toml never mention each other; history knows they pair."""
    for n in range(4):
        _commit(repo, f"release {n}", {
            "version.py": f"VERSION_STRING = '1.0.{n}'\n",
            "packaging.toml": f"version = '1.0.{n}'\n",
        })
    _commit(repo, "unrelated", {"other.py": "def unrelated_helper():\n    return 1\n"})
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "version.py")

    companions = {c["path"]: c for c in result["co_change"]}
    assert "packaging.toml" in companions, "the pairing must be recovered from history"
    assert companions["packaging.toml"]["confidence"] == 1.0
    assert companions["packaging.toml"]["support"] == 4
    assert "other.py" not in companions


def test_a_sweeping_commit_does_not_couple_everything_to_everything(repo):
    """One reformat touching every file would otherwise make every pair look coupled."""
    _commit(repo, "seed", {"a.py": "A = 1\n", "b.py": "B = 1\n"})
    sweeping = {f"mod{i}.py": f"VALUE_{i} = {i}\n" for i in range(40)}
    for _ in range(4):
        sweeping = {name: body + "# touched\n" for name, body in sweeping.items()}
        _commit(repo, "reformat everything", sweeping)
    engine.index_project(str(repo), force=True)

    mined = cochange.mine(str(repo))

    assert mined["stats"]["commits_skipped_as_sweeping"] >= 4
    assert mined["rules"] == [], "a sweeping commit is not evidence of coupling"


def test_a_single_shared_commit_is_a_coincidence_not_a_rule(repo):
    _commit(repo, "once", {"x.py": "X = 1\n", "y.py": "Y = 1\n"})
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "x.py")

    assert result["co_change"] == []
    assert any("nothing that reliably changes" in n for n in result["notes"])


def test_co_change_confidence_is_directional(repo):
    """A test ships with its module; the module often moves alone. Only one is a rule."""
    for n in range(4):
        _commit(repo, f"feature {n}", {
            "mod.py": f"def feature_{n}():\n    return {n}\n",
            "test_mod.py": f"def test_feature_{n}():\n    assert True\n",
        })
    for n in range(4):
        _commit(repo, f"internal {n}", {
            "mod.py": f"def feature_{n}():\n    return {n}  # tweak\n",
            "notes.md": f"tweak {n}\n",
        })
    engine.index_project(str(repo), force=True)

    from_test = {c["path"]: c["confidence"]
                 for c in engine.preflight(str(repo), "test_mod.py")["co_change"]}
    from_module = {c["path"]: c["confidence"]
                   for c in engine.preflight(str(repo), "mod.py")["co_change"]}

    assert from_test.get("mod.py") == 1.0, "the test never ships without its module"
    assert from_module.get("test_mod.py", 0) < 1.0, "the module does move alone"


# The wheel about to be reinvented.

def test_a_similar_existing_definition_is_surfaced_before_it_is_rewritten(repo):
    _commit(repo, "seed", {
        "health.py": "def get_health(project):\n    return {'ok': True}\n",
        "app.py": "def main():\n    return 1\n",
    })
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "app.py", symbol="get_project_health")

    names = [entry["name"] for entry in result["already_exists"]]
    assert "get_health" in names, "a differently-named equivalent still has to be found"


def test_a_genuinely_new_name_is_reported_as_new(repo):
    _commit(repo, "seed", {"app.py": "def main():\n    return 1\n"})
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "app.py", symbol="quantum_flux_capacitor")

    assert result["already_exists"] == []
    # And the note says what kind of check that was. "It looks new" was an overclaim:
    # nothing here compared shape, so an equivalent under an unrelated name would have
    # passed the same check.
    note = next(n for n in result["notes"] if "quantum_flux_capacitor" in n)
    assert "name check" in note
    assert "find_duplicates" in note


def test_one_shared_common_word_is_not_a_reuse_candidate(repo):
    """release_version against release is a shared verb, not a duplicate implementation."""
    _commit(repo, "seed", {
        "a.py": "def release():\n    return 1\n\n\ndef version():\n    return 2\n",
        "b.py": "def main():\n    return 1\n",
    })
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "b.py", symbol="release_version")

    assert result["already_exists"] == [], "one shared word is not similarity"


def test_a_definition_in_the_file_being_edited_outranks_a_distant_one(repo):
    _commit(repo, "seed", {
        "near.py": "def parse_duration_value(text):\n    return 1\n",
        "far.py": "def parse_duration_value(text):\n    return 2\n",
    })
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "near.py", symbol="parse_duration_value")

    assert result["already_exists"][0]["same_file"] is True


# Evidence, and failing softly.

def test_each_section_reports_the_evidence_behind_it(repo):
    for n in range(3):
        _commit(repo, f"pair {n}", {"p.py": f"P = {n}\n", "q.py": f"Q = {n}\n"})
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "p.py")

    rule = result["co_change"][0]
    assert rule["support"] == 3 and rule["changes"] == 3 and rule["confidence"] == 1.0
    assert result["cochange_stats"]["commits_used"] >= 3
    # Blast radius must not imply "nothing calls this" when nothing has been resolved yet.
    # Without a symbol there is nothing bounded to resolve, so the note has to say that
    # the section is empty for lack of asking rather than for lack of callers.
    assert result["blast_radius"]["resolved_edges_project_wide"] == 0
    assert result["blast_radius"]["resolution"]["status"] == "no-symbol"
    assert any("lack of asking rather than lack of callers" in n for n in result["notes"])


def test_a_project_without_git_still_answers(tmp_path, monkeypatch):
    """Two of three sections do not need history, and must not be lost with it."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "nogit"
    root.mkdir()
    _write(root, "health.py", "def get_health(project):\n    return 1\n")
    _write(root, "app.py", "def main():\n    return 1\n")
    engine.index_project(str(root), force=True)

    result = engine.preflight(str(root), "app.py", symbol="get_project_health")

    assert result["co_change"] == []
    assert result["cochange_stats"]["available"] is False
    assert [e["name"] for e in result["already_exists"]] == ["get_health"]


def test_a_broken_miner_costs_its_own_section_only(repo, monkeypatch):
    _commit(repo, "seed", {"app.py": "def main():\n    return 1\n"})
    engine.index_project(str(repo), force=True)

    def explode(*_args, **_kwargs):
        raise RuntimeError("git went sideways")

    monkeypatch.setattr(engine.cochange, "tally", explode)

    result = engine.preflight(str(repo), "app.py", symbol="main")

    assert result["cochange_stats"]["available"] is False
    assert "git went sideways" in result["cochange_stats"]["reason"]
    assert result["already_exists"], "the sections that still work must still answer"


def test_mining_is_cached_until_head_moves(repo):
    for n in range(3):
        _commit(repo, f"pair {n}", {"p.py": f"P = {n}\n", "q.py": f"Q = {n}\n"})
    engine.index_project(str(repo), force=True)

    assert engine.preflight(str(repo), "p.py")["cochange_stats"]["cached"] is False
    assert engine.preflight(str(repo), "p.py")["cochange_stats"]["cached"] is True

    _commit(repo, "pair 3", {"p.py": "P = 3\n", "q.py": "Q = 3\n"})
    assert engine.preflight(str(repo), "p.py")["cochange_stats"]["cached"] is False


def test_preflight_respects_its_token_budget(repo):
    for n in range(3):
        _commit(repo, f"wide {n}", {
            f"mod{i}.py": f"def function_number_{i}():\n    return {i} + {n}\n"
            for i in range(30)})
    engine.index_project(str(repo), force=True)

    import json

    def served(result):
        return len(json.dumps(result, ensure_ascii=False, default=str)) // 4

    generous = engine.preflight(str(repo), "mod0.py", symbol="function_number_0",
                                token_budget=20000)
    tight = engine.preflight(str(repo), "mod0.py", symbol="function_number_0",
                             token_budget=200)

    assert tight["truncated_by_budget"] is True
    assert served(tight) < served(generous), "a tight budget has to buy less"
    # What it reports having spent must describe what it actually sent, whether or not
    # the envelope alone already exceeds a budget this small.
    assert abs(tight["approx_tokens"] - served(tight)) <= 2
    assert served(generous) <= 20000


def test_preflight_requires_an_index(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "bare"
    root.mkdir()
    with pytest.raises(RuntimeError):
        engine.preflight(str(root), "anything.py")


def test_result_is_json_serializable(repo):
    import json
    _commit(repo, "seed", {"app.py": "def main():\n    return 1\n"})
    engine.index_project(str(repo), force=True)
    json.dumps(engine.preflight(str(repo), "app.py", symbol="main"),
               ensure_ascii=False, default=str)


def test_identifier_tokens_split_both_conventions():
    assert engine._identifier_tokens("parse_duration") == {"parse", "duration"}
    assert engine._identifier_tokens("parseDuration") == {"parse", "duration"}
    assert engine._identifier_tokens("ParseDuration") == {"parse", "duration"}
    assert engine._identifier_tokens("_ep_get_health") == {"ep", "get", "health"}


def test_a_target_outside_the_repository_is_not_given_history(repo):
    _commit(repo, "seed", {"app.py": "def main():\n    return 1\n"})
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), str(repo.parent / "outside.py"))

    assert result["co_change"] == []


def test_storage_adds_counts_rather_than_replacing_them(repo):
    """A batch of commits is added to the totals; the head records how far they reach."""
    _commit(repo, "seed", {"app.py": "A = 1\n"})
    engine.index_project(str(repo), force=True)
    with storage.ProjectStore.open(str(repo)) as store:
        store.clear_cochange_counts()
        store.add_cochange_counts({"a.py": 2, "b.py": 2}, {("a.py", "b.py"): 2}, "sha-one")
        store.add_cochange_counts({"a.py": 1, "b.py": 1}, {("a.py", "b.py"): 1}, "sha-two")

        rules = store.cochange_rules_for("a.py", min_support=3, min_confidence=0.5)
        assert rules == [{"companion": "b.py", "support": 3, "changes": 3,
                          "confidence": 1.0}], "two batches must sum, not overwrite"
        assert store.cochange_head() == "sha-two"
        # Pairs are stored under both orderings, so either side is one indexed read.
        assert store.cochange_rules_for("b.py", min_support=3, min_confidence=0.5)
        # Clearing is what a rewritten history gets, and it must leave nothing behind.
        store.clear_cochange_counts()
        assert store.cochange_rules_for("a.py", min_support=1, min_confidence=0.0) == []


def test_preflight_is_reachable_over_http_and_is_interactive():
    """It is called before every edit, so it needs reserved capacity, not a heavy queue."""
    from codesextant import daemon

    assert "/preflight" in daemon._ROUTES_GET
    assert "/preflight" in daemon._HEAVY_PATHS
    assert "/preflight" in daemon._INTERACTIVE_HEAVY_PATHS
    assert os.path.basename(__file__) == "test_preflight.py"


# Coupling keyed to the symbol rather than the whole file.

def _module(alpha_body: str, beta_body: str) -> str:
    return (f"def alpha():\n    return {alpha_body}\n\n\n"
            f"def beta():\n    return {beta_body}\n")


def test_symbol_scope_is_sharper_than_the_file_it_lives_in(repo):
    """The whole file couples weakly; the function inside it couples every time."""
    _commit(repo, "seed", {"mod.py": _module(0, 0), "README.md": "start\n"})
    for n in range(4):
        _commit(repo, f"alpha work {n}", {
            "mod.py": _module(n + 1, 0),
            "alpha_helper.py": f"ALPHA_SUPPORT = {n}\n",
        })
    for n in range(2):
        _commit(repo, f"beta work {n}", {
            "mod.py": _module(4, n + 1),
            "notes.md": f"beta {n}\n",
        })
    engine.index_project(str(repo), force=True)

    by_file = {c["path"]: c for c in engine.preflight(str(repo), "mod.py")["co_change"]}
    by_symbol = {c["path"]: c
                 for c in engine.preflight(str(repo), "mod.py", symbol="alpha")["co_change"]}

    assert by_symbol["alpha_helper.py"]["scope"] == "symbol"
    assert by_symbol["alpha_helper.py"]["confidence"] > by_file["alpha_helper.py"]["confidence"], (
        "narrowing the question to one function has to sharpen the answer")
    assert by_symbol["alpha_helper.py"]["confidence"] == 1.0


def test_a_symbol_rule_supersedes_the_file_rule_for_the_same_companion(repo):
    _commit(repo, "seed", {"mod.py": _module(0, 0), "README.md": "start\n"})
    for n in range(3):
        _commit(repo, f"work {n}",
                {"mod.py": _module(n + 1, 0), "pair.py": f"P = {n}\n"})
    engine.index_project(str(repo), force=True)

    entries = engine.preflight(str(repo), "mod.py", symbol="alpha")["co_change"]

    for_pair = [e for e in entries if e["path"] == "pair.py"]
    assert len(for_pair) == 1, "the same companion must not be claimed at two scopes"
    assert for_pair[0]["scope"] == "symbol"
    assert for_pair[0]["symbol"] == "alpha"


def test_without_a_symbol_nothing_is_mined_per_file(repo):
    for n in range(3):
        _commit(repo, f"work {n}", {"mod.py": _module(n, 0), "pair.py": f"P = {n}\n"})
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "mod.py")

    assert all(entry["scope"] == "file" for entry in result["co_change"])
    assert result["cochange_stats"]["symbol"]["available"] is False


def test_symbol_mining_is_cached_per_file_until_head_moves(repo):
    for n in range(3):
        _commit(repo, f"work {n}", {"mod.py": _module(n, 0), "pair.py": f"P = {n}\n"})
    engine.index_project(str(repo), force=True)

    first = engine.preflight(str(repo), "mod.py", symbol="alpha")
    second = engine.preflight(str(repo), "mod.py", symbol="alpha")
    assert first["cochange_stats"]["symbol"]["cached"] is False
    assert second["cochange_stats"]["symbol"]["cached"] is True

    _commit(repo, "work 3", {"mod.py": _module(3, 0), "pair.py": "P = 3\n"})
    third = engine.preflight(str(repo), "mod.py", symbol="alpha")
    assert third["cochange_stats"]["symbol"]["cached"] is False


def test_broken_symbol_mining_keeps_the_file_level_answer(repo, monkeypatch):
    for n in range(3):
        _commit(repo, f"work {n}", {"mod.py": _module(n, 0), "pair.py": f"P = {n}\n"})
    engine.index_project(str(repo), force=True)

    def explode(*_args, **_kwargs):
        raise RuntimeError("diff went sideways")

    monkeypatch.setattr(engine.cochange, "mine_symbols", explode)

    result = engine.preflight(str(repo), "mod.py", symbol="alpha")

    assert result["cochange_stats"]["symbol"]["available"] is False
    assert [e["path"] for e in result["co_change"]] == ["pair.py"]
    assert result["co_change"][0]["scope"] == "file", "the coarser answer must survive"


def test_only_definition_shaped_contexts_are_attributed():
    """A hunk outside every definition belongs to no symbol, and saying otherwise lies."""
    assert cochange._context_symbol("def parse_duration(text):") == "parse_duration"
    assert cochange._context_symbol("    def store_file(self, path):") == "store_file"
    assert cochange._context_symbol("class ProjectStore:") == "ProjectStore"
    assert cochange._context_symbol("export function buildMap(x) {") == "buildMap"
    assert cochange._context_symbol("async def fetch(url):") == "fetch"
    assert cochange._context_symbol("from . import storage") is None
    assert cochange._context_symbol("_INDEX_GENERATION_KEY = 'index_generation'") is None
    assert cochange._context_symbol("") is None


def test_the_generated_attributes_file_names_a_driver_per_language():
    """Without it Git reports the enclosing class, not the method actually edited."""
    path = cochange._diff_attributes_file()
    with open(path, encoding="utf-8") as handle:
        body = handle.read()
    assert "*.py diff=python" in body
    assert "*.go diff=golang" in body


def test_symbol_mining_reads_only_the_file_it_was_asked_about(repo, monkeypatch):
    """Reading full diffs for a whole repository is what makes this unaffordable."""
    for n in range(3):
        _commit(repo, f"work {n}", {"mod.py": _module(n, 0), "pair.py": f"P = {n}\n"})
    engine.index_project(str(repo), force=True)

    seen = []
    real = cochange.read_symbol_commits

    def watched(repo_path, rel_path, **kwargs):
        seen.append(rel_path)
        return real(repo_path, rel_path, **kwargs)

    monkeypatch.setattr(cochange, "read_symbol_commits", watched)
    engine.preflight(str(repo), "mod.py", symbol="alpha")

    assert seen == ["mod.py"]


def test_a_file_with_no_definitions_produces_no_symbol_rules(repo):
    """Markdown and config files have nothing to attribute to, and inventing one lies."""
    _commit(repo, "seed", {"notes.md": "# start\n", "pair.py": "P = 0\n"})
    for n in range(3):
        _commit(repo, f"docs {n}",
                {"notes.md": f"# start\n\nsection {n}\n", "pair.py": f"P = {n + 1}\n"})
    engine.index_project(str(repo), force=True)

    mined = cochange.mine_symbols(str(repo), "notes.md")

    assert mined["stats"]["symbols_seen"] == 0
    assert mined["rules"] == []
    # The file-level rule still holds; only the finer claim is absent.
    assert any(c["path"] == "pair.py"
               for c in engine.preflight(str(repo), "notes.md")["co_change"])


def test_a_language_git_has_no_driver_for_still_attributes(repo):
    """TypeScript has no built-in Git driver; the default heuristic still finds exports."""
    def module(body: str) -> str:
        return ("export function buildIndex(paths: string[]): number {\n"
                f"  return {body};\n}}\n")

    _commit(repo, "seed", {"index.ts": module("0"), "pair.py": "P = 0\n"})
    for n in range(3):
        _commit(repo, f"work {n}",
                {"index.ts": module(str(n + 1)), "pair.py": f"P = {n + 1}\n"})
    engine.index_project(str(repo), force=True)

    mined = cochange.mine_symbols(str(repo), "index.ts")

    assert "buildIndex" in {rule["symbol"] for rule in mined["rules"]}


def test_the_package_version_matches_the_packaging_version():
    """These two never mention each other, and drifting apart has shipped a bug before.

    0.19.2 exists only because pyproject carried 0.19.1's features while __version__
    still said 0.19.0. The map cache key includes __version__ so that a ranking change
    reaches an existing project, which makes a stale version quietly serve maps built by
    code that is no longer running. History knows the pairing -- preflight reports it at
    83% -- but knowing is not the same as being unable to get it wrong.
    """
    import sys
    import tomllib
    from pathlib import Path

    import codesextant

    root = Path(__file__).resolve().parent.parent
    with open(root / "pyproject.toml", "rb") as handle:
        packaging_version = tomllib.load(handle)["project"]["version"]
    assert codesextant.__version__ == packaging_version, (
        f"codesextant.__version__ is {codesextant.__version__} but pyproject.toml says "
        f"{packaging_version}; bump both or the map cache will not invalidate on upgrade")
    assert sys.version_info >= (3, 10)


# Adding a commit must cost a commit, not the history.

def test_a_new_commit_reads_only_itself(repo):
    """The whole point: totals accumulate, so an update is not a re-derivation."""
    for n in range(4):
        _commit(repo, f"work {n}", {"mod.py": f"M = {n}\n", "pair.py": f"P = {n}\n"})
    engine.index_project(str(repo), force=True)
    engine.preflight(str(repo), "mod.py")          # first mine reads everything

    reads = []
    real = cochange.read_commits

    def watched(repo_path, **kwargs):
        result = real(repo_path, **kwargs)
        reads.append((kwargs.get("since"), len(result or [])))
        return result

    import pytest as _pytest  # noqa: F401  (monkeypatch is function-scoped below)
    original = cochange.read_commits
    cochange.read_commits = watched
    try:
        _commit(repo, "work 4", {"mod.py": "M = 4\n", "pair.py": "P = 4\n"})
        result = engine.preflight(str(repo), "mod.py")
    finally:
        cochange.read_commits = original

    assert result["cochange_stats"]["incremental"] is True
    assert reads and reads[-1][0] is not None, "the update has to be bounded by a since"
    assert reads[-1][1] == 1, f"a single new commit should read one commit, read {reads[-1][1]}"


def test_counts_accumulate_across_updates(repo):
    """Five commits read as four-then-one must equal five read at once."""
    for n in range(5):
        _commit(repo, f"work {n}", {"mod.py": f"M = {n}\n", "pair.py": f"P = {n}\n"})
    engine.index_project(str(repo), force=True)

    incremental = engine.preflight(str(repo), "mod.py")["co_change"]

    with storage.ProjectStore.open(str(repo)) as store:
        store.clear_cochange_counts()
        changes, pairs = cochange.tally(cochange.read_commits(str(repo)))
        store.add_cochange_counts(changes, pairs, "rebuilt")
        from_scratch = store.cochange_rules_for(
            "mod.py", min_support=cochange.min_support(),
            min_confidence=cochange.min_confidence())

    assert [c["path"] for c in incremental] == [r["companion"] for r in from_scratch]
    assert incremental[0]["support"] == from_scratch[0]["support"]


def test_rewritten_history_rebuilds_instead_of_adding_to_stale_totals(repo):
    """After a rebase the old sha is off HEAD, so `old..HEAD` describes the wrong set."""
    for n in range(4):
        _commit(repo, f"work {n}", {"mod.py": f"M = {n}\n", "pair.py": f"P = {n}\n"})
    engine.index_project(str(repo), force=True)
    before = engine.preflight(str(repo), "mod.py")["co_change"][0]

    # Rewrite the branch so the mined commit is no longer an ancestor of HEAD.
    _run(repo, "checkout", "-q", "-b", "rebuilt", "HEAD~3")
    for n in range(4):
        _commit(repo, f"redone {n}",
                {"mod.py": f"M = {n} + 100\n", "pair.py": f"P = {n} + 100\n"})

    stats = engine.preflight(str(repo), "mod.py")["cochange_stats"]

    assert stats["incremental"] is False, "a rewritten history cannot be added to"
    after = engine.preflight(str(repo), "mod.py")["co_change"][0]
    assert after["changes"] <= before["changes"] + 4, (
        "counts must describe the new history, not both histories added together")


def test_thresholds_apply_without_re_reading_history(repo, monkeypatch):
    """Stored counts are raw, so raising a threshold takes effect immediately."""
    for n in range(4):
        _commit(repo, f"work {n}", {"mod.py": f"M = {n}\n", "pair.py": f"P = {n}\n"})
    engine.index_project(str(repo), force=True)
    assert engine.preflight(str(repo), "mod.py")["co_change"], "baseline has a rule"

    monkeypatch.setenv("CODESEXTANT_COCHANGE_MIN_SUPPORT", "99")

    def refuse(*_args, **_kwargs):
        raise AssertionError("changing a threshold must not re-read history")

    monkeypatch.setattr(cochange, "read_commits", refuse)
    assert engine.preflight(str(repo), "mod.py")["co_change"] == []


# The blast radius, on the call where it matters: the first one.

def _blast(result) -> dict:
    return result["blast_radius"]


def _seed_caller_and_callee(repo):
    """core.py defines load_settings; app.py and web.py import and call it."""
    _commit(repo, "seed", {
        "core.py": "def load_settings(path):\n    return {'path': path}\n",
        "app.py": ("from core import load_settings\n\n\n"
                   "def main():\n    return load_settings('x')\n"),
        "web.py": ("from core import load_settings\n\n\n"
                   "def serve():\n    return load_settings('y')\n"),
    })
    engine.index_project(str(repo), force=True)


def test_the_first_ask_resolves_instead_of_reporting_an_empty_radius(repo):
    """The refs table starts empty, so this section used to be worthless when it mattered.

    A blast radius that is only populated after you have separately run find_references
    is a blast radius that is empty on the one call that happens before the edit.
    """
    _seed_caller_and_callee(repo)

    result = engine.preflight(str(repo), "core.py", symbol="load_settings")

    blast = _blast(result)
    assert blast["resolution"]["status"] == "resolved"
    assert sorted(os.path.basename(p) for p in blast["dependent_files"]) == [
        "app.py", "web.py"]
    assert blast["dependent_count"] == 2


def test_a_resolved_absence_reads_differently_from_an_unasked_question(repo):
    """"Nothing calls this" and "nobody looked" print the same and mean opposites."""
    _commit(repo, "seed", {
        "core.py": "def orphan_helper():\n    return 1\n",
        "app.py": "def main():\n    return 2\n",
    })
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "core.py", symbol="orphan_helper")

    blast = _blast(result)
    assert blast["resolution"]["status"] == "resolved"
    assert blast["dependent_files"] == []
    note = next(n for n in result["notes"] if "orphan_helper" in n)
    assert "measured absence" in note


def test_the_second_ask_does_not_pay_for_resolution_again(repo, monkeypatch):
    """Cheap enough to call every time is the property that makes it get called."""
    _commit(repo, "seed", {"core.py": "def orphan_helper():\n    return 1\n"})
    engine.index_project(str(repo), force=True)
    assert engine.preflight(str(repo), "core.py",
                            symbol="orphan_helper")["blast_radius"]["resolution"][
                                "status"] == "resolved"

    def refuse(*_args, **_kwargs):
        raise AssertionError("an answer already resolved must not be resolved again")

    monkeypatch.setattr(engine, "find_references", refuse)
    again = engine.preflight(str(repo), "core.py", symbol="orphan_helper")
    assert _blast(again)["resolution"]["status"] == "cached"
    assert "measured absence" in next(n for n in again["notes"] if "orphan_helper" in n)


def test_editing_the_definition_makes_it_resolve_again(repo):
    """A cached "no callers" describes one revision of the file, not the file."""
    _commit(repo, "seed", {"core.py": "def orphan_helper():\n    return 1\n"})
    engine.index_project(str(repo), force=True)
    engine.preflight(str(repo), "core.py", symbol="orphan_helper")

    _commit(repo, "edit", {"core.py": "def orphan_helper():\n    return 99\n"})
    engine.index_project(str(repo))

    result = engine.preflight(str(repo), "core.py", symbol="orphan_helper")
    assert _blast(result)["resolution"]["status"] == "resolved"


def test_a_symbol_that_does_not_exist_yet_costs_nothing(repo, monkeypatch):
    """The commonest preflight of all: about to add something. There is nothing to resolve."""
    _commit(repo, "seed", {"core.py": "def load_settings(path):\n    return 1\n"})
    engine.index_project(str(repo), force=True)

    def refuse(*_args, **_kwargs):
        raise AssertionError("a symbol with no definition has no callers to resolve")

    monkeypatch.setattr(engine, "find_references", refuse)
    result = engine.preflight(str(repo), "core.py", symbol="brand_new_thing")

    blast = _blast(result)
    assert blast["resolution"]["status"] == "undefined-in-target"
    assert blast["name_match_count"] == 0, "no sweep is worth paying for either"
    assert any("not defined in this file yet" in n for n in result["notes"])


def test_a_name_in_too_many_files_is_declined_and_says_what_it_cost(repo, monkeypatch):
    """The cost is measured before it is spent, and the measurement is the reason given."""
    _seed_caller_and_callee(repo)
    monkeypatch.setenv("CODESEXTANT_PREFLIGHT_RESOLVE_MAX_FILES", "1")

    def refuse(*_args, **_kwargs):
        raise AssertionError("resolution must not run once it has been declined")

    monkeypatch.setattr(engine, "find_references", refuse)
    result = engine.preflight(str(repo), "core.py", symbol="load_settings")

    blast = _blast(result)
    assert blast["resolution"]["status"] == "declined"
    assert "above the inline limit of 1" in blast["resolution"]["reason"]
    # Declining must still leave something usable behind, or the section is worth
    # nothing again -- which was the whole complaint.
    assert sorted(os.path.basename(p) for p in blast["name_match_files"]) == [
        "app.py", "web.py"]
    note = next(n for n in result["notes"] if "not resolved" in n)
    assert "leads, not callers" in note


def test_leads_are_never_presented_as_callers(repo, monkeypatch):
    """Merging the two lists would be the exact inflation this tool exists to avoid."""
    _seed_caller_and_callee(repo)
    monkeypatch.setenv("CODESEXTANT_PREFLIGHT_RESOLVE_MAX_FILES", "1")
    result = engine.preflight(str(repo), "core.py", symbol="load_settings")

    blast = _blast(result)
    assert blast["dependent_files"] == [] and blast["dependent_count"] == 0
    assert blast["name_match_files"], "the leads are still reported, just separately"
    text = "\n".join(render.preflight_lines(result, str(repo)))
    assert "nothing resolved" in text
    assert "?  app.py" in text


def test_a_lead_list_never_includes_the_file_being_edited(repo, monkeypatch):
    """A file naming the symbol it defines is not a lead about itself."""
    _seed_caller_and_callee(repo)
    monkeypatch.setenv("CODESEXTANT_PREFLIGHT_RESOLVE_MAX_FILES", "1")
    blast = _blast(engine.preflight(str(repo), "core.py", symbol="load_settings"))
    assert not any(os.path.basename(p) == "core.py" for p in blast["name_match_files"])


def test_resolve_yes_spends_what_the_limit_would_have_saved(repo, monkeypatch):
    """A caller who wants the exact answer can say so and pay for it."""
    _seed_caller_and_callee(repo)
    monkeypatch.setenv("CODESEXTANT_PREFLIGHT_RESOLVE_MAX_FILES", "0")

    declined = engine.preflight(str(repo), "core.py", symbol="load_settings")
    assert _blast(declined)["resolution"]["status"] == "declined"

    forced = engine.preflight(str(repo), "core.py", symbol="load_settings",
                              resolve="yes")
    assert _blast(forced)["resolution"]["status"] == "resolved"
    assert sorted(os.path.basename(p) for p in _blast(forced)["dependent_files"]) == [
        "app.py", "web.py"]


def test_resolve_no_does_no_extra_work_at_all(repo, monkeypatch):
    """The escape hatch has to actually be an escape, sweep included."""
    _seed_caller_and_callee(repo)

    def refuse(*_args, **_kwargs):
        raise AssertionError("resolve=no must not resolve")

    monkeypatch.setattr(engine, "find_references", refuse)
    monkeypatch.setattr(engine.references, "candidate_files", refuse)
    blast = _blast(engine.preflight(str(repo), "core.py", symbol="load_settings",
                                   resolve="no"))
    assert blast["resolution"]["status"] == "off"
    assert blast["name_match_files"] == []


def test_a_language_without_import_resolution_says_so(repo, monkeypatch):
    """Running a resolver that cannot resolve would spend the time and change nothing."""
    _commit(repo, "seed", {
        "core.go": "package main\n\nfunc LoadSettings() int {\n\treturn 1\n}\n",
        "app.go": "package main\n\nfunc main() {\n\t_ = LoadSettings()\n}\n",
    })
    engine.index_project(str(repo), force=True)

    def refuse(*_args, **_kwargs):
        raise AssertionError("a language with no resolver must not be resolved")

    monkeypatch.setattr(engine, "find_references", refuse)
    result = engine.preflight(str(repo), "core.go", symbol="LoadSettings")

    blast = _blast(result)
    assert blast["resolution"]["status"] == "unsupported"
    assert "go" in blast["resolution"]["reason"]
    assert [os.path.basename(p) for p in blast["name_match_files"]] == ["app.go"]


def test_a_resolution_failure_costs_the_section_not_the_answer(repo):
    """Three sections; the expensive one failing must not take the other two down."""
    for n in range(4):
        _commit(repo, f"pair {n}", {
            "core.py": f"def load_settings():\n    return {n}\n",
            "settings.toml": f"value = {n}\n",
        })
    engine.index_project(str(repo), force=True)

    def explode(*_args, **_kwargs):
        raise RuntimeError("jedi fell over")

    original = engine.find_references
    engine.find_references = explode
    try:
        result = engine.preflight(str(repo), "core.py", symbol="load_settings")
    finally:
        engine.find_references = original

    assert _blast(result)["resolution"]["status"] == "failed"
    assert "jedi fell over" in _blast(result)["resolution"]["reason"]
    assert result["already_exists"], "the reuse check still answered"
    assert result["co_change"], "and so did co-change"


def test_a_caller_the_resolver_cannot_see_is_still_reported(repo):
    """Import resolution has blind spots, and silence about them is the dangerous part.

    Dynamic dispatch, re-exports and registries all look the same to a static
    resolver: nothing. Answering "one file calls this" when a second one does, through
    getattr, is exactly the "changed A, broke B" this section exists to prevent -- so
    the files that name it are reported beside the confirmed callers, in their own key
    and marked apart, never merged into one list.
    """
    _commit(repo, "seed", {
        "core.py": "def load_settings(path):\n    return {'path': path}\n",
        "app.py": ("from core import load_settings\n\n\n"
                   "def main():\n    return load_settings('x')\n"),
        "dyn.py": ("import core\n\n\n"
                   "def main():\n    return getattr(core, 'load_settings')()\n"),
    })
    engine.index_project(str(repo), force=True)

    blast = _blast(engine.preflight(str(repo), "core.py", symbol="load_settings"))

    assert [os.path.basename(p) for p in blast["dependent_files"]] == ["app.py"]
    assert [os.path.basename(p) for p in blast["name_match_files"]] == ["dyn.py"], (
        "the caller jedi cannot follow is still surfaced, as a lead")
    # Separate keys, and separate lines: nothing about the output invites reading the
    # two as one set.
    text = "\n".join(render.preflight_lines(
        engine.preflight(str(repo), "core.py", symbol="load_settings"), str(repo)))
    assert "1 file(s) with resolved references; 1 more name it" in text
    assert "    app.py" in text and "    ?  dyn.py" in text


# Staleness: what a cached "no callers" is allowed to claim.

def test_a_caller_appearing_elsewhere_invalidates_a_cached_absence(repo):
    """The obvious cache key is the defining file, and it is the wrong one.

    A new caller appears in some *other* file. The definition is untouched, so a
    marker keyed to its content hash still looks current, and preflight would go on
    reporting a measured absence that had stopped being true -- the worst kind of
    wrong answer, because it is confidently phrased.
    """
    _commit(repo, "seed", {"core.py": "def load_settings():\n    return 1\n"})
    engine.index_project(str(repo), force=True)
    first = _blast(engine.preflight(str(repo), "core.py", symbol="load_settings"))
    assert first["resolution"]["status"] == "resolved" and not first["dependent_files"]

    _write(repo, "app.py", "from core import load_settings\n\n\n"
                           "def main():\n    return load_settings()\n")

    second = _blast(engine.preflight(str(repo), "core.py", symbol="load_settings"))
    assert second["resolution"]["status"] == "resolved", "the cache had to be dropped"
    assert [os.path.basename(p) for p in second["dependent_files"]] == ["app.py"]


def test_an_existing_file_becoming_a_caller_invalidates_it_too(repo):
    """The set of naming files is unchanged; what one of them does with the name is not."""
    _commit(repo, "seed", {
        "core.py": "def load_settings():\n    return 1\n",
        "app.py": "import core\n\n\n# load_settings is documented here, not called\n",
    })
    engine.index_project(str(repo), force=True)
    first = _blast(engine.preflight(str(repo), "core.py", symbol="load_settings"))
    assert first["dependent_files"] == []
    assert [os.path.basename(p) for p in first["name_match_files"]] == ["app.py"]

    _write(repo, "app.py", "from core import load_settings\n\n\n"
                           "def main():\n    return load_settings()\n")

    second = _blast(engine.preflight(str(repo), "core.py", symbol="load_settings"))
    assert second["resolution"]["status"] == "resolved"
    assert [os.path.basename(p) for p in second["dependent_files"]] == ["app.py"]


def test_an_unchanged_repository_still_answers_from_the_cache(repo):
    """The invalidation has to be tight, or it is just a slower way of never caching."""
    _commit(repo, "seed", {
        "core.py": "def load_settings():\n    return 1\n",
        "notes.md": "nothing here names it\n",
    })
    engine.index_project(str(repo), force=True)
    engine.preflight(str(repo), "core.py", symbol="load_settings")

    # Touching a file that does not name the symbol cannot change who calls it.
    _write(repo, "notes.md", "still nothing here\n")
    _write(repo, "unrelated.py", "def other():\n    return 2\n")

    blast = _blast(engine.preflight(str(repo), "core.py", symbol="load_settings"))
    assert blast["resolution"]["status"] == "cached"


def test_the_budget_spends_the_lead_list_before_the_explanations(repo, monkeypatch):
    """A budget must shorten evidence, never the account of what the evidence is."""
    files = {"core.py": "def load_settings():\n    return 1\n"}
    for n in range(12):
        files[f"user{n}.py"] = ("from core import load_settings\n\n\n"
                                f"def use{n}():\n    return load_settings()\n")
    _commit(repo, "seed", files)
    engine.index_project(str(repo), force=True)

    monkeypatch.setenv("CODESEXTANT_PREFLIGHT_RESOLVE_MAX_FILES", "1")
    full = engine.preflight(str(repo), "core.py", symbol="load_settings",
                            token_budget=10_000)
    assert len(_blast(full)["name_match_files"]) == 12, "12 leads before any trimming"

    trimmed = engine.preflight(str(repo), "core.py", symbol="load_settings",
                               token_budget=300)

    assert trimmed["truncated_by_budget"] is True
    assert trimmed["approx_tokens"] < full["approx_tokens"]
    # Leads are spent down to nothing before a confirmed caller is touched. Here there
    # are none to protect, so the check is that the leads are what paid for the budget.
    assert _blast(trimmed)["name_match_files"] == []


# What counts as "you may already have written this".

def test_a_shared_verb_is_still_not_a_reuse_candidate():
    """The rule that keeps the section worth reading: one shared word is not evidence."""
    assert engine._name_similarity("release_version", "release") == 0.0
    assert engine._name_similarity("get_user", "get") == 0.0
    assert engine._name_similarity("run", "runner") == 0.0


def test_two_names_of_one_shape_differing_in_one_slot_are_a_family():
    """md5_utf8 beside sha256_utf8 is the same code twice, and shares one word.

    An experiment found the strict two-shared-words rule missing every differently
    named structural duplicate in requests -- md5_utf8/sha256_utf8,
    list_domains/list_paths, iterkeys/itervalues -- so the rule now separates a family
    from a shared verb by shape rather than by count.
    """
    assert engine._name_similarity("md5_utf8", "sha256_utf8") == pytest.approx(0.5)
    assert engine._name_similarity("list_domains", "list_paths") == pytest.approx(0.5)
    assert engine._name_similarity("read_config", "write_config") == pytest.approx(0.5)
    # Two slots differing is a different function, not a sibling of this one.
    assert engine._name_similarity("handle_get_request", "handle_post_response") == 0.0
    # And a single word has no shape to share.
    assert engine._name_similarity("iterkeys", "itervalues") == 0.0


def test_a_family_match_drops_out_when_the_bar_is_raised(repo, monkeypatch):
    """It scores exactly at the default threshold, so it is the first thing to go."""
    _commit(repo, "seed", {
        "hashes.py": ("def md5_utf8(value):\n    return value\n\n\n"
                      "def sha256_utf8(value):\n    return value\n"),
    })
    engine.index_project(str(repo), force=True)

    names = [entry["name"] for entry in engine.preflight(
        str(repo), "hashes.py", symbol="sha512_utf8")["already_exists"]]
    assert sorted(names) == ["md5_utf8", "sha256_utf8"]

    monkeypatch.setenv("CODESEXTANT_PREFLIGHT_NAME_SIMILARITY", "0.6")
    assert engine.preflight(str(repo), "hashes.py",
                            symbol="sha512_utf8")["already_exists"] == []


def test_a_name_shared_by_the_whole_project_is_reported_as_a_convention(repo):
    """Eight arbitrary __init__s is worse than nothing: it looks like a finding.

    This is a defect an experiment caught, by scoring the reuse check below plain
    grep on a repository whose structural duplicates were all called __init__.
    """
    files = {}
    for n in range(12):
        files[f"mod{n}.py"] = (f"class Widget{n}:\n"
                               "    def __init__(self, value):\n"
                               "        self.value = value\n")
    _commit(repo, "seed", files)
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "mod0.py", symbol="__init__")

    assert result["already_exists"] == [], "an arbitrary sample of twelve is not evidence"
    note = next(n for n in result["notes"] if "__init__" in n)
    assert "naming convention" in note
    assert "find_duplicates" in note


def test_below_that_threshold_every_match_is_listed_not_sampled(repo):
    """One number for both the cutoff and the list length, so nothing is truncated."""
    files = {}
    for n in range(6):
        files[f"mod{n}.py"] = (f"class Widget{n}:\n"
                               "    def __init__(self, value):\n"
                               "        self.value = value\n")
    _commit(repo, "seed", files)
    engine.index_project(str(repo), force=True)

    found = engine.preflight(str(repo), "mod0.py", symbol="__init__")["already_exists"]
    assert len(found) == 6, "all of them, or none of them, never an arbitrary subset"


# The module-level half of "who breaks", added in 0.27.0 after check gained it in 0.26.0.
#
# Measured over 525 held-out-file cases in six repositories: adding this tier beside
# the two symbol-level ones is +0.050 [+0.029, +0.076] on the blast radius and +0.040
# [+0.018, +0.065] on the whole answer, while *replacing* the leads tier with it is
# +0.004 and not established. So it is added, and the leads stay.

def test_a_file_importing_the_module_is_named_when_nothing_resolves(repo):
    """``report`` reaches ``parse`` through getattr, so no resolver can confirm it.

    That is the case this tier is for. The import is still there to be read, and the
    file still has to change when the module does.
    """
    _commit(repo, "seed", {
        "pkg/__init__.py": "",
        "pkg/parser.py": "def parse(raw):\n    return raw\n",
        "pkg/report.py": "from pkg import parser\n\n\ndef report(raw, name):\n"
                         "    return getattr(parser, name)(raw)\n",
    })
    engine.index_project(str(repo), force=True)

    blast = engine.preflight(str(repo), "pkg/parser.py",
                             symbol="parse")["blast_radius"]

    assert blast["dependent_files"] == [], "getattr resolves to nothing, correctly"
    assert [entry["path"] for entry in blast["module_dependents"]] == ["pkg/report.py"]


def test_the_three_tiers_stay_three_claims_in_the_rendering(repo):
    """Resolved, named, imported: marked apart, because they are not the same claim."""
    _commit(repo, "seed", {
        "pkg/__init__.py": "",
        "pkg/parser.py": "def parse(raw):\n    return raw\n",
        "pkg/user.py": "from pkg import parser\n\n\ndef go(raw, name):\n"
                       "    return getattr(parser, name)(raw)\n",
    })
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "pkg/parser.py", symbol="parse")
    text = "\n".join(render.preflight_lines(result, str(repo)))

    assert "BLAST RADIUS" in text
    assert "import the module" in text
    assert "?  pkg/user.py   (imports this module)" in text


def test_a_module_everything_imports_lists_nothing_and_says_so(repo):
    """Two of forty importers would be an arbitrary two, as with the common-name cutoff."""
    files = {"pkg/__init__.py": "", "pkg/core.py": "def run():\n    return 1\n"}
    for n in range(25):
        files[f"pkg/user{n}.py"] = f"import pkg.core\n\nX{n} = {n}\n"
    _commit(repo, "seed", files)
    engine.index_project(str(repo), force=True)

    result = engine.preflight(str(repo), "pkg/core.py", symbol="run")

    assert result["blast_radius"]["module_dependents"] == []
    assert any("import this module" in note for note in result["notes"])


def test_the_weakest_tier_is_the_first_one_the_budget_takes(repo):
    """A resolved caller outlives a lead, and a lead outlives an importer."""
    _commit(repo, "seed", {
        "pkg/__init__.py": "",
        "pkg/parser.py": "def parse(raw):\n    return raw\n",
        "pkg/user.py": "from pkg import parser\n\n\ndef go(raw, name):\n"
                       "    return getattr(parser, name)(raw)\n",
    })
    engine.index_project(str(repo), force=True)

    roomy = engine.preflight(str(repo), "pkg/parser.py", symbol="parse",
                             token_budget=100_000)
    assert roomy["blast_radius"]["module_dependents"], "the tier is there to be trimmed"

    tight = engine.preflight(str(repo), "pkg/parser.py", symbol="parse", token_budget=60)
    assert tight["blast_radius"]["module_dependents"] == []
    assert tight["truncated_by_budget"] is True
