# 接入 server-satori (基于 Koishi)

> [!TIP]
> server-satori 是 Koishi 平台的一个插件，可以将 Koishi 作为 Satori 协议的服务端，让 AstrBot 通过 Satori 协议接入 koishi 响应消息。

## 准备工作

确保你已经有一个运行中的 Koishi 实例。

如果没有，请先参考 [Koishi 官方文档](https://koishi.chat/zh-CN/manual/starter/windows.html) 完成安装和基础配置。

> 安装过程中遇到任何问题，欢迎前往 [Koishi 社区](https://koishi.chat/zh-CN/about/contact.html) 社区讨论。

## 在 Koishi 中启用 server-satori 插件

1. 打开 Koishi 管理界面
2. 进入`插件配置` 页面
3. 启用该插件（通常不需要额外配置，使用默认设置即可）

安装并启用插件后，server-satori 会自动在 Koishi 的 `/satori` 路径下提供 Satori 协议服务。

![image](https://files.astrbot.app/docs/source/images/satori/2025-09-07_17-14-55.png)

## 在 AstrBot 中配置 Satori 适配器

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `satori`

弹出的配置项填写：

- 机器人名称 (id): `server-satori`
- 启用 (enable): 勾选
- Satori API 终结点 (satori_api_base_url)：`http://localhost:5140/satori/v1`
- Satori WebSocket 终结点 (satori_endpoint)：`ws://localhost:5140/satori/v1/events`
- Satori Token (satori_token)：通常留空（除非在 Koishi 中特别配置了 Token）

> [!NOTE]
>
> - Koishi 默认运行在 5140 端口
> - server-satori 插件默认在 `/satori` 路径下提供服务
> - 因此完整的 URL 路径为 `http://localhost:5140/satori/v1`
>
> 如果你的 koishi 运行在其他端口或路由下，**请根据实际情况修改对应的配置！**

![image](https://files.astrbot.app/docs/source/images/satori/2025-10-10_16-16-25.png)

点击右下角 `保存` 完成配置。

## 🎉 大功告成

此时，你的 AstrBot 应该已经通过 Satori 协议成功连接到了 Koishi 的 server-satori 插件。

在 Koishi 的沙盒里 向机器人发送 AstrBot的指令（例如：`/help`）进行测试，

如果成功回复，则配置成功。

![image](https://files.astrbot.app/docs/source/images/satori/2025-09-07_17-19-04.png)

## 常见问题

如果遇到连接问题，请检查：

1. Koishi 是否正常运行
2. server-satori 插件是否已正确安装并启用
3. 端口和路径配置是否正确
4. 防火墙是否阻止了相关端口的访问
