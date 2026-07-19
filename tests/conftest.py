"""Keep the test suite out of the operator's live CodeSextant home.

Both ``storage.default_db_dir()`` and ``supervisor._logger()`` resolve through
``CODESEXTANT_HOME``.  Without this fixture a plain ``pytest`` run writes into
``~/.codesextant`` — most visibly by appending fabricated
``heavy job stuck ... pid=7 ... active_for_sec=5400.0`` ERROR lines to the real
``supervisor.log`` (from the recycle tests), which then reads like a production
incident during a postmortem.  Spawned daemon subprocesses inherit the variable,
so they are redirected too.

Individual tests may still monkeypatch ``storage.default_db_dir``; this fixture
only moves the default so that *forgetting* to isolate can no longer touch live
operator state.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_codesextant_home(tmp_path_factory):
    home = tmp_path_factory.mktemp("codesextant_home")
    previous = os.environ.get("CODESEXTANT_HOME")
    os.environ["CODESEXTANT_HOME"] = str(home)
    try:
        yield home
    finally:
        if previous is None:
            os.environ.pop("CODESEXTANT_HOME", None)
        else:
            os.environ["CODESEXTANT_HOME"] = previous
