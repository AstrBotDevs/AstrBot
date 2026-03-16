# Connect to Coze

AstrBot v4.2.1 and later versions support connecting to [Coze](https://www.coze.cn/) Agent service.

## Preparation: Get API Key

First, register and log in to your [Coze](https://www.coze.cn/) account, then go to the [API Key Management Page](https://www.coze.cn/open/oauth/pats) to create a new API Key.

You can follow the steps in the image to reach the API Key management page, or click the link above to go directly.

![Create API Key](https://files.astrbot.app/docs/source/images/coze/image_1.png)

Then, click "Create", fill in your API Key name on the following page, select an expiration time (permanent tokens are not recommended), click "Select All" under "Permissions", select a workspace, and then click "Confirm".

![Create Token](https://files.astrbot.app/docs/source/images/coze/image_2.png)

After that, we will get a new API Key. Please copy and save it, as it will be needed later.

![New API Key](https://files.astrbot.app/docs/source/images/coze/image_3.png)

## Preparation: Configure the Agent

Go to the [Project Development](https://www.coze.cn/space/develop) page, click "+Project" in the upper right corner to create a new project, and select to create an agent.

![Create Project](https://files.astrbot.app/docs/source/images/coze/image_4.png)

![Create Project](https://files.astrbot.app/docs/source/images/coze/image_5.png)

**Note**: After creating the agent, you must first click the **Publish** button in the upper right corner to publish the agent. In the "Select Publishing Platform" section, check all API options, then click "Publish".

> If you don't publish or don't check the API options during publishing, you won't be able to call the agent via API.

![Publish Agent](https://files.astrbot.app/docs/source/images/coze/image_6.png)

After clicking publish, the agent creation is complete. You can see the publish history on the left side of the publish button on the agent development page to confirm the agent has been published successfully.

Next, note the URL on the agent development page:

![Agent Development](https://files.astrbot.app/docs/source/images/coze/image_7.png)

For example, if the URL in the example is: "https://www.coze.cn/space/7553214941005004863/bot/7553248674860826660"

Then the `bot_id` is the string of numbers after `bot/` in the URL: `7553248674860826660`

We need to record the `bot_id` for later use.

## Configure Coze in AstrBot

After completing all the preparation work, we can now configure Coze in AstrBot.

Go to AstrBot Admin Panel -> Service Provider -> Add Service Provider -> Coze to enter the configuration page.

![Coze Provider](https://files.astrbot.app/docs/source/images/coze/image_8.png)

Fill in the API Key and bot_id you just created, then click Save.

> Other configuration notes:
>
> - API Base URL: Generally no modification is needed. If you are using the international version of Coze, change this to: "https://api.coze.com"
> - Let Coze manage conversation history: As described.

## Select Agent Runner

Go to the Configuration page in the left sidebar, click "Agent Execution Method", select "Coze", then select the ID of the Coze Agent Runner you just created in the new configuration options that appear below, and click "Save" in the bottom right corner to complete the configuration.

