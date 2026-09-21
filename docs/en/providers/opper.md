# Connecting to Opper

[Opper](https://opper.ai/) is an EU-hosted AI gateway operated by Opper Technology AB (Stockholm, Sweden). One API key and one OpenAI-compatible endpoint reach models from more than 30 upstream providers, including Anthropic, OpenAI, Google, Mistral and DeepSeek, at each provider's own token rates with no markup. Requests can be pinned to EU-hosted regions.

## Configuring the Chat Model

Create an API Key on the Opper [platform](https://platform.opper.ai) under **API Keys**. Save it for later use.

Browse the [model catalogue](https://opper.ai/models) and note the id you want. Opper serves two forms: a bare pool name such as `claude-sonnet-4-6` routes across every provider serving that model, while `<provider>/<model>` such as `anthropic/claude-sonnet-4-6` or `aws/claude-sonnet-4-6-eu` pins one provider or region.

In the AstrBot WebUI, open **Providers → Chat Completion**, click **Add**, and select `Opper`.

Enter the provider name and `API Key`, check the `API Base URL` (`https://api.opper.ai/v3/compat`), then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model id. Use **Test Model** beside the configured model to check availability.

## Applying the Chat Model

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.
