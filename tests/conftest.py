from pathlib import Path

import pytest


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake git repo as cwd, so karte resolves .karte/ under tmp_path."""
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path