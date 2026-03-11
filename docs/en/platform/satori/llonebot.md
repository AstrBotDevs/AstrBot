# Connect LLTwoBot (Satori)

> [!TIP]
> LLTwoBot is a multi-protocol implementation based on QQNT (OneBot v11 + Satori), allowing AstrBot to communicate with QQ via Satori.

> [!TIP]
> - Please control message frequency responsibly.
> - This project must not be used for illegal purposes.

## Preparation

First complete basic setup using official LLTwoBot documentation:

[LLTwoBot Docs](https://llonebot.com/guide/getting-started)

Make sure you have:

1. Installed LLTwoBot.
2. Logged into a QQ account successfully.

## Configure Satori in LLTwoBot

After QQ login succeeds, open LLTwoBot WebUI:

> Default WebUI URL: <http://localhost:3080/>

In the WebUI sidebar, open the `Satori` tab and configure:

1. Enable Satori protocol.
2. Port defaults to `5600`.
3. Set Satori token if needed.
4. Click Save.

![image](https://files.astrbot.app/docs/source/images/satori/2025-10-10_15-52-32.png)

## Configure Satori Adapter in AstrBot

1. Open AstrBot Dashboard.
2. Click `Bots`.
3. Click `+ Create Bot`.
4. Select `satori`.

Fill in:

- Bot ID (`id`): `LLTwoBot`
- Enable (`enable`): checked
- Satori API endpoint (`satori_api_base_url`): `http://localhost:5600/v1`
- Satori WebSocket endpoint (`satori_endpoint`): `ws://localhost:5600/v1/events`
- Satori token (`satori_token`): from LLTwoBot config if set

> [!NOTE]
> - LLTwoBot Satori service defaults to port `5600`.
> - The complete API base path is `http://localhost:5600/v1`.
> - If your Satori service runs on another port/path, adjust these values.

![image](https://files.astrbot.app/docs/source/images/satori/2025-10-10_16-10-54.png)

Click `Save`.

## Done

AstrBot should now be connected to LLTwoBot via Satori.

Send `/help` in QQ to verify.

## Troubleshooting

If connection fails, check:

1. LLTwoBot is running.
2. Satori service is enabled.
3. Port/path are configured correctly.
4. Token matches (if configured).
