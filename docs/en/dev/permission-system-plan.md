# Unified Permission System

Status: implemented (authorization v1).

The Chinese implementation and migration guide is the normative reference:
[统一权限系统实现计划](../../zh/dev/permission-system-plan.md). The runtime now
uses normalized `Subject`, `Resource`, `AuthContext`, and fail-closed
`AuthorizationService` decisions for commands, Dashboard/API principals,
plugins, agents, and tools. Legacy `admins_id`, `PermissionTypeFilter`,
`tool_permissions`, and `computer_use_require_admin` are migration inputs only;
they are not long-term runtime authorization systems.

WebChat/Open API `username` remains a compatibility field and is never treated
as an authenticated root/operator identity. High-risk Dashboard writes,
credentials, identity changes, system operations, and sensitive tools require
fresh step-up/elevation and produce redacted audit records.
