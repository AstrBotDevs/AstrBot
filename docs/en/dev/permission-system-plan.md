# Unified Permission System

Status: implemented (authorization v1).

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
users to migrate; legacy `admins_id`, `tool_permissions`, and related compatibility
fields are discarded and are not read by runtime authorization.

WebChat/Open API `username` remains a compatibility field and is never treated
as an authenticated root/operator identity. High-risk Dashboard writes,
credentials, identity changes, system operations, and sensitive tools require
fresh Dashboard step-up proof and produce redacted audit records. Cross-platform
IM elevation is a later design and has no runtime endpoint in v1.

Core updates, pip installation, and Dashboard restarts likewise require exact,
one-time step-up credentials for `system.update` / `system:core-update`,
`system.pip_install` / `system:pip-install`, and `system.restart` /
`system:restart`, respectively. API keys cannot invoke these actions.
