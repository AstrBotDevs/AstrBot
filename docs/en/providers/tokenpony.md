# Connecting to TokenPony

## Configuring the Chat Model

Register and log in to [TokenPony](https://www.tokenpony.cn/3YPyf).

Navigate to the TokenPony [API Keys](https://www.tokenpony.cn/#/user/keys) page and create a new API Key. Save it for later use.

Visit the TokenPony [Models page](https://www.tokenpony.cn/#/model) to select your desired model. Note down the model name for later use.

In the AstrBot WebUI, open **Providers → Chat Completion**, click **Add**, and select `TokenPony`.

Enter the provider name and `API Key`, check the `API Base URL`, then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

## Applying the Chat Model

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.
