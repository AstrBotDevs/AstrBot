# 自行部署文转图服务

AstrBot 使用 [AstrBotDevs/astrbot-t2i-service](https://github.com/AstrBotDevs/astrbot-t2i-service) 项目作为默认的文本转图像服务。默认使用的文转图服务接口是

```plain
https://t2i.soulter.top/text2img
https://t2i.rcfortress.site/text2img
```

此接口能够保障大部分时间正常响应。但是由于部署在国外的（纽约）服务器，因此响应速度可能会比较慢。

> [!TIP]
> 欢迎通过 [爱发电](https://afdian.com/a/astrbot_team) 支持我们，以帮助我们支付服务器费用。

您可以选择自行部署文转图服务，以提升响应速度。

```bash
docker run -itd -p 8999:8999 soulter/astrbot-t2i-service:latest
```

部署完成后，前往 AstrBot 仪表盘 -> 设置 -> 外观。在“文本转图像”中，将 `文本转图像策略` 设为 `remote`；随后会显示 `文本转图像服务 API 地址`，将其修改为你部署好的 URL。

> 如果你是使用本文档的 Docker 教程部署的 AstrBot，URL 应为 `http://文转图服务容器名:8999`。

> 如果部署在与 AstrBot 相同的机器上，URL 应为 `http://localhost:8999`。
