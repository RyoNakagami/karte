"""Storage layer: locate the repo, manage .karte/tickets.json (a plain JSON array).

The on-disk format is a human-readable, hand-editable JSON array of ticket
objects:

    [
      {"id": 1, "title": "...", "status": "todo", ...},
      {"id": 2, ...}
    ]

CRUD is done in plain Python (read -> mutate list -> write). Querying is done
with DuckDB, which reads this same JSON file directly. There is no separate
database engine or storage format; the JSON file is the single source of truth.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

TODO_DIR = ".karte"
DB_FILE = "tickets.json"

STATUSES = ["todo", "doing", "done"]
PRIORITIES = ["low", "mid", "high"]

# Built-in columns, in display/schema order. Custom fields are appended.
BASE_COLUMNS = [
    "id", "title", "description", "status", "priority",
    "created_at", "updated_at", "start_at", "end_at",
    "related_files", "tags",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Walk up to find a .git directory; fall back to cwd."""
    start = (start or Path.cwd()).resolve()
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return start


def karte_dir(root: Optional[Path] = None) -> Path:
    return find_repo_root(root) / TODO_DIR


def db_path(root: Optional[Path] = None) -> Path:
    return karte_dir(root) / DB_FILE


def is_initialized(root: Optional[Path] = None) -> bool:
    return db_path(root).exists()


def add_to_git_exclude(root: Path) -> bool:
    """Add .karte/ to .git/info/exclude (personal, does not touch .gitignore).

    Returns True if a line was added.
    """
    git_dir = root / ".git"
    if not git_dir.is_dir():
        return False
    exclude = git_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text() if exclude.exists() else ""
    if any(line.strip() in {TODO_DIR, f"{TODO_DIR}/"} for line in existing.splitlines()):
        return False
    sep = "" if existing.endswith("\n") or existing == "" else "\n"
    with exclude.open("a") as f:
        f.write(f"{sep}{TODO_DIR}/\n")
    return True


# ---- JSON load / save ------------------------------------------------------

def load_tickets(root: Optional[Path] = None) -> list[dict]:
    """Read the ticket array. Returns [] if the file is empty/new."""
    path = db_path(root)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}")
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array of tickets.")
    return data


def save_tickets(tickets: list[dict], root: Optional[Path] = None) -> None:
    """Write the ticket array back as indented, human-readable JSON."""
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(tickets, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def init_store(root: Path) -> None:
    """Create an empty tickets.json (an empty array)."""
    save_tickets([], root)


def next_id(tickets: list[dict]) -> int:
    return 1 + max((t["id"] for t in tickets), default=0)


def find(tickets: list[dict], ticket_id: int) -> Optional[dict]:
    for t in tickets:
        if t.get("id") == ticket_id:
            return t
    return None


def make_ticket(
    *,
    ticket_id: int,
    title: str,
    description: str = "",
    status: str = "todo",
    priority: str = "mid",
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    related_files: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    custom: Optional[dict] = None,
) -> dict:
    ts = now_iso()
    ticket = {
        "id": ticket_id,
        "title": title,
        "description": description,
        "status": status,
        "priority": priority,
        "created_at": ts,
        "updated_at": ts,
        "start_at": start_at,
        "end_at": end_at,
        "related_files": related_files or [],
        "tags": tags or [],
    }
    if custom:
        ticket.update(custom)
    return ticket


# ---- DuckDB query ----------------------------------------------------------

def run_sql(sql: str, root: Optional[Path] = None) -> tuple[list[str], list[tuple]]:
    """Run a DuckDB SQL query against the tickets.

    Tickets are exposed as a table named `tickets`, one row per ticket.
    `related_files` and `tags` are VARCHAR[] (lists); use DuckDB list
    functions, e.g.:

        SELECT * FROM tickets WHERE status = 'todo'
        SELECT id, title FROM tickets WHERE list_contains(tags, 'backend')
        SELECT status, count(*) FROM tickets GROUP BY status

    Custom fields defined in .karte/schema.json appear as additional columns.
    Returns (column_names, rows).
    """
    import tempfile

    import duckdb

    from . import schema as sch

    fields = sch.load_fields(karte_dir(root))
    custom_defaults = sch.defaults(fields)
    tickets = load_tickets(root)

    # Normalize each ticket to a stable column set so DuckDB's schema inference
    # is consistent (missing custom values become their default / NULL).
    normalized = []
    for t in tickets:
        rec = {
            "id": t.get("id"),
            "title": t.get("title"),
            "description": t.get("description"),
            "status": t.get("status"),
            "priority": t.get("priority"),
            "created_at": t.get("created_at"),
            "updated_at": t.get("updated_at"),
            "start_at": t.get("start_at"),
            "end_at": t.get("end_at"),
            "related_files": t.get("related_files") or [],
            "tags": t.get("tags") or [],
        }
        for f in fields:
            name = f["name"]
            rec[name] = t.get(name, custom_defaults.get(name))
        normalized.append(rec)

    custom_cols_sql = "".join(
        f", {f['name']} {sch.DUCKDB_TYPE[f['type']]}" for f in fields
    )

    con = duckdb.connect(":memory:")
    try:
        if normalized:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False, encoding="utf-8"
            ) as f:
                json.dump(normalized, f)
                tmp = f.name
            con.execute("CREATE TABLE tickets AS SELECT * FROM read_json_auto(?)", [tmp])
        else:
            con.execute(
                f"""
                CREATE TABLE tickets (
                    id BIGINT, title VARCHAR, description VARCHAR,
                    status VARCHAR, priority VARCHAR,
                    created_at VARCHAR, updated_at VARCHAR,
                    start_at VARCHAR, end_at VARCHAR,
                    related_files VARCHAR[], tags VARCHAR[]{custom_cols_sql}
                )
                """
            )
        cur = con.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        result = cur.fetchall()
        return columns, result
    finally:
        con.close()
