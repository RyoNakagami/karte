# karte — How to use

`karte` is a per-repository personal TODO/ticket manager. Tickets are stored
as a plain, human-readable JSON array in `.karte/tickets.json` at the
repository root, and `.karte/` is added to `.git/info/exclude` so it stays
personal and is never committed.

> 日本語版は [how-to-use-jp.md](how-to-use-jp.md) を参照してください．

## Install

```bash
uv tool install karte          # from a published package
# or, from a local checkout:
uv tool install --editable .
```

Upgrade with `uv tool upgrade karte`, uninstall with `uv tool uninstall karte`.
Check the installed version with `karte --version` (or `-V`).

## Getting started

Run once inside the target git repository:

```bash
karte init
```

This creates `.karte/tickets.json` (an empty JSON array) and adds `.karte/` to
`.git/info/exclude`, so your tickets never show up in `git status` and are
never committed. All other commands require `init` to have been run first.

## Everyday workflow

```bash
# Create a ticket
karte add "Fix auth bug" -d "token refresh fails" -p high \
     -f "src/auth.py,src/token.py" -t backend --end 2026-06-10

# See what's open (done tickets are hidden by default)
karte list

# Start working on it (status=doing, stamps start_at)
karte start 1

# Inspect the details
karte show 1

# Finish it
karte done 1
```

## Commands

### `karte add TITLE`

Create a ticket. All options are optional:

| Option | Meaning |
|---|---|
| `-d, --desc TEXT` | Description. |
| `-s, --status` | `todo` \| `doing` \| `done` (default `todo`). |
| `-p, --priority` | `low` \| `mid` \| `high` (default `mid`). |
| `--start DATE` | Start date, `YYYY-MM-DD` or full ISO 8601. |
| `--end DATE` | Due date, same formats. |
| `-f, --files` | Comma-separated related file paths. |
| `-t, --tags` | Comma-separated tags. |
| `--set key=value` | Custom field (repeatable; see below). |

### `karte list`

Tabular list, sorted by priority then id. Done tickets are hidden unless you
ask for them:

```bash
karte list                # active tickets only
karte list --all          # include done
karte list -s doing       # filter by status (use `-s done` to see done)
karte list -t backend     # filter by tag
```

### `karte show ID`

Full detail of one ticket, including custom fields (with their types) and the
description.

### `karte update ID`

Patch a ticket — only the options you pass change:

```bash
karte update 1 -s done --desc "fixed in #42"
karte update 1 --end 2026-07-01 -p high
karte update 1 -t "backend,urgent"        # NOTE: replaces the whole tag list
```

It accepts the same options as `add` plus `--title`. `--files` and `--tags`
**replace** the existing list rather than appending to it.

### `karte start ID` / `karte done ID`

Shortcuts. `start` sets `status=doing` and stamps `start_at` if it was unset;
`done` sets `status=done`.

### `karte delete ID`

Deletes a ticket after a confirmation prompt; pass `-y` / `--yes` to skip the
prompt (for scripts).

## Custom fields (per-project schema)

Each repo can define its own typed fields by hand-editing
`.karte/schema.json`. karte only reads this file — there are no schema
commands that write to it. Built-in field names cannot be redefined.

```json
{
  "fields": [
    {"name": "assignee", "type": "str"},
    {"name": "estimate", "type": "float", "default": 0},
    {"name": "sprint",   "type": "int", "required": true},
    {"name": "blocked",  "type": "bool", "default": false},
    {"name": "kind",     "type": "enum", "choices": ["bug","feat","chore"], "default": "feat"}
  ]
}
```

Types: `str`, `int`, `float`, `bool`, `date`, `enum`. Per-field keys: `name`
and `type` (required), `required` (default false), `default`, and `choices`
(required for `enum`).

```bash
karte schema                                  # show the loaded schema
karte add "Fix login" --set sprint=12 --set assignee=alice --set kind=bug
karte update 1 --set blocked=true             # validated & coerced
```

Values are type-checked on `add`/`update`: required fields must be supplied
(or have a default), enums must match `choices`, and bad types are rejected.
Custom fields also appear as columns in `karte query`.

## Query (DuckDB SQL)

Search tickets with SQL. All tickets are exposed as a table `tickets` with
columns `id, title, description, status, priority, created_at, updated_at,
start_at, end_at, related_files[], tags[]` plus any custom fields.
`related_files` and `tags` are DuckDB lists.

```bash
# Full SQL
karte query "SELECT id, title FROM tickets WHERE status='todo'"
karte query "SELECT status, count(*) AS n FROM tickets GROUP BY status"

# Tag / file search (lists)
karte query "SELECT * FROM tickets WHERE list_contains(tags, 'backend')"
karte query "SELECT id,title FROM tickets \
             WHERE len(list_filter(related_files, x -> x LIKE '%auth%')) > 0"

# Date comparison (strings are inferred as TIMESTAMP)
karte query "SELECT id,title,end_at FROM tickets WHERE end_at < '2026-07-01'"

# Shorthand: -w/-o/-l build a SELECT * FROM tickets ... for you
karte query -w "priority='high'" -o "end_at" -l 10

karte query -w "id=1" --raw          # tab-separated, script-friendly
```

Pass either a full SQL string **or** the `-w/--where`, `-o/--order`,
`-l/--limit` shorthand — not both. `--raw` prints plain tab-separated rows
instead of a rich table, which is what you want when piping into other tools.

## Data files & hand-editing

`.karte/tickets.json` is the single source of truth — an indented JSON array
you can open and edit by hand. Edits are picked up by the next command,
including `query`. Ticket fields:

`id`, `title`, `description`, `status` (todo|doing|done),
`priority` (low|mid|high), `created_at`, `updated_at`, `start_at`, `end_at`,
`related_files` (list), `tags` (list).

Dates accept `YYYY-MM-DD` or full ISO 8601. See
[ARCHITECTURE.md](ARCHITECTURE.md) for how the pieces fit together.
