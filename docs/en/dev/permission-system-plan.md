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

## Unified authorization v2 proposal (not implemented)

### 19.1 Position, scope, and non-goals

v2 is an incremental design proposal built on the current authorization
invariants. It keeps AuthorizationService.authorize(subject, action, resource,
context), canonical resources, step-up, redacted audit, and fail-closed
behavior. It is not a claim that the v2 model is already implemented.

**Review conclusion:** adopt the finite-relationship, structured-context, and
explicit-capability model incrementally. It addresses v1's object-scope,
API-key boundary, and agent/tool call-chain gaps without turning this
single-instance SQLite deployment into an external policy service. The first
deliverables should be an action/resource/policy registry, object-level query
filtering, and migration preflight; relationship evaluation, editable policy,
and cross-platform elevation come later.

The proposed model combines finite relationship tuples, a small set of
contextual (ABAC) conditions, and explicit API-key capabilities:

```text
subject -- relation --> resource
subject -- capability -> action/resource constraint
request  -- attributes -> contextual policy
```

This deployment is a single runtime with local SQLite, Dashboard, IM adapters,
plugins, and agents. It should not introduce OpenFGA, Zanzibar, Cedar, or
another policy service unless a future multi-instance authorization domain
requires it. User-editable deny DSLs, recursive relationship evaluation,
scripted policies, and credential-read actions are out of scope. Provider
credentials may only be safely written, replaced, or deleted; read responses
must be redacted.

### 19.2 Fit audit against the current implementation

The current code already provides useful v2 boundaries:

- `authorize(subject, action, resource, context)` is the single authorization entry point;
- `Subject`, `Resource`, and `AuthContext` separate identity, source, config, and origin session;
- `ACTIONS` is the action registry, with namespaced plugin actions;
- platform membership facts have source and TTL, while Dashboard high-risk operations use one-time step-up;
- API keys still use historical scope mappings, where `NULL` and explicit `*` have different semantics;
- high-risk allows require audit writes and authorization failures default to deny.

v2 should preserve these entry points and invariants while replacing “allow by
highest role” with scoped relationship evaluation. Earlier ideas to rename
actions to `tool.local.exec`, add `provider.credentials.read`, bind
`operator` to an instance, or delete all v1 data directly do not match the
current contract.

### 19.3 Subjects and trusted context

The existing subject namespaces remain canonical:

```text
dashboard-account:<account-id>
dashboard-session:<session-id>
im:<platform-instance>:<bot-account-id>:<sender-id>
api-key:<key-id>
plugin:<plugin-id>
agent:<agent-id>
system:<component>
guest:<id>
```

Dashboard accounts are stable relationship subjects; a Dashboard session is
only the current authenticated session. Plugin and agent identities are
execution components and cannot acquire the caller's root privilege. WebChat
username, display names, platform labels, and caller-supplied subject IDs are
never authorization identities.

Trusted entry points populate `AuthContext.source`, `config_id`,
`origin_session_resource_id`, authentication strength, and platform facts.
Missing or inconsistent context is denied rather than guessed. A sub-agent
must carry the original subject and call chain; handoff cannot elevate
authority.

### 19.4 Canonical resources: fix boundaries before relationship evaluation

Resource IDs are generated and canonicalized by trusted services. The v2
session resource must contain config id, platform instance, bot account id, and
normalized UMO. Conversations, memories, files, and knowledge-base documents
must carry a verifiable parent resource or configuration scope; a bare
session id is not sufficient. Parent links provide a candidate scope only:
inheritance is granted only when the action/resource policy explicitly allows
it, with a maximum parent depth of one and no caller-defined paths.

All list, search, export, download, and bulk endpoints must filter objects in
the service/query layer before serialization. Authorizing a collection while
returning unauthorized rows is not object-level authorization.

The v1 canonical session encoding remains unchanged. If v2 introduces a separate
`session:v2` encoding, an upgrade preflight must inspect every
v1 binding and supply missing trusted platform metadata. Ambiguous rows must
block the upgrade or be explicitly rebuilt; the absence of known users is not
evidence that the database contains no v1 runtime state.

### 19.5 A finite relationship model, not programmable ReBAC

The internal relationship tuple is:

```text
subject -- relation --> resource
```

The fixed relation registry is root, operator, instance_operator, owner, admin,
member, guest, viewer, editor, executor, and caller. The migration mapping from
the current `Role` vocabulary is `session_owner -> owner` and
`session_admin -> admin`; owner/admin/member platform facts remain short-lived,
source-tagged facts rather than global relationship bindings. `viewer`, `editor`,
`executor`, and `caller` are constrained placeholders until their corresponding
action/resource policies and data models exist. Root and operator are Dashboard
control-plane relationships on global; instance_operator is scoped to an
instance. Platform owner/admin/member facts can never create global or instance
control-plane authority.

Every action/resource pair must register its allowed relations, parent resource
types and depth, required context attributes, risk class, and step-up rule.
Relationship rows need uniqueness for active tuples, revocation/expiry
handling, source provenance, and indexes covering subject, resource, relation,
and revocation state. Decisions should report matched relations and sources,
not only a single effective role.

### 19.6 Decision order and applicability constraints

The decision sequence is fixed:

1. Bind the subject to trusted context.
2. Canonicalize and validate action, resource, config, and origin session.
3. Reject unknown actions or invalid resources.
4. Resolve direct and at most one parent relationship.
5. Check source, TTL, same-config, and other contextual conditions.
6. Check an API-key capability only when `source == api_key` and the subject
   kind is `api-key`.
7. Check Dashboard step-up for the action risk class.
8. Write required redacted audit data and return the decision.

An allow decision requires:

```text
authenticated
AND known_action
AND valid_resource
AND (relationship_grant OR api_key_capability_grant)
AND applicable_context_constraints_pass
AND applicable_capability_constraints_pass
AND step_up_passed
```

For an API key, an explicit capability is the grant; it does not require a
fabricated role binding. It must match the action, resource, configuration, and
expiry exactly, and it cannot cover high-risk actions. Other subjects use the
relationship grant from the fixed relations and bounded parent resolution.

The important rule is applicability. API-key capabilities constrain only
API-key requests; plugin declarations constrain only plugin-owned dynamic
actions; Persona tool allowlists constrain only the relevant Persona call; an
IM origin-session rule constrains only IM traffic. A non-applicable condition is
true. Intersecting every possible condition would incorrectly deny ordinary
Dashboard or IM users and built-in tools.

Agent, MCP, Computer Tool, and direct tool execution must retain the original
caller, executor component, and call chain. Plugin declarations are necessary
constraints, not a privilege-escalation mechanism. Dashboard Extension
`required_scope` values continue to map to the existing API scope/action
registry; they are distinct from plugin-owned `plugin:<plugin-id>:<action>`
namespaced actions and must not be conflated.

### 19.7 Action registry compatibility

v2 keeps the current action registry as the canonical vocabulary, including
session.read/manage/assign, provider.read/use/manage,
provider.credentials.write, platform.read/manage, extension.read/manage and
extension.plugin_install, data.manage/export_all, system actions, identity
actions, the current tool.* actions, and dashboard.account.manage. Plugin
actions retain the `plugin:<plugin-id>:<action>` namespace.

No action rename is allowed without a complete one-time migration table.
In particular, the runtime uses tool.file_write, not tool.file.write. There is
no provider.credentials.read action: provider responses must redact secrets,
while credential replacement/deletion remains a separately authorized write.
High-risk actions such as provider.credentials.write,
extension.plugin_install, data.export_all, tool.local_exec,
tool.python_exec, tool.file_write, tool.browser_control, tool.mcp_write,
tool.computer_use, identity.manage, dashboard.account.manage, and system
update/restart/install never inherit silently from a parent action.

### 19.8 Typical policy and entry-point matrix

| Entry/resource                 | Allowed relation or condition                                              | Additional requirements                                        |
| ------------------------------ | -------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Current IM session             | owner/admin/member; instance operator or global operator/root              | resource equals `origin_session_resource_id`                   |
| Session conversation/memory    | session owner/admin/member; instance operator; global operator/root        | service-layer object filtering                                 |
| Provider config/credentials    | instance operator, operator, root                                          | Dashboard only; credential writes need step-up; reads redacted |
| Plugin catalog and actions     | extension relationship; declared plugin-owned action                       | action still calls core authorization                          |
| API-key request                | explicit action/resource capability for that key; no role binding required | all high-risk actions denied                                   |
| Agent/Computer/MCP/local tools | original caller's authorization on the target resource                     | Persona/plugin/risk constraints only when applicable           |
| Export/download/update/restart | explicit high-risk action                                                  | Dashboard step-up; IM, plugin, agent, and API key denied       |

List, search, batch export, and download endpoints filter objects in the
service/query layer. Batch step-up binds the complete, sorted resource set to
prevent split or replayed requests.

### 19.9 Persistence and API-key migration

New API keys should store explicit capabilities of the form:

```json
{
  "capabilities": [
    { "action": "session.read", "resource": "session:v2:..." },
    { "action": "provider.use", "resource": "instance:default" }
  ],
  "expires_at": "..."
}
```

The current `NULL` scope is not a wildcard: it expands to the frozen historical
`DEFAULT_API_KEY_SCOPES` set. An explicit `*` is the separate legacy wildcard.
Neither may expand v2 permissions, but migration must treat them differently.
Inventory role bindings, policy overrides, v1 resources, and API keys; expand
`NULL` only into finite actions and automatically create capabilities when the
old key's configuration/resource boundary is unambiguous; require re-issuance
for keys without an object boundary; and disable/recreate explicit wildcards
or conflicting records. Write the audit record in the same transaction and
then remove old-field reads. This is a migration operation, not a permanent
runtime compatibility shim.

### 19.10 WebChat, Dashboard, and step-up

v2.0 retains Dashboard-only step-up for high-risk operations. The credential is
bound to the account/session, action, exact resource, config, source, and
policy version; it is short-lived, single-use, and atomically consumed. The
narrow current-session IM member-management exception remains limited to its
origin session. Plugins, agents, MCP, and API keys cannot execute high-risk
actions, and executable credentials are never sent to public groups.

### 19.11 Implementation and release gates

1. **Freeze contracts:** inventory `ACTIONS`, high-risk actions, plugin actions,
   and API-scope mappings into an action/resource/risk matrix.
2. **Relationship core:** add a finite relationship tuple and policy registry,
   retain `authorize()`, and compare shadow decisions with v1 before changing allows.
3. **Resources and storage:** complete v2 session resources, parent resolution,
   relationship indexes, and migration preflight.
4. **Capability migration:** add API-key capabilities, reject wildcards and
   unscoped resources, and rebuild or transactionally migrate old keys.
5. **Cover every entry point:** Dashboard JSON, WebSocket, SSE, downloads,
   plugins, agents, MCP, Computer Tool, and local tools; filter at query/service level.
6. **Switch and clean:** switch after shadow parity, explicitly migrate required
   policy overrides, and remove old scope/field reads rather than keeping a shim.
7. **Gate release:** block upgrade until migration preflight, authorization
   matrix, cross-config/platform, object-filtering, step-up replay, concurrent
   revocation, and bounded-audit fail-closed tests pass.

Existing `auth_role_bindings` should be reused as the relationship store where
possible; do not maintain parallel role and relationship tables. Structured
policy overrides that remain necessary must be migrated into the new registry,
not deleted blindly.

### 19.12 Acceptance criteria

1. Every decision identifies subject, action, resource, source, matched relation,
   and context.
2. Authorization does not depend on one effective role; relationships resolve
   at most one parent and cannot cycle.
3. A session cannot be constructed from a bare session ID; config, platform, and
   bot-account boundaries remain isolated.
4. Unknown actions/resources, missing context, policy errors, and unavailable
   audit writes fail closed.
5. `provider.credentials.read`, `tool.file.write`, and other unregistered or
   out-of-scope names are rejected; provider credentials never appear in responses.
6. API keys have explicit action/resource capabilities only: no runtime wildcard
   or NULL expansion, and no implicit operator privilege.
7. Lists, searches, exports, downloads, and bulk writes enforce object-level authorization.
8. Plugins, agents, MCP, Computer Tool, and local tools cannot bypass or elevate
   core authorization.
9. High-risk Dashboard operations require exact one-time step-up; IM, plugins,
   agents, and API keys are denied.
10. Relationship changes, step-up, denials, and high-risk allows produce
    redacted, queryable audit events.
11. Dashboard, WebSocket, SSE, download, plugin, and tool paths have matrix tests.
12. Migration preflight identifies unsafe mappings and blocks an incomplete upgrade.

### 19.13 Reference principles (checked 2026-08-15)

The design follows the [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
(default deny, least privilege, server-side object checks, and authorization
regression tests), [NIST SP 800-162](https://csrc.nist.gov/pubs/sp/800/162/upd2/final)
(subject/object/operation/environment attributes), and the
[object-relation-user expression described by OpenFGA](https://openfga.dev/docs/concepts).
These references were checked on 2026-08-15; they inform the model but do not
add an external authorization dependency.
