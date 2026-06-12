import json
from pathlib import Path

import pytest

from karte import storage as st


def test_find_repo_root_walks_up(repo: Path) -> None:
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    assert st.find_repo_root(nested) == repo


def test_find_repo_root_falls_back_to_start(tmp_path: Path) -> None:
    assert st.find_repo_root(tmp_path) == tmp_path


def test_init_and_load_save_roundtrip(repo: Path) -> None:
    st.karte_dir(repo).mkdir(parents=True)
    st.init_store(repo)
    assert st.is_initialized(repo)
    assert st.load_tickets(repo) == []

    t = st.make_ticket(ticket_id=st.next_id([]), title="hello", tags=["x"])
    st.save_tickets([t], repo)
    loaded = st.load_tickets(repo)
    assert loaded[0]["title"] == "hello"
    assert loaded[0]["tags"] == ["x"]
    # On-disk format is an indented, human-readable JSON array.
    text = st.db_path(repo).read_text()
    assert text.startswith("[\n")


def test_load_tickets_rejects_non_array(repo: Path) -> None:
    st.karte_dir(repo).mkdir(parents=True)
    st.db_path(repo).write_text('{"id": 1}')
    with pytest.raises(ValueError, match="expected a JSON array"):
        st.load_tickets(repo)


def test_next_id_and_find() -> None:
    tickets = [{"id": 1}, {"id": 5}]
    assert st.next_id(tickets) == 6
    assert st.next_id([]) == 1
    assert st.find(tickets, 5) == {"id": 5}
    assert st.find(tickets, 9) is None


def test_add_to_git_exclude(repo: Path) -> None:
    assert st.add_to_git_exclude(repo) is True
    exclude = repo / ".git" / "info" / "exclude"
    assert ".karte/" in exclude.read_text()
    # Idempotent.
    assert st.add_to_git_exclude(repo) is False
    assert exclude.read_text().count(".karte/") == 1


def test_run_sql_basic(repo: Path) -> None:
    st.karte_dir(repo).mkdir(parents=True)
    tickets = [
        st.make_ticket(ticket_id=1, title="a", status="todo", tags=["backend"]),
        st.make_ticket(ticket_id=2, title="b", status="done"),
    ]
    st.save_tickets(tickets, repo)
    columns, rows = st.run_sql("SELECT id, title FROM tickets WHERE status='todo'", repo)
    assert columns == ["id", "title"]
    assert rows == [(1, "a")]


def test_run_sql_list_functions(repo: Path) -> None:
    st.karte_dir(repo).mkdir(parents=True)
    st.save_tickets([st.make_ticket(ticket_id=1, title="a", tags=["backend"])], repo)
    _, rows = st.run_sql(
        "SELECT id FROM tickets WHERE list_contains(tags, 'backend')", repo
    )
    assert rows == [(1,)]


def test_run_sql_empty_store_has_schema(repo: Path) -> None:
    st.karte_dir(repo).mkdir(parents=True)
    st.init_store(repo)
    columns, rows = st.run_sql("SELECT * FROM tickets", repo)
    assert columns[:2] == ["id", "title"]
    assert rows == []


def test_run_sql_custom_field_columns(repo: Path) -> None:
    karte_dir = st.karte_dir(repo)
    karte_dir.mkdir(parents=True)
    (karte_dir / "schema.json").write_text(
        json.dumps({"fields": [{"name": "estimate", "type": "float", "default": 0}]})
    )
    tickets = [
        st.make_ticket(ticket_id=1, title="a", custom={"estimate": 2.5}),
        st.make_ticket(ticket_id=2, title="b"),  # missing -> default
    ]
    st.save_tickets(tickets, repo)
    _, rows = st.run_sql("SELECT id, estimate FROM tickets ORDER BY id", repo)
    assert rows[0][1] == pytest.approx(2.5)
    assert rows[1][1] == pytest.approx(0.0)