# AstrBot 4.27.3 and Volcengine Ark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (recommended) to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Fix proactive cron delivery, update AstrBot to 4.27.3 while retaining OpenCode Go/Zen, and add a Volcengine Ark preset for the requested models.

**Architecture:** Reuse the existing cron event and OpenAI-compatible provider. The cron fix stays at the shared _woke_main_agent delivery boundary; Ark is a configuration template, not a new provider class or dependency.

**Tech Stack:** Python 3.12+, pytest, Ruff, existing OpenAI client, and the existing dashboard configuration metadata.

**Spec:** `docs/superpowers/specs/2026-08-18-astrbot-4273-volcengine-design.md`

## Global Constraints

- Preserve `opencode_go_chat_completion` and `opencode_zen_chat_completion`.
- Use `https://ark.cn-beijing.volces.com/api/v3` as the Ark endpoint.
- Support `deepseek-v4-flash-ga-260731` and `doubao-seed-2-0`.
- Do not add a Volcengine SDK or new abstraction.
- Preserve unrelated dirty-worktree files.

---

### Task 1: Verify and complete cron delivery fallback

**Files:**
- Modify: `astrbot/core/cron/manager.py`
- Test: `tests/unit/test_cron_manager.py`

- [ ] Run the existing regression test:
```bash
uv run pytest tests/unit/test_cron_manager.py::TestRunActiveAgentJob::test_woke_main_agent_fallback_delivery -q
```
Expected: PASS if the existing uncommitted implementation is complete.

- [ ] Review the diff:
```bash
git diff -- astrbot/core/cron/manager.py tests/unit/test_cron_manager.py
```
Expected: the fallback requires a delivery session, assistant role, non-empty text, and `not cron_event._has_send_oper`; the test covers sent and unsent cases.

- [ ] If any condition or assertion is missing, add the smallest failing case, run the focused test to observe RED, then implement only that condition and rerun it to GREEN.

### Task 2: Add Volcengine Ark provider preset

**Files:**
- Modify: `astrbot/core/config/default.py`
- Test: `tests/test_openai_source.py`

- [ ] Add this failing test before the preset:
```python
def test_volcengine_ark_preset_uses_openai_compatible_endpoint():
    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]["Volcengine Ark"]
    assert template["type"] == "openai_chat_completion"
    assert template["api_base"] == "https://ark.cn-beijing.volces.com/api/v3"
    assert template["model"] == "deepseek-v4-flash-ga-260731"
    assert template["provider"] == "volcengine-ark"
```

- [ ] Run it to verify RED:
```bash
uv run pytest tests/test_openai_source.py -k volcengine_ark_preset -q
```
Expected: FAIL because the template is absent.

- [ ] Add the minimum template:
```python
"Volcengine Ark": {
    "id": "volcengine-ark",
    "provider": "volcengine-ark",
    "type": "openai_chat_completion",
    "provider_type": "chat_completion",
    "enable": True,
    "key": [],
    "model": "deepseek-v4-flash-ga-260731",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "timeout": 120,
    "proxy": "",
    "custom_headers": {},
},
```

- [ ] Run the focused test again and expect PASS.

### Task 3: Update version and preserve OpenCode

**Files:**
- Modify: `pyproject.toml`
- Modify: `astrbot/__init__.py`
- Create: `changelogs/v4.27.3.md`
- Test: existing version/provider tests selected with `rg`

- [ ] Add a failing assertion:
```python
def test_version_and_opencode_providers_are_present():
    import astrbot
    from astrbot.core.provider.register import provider_cls_map

    assert astrbot.__version__ == "4.27.3"
    assert provider_cls_map["opencode_go_chat_completion"]
    assert provider_cls_map["opencode_zen_chat_completion"]
```

- [ ] Run it to verify RED:
```bash
uv run pytest tests/test_main.py -k version_and_opencode_providers_are_present -q
```
Expected: FAIL because the current version is 4.27.0.

- [ ] Update metadata without commit or push:
```bash
uv run python scripts/prepare_release.py 4.27.3
```
Expected: synchronized version files and `changelogs/v4.27.3.md`.

- [ ] Verify:
```bash
uv run pytest tests/test_main.py -k version_and_opencode_providers_are_present -q
uv run pytest tests/test_openai_source.py -k 'opencode or provider' -q
```
Expected: PASS and both OpenCode adapters remain registered.

### Task 4: Review and full verification

**Files:** all files shown by `git diff --name-only`

- [ ] Spec compliance:
```bash
git diff --check
git diff --name-only
git diff -- astrbot/core/cron/manager.py tests/unit/test_cron_manager.py astrbot/core/config/default.py pyproject.toml astrbot/__init__.py
```
Expected: no whitespace errors, no API keys, and both OpenCode source files remain.

- [ ] Code quality:
```bash
uv run ruff format --check .
uv run ruff check .
```
Expected: exit code 0.

- [ ] Full Python verification:
```bash
uv run pytest -q
```
Expected: exit code 0 with zero failures.

- [ ] If provider metadata affects generated frontend artifacts:
```bash
cd dashboard && pnpm generate:api && pnpm build
```
Expected: both commands exit 0; no API schema change is expected.
