# Connecting to SiliconFlow

SiliconFlow leverages its proprietary inference engine to deliver efficient acceleration for large language model inference. It provides high-performance, cost-effective API services for a wide range of large models with pay-as-you-go pricing, making application development a breeze.

## Configuring the Chat Model

Navigate to the SiliconFlow [API Keys](https://cloud.siliconflow.cn/me/account/ak) page and create a new API Key. Save it for later use.

Visit the SiliconFlow [Models page](https://cloud.siliconflow.cn/me/models) to select your desired model. Note down the model name for later use.

In the AstrBot WebUI, open **Providers → Chat Completion**, click **Add**, and select `SiliconFlow`.

Enter the provider name and `API Key`, check the `API Base URL`, then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

## Applying the Chat Model

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.
