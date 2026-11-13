# Large Language Model Providers

In the WebUI, open **Providers → Chat Completion**, click **Add**, and select a provider type. For an OpenAI-compatible service, select `OpenAI Compatible` and enter the API Base URL and API key supplied by that service.

Enter the provider name and `API Key`, check the `API Base URL`, then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.

See [Connecting Model Services](./start.md) for detailed steps.

> Provider connection settings are stored in `provider_sources` in `data/cmd_config.json`; individual model configurations are stored in `provider`.

## Custom request header variables

Custom request headers in a provider configuration support variable templates that are rendered per request:

| Variable | Meaning |
| --- | --- |
| `{conversation_id}` | AstrBot conversation ID, falling back to the request ID when empty |
| `{umo}` | Unified message origin of the request |
| `{request_id}` | Request ID that stays stable within one agent run |
| `{model}` | Model used by this request |
| `{provider_id}` | Provider configuration ID |
| `{version}` | AstrBot version |

`{sha256:<template>}` computes a SHA-256 digest. `{uuid5:<template>}` generates a standard UUID v5 from the raw value in a fixed namespace, so the same input always produces the same UUID. Both transforms accept text and the variables above; a header is omitted when a referenced variable has no value. Outside these transforms, non-ASCII characters (for example a Chinese platform ID), control characters and `%` in variable values are percent-encoded as UTF-8, the same as URL encoding, so standard URL decoding restores them.

Only the variables in the table are replaced. Everything else, including other braces, is sent as is, and authentication headers such as `Authorization` and `x-api-key` are always sent as configured.

```json
{
  "x-opencode-session": "{sha256:{conversation_id}}",
  "x-session-uuid": "{uuid5:{conversation_id}}"
}
```

`{umo}` may contain platform, group or user information and is sent to third-party services; SHA-256 and UUID v5 are deterministic encodings, not anonymization.
