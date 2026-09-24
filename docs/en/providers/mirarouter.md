# Connect MiraRouter

[MiraRouter](https://mirarouter.com/) provides stable and secure OpenAI-compatible APIs for accessing popular AI models with one API key, while centralizing key, usage, and cost management.

## Get an API Key

1. Sign up and log in at [MiraRouter](https://mirarouter.com/).
2. Open the console, create an API key, and copy it. The full key is shown only once, so store it securely.

## Configure AstrBot

Open the AstrBot dashboard and go to **Providers → Chat Completion → Add → MiraRouter**. Enter the following values:

| Field | Value |
| --- | --- |
| Provider Name | `MiraRouter` |
| API Base URL | `https://api.mirarouter.com/v1` |
| API Key | The API key created in the MiraRouter console |

AstrBot automatically adds the `X-APP-CODE: astrbot` identifier to MiraRouter requests.

Enter the provider name and `API Key`, check the `API Base URL`, then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

## Set as Default

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.

For more details, see the [MiraRouter documentation](https://docs.mirarouter.com/).
