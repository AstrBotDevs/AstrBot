# 在 宝塔面板 部署 AstrBot

[宝塔面板](https://www.bt.cn/new/index.html)是一个安全高效、生产可用的 Linux/Windows 服务器运维面板。

AstrBot 已经上架至宝塔的 Docker 应用商店，支持一键安装。

## 安装宝塔面板

如果您还没有安装宝塔面板，请参考 [安装宝塔产品](https://www.bt.cn/new/download.html) 一键安装。

## 设置加速 URL（国内服务器用户）

进入宝塔面板页面后，点击左侧的 `Docker`，点击设置，修改`加速 URL`。

![alt text](https://files.astrbot.app/docs/source/images/btpanel/image-1.png)

## 安装 AstrBot

进入 Docker 的应用商店，搜索 `AstrBot`，如下图所示。

![image](https://files.astrbot.app/docs/source/images/btpanel/image.png)

点击安装，等待安装成功。

安装成功后，点击左侧 `安全`，放行对应的 AstrBot 端口（默认是 6185 端口）。

如果您正在使用 AWS、阿里云、腾讯云等厂商的云服务器，请确保其安全组也放行了对应的端口。

## 访问 AstrBot

访问 `http://IP:6185` 即可访问 AstrBot 的管理面板。

> [!TIP]
> 默认情况下，上述方法只会放行一个 6185 端口。如果需要部署消息平台，需要额外放行对应的端口。点击上栏 `容器`，找到 AstrBot 容器，点击 `管理`，点击 `编辑容器`，添加对应的端口即可。
>
> ![image](https://files.astrbot.app/docs/source/images/btpanel/image-2.png)
>
> 具体的消息平台对应端口可以参考下表：
>
>| 端口    | 描述 | 类型
>| -------- | ------- | ------- |
>| 6185 |  AstrBot WebUI `默认` 端口  | 需要 |
>| 6195 | 企业微信 `默认` 端口    | 可选 |
>| 6199 | QQ 个人号(aiocqhttp) `默认` 端口    | 可选 |
>| 6196    | QQ 官方接口(Webhook) `默认` 端口   | 可选 |
>
> 没有列举的平台表示不需要额外放行端口。

