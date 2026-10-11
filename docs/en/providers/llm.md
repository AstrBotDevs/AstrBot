# Large Language Model Providers

In the WebUI, open **Providers → Chat Completion**, click **Add**, and select a provider type. For an OpenAI-compatible service, select `OpenAI Compatible` and enter the API Base URL and API key supplied by that service.

Enter the provider name and `API Key`, check the `API Base URL`, then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.

See [Connecting Model Services](./start.md) for detailed steps.

> Provider connection settings are stored in `provider_sources` in `data/cmd_config.json`; individual model configurations are stored in `provider`.
