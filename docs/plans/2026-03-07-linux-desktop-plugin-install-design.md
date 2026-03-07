# Linux Desktop Plugin Install Design

## Context

AstrBot Desktop launches the backend with an embedded Python runtime and source entrypoint, not a frozen Python executable. The desktop process already exports `ASTRBOT_DESKTOP_CLIENT=1` and `ASTRBOT_ROOT`, but AstrBot currently treats desktop runtime as packaged only when both `ASTRBOT_DESKTOP_CLIENT=1` and `sys.frozen=True`.

That mismatch means Linux desktop plugin installs do not take the desktop-specific `data/site-packages` path. As a result, plugin dependency installation and dependency preference logic behave like a normal source checkout instead of the desktop-managed runtime.

## Decision

Treat `ASTRBOT_DESKTOP_CLIENT=1` as the canonical signal for AstrBot desktop backend runtime, regardless of whether Python is frozen.

Keep `is_frozen_runtime()` unchanged for callers that truly care about frozen behavior, but update `is_packaged_desktop_runtime()` to reflect the actual runtime contract used by AstrBot Desktop.

## Scope

- Update AstrBot runtime detection in `astrbot/core/utils/runtime_env.py`.
- Add regression tests for desktop runtime detection and affected installer/root-path behavior.
- Verify the plugin installer now enters the `--target <data>/site-packages` branch when `ASTRBOT_DESKTOP_CLIENT=1` even if `sys.frozen` is false.

## Non-Goals

- No changes to desktop launcher contract in `AstrBot-desktop` unless follow-up verification shows a separate mismatch.
- No refactor of unrelated frozen-runtime logic.
- No broad plugin installer redesign.

## Risks and Mitigations

- Risk: Some non-desktop environment might accidentally set `ASTRBOT_DESKTOP_CLIENT=1`.
  - Mitigation: That variable is already the explicit desktop child-process contract. Tests will lock in the intended semantics.
- Risk: Existing code may have implicitly used `is_packaged_desktop_runtime()` as a proxy for frozen-only behavior.
  - Mitigation: Current callers are the plugin installer and AstrBot root resolution, both of which should follow desktop runtime semantics rather than frozen semantics.

## Validation

- Add a failing unit test showing desktop runtime is detected when `ASTRBOT_DESKTOP_CLIENT=1` and `sys.frozen` is absent/false.
- Add a failing unit test showing `PipInstaller.install()` appends `--target <site-packages>` in that same environment.
- Run targeted tests for the new regression coverage.
