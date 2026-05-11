# OpenAI Responses Provider State

## Current Goal

Add a new `openai_responses_completion` provider type that uses OpenAI Responses APIs while preserving the existing OpenAI-compatible WebUI flow.

## Task Status

- [x] Task 1: Register the new provider type and template
- [x] Task 2: Add the Responses adapter class and loader hook
- [ ] Task 3: Map AstrBot request payloads to Responses API input
- [ ] Task 4: Parse Responses output, reasoning, tool calls, and streaming events
- [ ] Task 5: Wire WebUI creation flow and verify the full provider path
- [ ] Task 6: Final verification

## Notes

- Worktree: `.worktrees/openai-responses-provider`
- Latest verified Task 1 Python test: `uv run pytest tests/test_dashboard.py::test_provider_templates_include_openai_responses_type -q`
- Latest verified Task 1 dashboard test: `node --test tests/providerUtils.test.mjs` from `dashboard/`
- Task 1 concern resolved: Python metadata coverage stays in `tests/test_dashboard.py`, and dashboard helper behavior is covered in `dashboard/tests/providerUtils.test.mjs`.
- Latest verified Task 2 test: `uv run pytest tests/test_openai_source.py -q -k openai_responses`
- Task 2 outcome: `ProviderOpenAIResponses` is registered and loadable, but still inherits the existing OpenAI chat behavior until Tasks 3 and 4 replace request/response handling.
- Latest verified Task 3 tests: `uv run pytest tests/test_openai_source.py -q -k responses_payload`
- Task 3 payload helper is implemented in `c313c553`; review still wants follow-up fixes for empty assistant strings and assistant content/tool_call ordering before Task 4.
- Known unrelated baseline failures remain in the dashboard and openai source suites; they are not part of Task 1.
