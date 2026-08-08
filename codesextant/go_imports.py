"""Tree-sitter extraction of import declarations from Go source files."""
from __future__ import annotations

import tree_sitter

from . import symbols


def _node_text(source: bytes, node: tree_sitter.Node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _import_path(source: bytes, path_node: tree_sitter.Node) -> str:
    for child in path_node.named_children:
        if child.type == "interpreted_string_literal_content":
            return _node_text(source, child)
    return ""


def extract_go_imports_from_source(
    source: bytes,
    *,
    file_path: str = "<memory>",
) -> list[dict]:
    """Return Go imports with their explicit alias and source location."""
    spec = symbols.LANGUAGE_SPECS["go"]
    parser = tree_sitter.Parser(symbols._ts_language(spec["language"]))
    tree = parser.parse(source)
    imports: list[dict] = []

    def walk(node: tree_sitter.Node) -> None:
        if node.type == "import_spec":
            path_node = node.child_by_field_name("path")
            if path_node is not None:
                name_node = node.child_by_field_name("name")
                imports.append(
                    {
                        "path": _import_path(source, path_node),
                        "alias": _node_text(source, name_node) if name_node is not None else None,
                        "file_path": file_path,
                        "line": node.start_point[0] + 1,
                    }
                )
            return
        for child in node.named_children:
            walk(child)

    walk(tree.root_node)
    return imports
