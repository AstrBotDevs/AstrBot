# Connect a WeCom AI Bot

WeCom AI Bot works in internal direct messages and group chats and supports streaming replies. AstrBot provides two connection modes:

- **Long connection (default and recommended)**: AstrBot connects outbound to WeCom. It does not require a public IP, domain, or inbound Webhook.
- **Webhook callback**: WeCom calls AstrBot, so AstrBot needs a publicly reachable HTTPS endpoint.

The current `WeCom AI Bot` platform template selects `long_connection` by default. Prefer it unless your enterprise network or an existing integration specifically requires Webhook callbacks.

## Message Capabilities

| Message Type | Receive | Send | Notes                                        |
| ------------ | ------- | ---- | -------------------------------------------- |
| Text         | Yes     | Yes  | Streaming replies are supported.             |
| Image        | Yes     | Yes  | Sending requires a message-push Webhook URL. |
| Voice        | No      | Yes  | Sending requires a message-push Webhook URL. |
| Video        | No      | Yes  | Sending requires a message-push Webhook URL. |
| File         | No      | Yes  | Sending requires a message-push Webhook URL. |

Proactive messages also require a message-push Webhook URL. This is an **outbound** destination used by AstrBot to send to a WeCom group bot; it is different from the inbound callback where WeCom delivers events to AstrBot.

## Method 1: Long Connection (Recommended)

### 1. Create the Bot in WeCom

1. Sign in to the [WeCom Admin Console](https://work.weixin.qq.com/wework_admin).
2. Open `Management Tools` -> `AI Bot` and create an API-mode bot.
3. In the bot's long-connection settings, obtain its `BotID` and `Secret`. Protect the Secret like a password.

The exact WeCom labels may change over time. You need the long-connection credentials, not the Token and EncodingAESKey used by callback mode.

### 2. Create the Platform in AstrBot

1. Open the AstrBot WebUI and go to `Bots`.
2. Click `+ Create Bot` and select `WeCom AI Bot`.
3. Keep the connection mode set to `Long connection` (`long_connection`).
4. Fill in:
   - `wecom_ai_bot_name`: the same bot name used in WeCom.
   - `wecomaibot_ws_bot_id`: the BotID supplied by WeCom.
   - `wecomaibot_ws_secret`: the Secret supplied by WeCom.
5. Save the platform.

`wecomaibot_ws_url` defaults to `wss://openws.work.weixin.qq.com`, and the heartbeat interval defaults to 30 seconds. They normally do not need to be changed.

Long-connection mode does not start a local callback server and does not use `unified_webhook_mode`, Token, EncodingAESKey, or a callback port. The AstrBot host only needs outbound access to the WeCom WebSocket service.

### 3. Verify

Check `Console` in AstrBot for long-connection startup and connection logs, then send the bot a message in WeCom. If it cannot connect, check BotID, Secret, outbound network access, proxy settings, and TLS verification instead of inbound ports.

## Method 2: Webhook Callback

Use this only when callback mode is specifically required.

### 1. Prepare a Public Callback Endpoint

1. Prepare a publicly reachable HTTPS domain for AstrBot.
2. Reverse-proxy it to the AstrBot WebUI on port `6185`.
3. In the WebUI, open `Settings` -> `General` and set `Externally Accessible Callback API Address`, for example `https://astrbot.example.com`.

For Docker, the WebUI must also listen on the container network interface; see [Docker Deployment](/en/deploy/astrbot/docker). Publishing a port while retaining the `127.0.0.1` listener is not sufficient.

### 2. Configure WeCom and AstrBot

1. In WeCom Admin Console, create an API-mode AI bot, select the Webhook/callback connection method, and generate a Token and EncodingAESKey.
2. Create `WeCom AI Bot` in AstrBot and change its connection mode to `webhook`.
3. Fill in the bot name, `wecomaibot_token`, and `wecomaibot_encoding_aes_key`, and keep `unified_webhook_mode` enabled.
4. Save, then copy the unique callback URL generated for this platform from the AstrBot logs or its bot card in the WebUI.
5. Enter that URL as the WeCom callback and complete verification.

![Unified Webhook callback URL](https://files.astrbot.app/docs/source/images/use/unified-webhook.png)

Unified Webhook mode reuses AstrBot port `6185`; it does not require a separate `6198` port.

If Unified Webhook is disabled, the adapter starts a separate server on path `/webhook/wecom-ai-bot`, default port `6198`, and default bind address `127.0.0.1`. For a remote callback you must also change `callback_server_host` to `0.0.0.0` or a specific reachable interface and separately secure and proxy that port. This deployment is usually not recommended.

## Optional: Configure a Message-Push Webhook

Direct AI Bot replies have message-type and reply-window limits. For images, voice, video, files, multiple messages, or proactive delivery:

1. Create a message-push bot in the settings of an internal WeCom group.
2. Put its generated URL in AstrBot's `msg_push_webhook_url`.
3. Enable `only_use_webhook_url_to_send` if every reply should use that URL.

The URL contains a sensitive key. Do not include it in logs, screenshots, or public configuration. It can be used with either long-connection or inbound Webhook mode.

## Use the Bot

In an internal WeCom group, use `Add Member` -> `AI Bot` to add the bot, or open a direct chat with it. Enable streaming replies in AstrBot for a typing-style response.
