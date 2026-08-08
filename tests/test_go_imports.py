from __future__ import annotations

import textwrap

from codesextant.go_imports import extract_go_imports_from_source


def _imports(source: str, file_path: str = "main.go") -> list[dict]:
    return extract_go_imports_from_source(
        textwrap.dedent(source).encode("utf-8"),
        file_path=file_path,
    )


def test_extracts_single_import_with_source_location():
    assert _imports(
        """
        package demo

        import "fmt"
        """,
        file_path="cmd/demo/main.go",
    ) == [
        {
            "path": "fmt",
            "alias": None,
            "file_path": "cmd/demo/main.go",
            "line": 4,
        }
    ]


def test_extracts_each_import_from_group():
    assert _imports(
        """
        package demo
        import (
            "fmt"
            "os"
        )
        """
    ) == [
        {"path": "fmt", "alias": None, "file_path": "main.go", "line": 4},
        {"path": "os", "alias": None, "file_path": "main.go", "line": 5},
    ]


def test_extracts_named_import_alias():
    assert _imports(
        """
        package demo
        import logpkg "example.com/acme/logging"
        """
    ) == [
        {
            "path": "example.com/acme/logging",
            "alias": "logpkg",
            "file_path": "main.go",
            "line": 3,
        }
    ]


def test_extracts_blank_and_dot_import_aliases():
    assert _imports(
        """
        package demo
        import (
            _ "example.com/acme/driver"
            . "example.com/acme/helpers"
        )
        """
    ) == [
        {
            "path": "example.com/acme/driver",
            "alias": "_",
            "file_path": "main.go",
            "line": 4,
        },
        {
            "path": "example.com/acme/helpers",
            "alias": ".",
            "file_path": "main.go",
            "line": 5,
        },
    ]


def test_returns_empty_list_when_source_has_no_imports():
    assert _imports(
        """
        package demo

        func main() {}
        """
    ) == []
