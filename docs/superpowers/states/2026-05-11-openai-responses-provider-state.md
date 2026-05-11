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
- Latest verified Task 1 test: `uv run pytest tests/test_dashboard.py::test_provider_templates_include_openai_responses_description -q`
- Current Task 1 concern resolved: the dashboard test now executes `getProviderDescription()` at runtime through Node dynamic import instead of checking source text only.
- Known unrelated baseline failures remain in the dashboard and openai source suites; they are not part of Task 1.
