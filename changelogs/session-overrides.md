# Session overrides

- Move **Custom Rules / Session Management / More Features → Custom Rules** to **Config → Manage session mappings**. Redirect `/session-management` to `/config?scope=sessions`.
- Assign a base profile and override individual session settings, including models, persona, wake prefixes, voice, knowledge bases, and plugins. **Follow profile** restores inheritance; explicit lists replace inherited lists, including empty lists.
- Apply profiles or selected fields to multiple sessions or current group members. Groups do not create inheritance, and changing profiles preserves explicit overrides.
- Model commands and the editor share overrides. Remove `/persona`; manage personas under **Config → Manage session mappings → Overrides → Persona**. Switching conversation histories within a UMO preserves settings.
- Use **Session status** to enable or stop a session. On the Bots page, **Follow config routing** keeps overrides; deleting a mapping removes its profile assignment and overrides after saving. Bot deletion combines the former **Custom Rules** and **Config Routing** cleanup options into **Session mappings**.
- Migrate legacy rules while preserving route order, knowledge-base references, aliases, groups, conversation selection, and variables. Disabled AI/TTS flags remain off; enabled flags follow the profile. Remove the unused session Rerank toggle without changing knowledge-base reranking settings.
- Remove `GET /api/v1/sessions`, `PATCH /api/v1/sessions/provider`, and `PATCH /api/v1/sessions/service`, including their legacy aliases. Read active UMOs and mappings, then write per-session overrides through `/api/v1/sessions/rules`.

See [session configuration mappings](../docs/en/use/custom-rules.md) for setup and the API migration table.
