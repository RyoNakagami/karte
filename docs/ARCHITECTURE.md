# karte — Architecture

`karte` is a per-repository personal TODO/ticket manager. It is intentionally
small and built as three layers with a one-directional dependency flow:

```
  CLI layer        karte/cli.py        user interaction, parsing, presentation
      │  depends on
      ▼
  API / domain     karte/storage.py    ticket model, CRUD, query
                   karte/schema.py     custom-field definition & validation
      │  reads / writes
      ▼
  Data layer       .karte/tickets.json single source of truth (JSON array)
                   .karte/schema.json  per-project custom field schema
```

Dependencies point downward only: the CLI imports the API layer; the API layer
touches the data layer; nothing points back up. This keeps each layer testable
and replaceable in isolation (e.g. a different front-end could reuse
`storage.py` unchanged).

---

## Layer 1 — CLI (`karte/cli.py`)

The only layer the user interacts with. Built on [Typer]; output is rendered
with [rich].

Responsibilities:

- Define commands and parse arguments/options.
- Translate raw strings into typed values (dates, comma-separated lists,
  `key=value` custom-field sets).
- Enforce simple input rules (valid `status`/`priority`).
- Present results — tables for `list`/`query`/`schema`, detail view for `show`.
- Map domain errors (`SchemaError`, `FieldError`) to friendly messages and exit
  codes.

It holds **no persistence logic** of its own: every read or write is delegated
to `storage.py`. Helper functions in this layer (`_parse_dt`, `_split_csv`,
`_parse_sets`, `_load_schema`, `_require_init`) are pure glue between user input
and the API layer.

Commands:

| Command | Purpose |
|---|---|
| `init` | Create `.karte/tickets.json` and add `.karte/` to `.git/info/exclude`. |
| `add` | Create a ticket (built-in fields + `--set` custom fields). |
| `list` | Tabular list with status/tag filters. |
| `show` | Full detail of one ticket, including custom fields. |
| `update` | Patch any subset of fields on a ticket. |
| `start` | Shortcut: set `status=doing` and stamp `start_at` if unset. |
| `done` | Shortcut: set `status=done`. |
| `delete` | Remove a ticket. |
| `schema` | Display the loaded custom-field schema. |
| `query` | Run DuckDB SQL over the tickets. |

## Layer 2 — API / domain (`karte/storage.py`, `karte/schema.py`)

The reusable core. No knowledge of Typer, argv, or terminal rendering — it
takes and returns plain Python values, so it could back a different UI or be
imported as a library.

### `storage.py` — ticket model, location, CRUD, query

- **Location:** `find_repo_root` walks up for a `.git` dir; `karte_dir`,
  `db_path` derive the `.karte/` paths. `add_to_git_exclude` keeps the data
  personal by writing to `.git/info/exclude` rather than the shared
  `.gitignore`.
- **Model:** `make_ticket` builds a ticket dict with the built-in fields
  (`id, title, description, status, priority, created_at, updated_at,
  start_at, end_at, related_files, tags`) and merges in validated custom
  fields. `STATUSES` and `PRIORITIES` define the allowed enums.
- **CRUD:** `load_tickets` / `save_tickets` read and write the whole JSON
  array; `next_id` and `find` are small helpers. Mutations happen in plain
  Python (read list → mutate → write), which keeps the on-disk JSON diff-able.
- **Query:** `run_sql` is the one place DuckDB is used. It normalizes tickets
  to a stable column set (filling custom-field defaults), loads them into an
  in-memory DuckDB table named `tickets`, runs the user's SQL, and returns
  `(columns, rows)`. DuckDB is a **read-only query engine** here; it never owns
  or persists data.

### `schema.py` — custom field definitions

Loads and validates the hand-edited `.karte/schema.json`:

- `load_fields` parses the file and validates structure (known `type`, no
  shadowing of `RESERVED_NAMES`, enums have `choices`, defaults type-check).
- `coerce` converts a raw string/default into the field's typed value
  (`str/int/float/bool/date/enum`).
- `apply_sets` validates a batch of `key=value` inputs against the schema,
  rejecting unknown keys and enforcing required fields on `add`.
- `defaults` supplies per-field defaults; `DUCKDB_TYPE` maps each schema type
  to a DuckDB column type for the query view.

Two error types — `SchemaError` (bad schema file) and `FieldError` (bad input
value) — are raised here and caught/formatted by the CLI.

## Layer 3 — Data (`.karte/`)

The single source of truth. No database engine owns it.

- **`.karte/tickets.json`** — a plain, indented JSON array of ticket objects.
  Human-readable, hand-editable, and git-diff-friendly. Hand edits are picked
  up on the next command (including `query`).
- **`.karte/schema.json`** — optional, user-authored custom-field schema.

`.karte/` is excluded from git per-clone via `.git/info/exclude`, so tickets
stay personal without touching the repository's shared `.gitignore`.

---

## Design decisions

**Why JSON as the store, not a DB engine.** The data is small, per-repo, and
personal. A plain JSON array stays readable, hand-editable, and produces clean
diffs — properties a binary DB file (e.g. `.duckdb`) would lose. CRUD over a
short array in memory is trivially fast at this scale.

**Why DuckDB only for queries.** Earlier the project used TinyDB for storage
*and* DuckDB for queries, which duplicated the "store + read" role. That was
collapsed: JSON is the sole store, and DuckDB is brought in only to satisfy the
"query with SQL" requirement via `read_json`. DuckDB reads the JSON directly and
holds nothing — removing the overlap and dropping a dependency.

**Why custom fields live in a separate hand-edited file.** Schema changes are
rare and deliberate; keeping them in `schema.json` (read-only from karte's
perspective) avoids adding schema-mutation commands and keeps the tool's write
surface limited to tickets.

**Layer boundary as the seam.** Because the CLI depends on the API layer and
not vice-versa, the domain logic (`storage.py` + `schema.py`) can be unit-tested
without a terminal and reused behind any other front-end.

[Typer]: https://typer.tiangolo.com/
[rich]: https://rich.readthedocs.io/
