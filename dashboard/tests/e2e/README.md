# Real onboarding E2E

This opt-in test starts the actual Python backend with a private temporary data
directory and drives the built dashboard in Chromium. It does not intercept API
requests, replace services, or connect a OneBot client. The adapter test starts a
real loopback-only OneBot listener; external messaging delivery is not covered.

From the repository root, install backend dependencies with `uv sync`. Then:

```sh
cd dashboard
pnpm install
pnpm exec playwright install chromium
pnpm build
pnpm test:e2e:onboarding
```

Node 20+ is required. `ASTRBOT_E2E_PYTHON` can select an existing Python virtual
environment; `ASTRBOT_E2E_BROWSER` can select an existing Chromium executable.
`ASTRBOT_E2E_SCREENSHOT` optionally saves a failure screenshot to an external path.
`ASTRBOT_E2E_SCREENSHOT_DIR` saves desktop/mobile trial screenshots after a real reply.
The test uses random local ports and deletes its temporary configuration and
database on completion, including failed assertions. It never uses the normal
AstrBot data directory. Do not terminate it with SIGKILL, which prevents cleanup.

For a real model reply, set `ASTRBOT_E2E_MODEL_FILE` to an **external, private** JSON
file containing `api_base`, `api_key`, and `model` for an OpenAI-compatible service.
Use a dedicated, low-cost test credential: the test sends one short prompt and
the provider may charge for it. The key is entered through the real model form
and temporarily saved by AstrBot. Do not commit this file or record network traces.
The caller owns and must delete the input credential file after the run.
Without this variable, model/chat coverage is explicitly reported as **skipped**.

Coverage: initial setup and real browser login, unauthenticated access rejection,
skip-all without configuration writes, adapter form validation, creation, prefill,
unchanged save, draft discard, persisted edit, welcome exit, process restart,
and (with credentials) real model creation/default selection, embedded streamed
reply, minimal trial controls versus regular ChatUI, desktop/mobile layout,
session preservation and model/history persistence across restart.
