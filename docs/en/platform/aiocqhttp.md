# Connect OneBot v11 Protocol Implementations

OneBot is a standardized bot application interface designed to unify bot development across different chat platforms, so developers can write business logic once and use it on multiple platforms.

AstrBot supports all client implementations that implement OneBot v11 reverse WebSocket (AstrBot acts as the server).

Common OneBot v11 implementation projects are listed below:

- [NapCat](https://github.com/NapNeko/NapCatQQ)
- [OneDisc](https://github.com/ITCraftDevelopmentTeam/OneDisc)
- [Tele-KiraLink](https://github.com/Echomirix/Tele-KiraLink)

Please refer to each implementation project's deployment documentation.

## 1. Configure OneBot v11

1. Open AstrBot's WebUI
2. Click `Bots` in the left sidebar
3. In the right panel, click `+ Create Bot`
4. Select `OneBot v11`

Fill in the form:

- ID (`id`): any value, used only to distinguish instances of different platforms.
- Enable (`enable`): check it.
- Reverse WebSocket host: fill your machine IP, usually `0.0.0.0`.
- Reverse WebSocket port: choose any port, default is `6199`.
- Reverse WebSocket token: fill this only when NapCat network configuration has a token set.

Click `Save`.

## 2. Configure the protocol implementation side

Please refer to each protocol implementation project's deployment documentation.

Notes:

1. The implementation must support `Reverse WebSocket`, with AstrBot acting as the server and the implementation client as the client.
2. The reverse WebSocket URL is `ws(s)://<your-host>:6199/ws`.

## 3. Verify

Go to AstrBot WebUI `Console`. If a blue log appears saying `aiocqhttp(OneBot v11) adapter connected.`, the connection is successful.
If after a few seconds you see `aiocqhttp adapter has been closed`, it means the connection timed out (failed). Please double-check your configuration.
