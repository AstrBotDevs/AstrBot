# 接入 LLTwoBot (Satori)

> [!TIP]
> LLTwoBot 是一个基于 QQNT 的 Onebot v11、Satori 多协议实现端，可以让你在 QQ 平台使用 Satori 协议与 AstrBot 进行通信。

> [!TIP]
>
> - 请合理控制使用频率。过于频繁地发送消息可能会被判定为异常行为，增加触发风控机制的风险。
> - 本项目严禁用于任何违反法律法规的用途。若您意图将 AstrBot 应用于非法产业或活动，我们**明确反对并拒绝**您使用本项目。

## 准备工作

请先参考 LLTwoBot 官方文档完成基础配置：
[LLTwoBot 文档](https://llonebot.com/guide/getting-started)

完成文档中的步骤，确保你已经：

1. 下载并安装了 LLTwoBot
2. 成功登录了 QQ 账号

## 配置 LLTwoBot 的 Satori 服务

在成功登录 QQ 后，先打开 LLTwoBot 的 WebUI 配置界面。
> WebUI 默认地址为：<http://localhost:3080/>

---

在WebUI的配置界面侧边，选择【Satori】选项卡，进行如下配置：

1. 确认【启用 Satori 协议】配置项已开启
2. 端口默认为 5600（如需修改请记住新端口）
3. 如有必要，可填写【Satori Token】
4. 点击右下角的【保存配置】

![image](https://files.astrbot.app/docs/source/images/satori/2025-10-10_15-52-32.png)

## 在 AstrBot 中配置 Satori 适配器

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `satori`

弹出的配置项填写：

- 机器人名称 (id): `LLTwoBot`
- 启用 (enable): 勾选
- Satori API 终结点 (satori_api_base_url)：`http://localhost:5600/v1`
- Satori WebSocket 终结点 (satori_endpoint)：`ws://localhost:5600/v1/events`
- Satori 令牌 (satori_token)：根据 LLTwoBot 配置填写（如有设置）

> [!NOTE]
>
> - LLTwoBot 的 satori协议 默认在 `5600` 端口提供服务
> - 因此完整的 URL 路径为 `http://localhost:5600/v1`
>
> 如果你的 satori协议运行在其他端口，请根据实际情况修改对应的配置！

![image](https://files.astrbot.app/docs/source/images/satori/2025-10-10_16-10-54.png)

点击右下角 `保存` 完成配置。

## 🎉 大功告成

此时，你的 AstrBot 应该已经通过 Satori 协议成功连接到 LLTwoBot。

在 QQ 中发送 `/help` 以检查是否连接成功。

如果成功回复，则配置成功。

## 常见问题

如果遇到连接问题，请检查：

1. LLTwoBot 是否正常运行
2. Satori 服务是否已启用
3. 端口配置是否正确
4. Token 是否匹配（如设置了 Token）
