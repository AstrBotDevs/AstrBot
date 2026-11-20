# Connecting to LLMTR

[LLMTR](https://llmtr.com/) is an OpenAI-compatible API gateway. It exposes a Chat Completions endpoint at `https://llmtr.com/v1`, so AstrBot can talk to it with the built-in OpenAI-compatible adapter.

## Configuring the Chat Model

Create an API key on the [LLMTR keys dashboard](https://llmtr.com/dashboard/keys) and save it for later use.

Model IDs are vendor/model paths hosted by LLMTR, for example `minimax/minimax-m3.1-flash`. Note down the ID you want to use.

In the AstrBot WebUI, open **Providers → Chat Completion**, click **Add**, and select `LLMTR`.

Enter the provider name and `API Key`, check that the `API Base URL` is `https://llmtr.com/v1`, then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

You can also load the key from an environment variable by setting the API Key field to `$LLMTR_API_KEY`.

## Applying the Chat Model

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.
