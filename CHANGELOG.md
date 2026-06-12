# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-12

Initial release. A per-repository personal TODO / ticket manager that stores
tickets as a plain, human-readable JSON array in `.karte/tickets.json` at the
repository root.

### Added

- **`karte init`** — create `.karte/tickets.json` and register `.karte/` in
  `.git/info/exclude` so tickets stay personal and are never committed.
- **Ticket management commands**:
  - `add` — create a ticket with title, description, priority, status,
    related files, tags, and start/end dates.
  - `list` — show active tickets (hides `done`); `--all` to include done,
    `-s/--status` to filter by status.
  - `show` — display the full detail of a single ticket.
  - `update` — update only the fields supplied; leaves the rest untouched.
  - `start` — mark a ticket in progress (sets `status=doing` and `start_at`).
  - `done` — shortcut to mark a ticket done.
  - `delete` — remove a ticket (`-y` to skip confirmation).
- **Built-in ticket fields**: `id`, `title`, `description`,
  `status` (todo|doing|done), `priority` (low|mid|high), `created_at`,
  `updated_at`, `start_at`, `end_at`, `related_files` (list), `tags` (list).
  Dates accept `YYYY-MM-DD` or full ISO 8601.
- **Per-project custom schema** — define extra typed fields by hand-editing
  `.karte/schema.json`. Supported types: `str`, `int`, `float`, `bool`,
  `date`, `enum`. Values are type-checked and coerced on `add`/`update`
  (required fields enforced, enums validated against `choices`, defaults
  applied). `karte schema` shows the loaded schema; set custom values with
  `--set name=value`. Built-in fields cannot be redefined.
- **`karte query`** — search tickets with DuckDB SQL over a `tickets` table
  (built-in columns plus any custom fields; `related_files` and `tags` are
  DuckDB lists). Shorthand `-w/-o/-l` builds a `SELECT * FROM tickets …` for
  you, and `--raw` emits tab-separated, script-friendly output. DuckDB is a
  query engine only — `.karte/tickets.json` remains the single source of truth.
- Rich-formatted terminal output via [`rich`](https://github.com/Textualize/rich);
  CLI built with [`typer`](https://github.com/fastapi/typer).
- Documentation: `README.md`, `docs/ARCHITECTURE.md`, and usage guides
  (`docs/how-to-use.md`, `docs/how-to-use-jp.md`).
