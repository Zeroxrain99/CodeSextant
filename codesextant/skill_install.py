"""Install the bundled Agent Skill into a compatible agent's skill root."""
from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from importlib import metadata
from pathlib import Path

_BUNDLED_SUFFIX = "codesextant-skill/SKILL.md"


def bundled_skill_path() -> Path:
    """Return the installed skill file, with a source-tree fallback for contributors."""
    for entry in metadata.files("codesextant") or ():
        if entry.as_posix().endswith(_BUNDLED_SUFFIX):
            path = Path(entry.locate())
            if path.is_file():
                return path

    source_tree = Path(__file__).resolve().parents[1] / "skills" / "codesextant" / "SKILL.md"
    if source_tree.is_file():
        return source_tree
    raise FileNotFoundError(
        "The CodeSextant Agent Skill is missing from this installation. "
        "Reinstall CodeSextant from PyPI."
    )


def detected_skill_roots(home: Path | None = None) -> list[Path]:
    """Find installed agent homes, falling back to the open Agent Skills directory."""
    home = home or Path.home()
    candidates = [
        (home / ".codex", home / ".codex" / "skills"),
        (home / ".claude", home / ".claude" / "skills"),
        (home / ".agents", home / ".agents" / "skills"),
    ]
    detected = [skill_root for agent_home, skill_root in candidates if agent_home.is_dir()]
    return detected or [home / ".agents" / "skills"]


def _atomic_write(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=".SKILL.md.", delete=False
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def install_skill(
    target_roots: Iterable[str | Path] | None = None, *, force: bool = False
) -> list[dict[str, str]]:
    """Install CodeSextant's SKILL.md below one or more agent skill roots."""
    source = bundled_skill_path()
    payload = source.read_bytes()
    roots = [Path(root).expanduser() for root in target_roots] if target_roots else detected_skill_roots()
    results = []
    for root in roots:
        destination = root / "codesextant" / "SKILL.md"
        if destination.is_file():
            if destination.read_bytes() == payload:
                results.append({"path": str(destination), "action": "unchanged"})
                continue
            if not force:
                raise FileExistsError(
                    f"Refusing to replace a modified skill at {destination}. "
                    "Run again with --force to install the packaged version."
                )
        _atomic_write(destination, payload)
        results.append({"path": str(destination), "action": "installed"})
    return results
