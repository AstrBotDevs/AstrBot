# Session overrides

- Merge Custom Rules into **Config → Manage session mappings**, with a Material-style settings list, per-setting dialogs, three-state choices, unified saving, and restore-inheritance actions.
- Redirect `/session-management` to `/config?scope=sessions`. Previous Custom Rules, Session Management, and More Features → Custom Rules entries now map to Config → Manage session mappings.
- Share model overrides between commands and the editor. New or switched conversation histories within a UMO keep its overrides.
- Remove the built-in `/persona` command; manage session personas and restore inheritance through **Config → Manage session mappings → Overrides → Persona**.
- Remove the unused internal `SessionServiceManager` and `SessionPluginManager` classes. Runtime checks read effective session configuration; writes use the shared override API.
- Build message configuration snapshots with one full copy, reusing the independent override result instead of copying it again. Preserve isolation between concurrent messages and prevent snapshots from being saved as profiles.
- Use `AstrBotConfigSnapshot` for runtime configuration and declare explicit override paths on `MessageConfig`. Reject profile writes through the runtime type's save methods; remove dynamic configuration markers and object-identity inference during snapshot creation.
- Add `disabled_plugins` and `platform_settings.id_blacklist` to profiles. Lists replace inherited lists, including explicit empty lists.
- Migrate legacy rules and current conversation personas; move remarks into UMO aliases without replacing existing aliases. Remove the unused session Rerank toggle and field. Preserve groups, conversation selection, variables, and unrelated preferences.
- Preserve knowledge-base IDs during migration, including unavailable instances; recognize both names and IDs in the knowledge-base selector.
- Keep group membership as a batch-operation aid, without introducing group inheritance. UI navigation changes accompany this feature because inherited and overridden values must be edited in one configuration workspace.
- Unify ordered UMOP routes and session overrides as `config_binding` records. Migrate existing data without changing route order or pinning inherited profiles.
- Replace the Session overrides tab with a Manage session mappings dialog. Keep a search icon beside the profile selector that expands on click; show routes, assigned profiles, and overrides in one table. Add mappings by selecting a session or group, then a profile or field overrides. Reuse existing route, session-rule, and group APIs.

- Manage whole-bot routes only on the Bots page; omit them from the mappings dialog. Keep the dialog at a stable, viewport-bounded height.
- Use the same session binding API for exact-session assignments on the Bots page and in mapping management. Preserve field overrides when changing or removing the assigned profile. Display legacy exact routes as sessions and replace them on explicit profile edits without changing their effective configuration on read.

- Use standard dialog actions for next, save, and restore-inheritance controls, outside the scrollable settings content.
- Show the blacklist under Access Control, and hide the profile's Disabled plugins field when its list is empty.
- Replace Add mapping’s Next step with a two-pane editor: reuse the session selector for multiple sessions, or select groups, on the left and edit the destination on the right. Batch overrides apply only explicitly edited fields and preserve other session settings. Stack panes on narrow screens.
- Include override-only sessions on the Bots page, with their override count and routing inheritance. Selecting Follow config routing retains overrides. The trash button removes the entire mapping, including overrides, when the bot editor is saved.
- Replace the session editor’s Blocked sessions list with Session status (Follow profile / Enabled / Stopped). Keep blacklist lists in profile configuration; session status updates each target’s own blacklist while retaining unrelated entries.
- Explain profile selection and session override priority below the mappings dialog title, including the former Custom Rules entry point. Place Session status first in the override editor.
- Add session wake-prefix overrides using the existing `wake_prefix` key, including whole-list replacement and restoration to the profile. Resolve wake prefixes and additional AI prefix normalization per session.
- Group the continuous override list with small headings and dividers for Session, AI & conversation, Voice, Knowledge bases, and Plugins. Keep Session status and Wake prefixes first.
- Add a direct entry to the existing mappings dialog beside the Bots page's session profile instructions. Refresh mappings on return while preserving unsaved bot edits.

- Merge the bot deletion dialog’s former Custom Rules and Config Routing cleanup options into Session mappings, removing profile assignments, overrides, and routes together through the existing API.

- Remove `GET /api/v1/sessions`, `PATCH /api/v1/sessions/provider`, and `PATCH /api/v1/sessions/service`, plus their `/api/session/list-all-with-status`, `/api/session/batch-update-provider`, and `/api/session/batch-update-service` aliases. Remove their dedicated services and schemas. API clients should read active UMOs/mappings and submit per-UMO configuration overrides through `/api/v1/sessions/rules`; migration details are documented in the session mappings guide.
