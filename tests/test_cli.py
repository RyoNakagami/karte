import json
from pathlib import Path

from typer.testing import CliRunner

import karte
from karte.cli import app

runner = CliRunner()


def init_repo(repo: Path) -> None:
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output


def read_tickets(repo: Path) -> list[dict]:
    return json.loads((repo / ".karte" / "tickets.json").read_text())


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"karte {karte.__version__}" in result.output


def test_commands_require_init(repo: Path) -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert "Not initialized" in result.output


def test_init_creates_store_and_exclude(repo: Path) -> None:
    init_repo(repo)
    assert (repo / ".karte" / "tickets.json").exists()
    assert ".karte/" in (repo / ".git" / "info" / "exclude").read_text()
    # Second init is a no-op.
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "Already initialized" in result.output


def test_add_show_list(repo: Path) -> None:
    init_repo(repo)
    result = runner.invoke(
        app,
        ["add", "Fix auth bug", "-d", "token refresh", "-p", "high",
         "-f", "src/auth.py,src/token.py", "-t", "backend", "--end", "2026-06-10"],
    )
    assert result.exit_code == 0, result.output
    (ticket,) = read_tickets(repo)
    assert ticket["id"] == 1
    assert ticket["priority"] == "high"
    assert ticket["related_files"] == ["src/auth.py", "src/token.py"]
    assert ticket["end_at"] == "2026-06-10T00:00:00"

    result = runner.invoke(app, ["show", "1"])
    assert result.exit_code == 0
    assert "Fix auth bug" in result.output

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Fix auth bug" in result.output


def test_add_rejects_bad_status(repo: Path) -> None:
    init_repo(repo)
    result = runner.invoke(app, ["add", "x", "-s", "bogus"])
    assert result.exit_code != 0


def test_list_hides_done_unless_all(repo: Path) -> None:
    init_repo(repo)
    runner.invoke(app, ["add", "open ticket"])
    runner.invoke(app, ["add", "closed ticket", "-s", "done"])

    result = runner.invoke(app, ["list"])
    assert "closed ticket" not in result.output
    result = runner.invoke(app, ["list", "--all"])
    assert "closed ticket" in result.output


def test_update_start_done_delete(repo: Path) -> None:
    init_repo(repo)
    runner.invoke(app, ["add", "t"])

    result = runner.invoke(app, ["update", "1", "--title", "renamed"])
    assert result.exit_code == 0, result.output
    assert read_tickets(repo)[0]["title"] == "renamed"

    result = runner.invoke(app, ["start", "1"])
    assert result.exit_code == 0
    (ticket,) = read_tickets(repo)
    assert ticket["status"] == "doing"
    assert ticket["start_at"]

    result = runner.invoke(app, ["done", "1"])
    assert result.exit_code == 0
    assert read_tickets(repo)[0]["status"] == "done"

    result = runner.invoke(app, ["delete", "1", "-y"])
    assert result.exit_code == 0
    assert read_tickets(repo) == []


def test_missing_ticket_exits_1(repo: Path) -> None:
    init_repo(repo)
    for cmd in (["show", "9"], ["update", "9", "--title", "x"],
                ["start", "9"], ["done", "9"], ["delete", "9", "-y"]):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 1
        assert "No ticket #9" in result.output


def test_custom_fields_via_set(repo: Path) -> None:
    init_repo(repo)
    (repo / ".karte" / "schema.json").write_text(json.dumps({
        "fields": [
            {"name": "sprint", "type": "int", "required": True},
            {"name": "kind", "type": "enum", "choices": ["bug", "feat"], "default": "feat"},
        ]
    }))
    # Required field missing -> error.
    result = runner.invoke(app, ["add", "x"])
    assert result.exit_code == 1
    assert "sprint" in result.output

    result = runner.invoke(app, ["add", "x", "--set", "sprint=12"])
    assert result.exit_code == 0, result.output
    (ticket,) = read_tickets(repo)
    assert ticket["sprint"] == 12
    assert ticket["kind"] == "feat"  # default filled in

    result = runner.invoke(app, ["update", "1", "--set", "kind=bug"])
    assert result.exit_code == 0
    assert read_tickets(repo)[0]["kind"] == "bug"

    result = runner.invoke(app, ["update", "1", "--set", "kind=nope"])
    assert result.exit_code == 1

    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    assert "sprint" in result.output


def test_query_full_sql_and_shorthand(repo: Path) -> None:
    init_repo(repo)
    runner.invoke(app, ["add", "alpha", "-p", "high"])
    runner.invoke(app, ["add", "beta", "-p", "low"])

    result = runner.invoke(app, ["query", "SELECT id, title FROM tickets WHERE priority='high'"])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
    assert "beta" not in result.output

    result = runner.invoke(app, ["query", "-w", "priority='low'", "--raw"])
    assert result.exit_code == 0
    assert "beta" in result.output

    # Full SQL and shorthand are mutually exclusive.
    result = runner.invoke(app, ["query", "SELECT 1", "-w", "id=1"])
    assert result.exit_code != 0

    result = runner.invoke(app, ["query", "SELECT bogus FROM tickets"])
    assert result.exit_code == 1
    assert "Query error" in result.output