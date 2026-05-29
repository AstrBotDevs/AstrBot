# WebUI

The AstrBot admin panel features plugin management, log viewing, visual configuration, statistics viewing, and more.

![image](https://files.astrbot.app/docs/source/images/webui/image-4.png)

## Accessing the Admin Panel

After starting AstrBot, you can access the admin panel by visiting `http://localhost:6185` in your browser.

> [!TIP]
> - If you're deploying AstrBot on a cloud server, replace `localhost` with your server's IP address.

## Login

For first-time login, AstrBot generates a random initial password and prints it in startup logs. Please read the startup log line containing the WebUI credential and use that password to log in (username is usually `astrbot`).

## ChatUI

AstrBot includes a built-in ChatUI for talking to configured models directly in your browser.

ChatUI supports these common workflows:

- Create, rename, and delete conversations, and switch previous conversations from the sidebar.
- Select the config profile, model provider, and model on the chat page; if Provider session separation is enabled, you can also choose a model for the current session only.
- Send text, images, files, and voice input; uploaded attachments show previews and use file signature checks to help identify file types.
- View model thinking, tool-call status, knowledge-base or web-search references, and per-message token and latency statistics.
- Copy or regenerate existing replies, including regenerating with another model.
- Edit a user message and continue generation from that point, or start a thread from a specific excerpt.
- Switch between streaming/normal response modes and SSE/WebSocket transport modes.

> [!NOTE]
> To keep message delivery ordered, keep only one ChatUI page open for the same browser session. If you open chat in multiple tabs, the system may ask you to reconnect.

## Visual Configuration

In the admin panel, you can configure AstrBot's plugins through visual configuration. Click `Configuration` in the left sidebar to enter the configuration page.

![image](https://files.astrbot.app/docs/source/images/webui/image-3.png)

After modifying the configuration, you need to click the `Save` button in the bottom right corner to successfully save the configuration.

Use the first circular button in the bottom right corner to switch to `Code Edit Configuration`. In `Code Edit Configuration`, you can directly edit the configuration file.

After editing, first click `Apply This Configuration`, which will apply the configuration to the visual configuration, then click the `Save` button in the bottom right corner to save the configuration. If you don't click `Apply This Configuration`, your modifications won't take effect.

![alt text](https://files.astrbot.app/docs/source/images/webui/image-5.png)

## Plugins

In the admin panel, you can view installed plugins and install new plugins through the `Plugins` section in the left sidebar.

Click the Plugin Market tab to browse plugins officially listed by AstrBot.

![image](https://files.astrbot.app/docs/source/images/webui/image-1.png)

You can also click the + button in the bottom right corner to manually install plugins via URL or file upload.

> Due to the plugin update mechanism, the AstrBot Team cannot fully guarantee the security of plugins in the plugin market. Please carefully verify them. The AstrBot Team is not responsible for any losses caused by plugins.

### Handling Plugin Load Failures

If a plugin fails to load, the admin panel will display the error message and provide a **"Try one-click reload fix"** button. This allows you to quickly reload the plugin after fixing the environment (e.g., installing missing dependencies) or modifying the code, without having to restart the entire application.

## Command Management

Use the `Command Management` menu on the left to centrally manage all registered commands; system plugins are hidden by default.

Filter by plugin, type (command / command group / subcommand), permission, and status, and combine with the search box for quick lookup. Command group rows can expand to show subcommands, badges display the subcommand count, and subcommand rows are indented to indicate hierarchy.

You can enable/disable and rename each command.

## Trace

In the `Trace` page of the admin panel, you can view the real-time execution trace of AstrBot. This is useful for debugging model call paths, tool invocation processes, etc.

You can enable or disable trace recording using the switch at the top of the page.

> [!NOTE]
> Currently only recording partial model call paths from AstrBot main Agent. More coverage will be added.

## Updating the Admin Panel

When AstrBot starts, it automatically checks if the admin panel needs updating. If it does, the first log entry (in yellow) will prompt you.

Use the `/dashboard_update` command to manually update the admin panel (admin command).

Admin panel files are located in the data/dist directory. If you need to manually replace them, download `dist.zip` from https://github.com/AstrBotDevs/AstrBot/releases/ and extract it to the data directory.

## Customizing WebUI Port

Modify the `port` in the `dashboard` configuration in the data/cmd_config.json file.

## Forgot Password

Modify the `password` in the `dashboard` configuration in the data/cmd_config.json file and delete the entire password key-value pair.
