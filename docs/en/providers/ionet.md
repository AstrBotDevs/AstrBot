# Connecting to IO Intelligence

IO Intelligence is the hosted inference API from [io.net](https://io.net/). It serves open-weight models such as Llama, DeepSeek and Qwen through an OpenAI-compatible endpoint.

## Configuring the Chat Model

Register and log in to [io.net](https://io.net/).

Create an API key by following the [API keys guide](https://io.net/docs/guides/intelligence/api-keys-and-secrets). Save it for later use.

Pick a model from the IO Intelligence model list and note down its model ID, for example `meta-llama/Llama-3.3-70B-Instruct`.

In the AstrBot WebUI, open **Providers → Chat Completion**, click **Add**, and select `IO Intelligence`.

Enter the provider name and `API Key`, check the `API Base URL` (`https://api.intelligence.io.solutions/api/v1`), then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

## Applying the Chat Model

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.
