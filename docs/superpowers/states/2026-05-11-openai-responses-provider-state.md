# OpenAI Responses Provider State

## Current Goal

Add a new `openai_responses_completion` provider type that uses OpenAI Responses APIs while preserving the existing OpenAI-compatible WebUI flow.

## Task Status

- [x] Task 1: Register the new provider type and template
- [ ] Task 2: Add the Responses adapter class and loader hook
- [ ] Task 3: Map AstrBot request payloads to Responses API input
- [ ] Task 4: Parse Responses output, reasoning, tool calls, and streaming events
- [ ] Task 5: Wire WebUI creation flow and verify the full provider path
- [ ] Task 6: Final verification

## Notes

- Worktree: `.worktrees/openai-responses-provider`
- Latest verified Task 1 Python test: `uv run pytest tests/test_dashboard.py::test_provider_templates_include_openai_responses_type -q`
- Latest verified Task 1 dashboard test: `node --test tests/providerUtils.test.mjs` from `dashboard/`
- Task 1 concern resolved: Python metadata coverage stays in `tests/test_dashboard.py`, and dashboard helper behavior is covered in `dashboard/tests/providerUtils.test.mjs`.
- Known unrelated baseline failures remain in the dashboard and openai source suites; they are not part of Task 1.
