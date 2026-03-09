# Connect server-satori (Koishi)

> [!TIP]
> `server-satori` is a Koishi plugin that exposes Koishi as a Satori server, so AstrBot can connect to Koishi through Satori.

## Preparation

Make sure you already have a running Koishi instance.

If not, follow official docs first:

- Koishi starter docs: <https://koishi.chat/zh-CN/manual/starter/windows.html>
- Koishi community: <https://koishi.chat/zh-CN/about/contact.html>

## Enable `server-satori` in Koishi

1. Open Koishi admin panel.
2. Go to `Plugin Config`.
3. Install and enable `server-satori` (defaults usually work).

After enabling, `server-satori` serves Satori API under `/satori`.

![image](https://files.astrbot.app/docs/source/images/satori/2025-09-07_17-14-55.png)

## Configure Satori Adapter in AstrBot

1. Open AstrBot Dashboard.
2. Click `Bots`.
3. Click `+ Create Bot`.
4. Select `satori`.

Fill in:

- Bot ID (`id`): `server-satori`
- Enable (`enable`): checked
- Satori API endpoint (`satori_api_base_url`): `http://localhost:5140/satori/v1`
- Satori WebSocket endpoint (`satori_endpoint`): `ws://localhost:5140/satori/v1/events`
- Satori token (`satori_token`): usually empty unless configured in Koishi

> [!NOTE]
> - Koishi default port is `5140`.
> - `server-satori` default path is `/satori`.
> - So the full API base is `http://localhost:5140/satori/v1`.
> - If your Koishi runs on different host/port/path, change accordingly.

![image](https://files.astrbot.app/docs/source/images/satori/2025-10-10_16-16-25.png)

Click `Save`.

## Done

AstrBot should now be connected to Koishi via `server-satori`.

Test by sending an AstrBot command (for example `/help`) in Koishi sandbox.

![image](https://files.astrbot.app/docs/source/images/satori/2025-09-07_17-19-04.png)

## Troubleshooting

If connection fails, check:

1. Koishi is running.
2. `server-satori` is installed and enabled.
3. Port/path are configured correctly.
4. Firewall is not blocking related ports.
