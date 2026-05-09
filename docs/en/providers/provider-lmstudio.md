# Connect LM Studio to Use DeepSeek-R1 and Other Models

LM Studio allows you to deploy models locally on your computer (hardware requirements must be met).

### Download and Install LM Studio

<https://lmstudio.ai/download>

### Download and Run a Model

<https://lmstudio.ai/models>

Follow the LM Studio instructions to download and run your desired model, e.g. `deepseek-r1-qwen-7b`:

```bash
lms get deepseek-r1-qwen-7b
```

### Configure AstrBot

In AstrBot:

Go to **Configuration → Service Providers → + → OpenAI**

Set `API Base URL` to `http://localhost:1234/v1`

Set `API Key` to `lm-studio`

> For users deploying AstrBot via Docker Desktop on Mac or Windows, set `API Base URL` to `http://host.docker.internal:1234/v1`.
>
> For users deploying AstrBot via Docker on Linux, set `API Base URL` to `http://172.17.0.1:1234/v1`, or replace `172.17.0.1` with your server's public IP (make sure port 1234 is open on the host).

If LM Studio itself is deployed in Docker, ensure port 1234 is mapped to the host.

Set the model name to the one you selected in the previous step, then save the configuration.

> Run `/provider` to view the models configured in AstrBot.
