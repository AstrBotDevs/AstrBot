# Connect Personal WeChat

> Introduced in v4.22.0.

AstrBot supports connecting a personal WeChat account through the `Personal WeChat` adapter. This adapter is implemented on top of Tencent's official `openclaw-weixin` interface, uses QR-code login plus long polling, and does not require a Webhook callback URL.

> [!NOTE]
> Please upgrade your mobile WeChat to a recent version.
>
> **iOS**: >= 4.0.70

## Supported Message Types

| Message Type | Receive | Send | Notes |
| --- | --- | --- | --- |
| Text | Yes | Yes | |
| Image | Yes | Yes | Downloaded and decrypted into the local temp directory on receive |
| Voice | Yes* | No | *WeChat cloud-side transcription is used, so no local transcription is required |
| Video | Yes | Yes | Downloaded and decrypted into the local temp directory on receive |
| File | Yes | Yes | Downloaded and decrypted into the local temp directory on receive |

## Create the Bot

1. Open AstrBot WebUI.
2. Click `Bots` in the left sidebar.
3. Click `+ Create Bot` in the upper-right corner.
4. Select `Personal WeChat`.
5. The login QR code is shown directly. Scan it with WeChat on your phone and confirm the login inside WeChat.
6. After login succeeds, click `Save`.

## Configuration Notes

In most cases, you only need to pay attention to these fields:

- `ID(id)`: Any value you like, used to distinguish different bot instances.
- `Enable(enable)`: Turn it on.

Leave the remaining options at their default values unless you explicitly know you need to change them:

- `QR Poll Interval (weixin_oc_qr_poll_interval)`
- `Long Poll Timeout (weixin_oc_long_poll_timeout_ms)`
- `API Timeout (weixin_oc_api_timeout_ms)`

> [!TIP]
> `token` and `account_id` are saved automatically by AstrBot after QR login succeeds. You normally do not need to fill them manually.

## QR Login

After you select `Personal WeChat`, AstrBot automatically requests a login QR code from WeChat and shows it directly in the create-bot dialog. Scan it with WeChat on your phone and confirm the login. When the QR area shows the login-success state, click `Save` to finish creating the bot.

After login succeeds and the bot is saved, AstrBot will automatically persist the login state. On later restarts, if the session is still valid, you usually do not need to scan again.

> [!NOTE]
> If the QR code expires, close and reopen the create-bot dialog, or select `Personal WeChat` again to request a new QR code.

## Verification

After login succeeds, send a message from WeChat. If AstrBot replies normally, the integration is working.

You can also watch the `Console` page in WebUI to confirm that the adapter has completed login and started polling messages.

## Media File Storage

Received images, videos, files, and voice messages are downloaded and decrypted into AstrBot's local temporary directory:

`data/temp`

These files are temporary cached files and can be further used by plugins, agents, or the file service.

## Notes

- This adapter logs in by scanning a QR code with a personal WeChat account, so its setup flow is different from WeChat Official Account and WeCom.
- No public callback URL is required, and Unified Webhook Mode is not needed.
