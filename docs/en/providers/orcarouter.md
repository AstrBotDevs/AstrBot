# Connect OrcaRouter

[OrcaRouter](https://www.orcarouter.ai) is a unified AI gateway that provides access to OpenAI, Anthropic, Google, DeepSeek, Kimi and more through a single API key, in a fully OpenAI-compatible format. It also runs gateway-level, zero-trust security for AI agents on the same endpoint — screening every prompt/response and governing every tool call on a default-deny basis, with no application code changes.

## Get an API Key

1. Sign up at [OrcaRouter](https://www.orcarouter.ai)
2. Go to Console → API Keys to create a new key (keys start with `sk-orca-`)

## Configure in AstrBot

AstrBot ships with a built-in OrcaRouter provider. Open the AstrBot dashboard, click **Providers → Add Provider → OrcaRouter**.

The API Base URL is pre-filled for you. Fill in the following:

| Field | Value |
|-------|-------|
| API Base URL | `https://api.orcarouter.ai/v1` |
| API Key | Your OrcaRouter key |

After saving, click the provider card to add models.

## Models

OrcaRouter provides unified access to a wide range of models, including OpenAI GPT, Anthropic Claude, Google Gemini, DeepSeek, Kimi and more. Click **Get Model List** in the provider panel to browse the models available to your account, or see the full model list in the [OrcaRouter documentation](https://www.orcarouter.ai).
