# karte

Per-repository personal TODO / ticket manager. Tickets are stored as a plain,
human-readable JSON array in `.karte/tickets.json` at the repository root, and
`.karte/` is added to `.git/info/exclude` so it stays personal and is never
committed.

## Install

```bash
uv tool install karte          # from a published package
# or, from a local checkout:
uv tool install --editable .
```

### Upgrade

```bash
uv tool upgrade karte          # upgrade to the latest published version
# editable installs track the checkout; just `git pull` (re-run
# `uv tool install --editable .` only if dependencies changed)
```

### Uninstall

```bash
uv tool uninstall karte
```

## Usage

```bash
karte init                                   # create .karte/tickets.json
karte add "Fix auth bug" -d "token refresh" -p high -s doing \
     -f "src/auth.py,src/token.py" -t backend --end 2026-06-10
karte list                                   # active tickets (hides done)
karte list --all                             # include done
karte list -s doing                          # filter by status
karte show 1                                 # full detail
karte update 1 -s done --desc "fixed"        # update only given fields
karte start 1                                # mark in progress (status=doing, sets start_at)
karte done 1                                 # shortcut: mark done
karte delete 1 -y                            # delete
```

## Custom fields (per-project schema)

Each repo can add its own typed fields by hand-editing `.karte/schema.json`.
karte only reads this file. Built-in fields cannot be redefined.

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

Types: `str`, `int`, `float`, `bool`, `date`, `enum`. Per-field keys: `name`,
`type` (both required), `required` (default false), `default`, and `choices`
(required for `enum`).

```bash
karte schema                                  # show the loaded schema
karte add "Fix login" --set sprint=12 --set assignee=alice --set kind=bug
karte update 1 --set blocked=true             # validated & coerced
```

Values are type-checked on `add`/`update`: required fields must be supplied (or
have a default), enums must match `choices`, and bad types are rejected. Custom
fields also appear as columns in `karte query`:

```bash
karte query "SELECT id, title, assignee, estimate FROM tickets WHERE kind='bug'"
```

## Query (DuckDB SQL)

Search tickets with SQL. All tickets are exposed as a table `tickets` with
columns: `id, title, description, status, priority, created_at, updated_at,
start_at, end_at, related_files[], tags[]`. `related_files` and `tags` are
DuckDB lists.

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

## Ticket fields

`id`, `title`, `description`, `status` (todo|doing|done),
`priority` (low|mid|high), `created_at`, `updated_at`, `start_at`, `end_at`,
`related_files` (list), `tags` (list).

Dates accept `YYYY-MM-DD` or full ISO 8601. List options (`--files`, `--tags`)
take comma-separated values and replace the existing list on update.

## Architecture

`.karte/tickets.json` is the single source of truth: a plain JSON array of
ticket objects, indented and hand-editable. There is no separate database
engine or storage format.

- **Writes** (`add`, `update`, `done`, `delete`) read the array, mutate it in
  Python, and write it back. Edits stay diff-friendly.
- **Reads/queries** (`query`) use DuckDB to run SQL directly over that same
  array. DuckDB is a query engine only; it never owns the data.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the layer design, and
[`docs/how-to-use.md`](docs/how-to-use.md) /
[`docs/how-to-use-jp.md`](docs/how-to-use-jp.md) for the full usage guide.
