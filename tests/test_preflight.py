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

from codesextant import cochange, engine, storage


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
    assert any("looks new" in note for note in result["notes"])


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
    assert result["blast_radius"]["resolved_edges_project_wide"] == 0
    assert any("only fills in as find_references runs" in n for n in result["notes"])


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
