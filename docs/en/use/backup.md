# Backup and Restore

Entry: `System Settings` → `Maintenance` → `Backup Manager`. The dialog has three tabs: `Export Backup`, `Import Backup`, and `Backup List`.

> [!WARNING]
> Restoring clears the existing data first and then writes the backup. A failure mid-way is not rolled back, and one kind of failure can leave you with an **empty main database** (see "What to check after restoring").
>
> Restoring also has to pass a version check: the **first two segments** of the backup's AstrBot version must match the running one (a `4.29.x` backup can only be restored on `4.29.x`). If you already upgraded and only have an older backup, the restore is refused — see "When the versions do not match".
>
> Stop AstrBot before restoring, and copy the data away as described in "Keep a way back".

## How to restore

1. On the `Import Backup` tab, pick the `.zip` and click `Upload & Check`. A backup has to be in the server-side backup list before it can be restored; for large files you can also copy it straight into `data/backups` and click `Refresh List` on the `Backup List` tab.
2. The check result shows the backup version, the current version, the backup time and the number of tables. If the first two version segments differ, it reports that the backup cannot be imported.
3. Click `Confirm Import` and keep the page open while it runs.
4. When it finishes it suggests restarting — click `Restart Now`.

For a backup that is already on the `Backup List` tab, click `Restore this backup` to jump straight to step 2.

## Keep a way back

1. On the `Export Backup` tab, click `Start Export`, then `Download Backup`, and save the ZIP locally.
2. If you can reach the data directory (self-hosted setups), stop AstrBot first and then copy these:

```
data/data_v4.db
data/data_v4.db-wal        # required: recent writes may only exist here
data/data_v4.db-shm        # copy it too; it can be rebuilt from -wal if lost
data/knowledge_base/
data/cmd_config.json
data/mcp_server.json
data/plugins/  data/plugin_data/  data/config/
data/t2i_templates/  data/webchat/  data/skills/
```

The database runs in WAL mode, so copying only the main file can lose the last stretch of data.

> Restoring first moves those directories to `<dir>.bak` before unpacking the new contents. Only one `.bak` is kept, and the next restore deletes it first — do not count on it as a repeatable rollback.

## What to check after restoring

A restore does not stop halfway, but the following failures are **written only to the server log** — neither the result nor the page shows them:

- A row does not fit (missing column, type mismatch): that row is dropped.
- The backup contains a table the running version does not know: the whole table is skipped.
- The backup format is below 1.1: plugins, plugin data, and the `data/config` directory are not imported.

There is also the opposite case, which fails harder: database constraint errors such as duplicate primary/unique keys or `NOT NULL` violations surface when the whole batch commits, roll back the entire main-database import and mark the task as failed — while the clear has already been committed, leaving the main database empty. Only the copy you took beforehand can save you here.

So after restoring, check: whether all plugins are on the `Plugins` page, whether model and platform settings reverted, whether knowledge bases open, and whether the conversation count looks right.

## When the versions do not match

| Case | What the UI does |
|---|---|
| Same first two segments, different third (`4.29.2` ↔ `4.29.4`) | Shows a version-difference warning; you can continue |
| Different first two segments (`4.28.x` ↔ `4.29.x`) | Reports that the backup cannot be imported; you cannot continue |

The rule is symmetric: an old backup restored into a newer version is refused, and a new backup restored into an older version is refused as well.

Two ways out:

1. **Export again from the original instance.** If it still starts, upgrade it to the current version first and take a fresh backup. This is the safest route.
2. **Restore on a matching version, then upgrade.** Install an AstrBot whose first two version segments match the backup, restore there, then upgrade. This only lowers the risk — an upgrade does not backfill every new column, so missing-column errors are still possible.

## What a backup contains

A backup is not a copy of the database file: data is exported row by row as JSON and then packed, so it can only restore what it contains.

- Included: all main-database tables (excluding the TOTP trusted-device table), knowledge bases (metadata, documents, vector index, media), `cmd_config.json` and `mcp_server.json`, attachments, and seven directories: `directories/plugins/`, `plugin_data/`, `config/`, `t2i_templates/`, `webchat/`, `temp/`, `skills/`. Import matches those seven names exactly — a missing name means that directory is not imported at all.
- Not included: workspace files under `data/workspaces`, and TOTP trusted-device records.

Backups are always full exports; there is no partial export. But "full" does not mean "complete": if exporting one table fails, that table is written as an empty array and the backup still reports success — restoring it then clears the same table on the target. After taking a backup you can open `manifest.json` inside the archive and compare the row counts under `statistics.main_db`.

## Common failures

- **"Invalid backup file"**: the ZIP has no `manifest.json`, or a chunked upload did not finish.
- **The knowledge base was unavailable at backup time**: the archive has no `databases/kb_metadata.json`, so restoring neither clears nor imports the knowledge bases.
- **All plugins are gone**: the backup format is below 1.1 and carries no plugin directories; export again from the original instance.
