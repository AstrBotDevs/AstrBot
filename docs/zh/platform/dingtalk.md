# 接入钉钉 DingTalk

## 支持的基本消息类型

> 版本 v4.15.0。

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注 |
| --- | --- | --- | --- |
| 文本 | 是 | 是 | |
| 图片 | 是 | 是 | |
| 语音 | 否 | 是 | |
| 视频 | 否 | 是 | |
| 文件 | 否 | 是 | |

主动消息推送：支持。

## 创建和配置应用

钉钉支持两种创建方式：在 AstrBot 中扫码一键创建，或在钉钉开放平台手动创建应用。

### 方式一：扫码一键创建

需要 AstrBot 版本 >= v4.25.0。

打开 AstrBot 管理面板 -> `机器人` -> `+ 创建机器人`，选择 `钉钉(DingTalk)`。

在 `选择创建方式` 中选择 `扫码一键创建`，使用手机钉钉扫描页面中的二维码，并在钉钉页面中创建或绑定机器人。创建成功后，AstrBot 会自动写入 `ClientID` 和 `ClientSecret`，此时点击 `保存` 即可。

扫码创建完成后，仍建议检查后文的事件订阅、版本发布和拉入群组步骤。

### 方式二：手动创建

前往 [钉钉开放平台](https://open-dev.dingtalk.com/fe/app)，点击创建应用：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-4.png)

创建好之后，添加应用能力，选择机器人：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-5.png)

点击机器人配置，填写填写机器人相关信息：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-7.png)

确认无误后，点击下面的发布按钮。

点击凭证与基础信息，将 `ClientID` 和 `ClientSecret` 复制下来。

## 开始连接

打开 AstrBot 管理面板 -> `机器人` -> `+ 创建机器人`，创建一个钉钉适配器。

如果使用扫码一键创建，选择 `扫码一键创建` 并完成扫码；如果使用自己创建的钉钉应用，选择 `手动创建`，将刚刚复制的 `ClientID` 和 `ClientSecret` 填入。点击保存后，AstrBot 将会自动向钉钉开放平台请求。

回到钉钉开放平台，点击事件订阅，选择 `Stream 模式推送`，点击保存，如果没有意外情况，将会看到 连接接入成功 字样。

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-8.png)

点击保存即可。

## 发布版本

点击边栏的 版本管理与发布，创建一个新版本。

填写应用版本号、版本描述、应用可见范围（选择全部员工或者按照您的需求），点击保存，确认发布。

![alt text](https://files.astrbot.app/docs/source/images/dingtalk/image-11.png)

找到一个钉钉群聊，点击右上角的设置：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-12.png)

下拉找到添加机器人，然后找到刚刚创建的机器人，点击添加即可：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-9.png)

## 🎉 大功告成

在群聊中 @ 机器人后附带 `/help` 指令，如果机器人回复了，那么说明接入成功。
