# Connecting to Slack

## Create AstrBot Slack Platform Adapter

Navigate to the `Bots` page, click `+ Create Bot`, find Slack and click to enter the Slack configuration page.

![image](https://files.astrbot.app/docs/source/images/slack/image-1.png)

In the configuration dialog that appears, click `Enable`.

## Create an App in Slack

Slack supports two connection methods: `Webhook` and `Socket`. If you don't have a public server and your message volume is relatively small, we recommend using the `socket` method. If you have a public server (or have technical knowledge about setting up tunnels, such as Cloudflare Tunnel), you can choose the `webhook` method. The `socket` method is relatively simpler to deploy.

1. Create a [Slack](https://slack.com/signin) account and a Workspace.
2. Go to [Apps Management](https://api.slack.com/apps), click "Create New App" -> "From Scratch", enter the `App Name` and the workspace to add it to, then click "Create App".
3. (Webhook only) Obtain the `Signing Secret`. In the Basic Information page on the left sidebar, find `Signing Secret` under App Credentials, click Show and copy it to the signing_secret field in the platform adapter configuration.

![image](https://files.astrbot.app/docs/source/images/slack/image.png)

4. In the Basic Information page on the left sidebar, find App-Level Tokens and click "Generate Token and Scopes". Enter any Token Name, click Add Scope, select `connections:write`, then click "Generate". Click Copy and paste the result into the app_token field on the AstrBot configuration page.

![image](https://files.astrbot.app/docs/source/images/slack/image-2.png)

5. In the OAuth & Permissions page on the left sidebar, add the following permissions under Bot Token Scopes:
   - channels:history
   - channels:read
   - channels:write.invites
   - chat:write
   - chat:write.customize
   - chat:write.public
   - files:read
   - files:write
   - groups:history
   - groups:read
   - groups:write
   - im:history
   - im:read
   - im:write
   - reactions:read
   - reactions:write
   - users:read

6. In the OAuth & Permissions page on the left sidebar, click `Install to xxx` under OAuth Token (where xxx is your workspace name). Then copy the generated Bot User OAuth Token to the bot_token field in the platform adapter configuration.

7. (Socket only) In the Socket Mode page on the left sidebar, enable Socket Mode.

![image](https://files.astrbot.app/docs/source/images/slack/image-3.png)

## Start the Platform Adapter

The configuration is now complete. If you're using Socket mode, simply click the Save button in the bottom right corner of the configuration.

If you're using Webhook mode, please keep `Unified Webhook Mode (unified_webhook_mode)` enabled.

> [!TIP]
> Before v4.8.0, there is no `Unified Webhook Mode`. You need to fill in the following configuration items:
> Slack Webhook Host, Slack Webhook Port, and Slack Webhook Path


## Enable Event Subscriptions

After successfully creating the platform adapter, return to the Slack settings. In the Event Subscriptions page on the left sidebar, click Enable Events to enable event reception.

If you're using Webhook mode:

- If `Unified Webhook Mode` is enabled, after clicking save, AstrBot will automatically generate a unique Webhook callback URL for you. You can find it in the logs or on the bot card in the WebUI's Bots page. Enter this URL in the `Request URL` field.

![unified_webhook](https://files.astrbot.app/docs/source/images/use/unified-webhook.png)

- If `Unified Webhook Mode` is not enabled, enter `https://your-domain/astrbot-slack-webhook/callback` in the `Request URL` field.

> [!TIP]
> In Webhook mode, you need to first set up your domain with your DNS provider, then use reverse proxy software to forward requests to port `6185` on the AstrBot server (if Unified Webhook Mode is enabled) or the port specified in your configuration (if Unified Webhook Mode is not enabled). Alternatively, you can use Cloudflare Tunnel. For detailed tutorials, please refer to online resources; this tutorial will not cover these in detail.

After enabling, under Subscribe to bot events below, click Add Bot User Event and add the following events:

1. channel_created
2. channel_deleted
3. channel_left
4. member_joined_channel
5. member_left_channel
6. message.channels
7. message.groups
8. message.im
9. reaction_added
10. reaction_removed
11. team_join

## Test the Connection

Enter the Slack workspace you just added, navigate to the channel where you want to use the bot, then @ mention the app you just created. Click the Add button in the message subsequently sent by Slackbot to add it to the workspace. Then, @ mention the app and type `/help`. If it responds successfully, the test is successful.

If you have any questions, please [submit an Issue](https://github.com/AstrBotDevs/AstrBot/issues).
