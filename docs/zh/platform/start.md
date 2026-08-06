# 接入消息平台

AstrBot 支持接入众多主流即时通讯软件平台，帮助您在自己喜欢的 IM 平台上使用 AstrBot 的强大功能。

在 WebUI 中，点击侧边栏的**机器人**，即可进入消息平台接入界面。点击右上角的**创建机器人**，选择您想要接入的平台，按照本文档左侧提供的接入指南进行操作，即可完成接入。

如果你接入的是 NapCat QQ，请直接选择独立的 `napcat` 平台，并参考 [NapCat](/platform/napcat) 页面；不要再按通用 `OneBot v11` 模板配置。

创建机器人时，内置平台模板会优先显示 QQ 官方机器人、OneBot v11、个人微信、飞书和企业微信等常用接入方式。将鼠标悬停在 QQ 官方机器人、OneBot v11 或个人微信条目上，可以查看连接方式、权限限制和扫码配置提示。插件还可以追加平台模板，因此列表内容和顺序以运行中 WebUI 为准。

## 当前内置适配器

当前代码会按需注册下列内置适配器类型。插件还可以注册额外类型，因此请以运行中 WebUI 的 **机器人 → 创建机器人** 列表为最终依据。

| 接入方式                  | 适配器类型                           | 指南                                            |
| ------------------------- | ------------------------------------ | ----------------------------------------------- |
| QQ 官方机器人             | `qq_official`、`qq_official_webhook` | [QQ 官方机器人](/platform/qqofficial)           |
| OneBot v11 反向 WebSocket | `aiocqhttp`                          | [OneBot v11](/platform/aiocqhttp)               |
| NapCat 正向 WebSocket     | `napcat`                             | [NapCat](/platform/napcat)                      |
| Telegram                  | `telegram`                           | [Telegram](/platform/telegram)                  |
| 企业微信应用              | `wecom`                              | [企业微信](/platform/wecom)                     |
| 企业微信智能机器人        | `wecom_ai_bot`                       | [企业微信智能机器人](/platform/wecom_ai_bot)    |
| 微信公众号                | `weixin_official_account`            | [微信公众号](/platform/weixin-official-account) |
| 个人微信                  | `weixin_oc`                          | [个人微信](/platform/weixin_oc)                 |
| 飞书                      | `lark`                               | [飞书](/platform/lark)                          |
| 钉钉                      | `dingtalk`                           | [钉钉](/platform/dingtalk)                      |
| Slack                     | `slack`                              | [Slack](/platform/slack)                        |
| Discord                   | `discord`                            | [Discord](/platform/discord)                    |
| LINE                      | `line`                               | [LINE](/platform/line)                          |
| Satori                    | `satori`                             | [Satori](/platform/satori/guide)                |
| KOOK                      | `kook`                               | [KOOK](/platform/kook)                          |
| Misskey                   | `misskey`                            | [Misskey](/platform/misskey)                    |
| Mattermost                | `mattermost`                         | [Mattermost](/platform/mattermost)              |
| 内置浏览器聊天            | `webchat`                            | [WebUI 与 ChatUI](/use/webui)                   |

社区页面或插件适配器不属于这份内置注册表。安装前请核对其代码仓库、兼容性声明和权限需求。

> [!TIP]
> 建议在部署前预先安装 `ffmpeg`（并确保支持 `amr`），否则媒体类文件可能无法正常收发。对于微信类平台接入，强烈建议安装。
