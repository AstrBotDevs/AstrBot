# Connect NapCat

`napcat` is AstrBot's built-in NapCat QQ adapter. It now runs on a forward OneBot v11 WebSocket only.

Compared with the generic `OneBot v11` adapter:

- the WebUI exposes NapCat-specific fields directly
- AstrBot keeps a single outbound WebSocket connection to NapCat
- platform actions and inbound event parsing share that same connection

> [!TIP]
> If you only need a generic OneBot v11 implementation, see [OneBot v11](/en/platform/aiocqhttp).

## 1. Prepare NapCat

Deploy NapCat first, then confirm:

- NapCat OneBot v11 forward WebSocket is enabled
- you know its WebSocket URL, for example `ws://127.0.0.1:3001`
- if WebSocket auth is enabled, you also know the token

## 2. Create a NapCat bot in AstrBot

1. Open AstrBot WebUI
2. Go to `Bots`
3. Click `+ Create Bot`
4. Select `NapCat`

At minimum, fill in:

- `id`: bot instance ID
- `enable`: turn it on
- `ws_url`: NapCat OneBot v11 forward WebSocket URL
- `token`: optional, only if NapCat uses WebSocket auth

Advanced fields:

- `verify_ssl`: disable only for self-signed WSS certificates
- `timeout_seconds`: action response timeout
- `reconnect_interval_seconds`: reconnect delay after disconnect
- `max_frame_size_mb`: maximum accepted frame size

## 3. Confirm the NapCat service

In NapCat WebUI, make sure the OneBot v11 forward WebSocket service is enabled and matches AstrBot's configuration.

Common examples:

- local host: `ws://127.0.0.1:3001`
- Docker Compose: `ws://napcat:3001`
- same Pod: `ws://localhost:3001`

## 4. Verify

After AstrBot starts, you should see logs like:

```text
[NapCat] Connecting forward WebSocket to ws://127.0.0.1:3001
[NapCat] Forward WebSocket connected to ws://127.0.0.1:3001
[NapCat] Forward WebSocket adapter ready: ...
```

Then send a QQ message and confirm AstrBot receives and replies to it.

## 5. Common Issues

- AstrBot starts but no inbound messages arrive
  - make sure NapCat forward WebSocket is actually enabled
  - verify `ws_url`
  - verify the token on both sides
- startup check fails
  - make sure NapCat is logged in and serving WebSocket
  - make sure you did not enter an HTTP URL by mistake
  - if you use `wss://`, verify the certificate and `verify_ssl`
- Docker networking fails
  - prefer container-local addresses such as `ws://napcat:3001` or `ws://localhost:3001`
