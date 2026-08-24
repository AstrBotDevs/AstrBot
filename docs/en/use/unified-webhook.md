# Unified Webhook Mode

Unified Webhook mode lets multiple platform adapters share the AstrBot Dashboard FastAPI service and port `6185`. Each platform instance receives its own callback path:

```text
/api/v1/webhooks/platforms/<webhook_uuid>
```

This normally requires only one domain and HTTPS reverse-proxy entry instead of a separate callback port for every bot.

## Supported Platforms

The current code supports Unified Webhook only for these platform types:

| Platform                             | Requirement                                                           |
| ------------------------------------ | --------------------------------------------------------------------- |
| QQ Official Bot                      | Create the `QQ Official Bot (Webhook)` platform.                      |
| WeChat Official Account              | Enable `unified_webhook_mode`.                                        |
| WeCom Application / Customer Service | Enable `unified_webhook_mode`.                                        |
| WeCom AI Bot                         | Connection mode must be `webhook`; long connection rejects callbacks. |
| Slack                                | Connection mode must be `webhook`.                                    |
| Lark / Feishu                        | Connection mode must be `webhook`.                                    |
| LINE                                 | The adapter always uses Unified Webhook.                              |

Other HTTP-based platforms do not join this endpoint merely because a similarly named setting is added manually.

## 1. Prepare a Public Endpoint

1. Point a domain such as `astrbot.example.com` to your server or load balancer.
2. Configure a valid HTTPS certificate.
3. Reverse-proxy external requests to AstrBot port `6185`. Allow both `GET` and `POST` for callback routes.

When the reverse proxy and AstrBot run on the same host, the proxy can reach the default `127.0.0.1:6185` listener. When AstrBot runs in another container, the WebUI must also listen on the relevant network interface; see [Docker Deployment](/en/deploy/astrbot/docker) or [Source Deployment](/en/deploy/astrbot/cli). Publishing a port while retaining a loopback-only listener inside the container does not work.

> [!CAUTION]
> Unified Webhook shares port `6185` with the admin panel. Restrict public access to management pages, use a strong password and TOTP, and apply suitable reverse-proxy or firewall controls.

## 2. Set the Public Base URL

In the AstrBot WebUI, open `Settings` -> `General` and set `Externally Accessible Callback API Address` (configuration key `callback_api_base`):

```text
https://astrbot.example.com
```

This is the public base address that external services actually use to reach AstrBot. It only generates and displays callback/file URLs; it does not configure DNS, TLS, port mappings, or a reverse proxy. Do not append a platform-specific `/api/v1/webhooks/...` path.

System settings save automatically. If the page reports that a restart is required, restart AstrBot before creating the platform.

## 3. Create the Platform and Copy Its URL

1. Create or edit a supported platform under `Bots`.
2. Enable `unified_webhook_mode` where the option exists. Slack, Lark, and WeCom AI Bot must also use their Webhook connection mode.
3. Save the platform. AstrBot automatically generates and persists its `webhook_uuid`.
4. Copy the complete URL from `View Webhook URL` on the bot card or from the AstrBot logs, for example:

   ```text
   https://astrbot.example.com/api/v1/webhooks/platforms/0123456789abcdef
   ```

5. Enter the full URL in the platform's event callback settings, then complete that platform's signature, Token, encryption-key, and event-subscription setup.

Do not manually reuse another bot instance's `webhook_uuid`. Multiple instances of the same platform must also use their own generated URLs.

## Troubleshooting

- The URL shows `http(s)://<your-astrbot-domain>`: `callback_api_base` is missing or the platform has not reloaded its configuration.
- External requests time out: check DNS, certificates, reverse proxy, cloud security groups, and firewall rules. For containers, also check the WebUI bind address.
- The platform gets 404: make sure the proxy preserves `/api/v1/webhooks/platforms/<uuid>` and that the UUID belongs to the current instance.
- WeCom AI Bot says long-connection mode does not accept callbacks: switch its connection mode to `webhook`, or keep the recommended long connection and do not configure an inbound URL.
- Signature verification fails: the unified endpoint only routes the request. Recheck the platform-specific Secret, Token, EncodingAESKey, or signing secret.
