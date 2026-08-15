# Unified Permission System

Status: implemented (authorization v1).

## Acceptance revision, 2026-08-14

The acceptance repair enforces these boundaries:

- Every new session binding is stored as a versioned canonical session resource. This branch has no pre-canonical binding data, so startup neither migrates nor merges legacy records.
- Inbound session contexts carry an immutable `origin_session_resource_id`. Default `member`, session bindings, platform facts, and session-scoped tool authority apply only to that origin; another session or a named `data` resource is denied by default.
- `root` and `operator` are Dashboard control-plane identities, never IM group authority. A current session owner may manage `session_admin` and `member` bindings only in that session; ownership cannot be delegated.
- Each Dashboard grant, single revoke, and account mutation consumes a one-time step-up credential bound to its exact resource. Batch revocation instead binds one password or TOTP verification to the complete, sorted binding snapshot, so it cannot be replayed for another set or reused one row at a time.
- Denials, high-risk decisions, step-up, and binding mutations are redacted audit events. A full bounded audit queue fails closed for high-risk allows, while step-up issuance and binding mutations commit their audit rows in the same transaction.

`openspec/openapi-v1.yaml` is the complete Dashboard authorization contract. `docs/public/openapi.json` deliberately contains only public API-key-facing operations and therefore excludes Dashboard-only Authorization control-plane paths.

Plugin package installation and remote package updates both require the high-risk
`extension.plugin_install` action and a Dashboard step-up credential. API keys
cannot perform either operation. The Dashboard asks for fresh proof before each
install or update request.

Conversation export is a Dashboard control-plane operation: it requires the
high-risk `data.export_all` action and an exact, one-time step-up credential for
the `conversation:export` resource. The Dashboard export dialog collects this
fresh proof before downloading; `data` API keys are always denied.

Backup download is a normal authenticated Dashboard API download under
`system.manage`. It is authorized by the runtime service like every other
backup route; the browser fetches the archive as a Blob so a Dashboard JWT is
never put in a query string. API keys cannot access the `system` scope.

Dashboard Extension Protocol control-plane requests also enter the same
runtime authorization service: catalog and page-session access require
`extension.read`, while every registered Action is checked against the Action's
declared API scope before the plugin handler runs. The extension API does not
introduce a separate role model or an implicit test/runtime bypass.

The Chinese implementation and migration guide is the normative reference:
[统一权限系统实现计划](../../zh/dev/permission-system-plan.md). The runtime now
uses normalized `Subject`, `Resource`, `AuthContext`, and fail-closed
`AuthorizationService` decisions for commands, Dashboard/API principals,
plugins, agents, and tools. Dashboard requests use stable account principals;
account CRUD is protected by root bindings and step-up. This fork has no existing
users to migrate. It performs no legacy permission migration or configuration
cleanup: Dashboard config writes explicitly reject `admins_id`, `tool_permissions`,
and `disable_builtin_commands`, and runtime authorization never reads them.

WebChat/Open API `username` remains a compatibility field and is never treated
as an authenticated root/operator identity. High-risk Dashboard writes,
credentials, identity changes, system operations, and sensitive tools require
fresh Dashboard step-up proof and produce redacted audit records. Cross-platform
IM elevation is a later design and has no runtime endpoint in v1.

Core updates, pip installation, and Dashboard restarts likewise require exact,
one-time step-up credentials for `system.update` / `system:core-update`,
`system.pip_install` / `system:pip-install`, and `system.restart` /
`system:restart`, respectively. API keys cannot invoke these actions.
