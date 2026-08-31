"""Model Context Protocol server: CodeSextant as tools an agent can just call.

Why this exists
---------------
Everything CodeSextant knows was already reachable -- through the CLI, through
``CodesextantClient``, through HTTP.  All three ask the agent to write code
first.  An agent weighing "fifteen lines of Python and a daemon I have to reason
about" against "one ``rg`` call" picks ``rg``, and then rebuilds something that
already existed.  The index is only worth having if consulting it is cheaper
than not consulting it, so the calling convention is part of the feature.

The protocol is spoken directly -- JSON-RPC 2.0, newline-delimited, over stdin
and stdout -- rather than through an SDK.  CodeSextant depends on tree-sitter,
jedi and watchdog and nothing else; a server this size does not justify a fourth
dependency, and the wire format is stable and small.

Requests are served by the shared local daemon when it will start, so several
agents on one machine share one index and one process rather than each paying
for their own.  When the daemon will not start the same call runs in-process and
the answer says so, because a tool that fails is a tool that gets abandoned.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from . import __version__, render
from .lazy_import import LazyModule

# Importing the engine costs tree-sitter; the daemon path never needs it. The
# TYPE_CHECKING branch never runs, and is there so static analysis can still see what
# the name is -- a call through an unannotated proxy is invisible to reference
# resolution, CodeSextant's own included.
if TYPE_CHECKING:
    from . import engine
else:
    engine = LazyModule(f"{__package__}.engine")

SERVER_NAME = "codesextant"
SERVER_TITLE = "CodeSextant"

# Newest first. A client asking for one of these gets it back verbatim; anything
# else is answered with the newest, which is what the specification requires of a
# server that cannot speak the requested revision.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

# Shown to the model once, at connect time. It says when to call preflight rather
# than what preflight returns, because the failure this server addresses is not
# misreading the answer -- it is never asking.
INSTRUCTIONS = """\
CodeSextant answers questions about this repository from a local index. Nothing leaves \
the machine and no model is called.

Call preflight BEFORE writing or changing code, not after. One call answers the three \
questions that cause the most rework: whether the thing you are about to build already \
exists, which files this repository's history says change together with the one you are \
editing (tests, allowlists, fixtures -- the half nothing in the source mentions), and \
which files hold references that your change would break.

The reference graph fills in as find_references runs, so a small blast radius early on \
means "not yet resolved", not "nothing depends on this"; the answer says which it is. If \
the project has never been indexed, the first call indexes it and tells you so.\
"""


class RpcError(Exception):
    """A JSON-RPC-level failure: the request itself could not be honoured."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


# ── argument coercion ────────────────────────────────────────────────────────
# Arguments arrive from a model, so they arrive wrong sometimes. Each coercion
# says which argument and what was expected: an agent can act on that, whereas a
# bare TypeError sends it back to guessing.

def _require_str(arguments: dict, key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RpcError(-32602, f"{key!r} is required and must be a non-empty string")
    return value


def _optional_str(arguments: dict, key: str) -> str | None:
    value = arguments.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise RpcError(-32602, f"{key!r} must be a string, got {type(value).__name__}")
    return value


def _optional_int(arguments: dict, key: str, default: int | None = None) -> int | None:
    value = arguments.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RpcError(-32602, f"{key!r} must be an integer, got {type(value).__name__}")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise RpcError(-32602, f"{key!r} must be an integer, got {value!r}") from None


def _optional_float(arguments: dict, key: str) -> float | None:
    value = arguments.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise RpcError(-32602, f"{key!r} must be a number, got {value!r}") from None


def _optional_bool(arguments: dict, key: str, default: bool = False) -> bool:
    value = arguments.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _optional_list(arguments: dict, key: str) -> list[str] | None:
    value = arguments.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = [part for part in (p.strip() for p in value.split(",")) if part]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise RpcError(-32602, f"{key!r} must be a list of strings")
    return value or None


_TEXT_ATTRIBUTE = "_codesextant_reason"


def _error_text(exc: BaseException) -> str:
    """The message a daemon or engine failure actually carries.

    An HTTPError prints as "HTTP Error 500: Internal Server Error", which names
    nothing. The daemon puts the real reason in the JSON body, so read it -- but
    a response body can only be read once, and this function is called more than
    once for the same exception (to classify it, then to report it). The second
    read returns nothing, so the answer is remembered on the exception instead of
    silently decaying back into "HTTP Error 500".
    """
    cached = getattr(exc, _TEXT_ATTRIBUTE, None)
    if cached is not None:
        return cached
    text = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", "replace")
        except (OSError, ValueError, AttributeError):
            body = ""
        if body.strip():
            try:
                parsed = json.loads(body)
            except ValueError:
                text = body.strip()
            else:
                text = (str(parsed["error"])
                        if isinstance(parsed, dict) and parsed.get("error")
                        else body.strip())
    try:
        setattr(exc, _TEXT_ATTRIBUTE, text)
    except AttributeError:  # an exception type with __slots__
        pass
    return text


def _means_unindexed(message: str) -> bool:
    return "has not been indexed" in message or "not been indexed yet" in message


# ── backend ──────────────────────────────────────────────────────────────────

class Backend:
    """Route a tool call to the shared daemon, or in-process when that is not possible.

    Two degradations are handled here rather than surfaced as failures, because a
    tool that returns an error is a tool the agent stops calling:

    * the daemon will not start -- run the same query in this process and say so;
    * the project has never been indexed -- index it once, then answer.

    Both leave a note on the next answer.  Silently degrading would be worse than
    failing: the caller would weigh a first-call-cold answer as if it were warm.
    """

    def __init__(self, project: str | None = None, *, use_daemon: bool = True):
        self.default_project = os.path.abspath(
            project or os.environ.get("CODESEXTANT_PROJECT") or os.getcwd())
        self._client = None
        self._direct_reason: str | None = (
            None if use_daemon else "the daemon is switched off (CODESEXTANT_MCP_NO_DAEMON)")
        self._indexed: set[str] = set()
        self._notes: list[str] = []

    # -- notes the next answer has to carry --
    def note(self, text: str) -> None:
        if text not in self._notes:
            self._notes.append(text)

    def take_notes(self) -> list[str]:
        notes, self._notes = self._notes, []
        return notes

    def resolve_project(self, arguments: dict) -> str:
        override = _optional_str(arguments, "project")
        return os.path.abspath(override) if override else self.default_project

    # -- transport --
    def _daemon(self):
        if self._direct_reason is not None:
            return None
        if self._client is None:
            try:
                from .client import CodesextantClient
                client = CodesextantClient(project=self.default_project)
                outcome = client.ensure()
            except Exception as exc:  # noqa: BLE001 - any startup failure means in-process
                self._fall_back(f"the shared daemon would not start ({_error_text(exc)})")
                return None
            if outcome.get("action") not in ("already-running", "spawned"):
                self._fall_back(
                    f"the shared daemon would not start ({outcome.get('action')})")
                return None
            self._client = client
        return self._client

    def _fall_back(self, reason: str) -> None:
        self._direct_reason = reason
        self.note(f"Answered in this process rather than the shared daemon: {reason}. "
                  "Results are the same; each agent pays for its own index load.")

    def execute(self, arguments: dict,
                daemon_call: Callable[[Any, str], dict],
                direct_call: Callable[[str], dict]) -> dict:
        project = self.resolve_project(arguments)
        try:
            return self._attempt(project, daemon_call, direct_call)
        except (RuntimeError, urllib.error.HTTPError) as exc:
            message = _error_text(exc)
            if not _means_unindexed(message) or project in self._indexed:
                raise
        # First contact with a repository nobody has indexed. Do it once, say so, and
        # answer the question that was actually asked.
        self._indexed.add(project)
        self._attempt(project,
                      lambda client, p: client.reindex(project=p),
                      lambda p: engine.index_project(p))
        self.note("This project had never been indexed; CodeSextant indexed it before "
                  "answering. Later calls reuse that index incrementally.")
        return self._attempt(project, daemon_call, direct_call)

    def _attempt(self, project: str,
                 daemon_call: Callable[[Any, str], dict],
                 direct_call: Callable[[str], dict]) -> dict:
        client = self._daemon()
        if client is not None:
            try:
                return daemon_call(client, project)
            except urllib.error.HTTPError:
                raise  # the daemon answered; the answer is "no", and it means it
            except TimeoutError:
                # The daemon is alive and busy. Re-running the same expensive query
                # in this process would double the work that is already too slow.
                raise
            except (urllib.error.URLError, ConnectionError, PermissionError,
                    RuntimeError, OSError) as exc:
                self._client = None
                self._fall_back(_error_text(exc))
        return direct_call(project)


# ── tools ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    schema: dict
    run: Callable[[Backend, dict], dict]
    render: Callable[[dict, str | None], list[str]]

    def describe(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.schema,
            # Nothing here writes to the repository or reaches the network.
            "annotations": {"readOnlyHint": self.name != "index",
                            "destructiveHint": False, "openWorldHint": False},
        }


_PROJECT_ARG = {
    "type": "string",
    "description": "Project root. Defaults to the directory the server was started in; "
                   "pass it only when working across several repositories.",
}


def _t_preflight(backend: Backend, arguments: dict) -> dict:
    target = _require_str(arguments, "file")
    symbol = _optional_str(arguments, "symbol")
    budget = _optional_int(arguments, "budget", 1200)
    # Passed through uncoerced: the engine normalizes it, so "auto", true and "yes"
    # cannot come to mean three different things on three surfaces.
    resolve = arguments.get("resolve")
    return backend.execute(
        arguments,
        lambda client, project: client.preflight(
            target, symbol=symbol, budget=budget, project=project, resolve=resolve),
        lambda project: engine.preflight(
            project, target, symbol=symbol, token_budget=budget, resolve=resolve),
    )


def _t_code_map(backend: Backend, arguments: dict) -> dict:
    budget = _optional_int(arguments, "budget", 2000)
    focus_files = _optional_list(arguments, "focus_files")
    focus_symbols = _optional_list(arguments, "focus_symbols")
    return backend.execute(
        arguments,
        lambda client, project: client.get_map(
            budget=budget, project=project,
            focus_files=focus_files, focus_symbols=focus_symbols),
        lambda project: engine.get_map(
            project, token_budget=budget,
            focus_files=focus_files, focus_symbols=focus_symbols),
    )


def _t_find_references(backend: Backend, arguments: dict) -> dict:
    symbol = _require_str(arguments, "symbol")
    def_path = _optional_str(arguments, "def_path")
    return backend.execute(
        arguments,
        lambda client, project: client.find_references(
            symbol, def_path=def_path, project=project),
        lambda project: engine.find_references(project, symbol, def_path=def_path),
    )


def _t_impact(backend: Backend, arguments: dict) -> dict:
    symbol = _require_str(arguments, "symbol")
    def_path = _optional_str(arguments, "def_path")
    max_hops = _optional_int(arguments, "max_hops")
    return backend.execute(
        arguments,
        lambda client, project: client.impact(
            symbol, max_hops=max_hops, def_path=def_path, project=project),
        lambda project: engine.impact(
            project, symbol, max_hops=max_hops, def_path=def_path),
    )


def _t_symbols(backend: Backend, arguments: dict) -> dict:
    target = _optional_str(arguments, "file")
    return backend.execute(
        arguments,
        lambda client, project: client.get_symbols(file=target, project=project),
        lambda project: engine.get_symbols(project, file=target),
    )


def _t_find_duplicates(backend: Backend, arguments: dict) -> dict:
    target = _optional_str(arguments, "file")
    near_global = _optional_bool(arguments, "near_global")
    min_similarity = _optional_float(arguments, "min_similarity")
    return backend.execute(
        arguments,
        lambda client, project: client.find_duplicates(
            file=target, near_global=near_global,
            min_similarity=min_similarity, project=project),
        lambda project: engine.find_duplicates(
            project, scope_file=target, near_global=near_global,
            min_similarity=min_similarity),
    )


def _t_index(backend: Backend, arguments: dict) -> dict:
    force = _optional_bool(arguments, "force")
    return backend.execute(
        arguments,
        lambda client, project: client.reindex(force=force, project=project),
        lambda project: engine.index_project(project, force=force),
    )


def _t_status(backend: Backend, arguments: dict) -> dict:
    return backend.execute(
        arguments,
        lambda client, project: client.status(project=project, fresh=True),
        lambda project: engine.status(project, check_freshness=True),
    )


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="preflight",
        title="Preflight a change",
        description=(
            "Run this BEFORE writing or changing code in a file. One call answers the "
            "three questions that cause the most rework:\n"
            "1. ALREADY EXISTS - does something like the symbol you are about to add "
            "already exist, so you do not build a second one;\n"
            "2. CO-CHANGE - which files this repository's history says change together "
            "with this one (tests, allowlists, fixtures, config: the obligations nothing "
            "in the source mentions), so you do not leave half the change undone;\n"
            "3. BLAST RADIUS - which files hold resolved references to it, so you know "
            "what a change here breaks. When nothing is recorded for the symbol yet, "
            "preflight resolves it on the spot if that is cheap, and otherwise lists the "
            "files that name it as leads and says why it stopped short.\n"
            "Pass `symbol` whenever you are adding or renaming a named thing; the reuse "
            "check is the half that has to happen before the code is written. Every claim "
            "comes with its evidence (similarity, commits supporting the rule, number of "
            "resolved edges) so you can tell a strong signal from a weak one."),
        schema={
            "type": "object",
            "properties": {
                "file": {"type": "string",
                         "description": "The file you are about to change, relative to "
                                        "the project root or absolute."},
                "symbol": {"type": "string",
                           "description": "The function, class or constant you are about "
                                          "to add or change. Supplying it turns on the "
                                          "reuse check and narrows co-change to that "
                                          "symbol's own history."},
                "budget": {"type": "integer",
                           "description": "Approximate token ceiling for the answer "
                                          "(default 1200). Longest lists are trimmed "
                                          "first and the answer says when it trimmed."},
                "resolve": {"type": "string", "enum": ["auto", "yes", "no"],
                            "description": "What to do when the symbol has no resolved "
                                           "references recorded. 'auto' (default) "
                                           "measures the cost and resolves when it is "
                                           "small; 'yes' always resolves, which is exact "
                                           "but can take seconds; 'no' never does."},
                "project": _PROJECT_ARG,
            },
            "required": ["file"],
        },
        run=_t_preflight,
        render=render.preflight_lines,
    ),
    Tool(
        name="code_map",
        title="Code map",
        description=(
            "The repository's most important symbols, ranked by PageRank over the "
            "reference graph. Use it to orient in unfamiliar code instead of listing "
            "directories: it answers 'what is this codebase built around', which a file "
            "tree does not. Narrow it with focus_files or focus_symbols."),
        schema={
            "type": "object",
            "properties": {
                "budget": {"type": "integer",
                           "description": "Approximate token ceiling (default 2000)."},
                "focus_files": {"type": "array", "items": {"type": "string"},
                                "description": "Restrict the ranking to these files."},
                "focus_symbols": {"type": "array", "items": {"type": "string"},
                                  "description": "Rank around these symbols."},
                "project": _PROJECT_ARG,
            },
        },
        run=_t_code_map,
        render=render.map_lines,
    ),
    Tool(
        name="find_references",
        title="Find references",
        description=(
            "Every use of a symbol, split into import-resolved references (high "
            "confidence, from jedi for Python and ts-morph for TS/JS) and name-only "
            "matches. The split is the point: grep gives you the second kind and calls it "
            "the first. Running this also fills in the reference graph the preflight "
            "blast radius reads from."),
        schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The symbol name to look up."},
                "def_path": {"type": "string",
                             "description": "The file the symbol is defined in. Pass it "
                                            "when several definitions share the name."},
                "project": _PROJECT_ARG,
            },
            "required": ["symbol"],
        },
        run=_t_find_references,
        render=render.references_lines,
    ),
    Tool(
        name="impact",
        title="Change impact",
        description=(
            "What transitively breaks if this symbol changes, followed through the caller "
            "hierarchy rather than one hop. Separates production code from tests and "
            "flags entry points and high-importance symbols, so you can see whether a "
            "change is contained before you make it."),
        schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The symbol about to change."},
                "max_hops": {"type": "integer",
                             "description": "How far to follow callers (default is the "
                                            "engine's own limit)."},
                "def_path": {"type": "string",
                             "description": "The file the symbol is defined in, when "
                                            "names collide."},
                "project": _PROJECT_ARG,
            },
            "required": ["symbol"],
        },
        run=_t_impact,
        render=render.impact_lines,
    ),
    Tool(
        name="symbols",
        title="List symbols",
        description=(
            "The symbols defined in one file, or across the project when no file is "
            "given. Cheaper and more exact than reading the file when all you need is "
            "what it defines and where."),
        schema={
            "type": "object",
            "properties": {
                "file": {"type": "string",
                         "description": "Restrict to one file. Omit for the whole project."},
                "project": _PROJECT_ARG,
            },
        },
        run=_t_symbols,
        render=render.symbols_lines,
    ),
    Tool(
        name="find_duplicates",
        title="Find duplicates",
        description=(
            "Structural duplicate detection: code that does the same thing under a "
            "different name. preflight's reuse check matches on names, so it cannot see a "
            "wheel that was reinvented and renamed; this matches on shape and does. Use it "
            "before adding a helper you suspect exists somewhere."),
        schema={
            "type": "object",
            "properties": {
                "file": {"type": "string",
                         "description": "Restrict the scan to one file's units."},
                "near_global": {"type": "boolean",
                                "description": "Also do approximate matching across the "
                                               "whole repository (slower)."},
                "min_similarity": {"type": "number",
                                   "description": "Similarity floor for near-duplicates, "
                                                  "0-1."},
                "project": _PROJECT_ARG,
            },
        },
        run=_t_find_duplicates,
        render=render.duplicates_lines,
    ),
    Tool(
        name="index",
        title="Index the project",
        description=(
            "Build or refresh the index. Safe to call repeatedly: unchanged files are "
            "skipped by content hash. You rarely need this -- the first query indexes an "
            "unindexed project on its own, and a running daemon watches for edits."),
        schema={
            "type": "object",
            "properties": {
                "force": {"type": "boolean",
                          "description": "Re-extract every file even if its content hash "
                                         "is unchanged."},
                "project": _PROJECT_ARG,
            },
        },
        run=_t_index,
        render=render.index_lines,
    ),
    Tool(
        name="status",
        title="Index status",
        description=(
            "Whether this project is indexed, how much it holds, and whether it has "
            "fallen behind git HEAD."),
        schema={"type": "object", "properties": {"project": _PROJECT_ARG}},
        run=_t_status,
        render=render.status_lines,
    ),
)

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


# ── JSON-RPC ─────────────────────────────────────────────────────────────────

class MCPServer:
    """Speak MCP over a pair of byte streams.

    The transport is deliberately separable from the streams so the protocol can
    be tested without a subprocess: everything below reads a parsed message and
    returns a parsed reply.
    """

    def __init__(self, backend: Backend | None = None):
        self.backend = backend or Backend()
        self.initialized = False
        self.client_info: dict = {}

    # -- message handling --
    def handle(self, message: Any) -> dict | None:
        """Return the reply to one message, or None when none is owed."""
        if isinstance(message, list):
            return _error_response(
                None, -32600,
                "JSON-RPC batching is not supported; send one message per line")
        if not isinstance(message, dict):
            return _error_response(None, -32600, "a JSON-RPC message must be an object")
        method = message.get("method")
        if not isinstance(method, str):
            # A response to something we never asked for. Replying would loop.
            return None
        request_id = message.get("id")
        is_notification = "id" not in message
        try:
            result = self._dispatch(method, message.get("params") or {})
        except RpcError as exc:
            return None if is_notification else _error_response(
                request_id, exc.code, exc.message, exc.data)
        except Exception as exc:  # noqa: BLE001 - a crash must not take the stream down
            return None if is_notification else _error_response(
                request_id, -32603, _error_text(exc))
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result if result is not None else {}}

    def _dispatch(self, method: str, params: dict) -> dict | None:
        if method == "initialize":
            return self._initialize(params)
        if method.startswith("notifications/"):
            if method == "notifications/initialized":
                self.initialized = True
            return None
        if method == "ping":
            return {}
        if not self.initialized:
            raise RpcError(-32002, "the server has not been initialized; send initialize first")
        if method == "tools/list":
            return {"tools": [tool.describe() for tool in TOOLS]}
        if method == "tools/call":
            return self._call_tool(params)
        raise RpcError(-32601, f"unknown method {method!r}")

    def _initialize(self, params: dict) -> dict:
        requested = params.get("protocolVersion")
        version = (requested if requested in SUPPORTED_PROTOCOL_VERSIONS
                   else PROTOCOL_VERSION)
        self.initialized = True
        self.client_info = params.get("clientInfo") or {}
        return {
            "protocolVersion": version,
            # listChanged is False and stays False: this server's tool list is
            # fixed at import, so promising notifications would be a promise to
            # send something that never comes.
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": SERVER_TITLE,
                           "version": __version__},
            "instructions": INSTRUCTIONS,
        }

    def _call_tool(self, params: dict) -> dict:
        name = params.get("name")
        tool = TOOLS_BY_NAME.get(name) if isinstance(name, str) else None
        if tool is None:
            raise RpcError(
                -32602,
                f"unknown tool {name!r}; this server offers "
                + ", ".join(sorted(TOOLS_BY_NAME)))
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise RpcError(-32602, "'arguments' must be an object")
        root = self.backend.resolve_project(arguments)
        try:
            result = tool.run(self.backend, arguments)
        except RpcError:
            raise
        except Exception as exc:  # noqa: BLE001
            # A tool that could not answer is not a protocol failure. Returning it
            # as a result lets the model read the reason and try something else,
            # which a JSON-RPC error would not.
            notes = self.backend.take_notes()
            text = "\n".join([*notes, f"{tool.name} could not answer: {_error_text(exc)}"])
            return {"content": [{"type": "text", "text": text}], "isError": True}
        lines = [*self.backend.take_notes(), *tool.render(result, root)]
        return {"content": [{"type": "text", "text": "\n".join(lines)}], "isError": False}

    # -- transport --
    def serve(self, reader, writer) -> None:
        """Read newline-delimited JSON from ``reader`` until it closes."""
        for raw in reader:
            line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError as exc:
                reply = _error_response(None, -32700, f"invalid JSON: {exc}")
            else:
                reply = self.handle(message)
            if reply is not None:
                _write_message(writer, reply)


def _error_response(request_id, code: int, message: str, data: Any = None) -> dict:
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _write_message(writer, message: dict) -> None:
    payload = json.dumps(message, ensure_ascii=False, default=str)
    data = payload.encode("utf-8") + b"\n"
    if hasattr(writer, "buffer"):
        writer = writer.buffer
    writer.write(data)
    writer.flush()


def serve_stdio(project: str | None = None, *, use_daemon: bool | None = None) -> int:
    """Run the server on stdin/stdout until the client closes the input stream."""
    if use_daemon is None:
        use_daemon = os.environ.get("CODESEXTANT_MCP_NO_DAEMON", "").strip().lower() not in (
            "1", "true", "yes", "on")
    stdout = sys.stdout.buffer
    # One stray print anywhere under this call corrupts the protocol stream, and
    # the failure surfaces as an unrelated parse error in the client. Give the
    # rest of the process stderr to print to.
    sys.stdout = sys.stderr
    try:
        MCPServer(Backend(project, use_daemon=use_daemon)).serve(sys.stdin.buffer, stdout)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    return 0
