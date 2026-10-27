# Messaging Platforms

AstrBot supports integration with many mainstream instant messaging platforms, so you can use AstrBot on the IM platform your team already uses.

In WebUI, click **Platforms** in the left sidebar to open the messaging platform integration page.
Then click **Add Adapter** above the bot list, choose the platform you want to connect, and follow the platform-specific guide in the left sidebar of this documentation.

To edit an existing bot, select it in the list, update **Connection settings**, and click **Save changes**. Use **Conversation configuration** to choose its default configuration profile or bind profiles to specific conversations. Connection status appears in the bot list; detailed logs are under **Data & Logs → Logs**.

## Delete a bot and its associated data

Click the delete button in the bot list, then choose which data to remove in the confirmation dialog. Hover over or click the information icon next to an option to see what it removes.

![Choose associated data when deleting a bot](../use/images/platform-delete-en.png)

- **Custom rules, Preferences, Configuration routes, and Future tasks** are selected by default. Preferences include the selected conversation, session variables, external service conversation IDs, adapter delivery mappings, and this bot's members in custom session groups. The groups themselves are kept.
- **AI conversations, Message history, Trace logs, and Usage statistics** are kept by default. Select them individually or use **Select all** in the history section.
- AI conversations contain model context; message history contains platform messages. Removing message history also removes the associated session names, aliases, and sender names. Trace logs refer to the local Trace store. Usage statistics removes this bot’s model-call, token and response-timing records; message totals aggregated by adapter type are kept.

Selected data is permanently deleted. Shared configuration profiles, personas, knowledge bases, model providers, attachments, and plugin-managed data are kept. Only routing rules whose platform part exactly matches this bot's ID are removed; cross-platform wildcard rules are preserved. Selecting future tasks cancels this bot's schedules and deletes their records.

Canceling and reopening the dialog restores the default selections. If deletion fails, some selected data may already have been removed; the bot configuration is retained so you can check the logs and retry.
