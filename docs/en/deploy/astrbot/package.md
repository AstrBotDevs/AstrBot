# Package Manager Deployment (uv)

Use `uv` to install and run AstrBot quickly.

## Before You Start

If `uv` is not installed, install it first by following the official guide:
<https://docs.astral.sh/uv/>

`uv` supports Linux, Windows, and macOS.

## Important Notes

> [!WARNING]
> AstrBot deployed via `uv` **does not support upgrading through the WebUI**. To update, run `uv tool upgrade astrbot --python 3.12` from the command line.

AstrBot requires Python 3.12 or later. Use `--python 3.12` to ensure that `uv` creates the tool environment with Python 3.12; if Python downloads are enabled, `uv` will download Python 3.12 automatically when it is missing.

## Install and Start

```bash
uv tool install astrbot --python 3.12
astrbot
```
