# Connect OrcaRouter

[OrcaRouter](https://www.orcarouter.ai) is an OpenAI-compatible AI gateway for both models and agents. One key reaches many vendors' models through a single endpoint, with adaptive routing, automatic failover, zero-markup inference, observability, guardrails, and agent-tool governance. It also runs gateway-level, zero-trust security for AI agents on the same endpoint — screening every prompt and response and governing every tool call on a default-deny basis, with no application code changes.

## Endpoints

| Purpose | URL |
| --- | --- |
| Inference and model catalog | `https://api.orcarouter.ai/v1` |
| Authorization and code exchange | `https://www.orcarouter.ai` |

These are two different public origins. AstrBot never derives one from the other, and self-hosted deployments can point them somewhere else with `ORCA_BASE_URL`, `ORCA_API_BASE_URL`, and `ORCA_AUTH_BASE_URL`.

## Choose how to sign in

Open the AstrBot dashboard and go to **Providers → Add Provider → OrcaRouter**. The card offers both methods side by side; either one is enough on its own.

### Option 1 — OrcaRouter - API

Paste an `sk-orca-…` key you already have into the provider's API Key field. Create one in the [OrcaRouter console](https://www.orcarouter.ai/console/tokens).

The key is stored with your other provider secrets. It is never written to logs, error messages, or telemetry, and the dashboard only ever shows a masked form.

### Option 2 — OrcaRouter - Auth

Click **Connect with OrcaRouter** to authorize with your OrcaRouter account using OAuth 2.0 + PKCE. No client secret and no pre-registered redirect URI are needed. The authorization code is bound to the AstrBot process by a randomly generated verifier that never leaves the server, so an intercepted code cannot be redeemed elsewhere.

Pick the delivery mode that matches where your browser is running:

| Mode | Use when |
| --- | --- |
| **This machine** (loopback redirect) | Your browser runs on the same machine as AstrBot. The code returns automatically. |
| **Another machine** (out-of-band code) | AstrBot runs on a NAS, in a container, or on a remote host. The consent screen shows a code to paste back into the dialog. |

Either way the result is an ordinary OrcaRouter API key that belongs to your account, is billed to you, and can be revoked at any time from [authorized apps](https://www.orcarouter.ai/console/authorized-apps).

A PKCE-issued key is **durable, not refreshable**. AstrBot reuses the stored key until OrcaRouter revokes it and never attempts a refresh grant. If the key is revoked, the provider is marked as needing reauthorization — issue a new key or connect again.

OrcaRouter limits PKCE key issuance to 10 keys per user per 24 hours, so AstrBot reuses the stored key instead of re-authorizing on every launch.

## Models

Model IDs keep their vendor namespace, for example `openai/gpt-5.5` or `anthropic/claude-opus-4.8`. AstrBot reads the model list from the live catalog at `https://api.orcarouter.ai/v1/models` using your key, so it shows the models your workspace can actually call.

The picker filters models by what each entry point needs:

- **Text chat** uses models that declare an OpenAI-compatible endpoint type, and excludes image-generation, video, rerank, and embedding models.
- **Multimodal understanding** additionally requires the model to declare the modality you actually upload (image, audio, or video). Models that do not declare a modality are never offered for it.
- **Embedding, image generation, video generation, and rerank** each require the matching endpoint type.

If the catalog cannot be reached, AstrBot falls back to a small verified set of models and shows the list as degraded rather than letting you type an arbitrary name. Live discovery is authoritative and is never mixed with the fallback.

## Set as Default

Go to **Settings → Provider Settings**, select the OrcaRouter model you just added as the default chat model, and save the configuration.

## Evidence

- Inference endpoint: `https://api.orcarouter.ai/v1`
- Model catalog: `https://api.orcarouter.ai/v1/models`
- Authorization: `https://www.orcarouter.ai/auth` (exchange at `/api/v1/auth/keys`)
- Key management: https://www.orcarouter.ai/console/tokens
- Revocation: https://www.orcarouter.ai/console/authorized-apps
- Service and terms: https://www.orcarouter.ai
