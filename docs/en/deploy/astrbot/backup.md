# Backup, restore, and upgrade drills

Back up runtime data before an upgrade or migration. This fork does not offer hosted backups.

Runtime data defaults to `data/` under the process working directory. With `ASTRBOT_ROOT` set, it lives at `$ASTRBOT_ROOT/data`. Configuration, SQLite, plugins, Skills, knowledge bases, temp files, and backups can all live there; treat the directory as a unit.

## Do not

- `cp` the live SQLite main database while the process is writing (WAL mode).
- Copy only `data/data_v4.db` and drop knowledge bases, plugins, and config.
- Commit a backup that contains secrets, or post it in a public channel.
- Drill against a developer's real `data/`; use a copy or a temporary root.
- Treat [Persona JSON export](../../use/persona) as a full backup.

## Preferred: WebUI backup ZIP

Open **Settings → Maintenance** in the Dashboard, then **Backup & Restore** / **Backup Manager**. The exporter writes main-database tables as JSON and packs:

- main-database tables (export of `data/data_v4.db`, not a copy of an open file)
- knowledge-base metadata, vector documents, and media files
- `cmd_config.json`, `config/`, plugins and plugin data, Skills, WebChat, attachments
- `t2i_templates/` and `temp/`

Create the backup in the WebUI and copy the ZIP outside the checkout. Import through the same dialog. Extraction rejects path traversal outside the intended directories.

Import is a destructive **replace**, not a transactional rollback. The ZIP `major.minor` must match the running AstrBot version; a `4.26` backup cannot import into `4.27`. A patch mismatch such as `4.27.4` into `4.27.5` is allowed after confirmation.

Before replacing directories (`plugins/`, `plugin_data/`, `config/`, `skills/`, `webchat/`, `t2i_templates/`, `temp/`), the importer moves each existing tree to a `{directory}.bak` sibling and overwrites any previous `.bak`. It copies `cmd_config.json` to `cmd_config.json.bak`. Main-database tables and knowledge-base stores are cleared in place with no snapshot. If import fails after that clear, restore from an external copy; do not treat `{directory}.bak` as a main-database rollback. The UI asks for a restart after a successful import.

## Stop-the-world directory copy

When the WebUI is unavailable:

1. Stop AstrBot (stop the process for a source deploy; `docker compose stop` for Compose).
2. Copy the entire `data/` tree outside the checkout.
3. Confirm the copy includes `data_v4.db`, any `data_v4.db-wal` / `-shm`, `knowledge_base/`, `plugins/`, `plugin_data/`, `skills/`, `config/`, and `cmd_config.json`.

## Restore drill before an upgrade

Do this at least once and record the date and result:

1. Take a backup with one of the methods above.
2. Stop the service.
3. Restore onto an isolated directory or a new volume: import the ZIP, or place the `data/` copy at the runtime root.
4. Start.
5. Log in as the original admin and confirm conversations, personas, plugins, knowledge-base search, and Provider config. After restore, check that plugin, MCP, Skill, and Provider names still resolve.

Breaking main-database rebuilds on current `master` do not migrate rows from an old `data_v4.db`. Read `changelogs/` across the versions you are jumping before you restore a snapshot or cut over to an empty database as documented.

## Log red lines

Failure paths may record error codes and task ids. Do not log passwords, API keys, full Authorization headers, cookies, or secrets from inside a backup ZIP. User-facing failures stay generic; see the repository security invariants.
