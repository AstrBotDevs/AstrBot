# Connect WorldRouter

[WorldRouter](https://router.worldclaw.ai) is an OpenAI-compatible model API platform. One API key gives access to Claude, GPT, Gemini, DeepSeek, Kimi and other models.

## Getting Started

Register an account at [WorldRouter](https://router.worldclaw.ai), then create an API key on the **API Keys** page of the console.

See the [model list](https://router.worldclaw.ai/models) for available models and prices, and the [quickstart](https://router.worldclaw.ai/docs/quickstart) for setup details.

## Connect

In the AstrBot WebUI, open **Providers → Chat Completion**, click **Add**, and select `WorldRouter`.

Enter the provider name and `API Key`, check that the `API Base URL` is `https://inference-api.worldrouter.ai/v1`, then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

## Usage

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.

Send the `/provider` command to the bot to switch to the WorldRouter provider you just added.
