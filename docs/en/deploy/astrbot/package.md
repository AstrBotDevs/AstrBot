# Package Manager Deployment (uv)

Use `uv` to install and run AstrBot quickly.

## Before You Start

If `uv` is not installed, install it first by following the official guide:
<https://docs.astral.sh/uv/>

`uv` supports Linux, Windows, and macOS.

## Important Notes

> [!WARNING]
> AstrBot deployed via `uv` **does not support upgrading through the WebUI**. To update, run `uv tool upgrade astrbot` from the command line.

## Install and Start

```bash
uv tool install astrbot
astrbot
```
