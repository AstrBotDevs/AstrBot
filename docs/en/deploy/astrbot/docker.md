# Deploy AstrBot with Docker

This fork does not publish a prebuilt container image. Build the image from the
current checkout so the backend and Dashboard stay version-matched.

## Build from Source

Clone this repository and build from its root `Dockerfile`, `Dockerfile.docs`,
and Compose files when you need the full profile, custom runtime features, or
the locally built documentation site.

## Choose a Compose File

The repository provides two locally built deployment paths:

- `compose.yml`: runs AstrBot and the locally built static documentation site. Use it for QQ Official Bot, Telegram, Discord, and other platforms, or when you manage the bot protocol implementation separately.
- `compose-with-napcat.yml`: runs AstrBot, the static documentation site, and NapCat together for personal QQ accounts. AstrBot and the documentation are still built from the local checkout; NapCat uses the referenced NapCat container image.

Clone the repository first:

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
```

## Container Listener and Host Ports

The Compose deployments explicitly set the container's WebUI listener to `0.0.0.0`; otherwise the host cannot reach the published port. Host ports bind to `127.0.0.1` by default. For remote access, explicitly set `ASTRBOT_BIND_ADDRESS` and configure a firewall or HTTPS reverse proxy.

For example:

```bash
ASTRBOT_BIND_ADDRESS=0.0.0.0 docker compose up -d --build
```

`ASTRBOT_DASHBOARD_HOST` takes precedence over `dashboard.host` in `data/cmd_config.json`.

> [!CAUTION]
> `0.0.0.0` makes the WebUI listen on every container interface. Do not expose the admin panel directly to the public internet. Restrict firewall access and use a reverse proxy, HTTPS, a strong password, and TOTP.

The default AstrBot service is unprivileged and does not mount
`/var/run/docker.sock`. In the NapCat Compose file, NapCat remains
`privileged: true` for its QQ/desktop runtime; AstrBot itself is unprivileged
but keeps the docker.sock mount. Computer-tool Docker access is opt-in via the
`computer` profile:

```bash
docker compose --profile computer up -d --build computer
```

That starts the `computer` service (AstrBot plus docker.sock) instead of the
default `astrbot` service. Do not run both at once or the published ports will
conflict. The static documentation service remains read-only and unprivileged.

## Start AstrBot and the Documentation Site

The root `compose.yml` uses the root Dockerfile's `runtime` stage to build the current checkout as `astrbot:local`; the documentation image is `astrbot-docs:local`. The Dockerfile's `dev` stage remains available for the development tool environment:

```bash
docker build --target dev -t astrbot:dev .
```

### Select Runtime Features

`ASTRBOT_FEATURES` is a Docker **build argument**, not a runtime container
environment variable. Compose passes it to the Dockerfile's `runtime` stage.
It defaults to `full`, which preserves the complete feature set. Changing it
requires rebuilding the image; an existing container is not changed in place.
Use one of these forms:

Set it for one build only:

```bash
ASTRBOT_FEATURES=minimal docker compose up -d --build
```

Persist it in a `.env` file at the project root (Compose loads this file
automatically):

```dotenv
ASTRBOT_FEATURES=browser,documents,media,ocr,fonts,node,docker
```

Override `.env` from the command line when needed:

```bash
ASTRBOT_FEATURES=browser,node,docker docker compose up -d --build
```

The NapCat stack uses the same argument:

```bash
ASTRBOT_FEATURES=browser,node,docker \
  docker compose -f compose-with-napcat.yml up -d --build
```

Available feature groups:

- `browser`: Chromium and its system dependencies.
- `documents`: Pandoc, Poppler, TeX, and related fonts.
- `media`: FFmpeg, ImageMagick, Ghostscript, and codec libraries.
- `ocr`: Tesseract with English and Simplified Chinese data.
- `fonts`: runtime font families and fontconfig.
- `node`: Node.js, npm, npx, and pnpm for MCP launchers.
- `docker`: Docker CLI and Compose plugin.

Note that `node` is not required to serve the WebUI. The Dashboard is built
with Node.js in the Dockerfile's `builder` stage, and the generated static
files are copied into the `runtime` image. AstrBot's Python/FastAPI service
serves those files at runtime, so the `minimal` profile still includes and
serves the WebUI. Add `node` only for Node-based MCP launchers or other
Node.js integrations.

For example:

```bash
docker compose config
```

Use this command to inspect the final `ASTRBOT_FEATURES` build argument passed
by Compose. The `minimal` profile keeps the Python application and core shell
utilities; enable the groups required by your integrations explicitly.
The builder still retains the toolchain needed to produce the Dashboard and
documentation, while the selected features affect the final runtime image.

```bash
docker compose up -d --build
docker compose logs -f astrbot docs
```

Its default mount and published ports are:

- `./data` -> `/AstrBot/data`: configuration, database, plugins, and other runtime data.
- `127.0.0.1:6185:6185`: AstrBot WebUI.
- `127.0.0.1:6199:6199`: optional OneBot v11 reverse WebSocket endpoint.
- `127.0.0.1:6186:8080`: the locally built documentation site, available at `http://localhost:6186`.

The documentation is an independent read-only static service. It neither reads `data/` nor shares the WebUI login state. Publish port `6186` only when you need to serve the documentation externally, and protect it with firewall rules or an HTTPS reverse proxy as appropriate.

Publishing `6199` does not change the OneBot listener address. Only set that platform's `ws_reverse_host` to `0.0.0.0` when its OneBot client runs outside the AstrBot container. Also configure `ws_reverse_token` and restrict network access to the port.

## Start AstrBot and NapCat Together

The file currently also sets NapCat `MODE=astrbot`. On every NapCat startup, that mode writes a **reverse** WebSocket client targeting `ws://astrbot:6199/ws`. To use AstrBot's currently recommended dedicated `NapCat` platform, change it first to:

```yaml
- MODE=ws
```

`MODE=ws` starts a OneBot v11 forward WebSocket server on `0.0.0.0:3001`. Then start the stack:

```bash
docker compose -f compose-with-napcat.yml up -d --build
docker compose -f compose-with-napcat.yml logs -f astrbot docs napcat
```

On Linux, you can run NapCat with your host user's UID/GID to reduce bind-mount permission issues:

```bash
NAPCAT_UID=$(id -u) NAPCAT_GID=$(id -g) \
  docker compose -f compose-with-napcat.yml up -d --build
```

This Compose file publishes (host ports bind to loopback by default):

- `6185`: AstrBot WebUI.
- `6186`: the locally built documentation site.
- `6099`: NapCat WebUI.

It persists:

- `./data`
- `./napcat/config`
- `./ntqq`

AstrBot and NapCat share an internal Docker network. With `MODE=ws`, create the dedicated `NapCat` platform in AstrBot and set `ws_url` to `ws://napcat:3001`. If NapCat's forward WebSocket uses a token, configure the same token on both sides. This path does not require publishing a QQ WebSocket port to the host.

> [!NOTE]
> NapCat `MODE` selects a startup template and rewrites `onebot11.json` on every start; the template token is empty. To persist a custom token, start once with `MODE=ws`, remove `MODE` from the Compose file, and then set the token in NapCat WebUI. The resulting configuration remains under `./napcat/config`.

If you retain the Compose file's original `MODE=astrbot`, do not create the dedicated `NapCat` platform. Create `OneBot v11`, set `ws_reverse_host` to `0.0.0.0`, and keep port `6199`. It only needs to be reachable on the internal Docker network and does not need to be published to the host. For authentication, likewise remove `MODE` after the initial configuration is generated, then set the same token in NapCat and AstrBot.

## First Login and Updates

On first startup, AstrBot prints the WebUI address and a random initial password in its logs. The default username is `astrbot`. Change the password immediately after logging in.

To update, back up `data/`, pull the latest code, and rebuild the selected service:

```bash
git pull --ff-only
docker compose up -d --build
```

For the NapCat stack, use:

```bash
git pull --ff-only
docker compose -f compose-with-napcat.yml up -d --build
```
