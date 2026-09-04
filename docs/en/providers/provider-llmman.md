# Integrating llmman

[llmman](https://github.com/llmmanorg/llmman) is a local model runner that serves the Ollama API (alongside OpenAI- and Anthropic-compatible ones) on port 17434. Models are pulled as OCI artifacts or straight from Hugging Face and served by upstream `llama.cpp`, `vllm`, or `mlx-lm`.

## Install llmman

Linux/macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/llmmanorg/llmman/main/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/llmmanorg/llmman/main/install.ps1 | iex
```

## Pull a Model and Start the Server

```bash
llmman pull gemma4
llmman serve
```

Model names can be short aliases such as `gemma4` or `qwen3.8`, or a Hugging Face reference such as `hf.co/unsloth/Qwen3.5-0.8B-GGUF`.

## Configure AstrBot

Open the AstrBot WebUI, go to Service Provider Management, click Add Provider, and choose `llmman`.

The default `API Base URL` is `http://127.0.0.1:17434/v1`. No API key is required; the placeholder `llmman` is used. Set the model name to the model you pulled, then save.

::: tip

For Mac/Windows users deploying AstrBot with Docker Desktop, enter `http://host.docker.internal:17434/v1` for the API Base URL.\
For Linux users deploying AstrBot with Docker, enter `http://172.17.0.1:17434/v1` for the API Base URL, or replace `172.17.0.1` with your public IP address (ensure that port 17434 is allowed by the host system).\
If llmman binds to another address, set `LLMMAN_HOST` (`[host][:port]`) when running `llmman serve`.

:::

## Embeddings

Use the `llmman Embedding` provider template, which points at `http://localhost:17434`. When AstrBot runs in Docker, adjust the host as described in the tip above.
