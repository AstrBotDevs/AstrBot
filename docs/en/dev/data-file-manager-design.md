# Dashboard `data` File Manager Design

**Status:** reviewed design

This page describes the native Dashboard file manager for the active runtime
`<ASTRBOT_ROOT>/data/` directory. It deliberately does not provide a terminal,
code execution, Git, LSP, plugins, or access to arbitrary host paths.

## 1. Design conclusion

The page is available at `/data` and is linked from the Sidebar's **More**
group. The desktop layout contains a lazy directory tree, file tabs and a
Monaco editor. On narrow screens the tree becomes a drawer. The URL may contain
only a relative data path (`/data?path=skills/demo/SKILL.md`); it never contains
file contents, credentials, or absolute paths.

The implementation follows the existing Skills editor visual language: Vuetify
surface and border variables, compact list rows, and the existing Monaco loader.
`AstrBotDark` maps to `vs-dark`; all light themes map to `vs-light`.

### Scope by phase

#### Phase 0: contract and safety foundation

`DataFileService` owns all `pathlib.Path` resolution, classification, metadata,
and capability calculation. The API exposes directory and metadata endpoints.
The runtime root is resolved from `get_astrbot_data_path()` on every service
instance. Empty paths mean the data root; absolute paths, empty segments,
`.`/`..`, control characters, Windows reserved names, and escaping symlinks are
rejected. Symlinks are metadata-only and cannot be traversed.

Every operation uses Dashboard session authentication and the canonical
`filesystem` resources. API keys are rejected. The actions are:

| Action              | Roles                  |
| ------------------- | ---------------------- |
| `filesystem.read`   | operator, root         |
| `filesystem.write`  | operator, root         |
| `filesystem.manage` | root, one-time step-up |

Only `filesystem.manage` is high risk. Sensitive configuration and state files
require a root session. `dist/`, `site-packages/`, active databases and their
WAL/SHM files remain hard read-only. `plugins/` is read-only until a managed,
step-up operation; `plugin_data/` is an ordinary data directory.

#### Phase 1: browse and text editing

The tree shows hidden files and directories and returns backend-computed
category, language, and capabilities. UTF-8 text is limited to 1 MiB. Reads
return a SHA-256 etag; writes require `expected_etag` or `If-Match`, return 409
on conflict, and use a same-directory temporary file, flush/fsync and atomic
replacement. Temporary names use a reserved hidden prefix and are cleaned on
failure. Monaco models are not persisted in Pinia or local storage. Leaving a
dirty tab prompts the user; a conflict dialog offers only **Keep local** or
**Reload**.

Configuration files must use their existing validation/persistence/reload
services. Files whose managers have no reliable reload are labelled as changing
disk only, without promising immediate runtime effect. Demo mode is read-only.

#### Phase 2: file operations

Phase 2 adds explicit file/directory creation, rename and move, empty-directory
deletion by default (recursive deletion requires confirmation), multipart upload,
safe download, binary metadata/preview, and recursive filename search. Uploads
are streamed, capped at 32 MiB per file and 64 MiB per request, and are never
auto-extracted. Downloads use the shared RFC 6266 `content_disposition_header()`
helper and authenticated raw responses.

Search runs in `asyncio.to_thread`, examines only names and relative paths,
returns at most 100 entries, has a 5,000-inode budget and a three-second
deadline, and reports `truncated`. It never indexes file contents. Full-text
search, history, live watchers, and a development-mode switch remain Phase 3
directions and are not implemented.

## File categories and policy

Classification is path-prefix-first. `dist/`, `site-packages/`, `plugins/`,
configuration/state/backup/WebChat paths, databases and knowledge-base indexes
are not made editable merely because a filename has a text extension.
`plugin_data/` and `workspaces/` follow ordinary text rules. Images and audio
may be previewed through authenticated responses; SVG, HTML and unknown binary
files are downloaded rather than injected into the DOM.

The backend independently authorizes every read, write, move, rename, create,
upload and delete. Frontend `readable`/`writable` fields are display hints only.
Audit records contain redacted relative-path metadata and never file contents,
tokens, secrets or absolute paths.

## API contract

The Dashboard-only API is under `/api/v1/data-files` and has its own `Data Files`
tag (intentionally excluded from the public API-key tag allow-list):

- `GET /tree`, `GET /metadata`, `GET /content/{path}`
- `PUT /content/{path}`, `POST /entries`, `PATCH /entries`,
  `DELETE /entries/{path}`
- `POST /upload`, `GET /download/{path}`, `GET /search`

JSON endpoints use the standard `status`/`message`/`data` envelope. Downloads
and media previews remain raw responses. The OpenAPI source, generated Hey API
client and filtered public document are updated together.

## Verification

Backend tests cover traversal, Unicode and hidden entries, symlinks and TOCTOU,
binary/text limits, etags, atomic writes and cleanup, demo mode, classification,
permission and step-up boundaries, sensitive downloads, move washing and search
truncation. Dashboard tests cover routing, tree/editor state, Monaco themes,
unsaved/conflict dialogs, read-only/binary states and Phase 2 operations. E2E
tests use a temporary `ASTRBOT_ROOT` and never the developer's real data.

## 2. Background and current foundation

The Dashboard already provides Vue 3, Vuetify, Vue Router, Pinia, Monaco, the
Skills editor, a Dashboard session principal, and a unified authorization
service. The manager builds on those pieces instead of introducing a second
login flow, a remote IDE, or a new service process. Runtime paths come from the
active `ASTRBOT_ROOT`; source-checkout and home-directory paths are outside the
contract.

The runtime data tree contains configuration, SQLite databases, plugins and
plugin data, Skills, workspaces, knowledge bases, templates, WebChat projects,
installed packages, backups, temporary files, logs, and static Dashboard
assets. These categories explain why metadata visibility and content or
mutation capability are separate decisions.

## 3. Goals and non-goals

### 3.1 Goals

The first release provides a native `/data` page, hidden-item browsing,
UTF-8 text editing with Monaco highlighting, optimistic etag saves, Phase 2
file operations, authenticated binary previews/downloads, filename search,
keyboard accessibility, and desktop/narrow-screen layouts. All operations are
bounded by the runtime data root and the backend capability model.

### 3.2 Non-goals

The page is not code-server or a general-purpose Web IDE. It has no terminal,
shell, REPL, process execution, package installation, plugin execution, Git,
LSP, debugger, collaboration, arbitrary host-path access, SQLite editor,
content search, history, or live watcher. Phase 3 remains future direction
only.

## 4. Information architecture

### 4.1 Entry point

`/data` is an authenticated FullLayout route. Sidebar text uses
`core.navigation.dataFiles` and lives in the **More** group. The page has a
lazy tree, an editor/preview surface, and an operation toolbar.

### 4.2 URL state

The optional `path` query parameter contains only a normalized relative path.
Invalid paths fall back to the root and produce a regular error message. File
contents, credentials, step-up tokens, and absolute paths never enter the URL,
local storage, or persisted Pinia state. A dirty editor blocks route changes
until the user keeps local text or reloads it.

### 4.3 Layout

On desktop the tree occupies roughly 280px and the editor uses the remaining
space. On narrow screens the tree is presented as a compact drawer/panel and
the editor fills the width. Existing surface, border, theme, MDI, Vuetify, and
Skills-editor spacing variables are reused; no new color palette is introduced.

## 5. Visual and editor rules

### 5.1 Surfaces and states

Rows use existing surface variables, a subtle hover/active background, a lock
for read-only entries, a shield for protected entries, and a warning dot for
unsaved text. Errors use existing alerts/snackbars. The UI never renders file
HTML, Markdown, or SVG through `v-html`.

### 5.2 Components and accessibility

The page uses `v-card`, `v-list`-style tree rows, `v-dialog`, `v-menu`, and
icon buttons with ARIA labels and keyboard focus styles. Destructive actions
require confirmation. Loading, error, read-only, binary, and unsaved states are
visible and announced through the normal Dashboard components.

### 5.3 Monaco settings

The editor keeps the Skills baseline: automatic layout, 13px text, line
numbers, no minimap, two-space tabs, wrapped lines, and no scroll past the
last line. `AstrBotDark` selects `vs-dark`; all light themes select `vs-light`.
Language selection comes from the backend and never grants an extra capability.

## 6. File types and operation policy

### 6.1 Classification

The service checks path prefixes before extensions. Known languages include
JSON, YAML, TOML, Python, JavaScript/TypeScript, HTML, CSS, Markdown, shell,
SQL, XML, PowerShell, Dockerfile, and Makefile. UTF-8 and size checks still
apply; an extension cannot make a binary file editable.

### 6.2 Text files

Text reads and edits are capped at 1 MiB and use UTF-8. Managed core and plugin
configuration is parsed and validated before its existing persistence service
and runtime reload are invoked. If a manager cannot reliably reload (for
example, a cached Skill or template), the response explicitly says that only
disk changed.

### 6.3 Binary files

Images and audio use an authenticated, short-lived browser object URL and are
revoked when the selection changes. Video, archives, fonts, databases, SVG,
and unknown binary data show metadata and offer download; untrusted SVG is
never inserted as markup.

### 6.4 Managed and protected paths

`cmd_config.json`, `config/*.json`, `mcp_server.json`, authentication/state
files, backups, WebChat state, database/WAL/SHM files, knowledge-base indexes,
`dist/`, and `site-packages/` receive protected or hard-read-only categories.
Root sessions may inspect sensitive raw configuration; operators cannot use
this page to bypass Config API redaction. `plugins/` needs the manage action
and one-time step-up for mutation, while `plugin_data/` remains ordinary data.

## 7. Backend design

### 7.1 Modules

`astrbot/dashboard/services/data_file_service.py` owns path resolution,
classification, safe opens, etags, atomic writes, uploads, downloads, and
search. `astrbot/dashboard/api/data_files.py` owns session authentication,
authorization, request validation, envelope conversion, and raw downloads.

### 7.2 Root and path resolution

Every path is normalized as a relative slash-separated sequence and checked for
absolute forms, empty segments, dot segments, controls, reserved names, and
root containment after `resolve()`. Intermediate symlinks are rejected;
final symlinks expose metadata only. POSIX directory and file operations use
`O_NOFOLLOW` and compare `fstat()` results with the pre-open `lstat()` result.
Directory enumeration uses the same opened-directory check to prevent a
resolve/open swap. Non-POSIX code uses the equivalent no-follow and identity
checks available on that platform.

### 7.3 API shape

All ordinary JSON responses use the Dashboard envelope. Collection resources
use `Resource.named("filesystem", "collection")`; path resources use the
opaque `object_resource("filesystem", relative_path)` helper, so Unicode,
spaces, dots, and long paths never become invalid authorization IDs.

### 7.4 Creation, move, and deletion

Creation does not invent parent directories. Source and destination paths are
classified again for every move/rename, so moving a protected file cannot
launder its policy. Hard-read-only directories and active runtime databases
remain rejected even after step-up. Recursive deletion is explicit and still
uses the same category and runtime-resource checks.

### 7.5 Upload and download

Upload filenames are basename-only and are streamed into a same-directory
reserved temporary file before an atomic replacement. ZIP/TAR archives are
never extracted. Download descriptors use `content_disposition_header()` and
an already validated file descriptor, not a public static URL.

### 7.6 Concurrent saves and atomicity

The text path computes a content SHA-256 etag, compares `expected_etag`/`If-Match`
before writing, and returns HTTP 409 on mismatch. Writes flush and fsync the
temporary file, replace atomically, fsync the parent directory where supported,
and remove temporary files on every error. Managed configuration failures roll
back persisted state before reporting the reload failure.

## 8. Authorization and security model

### 8.1 Actions

`filesystem.read` and `filesystem.write` grant to operator and root roles.
`filesystem.manage` grants only root and is the sole high-risk action. Every
new route directly depends on `require_dashboard_session_principal`; API keys,
legacy file/data scopes, and anonymous requests are refused.

### 8.2 Operation matrix

Ordinary reads use `filesystem.read`; ordinary mutations use
`filesystem.write`. Protected plugin/config operations use
`filesystem.manage` plus a one-time step-up. Sensitive raw reads are root-only,
and sensitive downloads/previews also consume step-up. Database, WAL/SHM,
temporary, `dist/`, and `site-packages/` writes/deletes are hard denied.

### 8.3 Sensitive content

Errors, logs, audit metadata, URLs, and browser persistence contain no content,
tokens, secrets, or absolute paths. Audit records retain only the action,
opaque resource identity, safe category, and size. Demo mode turns every
mutation into a read-only response.

## 9. Frontend component design

### 9.1 Component tree

`DataFilesPage.vue` keeps the initial implementation small: tree, toolbar,
editor/preview, operation dialogs, snackbar, and the existing step-up dialog.
The API wrapper lives in `dashboard/src/api/v1/dataFiles.ts`.

### 9.2 Directory tree

Directories load lazily and retain relative paths only. Hidden entries and
protected/read-only icons are shown. Search results are bounded and open the
same authenticated entry view rather than constructing a static file URL.

### 9.3 Tabs and unsaved state

The selected file path is reflected in the query string; content remains in the
component/Monaco model only. A dirty marker, browser unload guard, route guard,
and the conflict dialog prevent accidental loss. Conflict handling deliberately
offers only **Keep local** and **Reload**.

### 9.4 Editor and previews

Monaco is read-only whenever the backend says so. Binary previews use object
URLs and are released on unmount or selection change. Downloads and sensitive
previews retry once after the user completes the exact manage step-up.

### 9.5 Shortcuts and accessibility

Ctrl/Cmd+S saves the active text file. Icon-only controls have ARIA labels,
buttons are keyboard reachable, and narrow layouts preserve a clear route back
to the directory tree.

## 10. Search and performance

### 10.1 Phase 2 search scope

Search is case-insensitive over names and relative paths only. It skips reserved
temporary files, follows no symlink, filters entries through the same read
capabilities, and returns at most 100 results with a `truncated` flag.

### 10.2 Budgets

The worker-thread walk has a 5,000-entry inode budget and a three-second
deadline. Tree responses cap the initial directory listing at 200 entries.
Text, upload, and request limits are hard service/API limits rather than UI
validation hints.

## 11. OpenAPI and generated code

The source contract is `openspec/openapi-v1.yaml` with the private `Data Files`
tag. The generated Dashboard Hey client and the filtered `docs/public/openapi.json`
are regenerated mechanically; the private tag is intentionally absent from the
public API-key documentation allow-list.

## 12. Test plan

### 12.1 Backend unit tests

Coverage includes traversal and reserved names, Unicode/hidden entries,
symlinks and directory/file TOCTOU, UTF-8/binary and size limits, etag
conflicts, atomic-write cleanup, demo mode, role and step-up policy, sensitive
download boundaries, plugin read-only behavior, move-washing prevention,
search truncation, and audit redaction.

### 12.2 Dashboard unit tests

Vitest covers the `/data` route, tree/editor state, Monaco theme selection,
unsaved and 409 dialogs, read-only/sensitive/binary rendering, Phase 2
create/move/delete/upload/search actions, and step-up retries.

### 12.3 E2E tests

Playwright starts the Dashboard against a temporary runtime root and verifies
that a text file can be browsed and edited. It uses isolated ports and never
reads or writes a developer's real `data/` directory.

## 13. Phased delivery

### Phase 0: contract and safety

Ship the root-isolated service, metadata/tree API, action registry, resource
helpers, category/capability model, audit redaction, and OpenAPI/client base.

### Phase 1: browse and edit

Ship text reads/writes, Monaco language/theme mapping, etags, atomic replacement,
configuration-service delegation, and unsaved/conflict handling.

### Phase 2: file operations

Ship create, rename/move, delete, streaming upload/download, authenticated
binary preview, and bounded recursive filename search with protected-path
step-up. Do not implement Phase 3 in this release.

### Phase 3: later direction

Full-text search, history, live watchers, and development-mode switching remain
explicit follow-up work and have no implementation or API surface here.

## 14. Acceptance criteria

The implementation must keep all access below the active data root, reject
path traversal and symlink escapes, preserve etag conflict semantics, show
hidden entries, enforce backend capabilities independently of the frontend,
keep demo mode read-only, and avoid leaking content or secrets into logs,
audits, URLs, or browser persistence. Phase 0/1/2 behavior, generated clients,
localized navigation, docs, unit tests, Vitest, and isolated E2E must all pass.

## 15. Confirmed product decisions

The page is native Dashboard UI rather than code-server; only Dashboard
sessions are accepted; `filesystem.manage` is root-only and high-risk; private
Data Files OpenAPI routes are excluded from public API-key tags; root-sensitive
raw configuration is deliberate but protected; and Phase 3 is deferred.

## 16. References

Implementation references are the Skills page/editor, Monaco loader, Dashboard
session principal and authorization registry, `content_disposition_header()`,
the OpenAPI generation workflow in `AGENTS.md`, and the corresponding Chinese
design page at `docs/zh/dev/data-file-manager-design.md`.
