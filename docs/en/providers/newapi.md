# NewAPI

[NewAPI](http://newapi.ai/) is a next-generation LLM gateway and AI asset management system built on top of One API. It provides a unified interface for managing and using multiple AI model services, including OpenAI, Anthropic, Gemini, Midjourney, and more.

AstrBot can integrate with NewAPI as a model provider, so you can access those model services through AstrBot.

## Setup Steps

### 1. Create a NewAPI API Key

After registering and signing in to NewAPI, open `Console` in the top navigation bar, go to `Token Management`, then click `Add Token` to create a new API key with appropriate permissions.

![create-api-key](https://files.astrbot.app/docs/source/images/newapi/image.png)

After creation, copy the generated API key.

![copy-api-key](https://files.astrbot.app/docs/source/images/newapi/image-1.png)

### 2. Configure NewAPI in AstrBot

Open AstrBot WebUI, go to `Service Providers`, and click `Add Provider`.

NewAPI fully supports OpenAI Chat Completion and Responses APIs, so select `OpenAI` and open its provider configuration.

Set `API Base URL` to your NewAPI endpoint:

- Self-hosted NewAPI example: `http://localhost:3000/v1`
- Hosted service example: `https://api.example.com/v1`

Then paste your API key into `API Key` and click `Save`.

![astrbot-provider-config](https://files.astrbot.app/docs/source/images/newapi/image-2.png)

### 3. Apply the Provider

Go to `Configuration`, find the model section, set `Default Chat Model` to the NewAPI-based provider you just created, and click `Save`.

![apply](https://files.astrbot.app/docs/source/images/newapi/image-3.png)

You have now successfully configured NewAPI as an AstrBot model provider.
