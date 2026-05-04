# 接入 Discord

## 创建 AstrBot Discord 平台适配器

进入机器人，点击新增适配器，找到 Discord 并点击进入 Discord 配置页。
> 旧版本`机器人`为`消息平台`
![点击创建机器人，选择discord类型](https://files.astrbot.app/docs/source/images/discord/image.png)

![选项从上到下依次是 1.机器人名称 2. 启用 3. Bot token 4. Discord 代理地址 5. 是否自动将插件指令注册为 Discord 斜杠指令 6. discord_guild_id_for_debug 7.Discord 活动名称](https://files.astrbot.app/docs/source/images/discord/image-3.png)
> 本次教程只用管1,2,3,5项

- 机器人名称：自定义，方便区分不同适配器
- 启用：勾选后启用该适配器
- Bot Token：在 Discord 创建 App 后获取的 Token（见下文）
- Discord 代理地址：如果你需要使用代理访问 Discord，可以在这里填写代理地址（可选）
- 是否自动将插件指令注册为 Discord 斜杠指令：勾选后，AstrBot 会自动将已安装插件中的指令注册为 Discord 斜杠指令，方便用户使用。

## 在 Discord 创建 App

1. 前往 [Discord](https://discord.com/developers/applications)，点击右上角蓝色按钮，输入应用名字，创建应用。

![创建bot（输入名字）](https://files.astrbot.app/docs/source/images/discord/image-1.png)

2. 点击左边栏的 Bot，点击 Reset Token 按钮，创建好 Token 后，点击 Copy 按钮，将 Token 填入配置中的 Discord Bot Token 处。

![token选项](https://files.astrbot.app/docs/source/images/discord/image-4.png)
4. 下滑找到这三个选项全开启

![Presence Intent,Server Members Intent,Message Content Intent截图](https://files.astrbot.app/docs/source/images/discord/image-2.png)

- Presence Intent：允许机器人获取用户在线状态
- Server Members Intent：允许机器人获取服务器成员信息
- Message Content Intent：允许机器人读取消息内容

5. 点击左边栏的 OAuth2，在 OAuth2 URL Generator 中选中 `Bot`
也就是这样
![OAuth2 URL Generator](https://files.astrbot.app/docs/source/images/discord/image-6.png)
然后在下方出现的 Bot Permissions 处选择允许的权限。一般来说，建议添加如下权限：
    - Send Messages
    - Create Public Threads
    - Create Private Threads
    - Send TTS Messages
    - Manage Messages
    - Manage Threads
    - Embed Links
    - Attach Files
    - Read Message History
    - Add Reactions
如果你觉得麻烦也可以直接使用administrator权限，但仍然建议在使用环境中使用上文的配置权限（或您自己需要的权限）
> 记住，权限越高，风险越大。

6. 复制下方出现的 Generated URL。打开这个 URL，将 Bot 添加到所需要的服务器。
![Generated URL位置](https://files.astrbot.app/docs/source/images/discord/image-5.png)

7. 进入 Discord 服务器，你的机器人应该已经提示在线了
![机器人在线](https://files.astrbot.app/docs/source/images/discord/image-7.png)
@ 刚刚创建的机器人（也可以不 @），输入 `/help`，如果成功返回，则测试成功。

## 预回应表情

Discord 支持预回应表情功能。启用后，机器人在处理消息时会先添加一个表情反应，让用户知道机器人正在处理消息。

在管理面板的「配置」页面中，找到 `平台特定配置 -> Discord -> 预回应表情`：

- **启用预回应表情**：开启后，机器人收到消息时会自动添加表情反应
- **表情列表**：填写 Unicode 表情符号，例如：👍、🤔、⏳。可填写多个，机器人会随机选择一个使用

# 故障排除

- 如果卡在最后的步骤，机器人不在线请确定自己的服务器可以直接连接discord

如果有疑问，请[提交 Issue](https://github.com/AstrBotDevs/AstrBot/issues)。
