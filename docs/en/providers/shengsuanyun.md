# Connect ShengSuanYun

[ShengSuanYun](https://www.shengsuanyun.com/?from=CH_T70U2X9L) provides a unified OpenAI-compatible API for accessing a range of popular AI models with one API key.

## Get an API Key

1. Sign up and log in at [ShengSuanYun](https://www.shengsuanyun.com/?from=CH_T70U2X9L).
2. Open the console, create an API key, and copy it.

## Configure AstrBot

Open the AstrBot dashboard and go to **Providers → Chat Completion → Add → OpenAI Compatible**. Enter the following values:

| Field | Value |
| --- | --- |
| Provider Name | `ShengSuanYun` |
| API Base URL | `https://router.shengsuanyun.com/api/v1` |
| API Key | The API key created in the ShengSuanYun console |

Enter the provider name and `API Key`, check the `API Base URL`, then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

## Set as Default

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.
