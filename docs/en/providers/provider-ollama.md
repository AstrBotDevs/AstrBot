# Integrating Ollama

🦙 Ollama is a free, open-source tool that lets you run large language models (LLMs) on your own computer. (hardware must meet requirements)

## Download and Install Ollama

You can download Ollama from [https://ollama.com](https://ollama.com/download).

## Select and Pull a Model

Choose the model you want to use at [https://ollama.com/search](https://ollama.com/search).

In the terminal (PowerShell on Windows), enter `ollama pull <model_name>` to download the model.

model_name format: `<model_name>:<model_version>`. For example, `deepseek-r1:8b`.
> The 8b parameter model requires at least 16GB of video memory (VRAM). Refer to other documentation for detailed information on configurations and parameter sizes.

After pulling is complete, use `ollama list` to view the models you have pulled.

Then use `ollama run <model_name>` to run the model.

## Configure AstrBot

Open **Providers → Chat Completion**, click **Add**, and select `Ollama`. The default API endpoint is `http://127.0.0.1:11434/v1`; adjust it to match your deployment.

Enter the provider name and check the `API Base URL`. The template pre-fills `API Key` with `ollama`; replace it if your server requires a different key. Click **Save and Fetch Models**. Click `+` beside the desired model and make sure it is enabled. Alternatively, click **Save Configuration**, then **Custom Model** and enter the exact model ID. Use **Test Model** beside the configured model to check availability.

Open **Config**, select the profile to use, and go to **AI → Model**. Set **Chat Model** to the model you just added, then click **Save Configuration** at the bottom right. This setting is for AstrBot built-in AI.

::: tip

For Mac/Windows users deploying AstrBot with Docker Desktop, enter `http://host.docker.internal:11434/v1` for the API Base URL.\
For Linux users deploying AstrBot with Docker, enter `http://172.17.0.1:11434/v1` for the API Base URL, or replace `172.17.0.1` with your public IP address (ensure that port 11434 is allowed by the host system).\
If Ollama is deployed using Docker, ensure that port 11434 is mapped to the host.

:::

## FAQ

Error:
```
AstrBot request failed.
Error type: NotFoundError
Error message: Error code: 404 - {'error': {'message': 'model "llama3.1-8b" not found, try pulling it first', 'type': 'api_error', 'param': None, 'code': None}}

```
Please refer to the instructions above and use `ollama pull <model_name>` to pull the model, then use `ollama run <model_name>` to run the model.
