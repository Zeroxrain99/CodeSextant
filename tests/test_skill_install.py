from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from codesextant import skill_install
from codesextant.__main__ import main

REPO_ROOT = Path(__file__).parents[1]


def test_distribution_declares_the_agent_skill_as_package_data():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    data_files = pyproject["tool"]["setuptools"]["data-files"]

    assert data_files["codesextant-skill"] == ["skills/codesextant/SKILL.md"]


def test_install_skill_copies_the_bundled_skill_to_a_skill_root(tmp_path, monkeypatch):
    source = tmp_path / "bundle" / "SKILL.md"
    source.parent.mkdir()
    source.write_text("---\nname: codesextant\ndescription: Test skill.\n---\n", encoding="utf-8")
    target_root = tmp_path / "agent-skills"
    monkeypatch.setattr(skill_install, "bundled_skill_path", lambda: source)

    result = skill_install.install_skill([target_root])

    installed = target_root / "codesextant" / "SKILL.md"
    assert installed.read_bytes() == source.read_bytes()
    assert result == [{"path": str(installed), "action": "installed"}]


def test_install_skill_cli_accepts_an_explicit_skill_root(tmp_path, monkeypatch):
    source = tmp_path / "bundle" / "SKILL.md"
    source.parent.mkdir()
    source.write_text("---\nname: codesextant\ndescription: Test skill.\n---\n", encoding="utf-8")
    target_root = tmp_path / "skills"
    monkeypatch.setattr(skill_install, "bundled_skill_path", lambda: source)

    assert main(["install-skill", "--target", str(target_root)]) == 0
    assert (target_root / "codesextant" / "SKILL.md").is_file()
