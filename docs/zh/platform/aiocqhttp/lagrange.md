# 接入 Lagrange

> [!TIP]
>
> - 请合理控制使用频率。过于频繁地发送消息可能会被判定为异常行为，增加触发风控机制的风险。
> - 本项目严禁用于任何违反法律法规的用途。若您意图将 AstrBot 应用于非法产业或活动，我们**明确反对并拒绝**您使用本项目。
> - 最新的部署方式请以 [Lagrange Doc](https://lagrangedev.github.io/Lagrange.Doc/Lagrange.OneBot/Config/#%E4%B8%8B%E8%BD%BD%E5%AE%89%E8%A3%85) 为准。

## 下载

从 [GitHub Release](https://github.com/LagrangeDev/Lagrange.Core/releases) 下载最新版的 `Lagrange.OneBot`。

对于 Windows 设备，请下载 `Lagrange.OneBot_win-x64_xxxx` 压缩包。

对于 X86 的 Linux 用户，下载 `Lagrange.OneBot_linux-x64_xxx` 压缩包。

对于 Arm 的 Linux 用户，下载 `Lagrange.OneBot_linux-arm64_xxx` 压缩包。

对于 M 芯片 Mac 用户，下载 `Lagrange.OneBot_osx-arm64_xxx` 压缩包。

对于 Intel 芯片 Mac 用户，下载 `Lagrange.OneBot_osx-x64_xxx` 压缩包。

## 部署

请参阅 [Lagrange Doc](https://lagrangedev.github.io/Lagrange.Doc/Lagrange.OneBot/Config/#%E8%BF%90%E8%A1%8C)。

运行完成后，请修改 [配置文件](https://lagrangedev.github.io/Lagrange.Doc/Lagrange.OneBot/Config/#%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6)，

在 `Implementations` 字段下添加：

```json
{
    "Type": "ReverseWebSocket",
    "Host": "127.0.0.1",
    "Port": 6199,
    "Suffix": "/ws",
    "ReconnectInterval": 5000,
    "HeartBeatInterval": 5000,
    "AccessToken": ""
}
```

一定要保证 `Suffix` 为 `/ws`。

## 连接到 AstrBot

### 配置 aiocqhttp

1. 进入 AstrBot 的管理面板
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `aiocqhttp(OneBotv11)`

弹出的配置项填写：

配置项填写：

- ID(id)：随意填写，用于区分不同的消息平台实例。
- 启用(enable): 勾选。
- 反向 WebSocket 主机地址：请填写你的机器的 IP 地址。一般情况下请直接填写 `0.0.0.0`
- 反向 WebSocket 端口：填写一个端口，例如 `6199`。
