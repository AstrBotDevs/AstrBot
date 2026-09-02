# Connect MiraRouter

[MiraRouter](https://mirarouter.com/) provides stable and secure OpenAI-compatible APIs for accessing popular AI models with one API key, while centralizing key, usage, and cost management.

## Get an API Key

1. Sign up and log in at [MiraRouter](https://mirarouter.com/).
2. Open the console, create an API key, and copy it. The full key is shown only once, so store it securely.

## Configure AstrBot

Open the AstrBot dashboard and go to **Providers → Add Provider Source → MiraRouter**. Enter the following values:

| Field         | Value                                         |
| ------------- | --------------------------------------------- |
| Provider Name | `MiraRouter`                                  |
| API Base URL  | `https://api.mirarouter.com/v1`               |
| API Key       | The API key created in the MiraRouter console |

AstrBot automatically adds the `X-APP-CODE: astrbot` identifier to MiraRouter requests.

Save the source, then add the models you want to use from the [MiraRouter models and pricing](https://mirarouter.com/models) page.

## Set as Default

Go to **Config → Provider Settings**, select the MiraRouter model you just added as the default chat model, and save the configuration.

For more details, see the [MiraRouter documentation](https://docs.mirarouter.com/).
