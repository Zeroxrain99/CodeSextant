"""PineScript, which is read line by line because no grammar exists for it.

Every other language here goes through `tree_sitter_language_pack`, which ships 371
grammars and does not ship this one. So this reader is a weaker instrument, and these
tests exist to pin exactly where it is weak -- a grammar knows a `=>` inside a string is
not a function, and this knows it only because strings are stripped first.

It is still worth having. Before it, a PineScript project indexed to zero symbols and
every question about it came back empty -- and an empty answer is indistinguishable from
"this tool cannot read your language" unless something says so.
"""
from __future__ import annotations

import textwrap

import pytest

from codesextant import engine, pinescript, references, symbols


def _extract(source: str) -> dict[str, dict]:
    return {s["name"]: s for s in pinescript.extract_symbols(textwrap.dedent(source))}


def test_the_forms_pine_uses_to_declare_things():
    found = _extract('''
        //@version=6
        indicator("Demo", overlay=true)

        MAX_LEVERAGE = 3.0
        var counter = 0
        lookback = input.int(20, "Lookback")

        export f_size(float equity, float risk) =>
            equity * risk

        oneLiner(x) => x * 2
    ''')
    assert found["f_size"]["kind"] == "function"
    assert found["oneLiner"]["kind"] == "function"
    assert found["MAX_LEVERAGE"]["kind"] == "variable"
    assert found["counter"]["kind"] == "variable"
    assert found["lookback"]["kind"] == "variable"
    # The script declaration is a call, not a definition.
    assert "indicator" not in found


def test_a_type_and_its_fields_and_an_enum_and_its_members():
    """Fields are the point: `this.price` is exactly the reference an impact question
    is asking about, and a type whose fields are invisible answers it wrongly."""
    found = _extract('''
        type Signal
            float price
            int   bar = 0
            Order[] history

        enum Trend
            up = "Up"
            down

        method isFresh(Signal this, int maxAge) =>
            bar_index - this.bar < maxAge
    ''')
    assert found["Signal"]["kind"] == "type"
    assert found["Trend"]["kind"] == "enum"
    assert [found[n]["scope"] for n in ("price", "bar", "history")] == ["Signal"] * 3
    assert [found[n]["scope"] for n in ("up", "down")] == ["Trend"] * 2
    # A method is scoped to the type its first parameter extends, not to the file.
    assert found["isFresh"]["kind"] == "method"
    assert found["isFresh"]["scope"] == "Signal"


def test_an_arrow_inside_a_string_is_not_a_function():
    """The one thing a line reader gets wrong if it is careless, so it is pinned."""
    found = _extract('''
        msg = "this => is not a function // and this is not a comment"
        plot(close, "series // with a marker")
    ''')
    assert set(found) == {"msg"}


def test_reassignment_is_not_a_second_declaration():
    found = _extract('''
        counter = 0
        counter := counter + 1
    ''')
    assert found["counter"]["line"] == 2


def test_a_body_is_scoped_by_indentation_the_way_pine_scopes_it():
    found = _extract('''
        f_outer(a) =>
            step = a * 2

            step + 1

        after = 1
    ''')
    assert found["f_outer"]["line"] == 2
    assert found["f_outer"]["end_line"] == 5, "a blank line does not close a body"
    # A local inside a closure is not addressable from outside, so it is not indexed.
    assert "step" not in found
    assert found["after"]["line"] == 7


# Wiring: the rest of the tool has to see this as a language like any other.

def test_pine_is_registered_as_a_language_without_a_grammar():
    assert symbols.language_for_file("strategy.pine") == "pinescript"
    assert ".pine" in symbols.SUPPORTED_EXTENSIONS
    assert not symbols.has_grammar("pinescript")
    assert symbols.has_grammar("python")


def test_extraction_goes_through_the_one_entry_point_every_language_uses():
    """A caller that has to know which language produced a record will forget to."""
    rows = symbols.extract_symbols_from_source(
        b"f_x(a) =>\n    a + 1\n", "pinescript", file_path="a.pine")
    assert rows == [{"kind": "function", "name": "f_x", "line": 1, "end_line": 2,
                     "scope": ""}]


def test_a_pine_project_indexes_and_answers_instead_of_coming_back_empty(
        tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "pine"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "risk.pine").write_text(textwrap.dedent('''
        //@version=5
        library("risk")

        export f_position_size(float equity, float risk) =>
            equity * risk
    ''').lstrip(), encoding="utf-8")
    (root / "entry.pine").write_text(textwrap.dedent('''
        //@version=5
        strategy("Entry")
        import myuser/risk/1 as risk
        size = risk.f_position_size(strategy.equity, 0.01)
    ''').lstrip(), encoding="utf-8")

    report = engine.index_project(str(root), force=True)
    assert report["indexed"] == 2
    assert report["errors"] == 0
    # By name rather than by count: the exported function and the variable that holds
    # the call. `import myuser/risk/1 as risk` is not a definition and must not be one.
    names = {row["name"] for row in engine.get_symbols(str(root))["symbols"]}
    assert {"f_position_size", "size"} <= names
    assert "risk" not in names

    found = engine.find_references(str(root), "f_position_size")
    hits = {m["src_path"] for m in found["low_confidence"]}
    assert any(p.endswith("entry.pine") for p in hits), (
        "the call site is the whole reason to index this language")
    assert found["high_confidence"] == [], "name matching is not a resolved reference"


def test_impact_says_the_chain_cannot_fill_in_rather_than_sending_you_in_a_loop(
        tmp_path, monkeypatch):
    """Its standing advice is "run find_references to accumulate edges". Without a
    resolver that loop cannot terminate, and an empty chain reads as "nothing depends on
    this" when it means "nobody can tell you"."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "pine"
    root.mkdir()
    (root / "a.pine").write_text("f_x(a) =>\n    a + 1\n", encoding="utf-8")
    engine.index_project(str(root), force=True)

    note = engine.impact(str(root), "f_x")["note"]
    assert "no import resolver for 'pinescript'" in note
    assert "not as 'nothing depends on this'" in note


def test_which_languages_claim_a_resolver_is_stated_once():
    assert references.resolves_imports("python")
    assert not references.resolves_imports("pinescript")
    assert not references.resolves_imports(None)


@pytest.mark.parametrize("source", ["", "\n\n", "// only a comment\n"])
def test_a_file_with_nothing_in_it_is_not_an_error(source):
    assert pinescript.extract_symbols(source) == []
