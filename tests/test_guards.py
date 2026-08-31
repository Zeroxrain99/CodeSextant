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
    repository. The fix was never "never show them": exp9 scored that and the file-level
    tiers are worth +0.072 held out where they fill slots nothing else reached. The fix
    is that inheriting a file's relevance can never outrank reading the fence itself,
    and can never be *labelled* as though it had.
    """
    result = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                           token_budget=100_000)
    ordered = [(entry["name"], entry["why"]) for entry in result["guards"]]
    named = {name for name, _why in ordered}
    assert "test_an_unknown_format_is_refused_rather_than_guessed" in named

    positions = {name: index for index, (name, _why) in enumerate(ordered)}
    assert positions["test_an_unknown_format_is_refused_rather_than_guessed"] == 0
    unrelated = positions.get("test_something_entirely_unrelated")
    if unrelated is not None:
        why = dict(ordered)["test_something_entirely_unrelated"]
        assert why.startswith("imports"), (
            "an unrelated fence may fill a leftover slot, but never while claiming to "
            f"name what you changed: {why!r}")
        assert unrelated > positions[
            "test_an_unknown_format_is_refused_rather_than_guessed"]


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


# The importer tier. It was built, rejected by eye for resting on a file-level claim,
# and then scored across 360 commits: +0.072 held out, taking `guards` from 0.228 to
# 0.300. The argument for rejecting it was sound and the conclusion was wrong. What
# follows pins the bounds that make it safe to keep, since the reasoning did not.


def test_a_fence_reachable_only_through_an_import_is_still_found(repo):
    """A test that imports the module and drives it through a helper never spells the
    changed symbol, so every tier that reads names is empty by construction."""
    _write(repo, "tests/test_indirect.py", """
        import pkg.limits


        def drive(fmt):
            return pkg.limits.encode([], fmt)


        def test_the_pipeline_refuses_what_it_cannot_write():
            try:
                drive("xml")
            except ValueError:
                assert True
    """)
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "indirect")
    engine.index_project(str(repo), force=True)

    found = engine.guards(str(repo), target="pkg/limits.py", symbol="nothing_by_this_name",
                          token_budget=100_000)
    reached = {row["path"]: row["why"] for row in found["guards"]}
    assert "tests/test_indirect.py" in reached
    assert reached["tests/test_indirect.py"].startswith("imports")


def test_the_importer_tier_cannot_spend_the_whole_section(repo):
    body = "\n\n".join(
        f"def test_filler_{n}():\n    assert {n} == {n}" for n in range(12))
    _write(repo, "tests/test_bulk.py", "import pkg.limits  # noqa: F401\n\n\n" + body + "\n")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "bulk")
    engine.index_project(str(repo), force=True)

    importers = engine._guard_importer_reach(str(repo), {"pkg/limits.py": "M"}, [])
    rows = engine._guards_in_reach(str(repo), set(), {"pkg/limits.py": "M"}, set(),
                                   None, importers)
    assert "tests/test_bulk.py" in importers
    from_bulk = [row for row in rows if row["path"] == "tests/test_bulk.py"]
    assert len(from_bulk) <= engine._GUARDS_IMPORTER_PER_FILE
    assert len(rows) <= engine._GUARDS_IMPORTER_SHOWN


def test_a_file_level_lead_never_outranks_the_fence_that_names_you(repo):
    """The ordering is the whole safety argument: two file-level tiers exist only to
    fill slots the fence's own text left empty, and a ranking that let either of them
    rise would be the rejected per-file design with extra steps."""
    found = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                          token_budget=100_000)
    tiers = []
    for row in found["guards"]:
        why = row["why"]
        tiers.append(0 if why.startswith("names")
                     else 2 if why.startswith("history")
                     else 3 if why.startswith("imports") else 1)
    assert tiers == sorted(tiers)


# The cap. Six was set by argument -- exp1's finding that a section naming twenty things
# stops being read -- and stayed unmeasured through three versions of this command.
# exp9 priced it: recall at k over 180 held-out commits is 0.233 @1, 0.306 @6, 0.394 @20
# and 0.506 uncapped. Six is not free, so it is a default with a way past it rather than
# a wall, and the number is in the help text where the person paying it can see it.


def test_the_six_shown_is_a_default_and_not_a_ceiling(repo):
    capped = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                           token_budget=100_000)
    raised = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                           token_budget=100_000, limit=20)
    assert len(capped["guards"]) <= engine._GUARDS_SHOWN
    assert len(raised["guards"]) >= len(capped["guards"])
    # Raising it must not reorder what was already there: the extra rows go on the end,
    # or the default answer was not the top of the same list.
    kept = [(row["path"], row["line"]) for row in raised["guards"]][:len(capped["guards"])]
    assert kept == [(row["path"], row["line"]) for row in capped["guards"]]


def test_a_limit_cannot_be_used_to_ask_for_the_whole_repository(repo):
    """A cap a caller can remove is not a cap. The ceiling is what exp9 measured out to,
    and past fifty the section is a second codebase again -- the thing exp8 refused."""
    huge = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                         token_budget=1_000_000, limit=100_000)
    assert len(huge["guards"]) <= engine._GUARDS_LIMIT_MAX
    zero = engine.guards(str(repo), target="pkg/limits.py", symbol="encode",
                         token_budget=100_000, limit=0)
    assert len(zero["guards"]) >= 1, "asking for none is a mistake, not an instruction"


# Schema constraints. `exp10` looked for these in `.sql` first and found none in any of
# ten repositories -- including alembic, a migration tool, which was added to the corpus
# specifically to unblock them. A Python project writes its constraints in Python:
# alembic holds 1,023 across 28 files, touched in 0.325 of its commits. A detector that
# finds nothing in a database library is looking in the wrong place.


def test_a_column_that_forbids_null_is_a_fence_and_one_that_allows_it_is_not(repo):
    """The two families constrain with opposite values, and getting that backwards would
    fill the section with every optional column in the schema."""
    found = guards.extract("models.py", textwrap.dedent("""
        from sqlalchemy import Column, String

        class Order:
            user_id = Column(String, nullable=False)
            note = Column(String, nullable=True)
            slug = Column(String, unique=True)
            tag = Column(String, unique=False)
    """))
    constraints = {g.name: g.rule for g in found if g.kind == "constraint"}
    assert set(constraints) == {"user_id", "slug"}
    assert constraints["user_id"] == "user_id is NOT NULL"
    assert constraints["slug"] == "slug is UNIQUE"


def test_a_standalone_constraint_names_itself_rather_than_one_of_its_columns(repo):
    found = guards.extract("models.py", textwrap.dedent("""
        from sqlalchemy import UniqueConstraint
        table_args = (UniqueConstraint("user_id", "slug"),)
    """))
    row = next(g for g in found if g.kind == "constraint")
    assert row.name == "UniqueConstraint"
    assert row.rule == "UniqueConstraint on user_id, slug"


def test_the_word_nullable_in_prose_is_not_a_constraint(repo):
    """Read from the AST, not the text. A docstring explaining nullability is not a
    fence, and counting it would put prose in a section whose whole claim is that its
    rules come from the code."""
    found = guards.extract("notes.py", textwrap.dedent('''
        """Historically every column was nullable=False; see the migration notes."""
        VALUE = 1
    '''))
    assert not [g for g in found if g.kind == "constraint"]
