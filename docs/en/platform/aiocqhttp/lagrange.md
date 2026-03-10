# Connect to Lagrange

> [!TIP]
> - Please control message frequency responsibly. Sending messages too frequently may trigger risk control.
> - This project must not be used for illegal purposes.
> - For the latest deployment steps, always refer to the official [Lagrange Docs](https://lagrangedev.github.io/Lagrange.Doc/Lagrange.OneBot/Config/#%E4%B8%8B%E8%BD%BD%E5%AE%89%E8%A3%85).

## Download

Download the latest `Lagrange.OneBot` from [GitHub Releases](https://github.com/LagrangeDev/Lagrange.Core/releases).

- Windows: `Lagrange.OneBot_win-x64_xxxx`
- Linux x86_64: `Lagrange.OneBot_linux-x64_xxx`
- Linux ARM64: `Lagrange.OneBot_linux-arm64_xxx`
- macOS Apple Silicon: `Lagrange.OneBot_osx-arm64_xxx`
- macOS Intel: `Lagrange.OneBot_osx-x64_xxx`

## Deploy

Follow the official docs:

- Run guide: <https://lagrangedev.github.io/Lagrange.Doc/Lagrange.OneBot/Config/#%E8%BF%90%E8%A1%8C>
- Config file guide: <https://lagrangedev.github.io/Lagrange.Doc/Lagrange.OneBot/Config/#%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6>

In your config file, add this under `Implementations`:

```json
{
  "Type": "ReverseWebSocket",
  "Host": "127.0.0.1",
  "Port": 6199,
  "Suffix": "/ws",
  "ReconnectInterval": 5000,
  "HeartBeatInterval": 5000,
  "AccessToken": ""
}
```

Make sure `Suffix` is exactly `/ws`.

## Connect to AstrBot

### Configure `aiocqhttp` Adapter

1. Open AstrBot Dashboard.
2. Click `Bots` in the left sidebar.
3. Click `+ Create Bot`.
4. Select `aiocqhttp (OneBot v11)`.

Fill in:

- ID (`id`): any unique identifier.
- Enable (`enable`): checked.
- Reverse WebSocket host: your machine IP (usually `0.0.0.0`).
- Reverse WebSocket port: an available port, for example `6199`.
