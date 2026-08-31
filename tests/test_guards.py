"""The fences a change is about to meet, and why this answer is shaped the way it is.

The design these pin was not chosen, it was measured into shape. ``exp8`` surveyed seven
repositories and refused the obvious registry: guards are dense (16-34 per thousand
lines), the author's reason is missing for four in five, and the commit that introduced
them does not carry it either (0.00-0.04). So the answer leads with a *derived rule*
rather than prose, discloses progressively, and admits a fence only on per-guard
evidence.

Each test below fixes one of those decisions, because each was arrived at by throwing
away a version that did not have it.
"""
from __future__ import annotations

import subprocess
import textwrap

import pytest

from codesextant import engine, guards, render


def _run(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "proj"
    root.mkdir()
    _run(root, "init", "-q")
    _run(root, "config", "user.email", "test@example.com")
    _run(root, "config", "user.name", "Test")
    _write(root, "pkg/__init__.py", "")
    _write(root, "pkg/limits.py", """
        # A request larger than this is a mistake upstream, not a big request.
        MAX_BATCH_SIZE = 100

        SUPPORTED_FORMATS = ("json", "csv", "ndjson")

        DEBUG = 0


        def encode(rows, fmt):
            if fmt not in SUPPORTED_FORMATS:
                raise ValueError(f"unsupported {fmt}; add it to SUPPORTED_FORMATS first")
            return fmt
    """)
    _write(root, "tests/test_limits.py", """
        from pkg.limits import encode


        def test_an_unknown_format_is_refused_rather_than_guessed():
            \"\"\"A silent fallback shipped bad data once; the allowlist is the fence.\"\"\"
            try:
                encode([], "xml")
            except ValueError as exc:
                assert "SUPPORTED_FORMATS" in str(exc)


        def test_something_entirely_unrelated():
            assert 1 + 1 == 2
    """)
    _run(root, "add", "-A")
    _run(root, "commit", "-q", "-m", "seed")
    engine.index_project(str(root), force=True)
    return root


# The rule is the point: it exists whether or not anybody wrote down why.

def test_every_guard_carries_a_rule_derived_from_the_code(repo):
    """Four guards in five have no stated reason. A registry of names would be useless
    for exactly those, which is why what a fence *checks* is derived rather than read."""
    found = guards.extract_file(str(repo / "pkg/limits.py"), "pkg/limits.py")
    by_name = {guard.name: guard for guard in found}

    assert by_name["MAX_BATCH_SIZE"].rule == "MAX_BATCH_SIZE = 100"
    assert by_name["SUPPORTED_FORMATS"].rule == (
        "SUPPORTED_FORMATS admits 3: 'json', 'csv', 'ndjson'")
    assert "add it to SUPPORTED_FORMATS first" in by_name["ValueError"].rule
    assert all(guard.rule for guard in found), "a guard with no rule is a guard with no use"


def test_a_stated_reason_is_kept_and_labelled_with_who_said_it(repo):
    """"The author said this" and "the tool derived this" are different claims, and a
    reader deciding whether to satisfy a fence or move it needs to tell them apart."""
    found = {g.name: g for g in
             guards.extract_file(str(repo / "pkg/limits.py"), "pkg/limits.py")}

    limit = found["MAX_BATCH_SIZE"]
    assert limit.reason.startswith("A request larger than this")
    assert limit.reason_source == "comment"

    assert found["SUPPORTED_FORMATS"].reason == "", "nobody wrote one, so none is claimed"
    assert found["SUPPORTED_FORMATS"].reason_source == "none"
    assert found["SUPPORTED_FORMATS"].rule, "and the rule carries the answer regardless"


def test_a_constant_that_gates_nothing_is_not_a_guard(repo):
    """`DEBUG = 0` is a module-level number and is not a fence. A section that lists
    every constant is a section nobody reads twice."""
    names = {g.name for g in
             guards.extract_file(str(repo / "pkg/limits.py"), "pkg/limits.py")}
    assert "MAX_BATCH_SIZE" in names
    assert "DEBUG" not in names


# Relevance, which is what makes hundreds of guards into a handful.

def test_the_test_that_fences_a_symbol_is_found_and_comes_first(repo):
    """The whole point, in one assertion: ask about `encode` and the fence that will
    fail is at the top, with the reason its author left."""
    result = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                           token_budget=100_000)
    first = result["guards"][0]

    assert first["kind"] == "test"
    assert first["name"] == "test_an_unknown_format_is_refused_rather_than_guessed"
    assert first["why"] == "names encode"
    assert "SUPPORTED_FORMATS" in first["rule"]
    assert first["reason_source"] == "docstring"


def test_a_file_mentioning_a_symbol_does_not_drag_in_its_other_guards(repo):
    """The defect that made the first version unreadable.

    `tests/test_limits.py` names `encode`, but only one of its two tests does. Letting
    a guard inherit its file's relevance put unrelated fences in front of the one that
    mattered -- eleven environment switches ahead of the three tests, on the real
    repository. Evidence is now required per guard.
    """
    result = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                           token_budget=100_000)
    named = {entry["name"] for entry in result["guards"]}

    assert "test_an_unknown_format_is_refused_rather_than_guessed" in named
    assert "test_something_entirely_unrelated" not in named


# Progressive disclosure, because 182 to 935 guards will not fit and never could.

def test_the_third_layer_is_not_fetched_unless_it_is_asked_for(repo):
    """Layer three is the expensive one and rarely the one needed."""
    quiet = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                          token_budget=100_000)
    assert all("source" not in entry for entry in quiet["guards"])

    loud = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                         full=True, token_budget=100_000)
    body = loud["guards"][0]["source"]
    assert "def test_an_unknown_format_is_refused_rather_than_guessed" in body
    assert "SUPPORTED_FORMATS" in body


def test_what_is_withheld_is_counted_rather_than_dropped_silently(repo):
    """A cut list that does not say it was cut reads as "there were only six"."""
    result = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                           token_budget=100_000)
    assert result["total_in_reach"] >= len(result["guards"])
    assert len(result["guards"]) <= engine._GUARDS_SHOWN

    tight = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                          token_budget=120)
    assert tight["truncated_by_budget"] is True
    assert tight["approx_tokens"] <= 120 or not tight["guards"]


def test_finding_nothing_is_reported_as_a_search_not_a_clean_bill(repo):
    _write(repo, "pkg/quiet.py", "def plain(value):\n    return value\n")
    engine.index_project(str(repo), force=True)

    result = engine.guards(str(repo), target="pkg/quiet.py", symbol="plain",
                           token_budget=100_000)

    assert result["guards"] == []
    note = " ".join(result["notes"])
    assert "not a clean bill of health" in note
    assert "Only Python" in note or "only Python" in note


# The diff-driven half, and the one renderer both surfaces print from.

def test_the_diff_is_read_when_no_target_is_given(repo):
    _write(repo, "pkg/limits.py", """
        # A request larger than this is a mistake upstream, not a big request.
        MAX_BATCH_SIZE = 100

        SUPPORTED_FORMATS = ("json", "csv", "ndjson")


        def encode(rows, fmt):
            if fmt not in SUPPORTED_FORMATS:
                raise ValueError(f"unsupported {fmt}; add it to SUPPORTED_FORMATS first")
            return fmt.upper()
    """)
    engine.index_project(str(repo), force=True)

    result = engine.guards(str(repo), token_budget=100_000)

    assert result["changed_files"] == ["pkg/limits.py"]
    assert any(entry["name"] == "test_an_unknown_format_is_refused_rather_than_guessed"
               for entry in result["guards"]), "editing encode still meets its fence"


def test_the_rendering_separates_what_it_checks_from_why_it_is_there(repo):
    result = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                           token_budget=100_000)
    text = "\n".join(render.guards_lines(result, str(repo)))

    assert "checks" in text
    assert "because" in text and "(docstring)" in text
    assert "reached  names encode" in text


# The history tier. It is the one per-file claim the section admits, and it is here
# because exp9 measured it rather than because it sounded reasonable: the symbol tiers
# reach 0.206 held out, history alone 0.150, and the two together 0.317. What follows
# pins the three things that make it safe to admit -- it is labelled, it is bounded, and
# it never displaces evidence read off the fence itself.


@pytest.fixture()
def repo_with_history(repo):
    """A companion pair: ``pkg/render.py`` and ``tests/test_render.py`` move together.

    Four commits touching both, and none naming a symbol from ``pkg/limits.py``, so the
    fence in the companion is reachable by history and by nothing else -- which is the
    case the tier exists for.
    """
    _write(repo, "pkg/render.py", "def render(rows):\n    return rows\n")
    _write(repo, "tests/test_render.py", """
        from pkg.render import render


        def test_render_returns_rows():
            assert render([1]) == [1]
    """)
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "render")
    for n in range(4):
        _write(repo, "pkg/render.py", f"def render(rows):\n    return rows[:{n + 1}]\n")
        _write(repo, "tests/test_render.py", f"""
            from pkg.render import render


            def test_render_returns_rows():
                assert render([1]) == [1][:{n + 1}]
        """)
        _run(repo, "add", "-A")
        _run(repo, "commit", "-q", "-m", f"render {n}")
    engine.index_project(str(repo), force=True)
    return repo


def test_a_fence_reachable_only_through_history_is_still_found(repo_with_history):
    found = engine.guards(str(repo_with_history), target="pkg/render.py")
    reached = {row["path"]: row["why"] for row in found["guards"]}
    assert "tests/test_render.py" in reached
    assert reached["tests/test_render.py"].startswith("history: changes with")


def test_the_history_tier_says_it_is_history_and_how_strong(repo_with_history):
    """A file-level claim printed as though it were the fence's own text is a lie the
    reader cannot detect. It says which claim it rests on, and how much of one."""
    found = engine.guards(str(repo_with_history), target="pkg/render.py")
    row = next(r for r in found["guards"] if r["path"] == "tests/test_render.py")
    assert 0.0 < row["history_confidence"] <= 1.0
    printed = "\n".join(render.guards_lines(found))
    assert "history: changes with pkg/render.py" in printed
    assert f"({row['history_confidence']} confidence)" in printed


def test_history_never_outranks_a_fence_that_names_what_you_changed(repo_with_history):
    """The tier fills the slots the first two left empty. It does not compete for
    theirs: naming the symbol is evidence about the fence, history is evidence about
    its file, and mixing the two orders would sell the weaker claim as the stronger."""
    found = engine.guards(str(repo_with_history), target="pkg/limits.py",
                          symbol="encode")
    tiers = [0 if row["why"].startswith("names")
             else 2 if row["why"].startswith("history") else 1
             for row in found["guards"]]
    assert tiers == sorted(tiers)
    assert tiers[0] == 0, "the fence naming the changed symbol still leads"


def test_the_history_tier_cannot_spend_the_whole_section(repo_with_history):
    """One companion holding forty tests would otherwise bury everything above it. Two
    guards from each of three files: enough to fill an empty section, never more."""
    body = "\n\n".join(
        f"def test_number_{n}():\n    assert {n} == {n}" for n in range(12))
    _write(repo_with_history, "tests/test_render.py",
           "from pkg.render import render\n\n\n" + body + "\n")
    _run(repo_with_history, "add", "-A")
    _run(repo_with_history, "commit", "-q", "-m", "many tests")
    engine.index_project(str(repo_with_history), force=True)

    history = engine._guard_history_reach(str(repo_with_history), {"pkg/render.py": "M"})
    rows = engine._guards_in_reach(str(repo_with_history), set(), {}, set(), history)
    assert len(history) <= engine._GUARDS_HISTORY_SCAN
    per_file = [r for r in rows if r["path"] == "tests/test_render.py"]
    assert len(per_file) <= engine._GUARDS_HISTORY_PER_FILE


def test_a_companion_already_reached_by_name_is_not_listed_twice(repo_with_history):
    found = engine.guards(str(repo_with_history), target="pkg/render.py",
                          symbol="render")
    keys = [(row["path"], row["line"]) for row in found["guards"]]
    assert len(keys) == len(set(keys))
    named = [row for row in found["guards"]
             if row["path"] == "tests/test_render.py" and row["why"].startswith("names")]
    assert named, "the stronger evidence is the one kept"
