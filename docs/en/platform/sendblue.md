# Connecting Sendblue (iMessage and SMS)

Sendblue provides a hosted phone line for direct text conversations. AstrBot receives
messages through its unified webhook and replies through Sendblue's API. Groups and
media uploads are not supported by this adapter. An LLM provider must also be configured
in AstrBot; messaging credentials do not provide model access.

## Create or connect an account

For a new free agent account, install Node.js and run:

```sh
npx -y @sendblue/cli@0.10.0 setup --phone +YOUR_PERSONAL_PHONE
```

Send the displayed verification text from that phone, then run
`npx -y @sendblue/cli@0.10.0 setup --check`. Exit code 3 means verification is pending.
After verification, `~/.sendblue/credentials.json` contains `apiKey`, `apiSecret`, and
`assignedNumber`. Your personal phone is the recipient; the assigned number is the
sending line. Existing accounts can use API credentials and a registered line.

## Configure the adapter

Start AstrBot normally (`uv sync --group dev`, then `uv run main.py` for a source
installation). In the admin panel, open **Platforms**, add an adapter and select
**Sendblue**. Fill in:

| Field | Value |
| --- | --- |
| ID | A unique ID, such as `sendblue` |
| Enable | Enabled |
| Sendblue API key ID | `apiKey` from your credentials |
| Sendblue API secret | `apiSecret` from your credentials |
| Sendblue webhook signing secret | A random value, e.g. generated with `openssl rand -hex 32` |
| Assigned Sendblue line | `assignedNumber`, in E.164 format |
| Allowed sender numbers | Your personal E.164 number, e.g. `+15555550101` |

Keep the same signing secret when registering the webhook. Empty sender lists fail
startup. `*` explicitly allows any sender. AstrBot's normal permission and whitelist
rules still apply. Save, then copy the adapter's webhook URL:
`https://YOUR_HOST/api/platform/webhook/GENERATED_UUID`.

Route that endpoint through a public HTTPS reverse proxy or tunnel to AstrBot's
usual dashboard listener (port 6185 by default). Sendblue must be able to reach it.
Keep API credentials and signing secrets out of logs, chat messages and Git.

## Register the receive webhook

Set `SENDBLUE_API_KEY`, `SENDBLUE_API_SECRET`, `SENDBLUE_FROM_NUMBER`,
`SENDBLUE_SIGNING_SECRET`, and `SENDBLUE_WEBHOOK_URL` in a local shell using the same
values as the adapter. Append a receive webhook with `curl` and `jq`:

```sh
jq -n --arg url "$SENDBLUE_WEBHOOK_URL" --arg secret "$SENDBLUE_SIGNING_SECRET" \
  --arg line "$SENDBLUE_FROM_NUMBER" \
  '{webhooks:{receive:[{url:$url,secret:$secret,sendblue_numbers:[$line]}]}}' |
curl --fail-with-body https://api.sendblue.com/api/account/webhooks \
  -H "sb-api-key-id: $SENDBLUE_API_KEY" \
  -H "sb-api-secret-key: $SENDBLUE_API_SECRET" \
  -H 'Content-Type: application/json' --data-binary @-
```

Register once; inspect existing webhooks before repeating. POST appends to existing
account webhooks. On free accounts, other recipients must complete contact verification:
run `npx -y @sendblue/cli@0.10.0 add-contact +RECIPIENT` and have that person text the
assigned line. AstrBot's allowlist does not replace provider verification.

## Verify a conversation

1. From an allowed, verified phone, text the assigned line: “Remember cobalt.”
2. Confirm the reply arrives on the phone, then ask “What word did I ask you to remember?”
3. Check the reply and AstrBot's conversation history.
4. Confirm an unlisted sender does not start an agent turn; an incorrect
   `sb-signing-secret` must return HTTP 401.

A `QUEUED` API response confirms acceptance, not handset delivery. Check Sendblue's
message status and the actual phone. For missing replies, check public HTTPS routing,
the signing secret, the assigned line, sender permissions, model configuration and
free-plan contact verification. Disable text-to-image/TTS reply transformations for
this text-only adapter.

## Limits and recovery

- Only incoming direct messages addressed to the configured line are admitted. Echoes,
  status callbacks and groups are ignored. Attachment URLs are never downloaded;
  the agent receives an unsupported-media notice. Outgoing non-text components fail
  explicitly rather than silently disappearing.
- Bodies are limited to 64 KiB. Admission stops when the shared event queue contains
  128 messages (HTTP 503). HTTP 200 means enqueued in memory, not durably stored.
- The most recent 4096 accepted handles are deduplicated per adapter process. Restart
  or eviction clears this cache; it does not provide exactly-once delivery.
- Replies split into 2000-character chunks. API calls have a 30-second timeout and
  never automatically retry. If a later chunk fails, earlier chunks may already be
  accepted. Check provider status before manually resending.
- To disconnect, disable the adapter and remove only its Sendblue receive webhook.

Provider reference: [credentials](https://docs.sendblue.com/getting-started/credentials),
[webhooks](https://docs.sendblue.com/api/resources/webhooks),
[sending messages](https://docs.sendblue.com/api/resources/messages/methods/send).
