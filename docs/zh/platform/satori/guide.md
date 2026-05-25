# 接入 Satori 协议

## Satori 协议简介

> 摘录自：https://satori.chat/zh-CN/introduction.html

Satori 是一个通用的聊天协议。Satori 协议希望能够抹平不同聊天平台之间的差异，让开发者以更低的成本开发出跨平台、可扩展、高性能的聊天应用。

Satori 的名称来源于游戏东方 Project 中的角色 [古明地觉 (Komeiji Satori)](https://zh.touhouwiki.net/wiki/%E5%8F%A4%E6%98%8E%E5%9C%B0%E8%A7%89)。古明地觉能够以心灵感应的方式与各种动物交流，取这个名字是希望 Satori 能够成为各个聊天平台之间的桥梁。

Satori 的开发团队长期从事聊天机器人开发，熟悉各种聊天平台的通信方式。经过长达 4 年的发展，Satori 有了健全的设计和完善的实现。目前，Satori 官方提供了超过 15 个聊天平台的适配器，完全覆盖了世界上主流的聊天平台，如 QQ、Discord、企业微信、KOOK 等等。

## 1. 配置协议实现端

请参阅对应的协议实现端项目的部署文档。

## 2. 配置 Satori 协议

1. 进入 AstrBot 的 WebUI
2. 点击左边栏 `机器人`
3. 然后在右边的界面中，点击 `+ 创建机器人`
4. 选择 `Satori`

弹出的配置项填写：

- 机器人名称 (id): `satori` (随意)
- 启用 (enable): 勾选
- Satori API 终结点 (satori_api_base_url)：`http://localhost:5600/v1`（端口和上面配置的协议端端口一致）
- Satori WebSocket 终结点 (satori_endpoint)：`ws://localhost:5600/v1/events`（端口和上面配置的协议端端口一致）
- Satori 令牌 (satori_token)：根据协议端配置情况选择填写

点击 `保存`。
