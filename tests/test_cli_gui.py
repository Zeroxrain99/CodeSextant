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
        ("browser", "http://127.0.0.1:8790/"),
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

    monkeypatch.setattr(client, "CodesextantClient", FakeClient)
    monkeypatch.setattr(
        "webbrowser.open_new_tab",
        lambda _url: (_ for _ in ()).throw(AssertionError("browser must stay closed")),
    )

    assert main(["gui", str(tmp_path), "--no-browser"]) == 0
    assert "Dashboard: http://127.0.0.1:8790/" in capsys.readouterr().out
