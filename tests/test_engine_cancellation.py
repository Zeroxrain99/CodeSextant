"""Cooperative cancellation must leave index freshness fail-closed."""

from __future__ import annotations

import pytest


def test_cancelled_index_never_records_git_freshness(tmp_path, monkeypatch):
    from codesextant import engine, work_coordinator

    (tmp_path / "main.py").write_text("def ready():\n    return True\n", encoding="utf-8")
    git_checks = []
    monkeypatch.setattr(
        engine,
        "_git_head_sha",
        lambda _path: git_checks.append("called") or "deadbeef",
    )

    def cancel_now():
        raise work_coordinator.HeavyWorkDeadlineExceeded("cancelled")

    monkeypatch.setattr(work_coordinator, "cancellation_point", cancel_now)

    with pytest.raises(work_coordinator.HeavyWorkDeadlineExceeded):
        engine.index_project(str(tmp_path))
    assert git_checks == []
