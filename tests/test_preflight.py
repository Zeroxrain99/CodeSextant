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

    monkeypatch.setattr(engine.cochange, "mine", explode)

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
    result = engine.preflight(str(repo), "mod0.py", symbol="function_number_0",
                              token_budget=200)
    served = len(json.dumps(result, ensure_ascii=False, default=str)) // 4
    assert served <= 260, f"budget 200 served about {served} tokens"
    assert result["truncated_by_budget"] is True


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


def test_storage_replaces_rules_wholesale(repo):
    """Rules describe the history up to one commit; a half-updated mixture describes none."""
    _commit(repo, "seed", {"app.py": "A = 1\n"})
    engine.index_project(str(repo), force=True)
    with storage.ProjectStore.open(str(repo)) as store:
        store.store_cochange_rules(
            [{"path": "old.py", "companion": "gone.py", "support": 9,
              "changes": 9, "confidence": 1.0}], "sha-one")
        assert store.cochange_for("old.py")
        store.store_cochange_rules([], "sha-two")
        assert store.cochange_for("old.py") == []
        assert store.cochange_head() == "sha-two"


def test_preflight_is_reachable_over_http_and_is_interactive():
    """It is called before every edit, so it needs reserved capacity, not a heavy queue."""
    from codesextant import daemon

    assert "/preflight" in daemon._ROUTES_GET
    assert "/preflight" in daemon._HEAVY_PATHS
    assert "/preflight" in daemon._INTERACTIVE_HEAVY_PATHS
    assert os.path.basename(__file__) == "test_preflight.py"
