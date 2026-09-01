"""Symbol extraction for PineScript, which has no tree-sitter grammar.

Every other language here is read through `tree_sitter_language_pack`, which ships 371
grammars. PineScript is not one of them, so this reads lines. That is a real difference
in kind and it is stated rather than hidden: a grammar knows that a `=>` inside a string
is not a function, and this knows it only because strings are stripped first. Where the
two disagree, this one is wrong.

It is still worth having. The alternative -- what happened before this file existed --
is that a PineScript project indexes to zero symbols, and every question about it comes
back empty. An empty answer and "this tool cannot read your language" look identical and
mean opposite things, and an agent that cannot tell them apart abandons the tool without
learning why.

What Pine actually declares, and what each maps to:

    f_atr_stop(src, len) =>            function
    export f_size(float eq) =>         function, exported from a library
    method next(Signal this) =>        method, scoped to the type it extends
    type Signal                        type; each indented field is a variable on it
    enum Trend                         enum (Pine v6); each member is a variable on it
    MAX_LEVERAGE = 3.0                 variable at the top level
    var count = 0                      variable, `var`/`varip` declared
    lookback = input.int(20, ...)      variable -- and the ones users tune

Line and end_line come from indentation, the way Pine itself scopes a body.
"""
from __future__ import annotations

import re

LANGUAGE = "pinescript"
EXTENSIONS = (".pine",)

# `name(args) =>` at any indent, optionally exported. The name is an identifier and the
# arrow has to be the last thing on the line or followed by a single-line body.
_FUNCTION = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?P<name>[A-Za-z_]\w*)\s*\((?P<args>[^)]*)\)\s*=>")
# `method name(Type this, ...) =>` -- the first parameter's type is what it extends.
_METHOD = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?method\s+(?P<name>[A-Za-z_]\w*)\s*"
    r"\(\s*(?:(?P<owner>[A-Za-z_][\w.]*)\s+)?[A-Za-z_]\w*")
_TYPE = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?P<keyword>type|enum)\s+(?P<name>[A-Za-z_]\w*)")
# An assignment that declares something. Type annotations and var/varip are optional,
# and `:=` is reassignment rather than declaration, so it is excluded.
_ASSIGN = re.compile(
    r"^(?P<indent>\s*)(?:(?:var|varip|const)\s+)?"
    r"(?:(?:float|int|bool|string|color|line|label|box|table|array|matrix|map|"
    r"simple|series)(?:<[^>]*>)?\s+)?"
    r"(?P<name>[A-Za-z_]\w*)\s*=(?!=|>)")
_DECLARATION = re.compile(r"^\s*(?:indicator|strategy|library)\s*\(")
# A field inside a `type` body: `float price`, `int bar = 0`, `Signal[] history`.
# Unlike a top-level assignment these have no `=`, so they need their own pattern --
# and they are worth having, because `this.price` is exactly the kind of reference an
# impact question is asking about.
_FIELD = re.compile(
    r"^\s*(?P<type>[A-Za-z_][\w.]*(?:<[^>]*>)?(?:\[\])?)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:=(?!=)|$)")
# An enum member is a bare identifier on its own line inside an `enum` body, optionally
# with a display string: `up = "Up"`.
_ENUM_MEMBER = re.compile(r"^\s*(?P<name>[A-Za-z_]\w*)\s*(?:=(?!=)[^=]*)?$")

_STRING = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')


def _strip(line: str) -> str:
    """Remove strings and the trailing comment, keeping the line's length semantics.

    Strings first, then `//`: a `//` inside a string is not a comment, and stripping
    comments first would truncate `plot(close, "a // b")` in the middle of its argument
    list and lose the closing paren.
    """
    without_strings = _STRING.sub(lambda m: '"' + "x" * (len(m.group(0)) - 2) + '"', line)
    cut = without_strings.find("//")
    return without_strings if cut < 0 else without_strings[:cut]


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def _body_end(lines: list[str], start: int, own_indent: int) -> int:
    """The last line of a block opened at ``start``, by indentation.

    Blank lines do not close a block -- Pine allows them inside one -- so the end is the
    last line that is both non-blank and more indented than the opener.
    """
    end = start
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        if _indent_of(line) <= own_indent:
            break
        end = index
    return end


def extract_symbols(source: str, file_path: str = "<memory>") -> list[dict]:
    """Definitions in one PineScript file, in the shape every other language returns.

    Same keys as the tree-sitter path -- kind, name, line, end_line, scope -- because a
    caller that has to know which language produced a record will eventually forget to.
    """
    lines = source.splitlines()
    found: list[dict] = []
    # Type and enum bodies are the only scopes Pine has; a `=>` body is a closure whose
    # locals are not addressable from outside, so nothing inside one is a definition
    # worth indexing.
    open_scopes: list[tuple[int, str, int, str]] = []  # (indent, name, end index, kind)

    for index, raw in enumerate(lines):
        line = _strip(raw)
        if not line.strip():
            continue
        indent = _indent_of(line)
        while open_scopes and index > open_scopes[-1][2]:
            open_scopes.pop()
        inside = (open_scopes[-1] if open_scopes and indent > open_scopes[-1][0]
                  else None)
        scope = inside[1] if inside else ""

        matched = _TYPE.match(line)
        if matched:
            end = _body_end(lines, index, indent)
            found.append({"kind": matched.group("keyword"),
                          "name": matched.group("name"),
                          "line": index + 1, "end_line": end + 1, "scope": scope})
            open_scopes.append((indent, matched.group("name"), end,
                                matched.group("keyword")))
            continue

        matched = _METHOD.match(line)
        if matched:
            found.append({"kind": "method", "name": matched.group("name"),
                          "line": index + 1,
                          "end_line": _body_end(lines, index, indent) + 1,
                          "scope": matched.group("owner") or scope})
            continue

        matched = _FUNCTION.match(line)
        if matched and not _DECLARATION.match(line):
            found.append({"kind": "function", "name": matched.group("name"),
                          "line": index + 1,
                          "end_line": _body_end(lines, index, indent) + 1,
                          "scope": scope})
            continue

        # Inside a type or an enum body, the members are declared without `=`.
        if inside:
            member = (_ENUM_MEMBER.match(line) if inside[3] == "enum"
                      else _FIELD.match(line))
            if member:
                found.append({"kind": "variable", "name": member.group("name"),
                              "line": index + 1, "end_line": index + 1,
                              "scope": scope})
                continue

        matched = _ASSIGN.match(line)
        # Only declarations that are addressable: the top level, or a type's fields.
        if matched and (indent == 0 or scope):
            found.append({"kind": "variable", "name": matched.group("name"),
                          "line": index + 1, "end_line": index + 1, "scope": scope})

    return found
