# Anthropic

Anthropic is the provider of the Claude series of models. AstrBot natively supports the Anthropic API format.

## Setup

1. Go to [Anthropic Console](https://console.anthropic.com/) to register and get your API Key
2. In AstrBot Dashboard → Providers, click "Add Provider" and select `Anthropic`
3. Enter your API Key, click "Get Model List", and select the model you want

## Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| API Key | Anthropic API key | - |
| API Base | API endpoint. No need to change for official service | `https://api.anthropic.com/v1` |
| Timeout | Request timeout in seconds | 120 |
| Proxy | Proxy URL | - |
| **Max Tokens** | Maximum number of tokens the model can generate per response. Increase if responses are frequently truncated | 4096 |
| Thinking Config | Thinking configuration. Recommended to set `adaptive` for Opus 4.6+ / Sonnet 4.6+ | - |

### Max Tokens

`max_tokens` controls the maximum number of tokens the model can generate in a single response. When using Agent/tool calling scenarios, model outputs can be lengthy. Consider increasing this value (e.g., 8192 or 16384) based on your needs.

Configure it in AstrBot Dashboard → Providers → click the Anthropic provider → find "Max Output Tokens".
