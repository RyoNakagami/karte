"""karte: per-repository personal TODO/ticket manager."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import storage as st
from . import schema as sch
from .lib.helper_func import get_version

app = typer.Typer(
    add_completion=False,
    help="Per-repository personal TODO manager. Tickets live in .karte/tickets.json.",
    no_args_is_help=True,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"karte {get_version()}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    pass


# ---- helpers ---------------------------------------------------------------

def _require_init() -> None:
    if not st.is_initialized():
        console.print("[red]Not initialized.[/] Run [bold]karte init[/] first.")
        raise typer.Exit(1)


def _parse_dt(value: Optional[str]) -> Optional[str]:
    """Accept ISO-ish input (YYYY-MM-DD or full ISO) -> normalized ISO string."""
    if value is None:
        return None
    if value == "":
        return None
    try:
        return datetime.fromisoformat(value).isoformat()
    except ValueError:
        raise typer.BadParameter(f"Invalid datetime: {value!r} (use YYYY-MM-DD or ISO 8601)")


def _split_csv(value: Optional[str]) -> Optional[list[str]]:
    if value is None:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def _parse_sets(pairs: Optional[list[str]]) -> dict[str, str]:
    """Turn ['k=v', 'a=b=c'] into {'k':'v', 'a':'b=c'}."""
    out: dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise typer.BadParameter(f"--set expects key=value, got {item!r}")
        k, v = item.split("=", 1)
        k = k.strip()
        if not k:
            raise typer.BadParameter(f"--set has empty key in {item!r}")
        out[k] = v
    return out


def _load_schema():
    try:
        return sch.load_fields(st.karte_dir())
    except sch.SchemaError as e:
        console.print(f"[red]schema.json error:[/] {e}")
        raise typer.Exit(1)


_PRIO_COLOR = {"high": "red", "mid": "yellow", "low": "dim"}
_STATUS_COLOR = {"todo": "white", "doing": "cyan", "done": "green"}


# ---- commands --------------------------------------------------------------

@app.command()
def init() -> None:
    """Create .karte/tickets.json and add .karte/ to .git/info/exclude."""
    root = st.find_repo_root()
    if st.is_initialized(root):
        console.print(f"[yellow]Already initialized[/] at {st.db_path(root)}")
        raise typer.Exit()
    st.karte_dir(root).mkdir(parents=True, exist_ok=True)
    st.init_store(root)  # write an empty JSON array
    excluded = st.add_to_git_exclude(root)
    console.print(f"[green]Initialized[/] {st.db_path(root)}")
    if excluded:
        console.print("Added [bold].karte/[/] to .git/info/exclude (personal, not committed).")


@app.command()
def add(
    title: str = typer.Argument(..., help="Ticket title"),
    description: str = typer.Option("", "--desc", "-d"),
    status: str = typer.Option("todo", "--status", "-s", help="todo|doing|done"),
    priority: str = typer.Option("mid", "--priority", "-p", help="low|mid|high"),
    start_at: Optional[str] = typer.Option(None, "--start", help="YYYY-MM-DD or ISO"),
    end_at: Optional[str] = typer.Option(None, "--end", help="YYYY-MM-DD or ISO"),
    files: Optional[str] = typer.Option(None, "--files", "-f", help="comma-separated paths"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="comma-separated tags"),
    set_: Optional[list[str]] = typer.Option(
        None, "--set", help="custom field, key=value (repeatable; see schema.json)"
    ),
) -> None:
    """Add a ticket."""
    _require_init()
    if status not in st.STATUSES:
        raise typer.BadParameter(f"status must be one of {st.STATUSES}")
    if priority not in st.PRIORITIES:
        raise typer.BadParameter(f"priority must be one of {st.PRIORITIES}")
    fields = _load_schema()
    try:
        custom = sch.apply_sets(fields, _parse_sets(set_), existing=None)
        # Fill in defaults for fields not provided.
        for name, dval in sch.defaults(fields).items():
            custom.setdefault(name, dval)
    except sch.FieldError as e:
        console.print(f"[red]Custom field error:[/] {e}")
        raise typer.Exit(1)
    tickets = st.load_tickets()
    ticket = st.make_ticket(
        ticket_id=st.next_id(tickets),
        title=title,
        description=description,
        status=status,
        priority=priority,
        start_at=_parse_dt(start_at),
        end_at=_parse_dt(end_at),
        related_files=_split_csv(files),
        tags=_split_csv(tags),
        custom=custom,
    )
    tickets.append(ticket)
    st.save_tickets(tickets)
    console.print(f"[green]Added[/] #{ticket['id']}: {ticket['title']}")


@app.command(name="list")
def list_(
    status: Optional[str] = typer.Option(None, "--status", "-s"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t"),
    all_: bool = typer.Option(False, "--all", "-a", help="include done"),
) -> None:
    """List tickets (hides done unless --all or --status done)."""
    _require_init()
    rows = st.load_tickets()
    if status:
        rows = [r for r in rows if r["status"] == status]
    elif not all_:
        rows = [r for r in rows if r["status"] != "done"]
    if tag:
        rows = [r for r in rows if tag in r.get("tags", [])]
    rows.sort(key=lambda r: (st.PRIORITIES[::-1].index(r["priority"]), r["id"]))

    if not rows:
        console.print("[dim]No tickets.[/]")
        return

    table = Table(show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("Pri")
    table.add_column("Status")
    table.add_column("Title")
    table.add_column("End")
    table.add_column("Files", overflow="fold")
    for r in rows:
        pc = _PRIO_COLOR.get(r["priority"], "white")
        sc = _STATUS_COLOR.get(r["status"], "white")
        table.add_row(
            str(r["id"]),
            f"[{pc}]{r['priority']}[/]",
            f"[{sc}]{r['status']}[/]",
            r["title"],
            (r.get("end_at") or "")[:10],
            ", ".join(r.get("related_files", [])),
        )
    console.print(table)


@app.command()
def show(ticket_id: int = typer.Argument(...)) -> None:
    """Show full detail of one ticket."""
    _require_init()
    r = st.find(st.load_tickets(), ticket_id)
    if not r:
        console.print(f"[red]No ticket #{ticket_id}[/]")
        raise typer.Exit(1)
    console.print(f"[bold]#{r['id']} {r['title']}[/]")
    for k in ["status", "priority", "created_at", "updated_at", "start_at", "end_at"]:
        console.print(f"  {k:12} {r.get(k)}")
    console.print(f"  {'tags':12} {', '.join(r.get('tags', []))}")
    console.print(f"  {'files':12} {', '.join(r.get('related_files', []))}")
    fields = _load_schema()
    if fields:
        defaults = sch.defaults(fields)
        for f in fields:
            name = f["name"]
            console.print(f"  {name:12} {r.get(name, defaults.get(name))}  [dim]({f['type']})[/]")
    if r.get("description"):
        console.print(f"\n{r['description']}")


@app.command()
def schema() -> None:
    """Show the custom field schema loaded from .karte/schema.json."""
    _require_init()
    fields = _load_schema()
    path = sch.schema_path(st.karte_dir())
    if not fields:
        console.print(f"[dim]No custom fields.[/] Create {path} to add some.")
        console.print(
            '\nExample:\n'
            '  {\n'
            '    "fields": [\n'
            '      {"name": "assignee", "type": "str"},\n'
            '      {"name": "estimate", "type": "float", "default": 0},\n'
            '      {"name": "kind", "type": "enum", "choices": ["bug","feat"], "default": "feat"}\n'
            '    ]\n'
            '  }'
        )
        return
    console.print(f"[bold]Custom fields[/] ({path}):")
    table = Table(show_lines=False)
    table.add_column("name")
    table.add_column("type")
    table.add_column("required")
    table.add_column("default")
    table.add_column("choices")
    for f in fields:
        table.add_row(
            f["name"],
            f["type"],
            "yes" if f.get("required") else "",
            "" if f.get("default") is None else str(f.get("default")),
            ", ".join(str(c) for c in f.get("choices", [])),
        )
    console.print(table)


@app.command()
def update(
    ticket_id: int = typer.Argument(...),
    title: Optional[str] = typer.Option(None, "--title"),
    description: Optional[str] = typer.Option(None, "--desc", "-d"),
    status: Optional[str] = typer.Option(None, "--status", "-s"),
    priority: Optional[str] = typer.Option(None, "--priority", "-p"),
    start_at: Optional[str] = typer.Option(None, "--start"),
    end_at: Optional[str] = typer.Option(None, "--end"),
    files: Optional[str] = typer.Option(None, "--files", "-f", help="replaces list"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="replaces list"),
    set_: Optional[list[str]] = typer.Option(
        None, "--set", help="custom field, key=value (repeatable)"
    ),
) -> None:
    """Update fields of a ticket. Only passed options change."""
    _require_init()
    tickets = st.load_tickets()
    existing = st.find(tickets, ticket_id)
    if not existing:
        console.print(f"[red]No ticket #{ticket_id}[/]")
        raise typer.Exit(1)
    if status is not None and status not in st.STATUSES:
        raise typer.BadParameter(f"status must be one of {st.STATUSES}")
    if priority is not None and priority not in st.PRIORITIES:
        raise typer.BadParameter(f"priority must be one of {st.PRIORITIES}")

    fields = _load_schema()
    try:
        custom = sch.apply_sets(fields, _parse_sets(set_), existing=existing)
    except sch.FieldError as e:
        console.print(f"[red]Custom field error:[/] {e}")
        raise typer.Exit(1)

    patch: dict = {}
    if title is not None:
        patch["title"] = title
    if description is not None:
        patch["description"] = description
    if status is not None:
        patch["status"] = status
    if priority is not None:
        patch["priority"] = priority
    if start_at is not None:
        patch["start_at"] = _parse_dt(start_at)
    if end_at is not None:
        patch["end_at"] = _parse_dt(end_at)
    if files is not None:
        patch["related_files"] = _split_csv(files) or []
    if tags is not None:
        patch["tags"] = _split_csv(tags) or []
    patch.update(custom)

    if not patch:
        console.print("[yellow]Nothing to update.[/]")
        raise typer.Exit()
    patch["updated_at"] = st.now_iso()
    existing.update(patch)
    st.save_tickets(tickets)
    console.print(f"[green]Updated[/] #{ticket_id}: {', '.join(patch)}")


@app.command()
def start(ticket_id: int = typer.Argument(...)) -> None:
    """Mark a ticket as in progress (status=doing, sets start_at if unset)."""
    _require_init()
    tickets = st.load_tickets()
    t = st.find(tickets, ticket_id)
    if not t:
        console.print(f"[red]No ticket #{ticket_id}[/]")
        raise typer.Exit(1)
    t["status"] = "doing"
    if not t.get("start_at"):
        t["start_at"] = st.now_iso()
    t["updated_at"] = st.now_iso()
    st.save_tickets(tickets)
    console.print(f"[green]Started[/] #{ticket_id} (start_at={t['start_at']})")


@app.command()
def done(ticket_id: int = typer.Argument(...)) -> None:
    """Shortcut to mark a ticket done."""
    _require_init()
    tickets = st.load_tickets()
    t = st.find(tickets, ticket_id)
    if not t:
        console.print(f"[red]No ticket #{ticket_id}[/]")
        raise typer.Exit(1)
    t["status"] = "done"
    t["updated_at"] = st.now_iso()
    st.save_tickets(tickets)
    console.print(f"[green]Done[/] #{ticket_id}")


@app.command()
def delete(
    ticket_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y", help="skip confirmation"),
) -> None:
    """Delete a ticket."""
    _require_init()
    tickets = st.load_tickets()
    r = st.find(tickets, ticket_id)
    if not r:
        console.print(f"[red]No ticket #{ticket_id}[/]")
        raise typer.Exit(1)
    if not yes:
        typer.confirm(f"Delete #{ticket_id} {r['title']!r}?", abort=True)
    tickets = [t for t in tickets if t.get("id") != ticket_id]
    st.save_tickets(tickets)
    console.print(f"[green]Deleted[/] #{ticket_id}")


@app.command()
def query(
    sql: Optional[str] = typer.Argument(
        None,
        help="SQL over the 'tickets' table. Omit to just SELECT * (with --where etc).",
    ),
    where: Optional[str] = typer.Option(
        None, "--where", "-w", help="Shorthand: SELECT * FROM tickets WHERE <this>"
    ),
    order: Optional[str] = typer.Option(None, "--order", "-o", help="ORDER BY clause"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l"),
    raw: bool = typer.Option(False, "--raw", help="plain tab-separated output"),
) -> None:
    """Query tickets with DuckDB SQL.

    Table: tickets(id, title, description, status, priority, created_at,
    updated_at, start_at, end_at, related_files[], tags[]).

    Examples:
      karte query "SELECT id, title FROM tickets WHERE status='todo'"
      karte query -w "priority='high'" -o "end_at"
      karte query "SELECT * FROM tickets WHERE list_contains(tags,'backend')"
    """
    _require_init()
    if sql is None:
        sql = "SELECT * FROM tickets"
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        if limit is not None:
            sql += f" LIMIT {limit}"
    elif where or order or limit is not None:
        raise typer.BadParameter("Pass either a full SQL string OR --where/--order/--limit, not both.")

    try:
        columns, rows = st.run_sql(sql)
    except Exception as e:  # duckdb raises various subclasses
        console.print(f"[red]Query error:[/] {e}")
        raise typer.Exit(1)

    if not rows:
        console.print("[dim]No rows.[/]")
        return

    if raw:
        # Plain stdout: no terminal-width wrapping or markup mangling.
        print("\t".join(columns))
        for r in rows:
            print("\t".join("" if v is None else str(v) for v in r))
        return

    table = Table(show_lines=False)
    for c in columns:
        # description tends to be long; let it ellipsize rather than wrap the row.
        table.add_column(c, overflow="ellipsis", no_wrap=(c == "description"), max_width=40)
    for r in rows:
        cells = []
        for v in r:
            if v is None:
                cells.append("")
            elif isinstance(v, list):
                cells.append(", ".join(str(x) for x in v))
            else:
                cells.append(str(v))
        table.add_row(*cells)
    console.print(table)


if __name__ == "__main__":
    app()
