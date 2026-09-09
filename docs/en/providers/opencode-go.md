# Connect OpenCode Go

[OpenCode Go](https://opencode.ai/docs/go/) is a model subscription service for coding agents.

## Get an API Key

Open the [OpenCode console](https://opencode.ai/auth), subscribe to Go, and copy your API key.

## Configure AstrBot

Open the AstrBot dashboard and go to **Providers → Add Provider**. Select **OpenCode Go Chat Completions**, **OpenCode Go Responses**, or **OpenCode Go Messages** according to the model's API format in the [OpenCode Go documentation](https://opencode.ai/docs/go/#endpoints).

| Field | Value |
| --- | --- |
| API Base URL | `https://opencode.ai/zen/go/v1` |
| API Key | The API key obtained from the OpenCode console |

Save the provider, then open its card and add the models you want to use.

## Set as Default

Go to **Settings → Provider Settings**, select the OpenCode Go model you just added as the default chat model, and save the configuration.

For supported models, usage requirements, and limits, see the [OpenCode Go documentation](https://opencode.ai/docs/go/).
