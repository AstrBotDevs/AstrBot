# Large Language Model Providers

In the WebUI, open **Providers → Chat Completion**, click **Add**, and select a provider type. For an OpenAI-compatible service, select `OpenAI Compatible` and enter the API Base URL and API key supplied by that service.

Enter the provider name and `API Key`, check the `API Base URL`, then click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.

See [Connecting Model Services](./start.md) for detailed steps.

> Provider connection settings are stored in `provider_sources` in `data/cmd_config.json`; individual model configurations are stored in `provider`.

## Google Vertex AI

Select `Google Vertex AI` to call Gemini models through Google Cloud Vertex AI. It supports the same features as `Gemini Compatible`, such as thinking, native search and safety filters. Leave `API Base URL` empty; the endpoint is chosen from the location. Use one of these authentication methods:

- **API key bound to a service account (recommended)**: no key file is stored. Create a key restricted to Vertex AI, for example `gcloud services api-keys create --service-account=SA_EMAIL --api-target=service=aiplatform.googleapis.com`, enter it in `API Key`, and set `Vertex AI project ID` and `Vertex AI location`. Use a location where the model is available; some models are only offered in `global`.
- **API key (Vertex AI express mode)**: enter an express-mode API key in `API Key` and leave `Vertex AI project ID` empty. Requests go to Google's default region.
- **Service account**: leave `API Key` empty, set `Service account key file` to the path of a service account JSON key with the `Vertex AI User` role, and set `Vertex AI location` (default `global`). `Vertex AI project ID` is read from the key file when left empty. In Docker, mount the key file into the container and use the in-container path.
- **Application Default Credentials**: leave `API Key` and the key file empty. AstrBot uses `GOOGLE_APPLICATION_CREDENTIALS` or the credentials of the Google Cloud environment it runs in.

Use the model ID shown in Vertex AI Model Garden, for example `gemini-2.5-flash`. Google does not allow listing models with an API key, so with API key authentication add the model with **Custom Model** instead of fetching the model list.
