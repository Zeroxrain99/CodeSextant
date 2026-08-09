from __future__ import annotations

import os

from codesextant import client
from codesextant.__main__ import main


def test_gui_indexes_starts_daemon_and_opens_browser(tmp_path, monkeypatch, capsys):
    calls = []

    class FakeClient:
        def __init__(self, project):
            calls.append(("client", project))
            self.base = "http://127.0.0.1:8790"

        def ensure(self):
            calls.append(("ensure",))
            return {"action": "spawned"}

        def status(self):
            calls.append(("status",))
            return {"indexed": False}

        def reindex(self):
            calls.append(("reindex",))
            return {"indexed": 2, "skipped": 0, "removed": 0}

        def dashboard_url(self):
            calls.append(("dashboard_url",))
            return "http://127.0.0.1:8790/_session?code=one-time"

    monkeypatch.setattr(client, "CodesextantClient", FakeClient)
    monkeypatch.setattr(
        "webbrowser.open_new_tab",
        lambda url: calls.append(("browser", url)) or True,
    )

    assert main(["gui", str(tmp_path)]) == 0

    assert calls == [
        ("client", os.path.abspath(tmp_path)),
        ("ensure",),
        ("status",),
        ("reindex",),
        ("dashboard_url",),
        ("browser", "http://127.0.0.1:8790/_session?code=one-time"),
    ]
    assert "Dashboard: http://127.0.0.1:8790/" in capsys.readouterr().out


def test_gui_no_browser_keeps_the_printed_url(tmp_path, monkeypatch, capsys):
    class FakeClient:
        def __init__(self, project):
            self.base = "http://127.0.0.1:8790"

        def ensure(self):
            return {"action": "already-running"}

        def status(self):
            return {"indexed": True}

        def dashboard_url(self):
            return "http://127.0.0.1:8790/_session?code=one-time"

    monkeypatch.setattr(client, "CodesextantClient", FakeClient)
    monkeypatch.setattr(
        "webbrowser.open_new_tab",
        lambda _url: (_ for _ in ()).throw(AssertionError("browser must stay closed")),
    )

    assert main(["gui", str(tmp_path), "--no-browser"]) == 0
    assert "Dashboard: http://127.0.0.1:8790/_session?code=one-time" in capsys.readouterr().out


def test_cache_command_reports_managed_usage_without_paths(
        tmp_path, monkeypatch, capsys):
    from codesextant import cache_gc

    monkeypatch.setattr(cache_gc, "inventory", lambda: {
        "managed_bytes": 1024,
        "project_count": 1,
        "projects": [{
            "project_key": "a" * 40,
            "bytes": 1024,
            "repo_state": "present",
            "artifact_count": 2,
        }],
        "issues": [],
    })

    assert main(["cache"]) == 0
    output = capsys.readouterr().out
    assert "Managed cache: 1 project(s)" in output
    assert "aaaaaaaaaaaa" in output
    assert str(tmp_path) not in output
