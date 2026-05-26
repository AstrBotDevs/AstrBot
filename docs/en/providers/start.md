# Connecting Model Services

AstrBot supports the native API formats of OpenAI, Google GenAI, and Anthropic. You can connect any model service provider that conforms to one of these three API formats.

> [!NOTE]
> If you are located in mainland China, we strongly recommend using **official model providers** or compliant providers that follow local laws and regulations, for example:
>
> - [MoonshotAI](https://moonshot.cn/)
> - [GLM](https://bigmodel.cn/)
> - [MiniMax](https://www.minimax.io/)
> - [Qwen](https://qwen.ai/apiplatform)
> - [DeepSeek](https://deepseek.com/)
>
> These providers support the OpenAI API format. You can find the API Base URL and API Key from their documentation and fill them into AstrBot provider settings.
>
> Please note that using non-compliant third-party model services may introduce availability, privacy, or legal risks. For details, see the [EULA](https://github.com/AstrBotDevs/AstrBot/blob/master/EULA.md).

For example, you may choose to connect model services provided by (but not limited to):

- Official OpenAI model services ([OpenAI](https://openai.com/))
- Official Anthropic model services ([Anthropic](https://www.anthropic.com/))
- Google's Gemini model services via Google Cloud ([Google Cloud](https://cloud.google.com/))
- OpenRouter model services ([OpenRouter](https://openrouter.ai/))

## Integration Steps Using DeepSeek as an Example

Using DeepSeek as an example, assuming you have registered and logged in to a DeepSeek account, the steps to connect are:

1. Go to the DeepSeek Console (https://platform.deepseek.com/).
2. Click the "API Keys" menu in the left sidebar, create a new API Key, and copy the key.
3. Click the "API Documentation" link near the bottom of the left sidebar to open the API documentation page.
4. On the API documentation page, find the section about the "OpenAI-compatible interface" and note the API Base URL, for example `https://api.deepseek.com/v1`. (If there is no `/v1`, please add `/v1`.)
5. Open the AstrBot Console -> Service Providers page, click Add Provider, find and click `OpenAI` (if the provider type you want to connect is listed, prefer clicking that type; for some providers like DeepSeek we provide optimized adapter support). Paste the API Key into the `API Key` field of the form and paste the API Base URL into the `API Base URL` field.
6. Click Get Model List, find the model you want to use, click the + button on the right, then toggle the switch that appears on the right to enable it.
7. Go to the Configuration page, find the conversational model, click the selection button on the right, choose the provider and model you just added, then click the Save Configuration button at the bottom-right of the screen.

## Using Environment Variables to Load Keys

> Introduced in v4.13.0.

You can use environment variables to load provider API keys. In the provider configuration page, set the API Key field to `$ENV_VARIABLE_NAME`, for example: `$DEEPSEEK_API_KEY`.
