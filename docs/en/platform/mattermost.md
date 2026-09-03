# Connecting to Mattermost

The Mattermost adapter connects to your Mattermost server through a Bot Token and WebSocket. After finishing the two parts below, AstrBot can send and receive messages in Mattermost channels and direct messages.

## Create the AstrBot Mattermost Platform Adapter

Go to the `Bots` page, click `+ Create Bot`, and choose `Mattermost`.

On the configuration page, enable it first, then fill in:

- `Mattermost URL`: your Mattermost server URL, for example `https://chat.example.com`
- `Mattermost Bot Token`: the access token generated after creating a bot account in Mattermost
- `Mattermost Reconnect Delay`: how long AstrBot waits before reconnecting after a WebSocket disconnect, default `5`

Then click save.

## Deploy Mattermost

If you do not have a Mattermost server yet, use the official Mattermost Docker Compose repository:

- Official docs: https://docs.mattermost.com/deployment-guide/server/containers/install-docker.html
- Official repository: https://github.com/mattermost/docker

The current quick-start flow recommended by Mattermost is:

```bash
git clone https://github.com/mattermost/docker
cd docker
cp env.example .env
```

Then update at least these values in `.env`:

- `DOMAIN`
- `MATTERMOST_IMAGE_TAG`
- It is also recommended to set `MM_SUPPORTSETTINGS_SUPPORTEMAIL`

Create the data directories and set ownership:

```bash
mkdir -p ./volumes/app/mattermost/{config,data,logs,plugins,client/plugins,bleve-indexes}
sudo chown -R 2000:2000 ./volumes/app/mattermost
```

Choose one startup mode:

Without the bundled NGINX:

```bash
docker compose -f docker-compose.yml -f docker-compose.without-nginx.yml up -d
```

With the bundled NGINX:

```bash
docker compose -f docker-compose.yml -f docker-compose.nginx.yml up -d
```

Access URLs:

- Without NGINX: `http://your-domain:8065`
- With NGINX: `https://your-domain`

> [!TIP]
> Mattermost currently states that production Docker support is Linux-only. macOS and Windows are better suited for development or testing.

## Create a Bot in Mattermost

### 1. Enable Bot Account Creation

Open the Mattermost system console:

`System Console > Integrations > Bot Accounts`

Enable `Enable Bot Account Creation`.

### 2. Create the Bot Account

Go to:

`Product menu > Integrations > Bot Accounts`

Click `Add Bot Account` and fill in:

- `Username`
- `Display Name`
- `Description`

After creation, copy the generated Bot Token. It is shown only once. Paste it into AstrBot's `Mattermost Bot Token` field.

### 3. Add the Bot to a Channel

Add the bot to the channel where AstrBot should work. Otherwise the bot will not be able to properly receive and send messages in that channel.

## How to Fill in Mattermost URL

`Mattermost URL` should be the external URL of your Mattermost server, without a trailing slash. For example:

```text
https://chat.example.com
```

If you are only testing locally, you can also use:

```text
http://127.0.0.1:8065
```

If both AstrBot and Mattermost run in containers, prefer an address reachable from the AstrBot container, such as the Mattermost service name on the same Docker network.

## Start and Verify

After saving the AstrBot platform adapter configuration:

1. Make sure the AstrBot logs do not show Mattermost authentication or WebSocket connection errors.
2. Send a message in a channel that includes the bot, or send the bot a direct message.
3. If AstrBot replies normally, the integration is working.

## Common Issues

### Invalid Token Errors

Usually one of these:

- You copied a user token instead of the bot token
- The token contains extra spaces
- The bot account was deleted or the token was regenerated

### Connected but No Channel Messages Arrive

Check these first:

- The bot has been added to the target channel
- `Mattermost URL` points to an address AstrBot can actually reach
- Your Mattermost reverse proxy forwards WebSocket traffic correctly

### Mattermost Opens in Browser but AstrBot Still Cannot Connect

If AstrBot runs in a container while `Mattermost URL` is set to `localhost` or `127.0.0.1`, AstrBot will connect to itself instead of the Mattermost service. In that case, switch to an address reachable inside the Docker network.
