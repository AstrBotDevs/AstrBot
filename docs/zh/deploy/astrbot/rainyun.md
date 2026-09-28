# 通过 雨云 一键部署

雨云成立于 2018 年，是具有自主知识产权的国产云计算服务提供商，具有可靠的营业资质和实体办公场所。

AstrBot 已经上架至雨云的预装软件列表，支持**一键安装** AstrBot 并提供高性能的云计算资源，保证 `AstrBot` 24 小时在线。

目前有两种部署方式：云服务器部署和云应用部署。

## 云应用

点击下面的按钮进入 AstrBot 云应用安装页：

[![Deploy on RainYun](https://rainyun-apps.cn-nb1.rains3.com/materials/deploy-on-rainyun-en.svg)](https://app.rainyun.com/apps/rca/store/5994?ref=NjU1ODg0)

### 选择地区和资源配置

在 `应用信息` 中选择要安装的 AstrBot 版本。通常保持页面默认的最新稳定版本即可。

在 `安装到项目` 中选择 `中国香港`（或其他海外的地区优先）。如果账号中还没有云应用项目，安装时会自动在该地区创建一个新项目。

![选择 AstrBot 版本和中国香港地区](https://files.astrbot.app/docs/source/images/rainyun/rainyun-cloud-app-region.png)

接下来调整 CPU 和内存。建议选择 2C2G - 4C8G 的区间，推荐 2C4G。

### 安装应用并手动进入项目

确认地区、资源配置、端口和页面底部的 `预计每月消耗` 后，点击 `安装应用`。

安装会开始消耗雨点或使用页面显示的试用权益。安装前请确认账户余额、试用条件和预计月消耗均符合预期。

> [!IMPORTANT]
> 点击 `安装应用` 并创建成功后，页面**不会自动进入新项目**。此时必须手动点击页面上方的 `我的项目`，再进入刚创建的香港项目。

完整路径如下：

1. 在雨云云应用页面顶部点击 `我的项目`。
2. 在项目选择器中选择新创建的 `默认项目（香港）`。如果您安装时填写了其他项目名，请选择对应的香港项目。
3. 在 `应用` 页面找到 `AstrBot` 卡片。
4. 点击 AstrBot 卡片，进入应用详情页。

![创建成功后手动进入“我的项目”并打开 AstrBot](https://files.astrbot.app/docs/source/images/rainyun/rainyun-cloud-project-cropped.png)

AstrBot 会自动拉取镜像并启动，通常几分钟内即可完成。项目列表和应用详情页的状态刷新可能有约 1 分钟延迟。

### 在日志中获取初始账号

进入应用后，按照下面的完整路径打开日志：

`我的项目` → `默认项目（香港）` → `AstrBot` 应用卡片 → `日志`

等待日志中出现 `AstrBot ... WebUI is ready`，表示 WebUI 已经启动完成。随后查找下面两行：

```text
Initial username: astrbot
Initial password: <随机初始密码>
```

![在 AstrBot 应用日志中查看初始账号和密码](https://files.astrbot.app/docs/source/images/rainyun/rainyun-cloud-log-redacted-cropped.png)

上图已经隐藏真实的随机初始密码。请在您自己的日志中复制完整密码，不要使用截图中的占位内容。

> [!WARNING]
> 不要把运行日志中的初始密码截图分享或提交到公开仓库。完成首次登录和密码修改后，请妥善保管新密码。

### 获取 WebUI 公网地址

按照下面的完整路径打开服务列表：

`我的项目` → `默认项目（香港）` → `AstrBot` 应用卡片 → `服务`

在 `webui` 这一行读取两个值：

- `地址`：WebUI 使用的公网 IP。
- `端口映射`：左侧是容器内端口 `6185`，右侧是雨云分配的外部端口。

![在服务页面查看 WebUI 公网 IP 和端口映射](https://files.astrbot.app/docs/source/images/rainyun/rainyun-cloud-service-address-cropped.png)

以截图为例，`webui` 的端口映射为 `6185 → 48492`，因此需要访问外部端口 `48492`，而不是直接访问内部端口 `6185`。外部端口和公网 IP 由雨云分配，您的实际值可能与截图不同。

`onebot` 是项目内访问的内网服务，默认不提供公网地址。仅使用 AstrBot WebUI 时不需要修改它。

### 打开 AstrBot 管理面板

在浏览器中打开：

```text
http://<webui 行中的地址>:<6185 右侧的外部端口>
```

例如，地址为 `203.0.113.10`、端口映射为 `6185 → 48492` 时，访问地址就是 `http://203.0.113.10:48492`。请替换为您自己的公网 IP 和外部端口。

![通过雨云公网服务打开 AstrBot WebUI 登录页](https://files.astrbot.app/docs/source/images/rainyun/rainyun-cloud-login-cropped.png)

默认情况下 AstrBot 使用 HTTP，因此浏览器地址栏显示 `不安全` 属于正常现象。不要自行把地址开头改成 `https://`；如需 HTTPS，可在雨云的 `网站` 页面添加应用代理并绑定域名和证书。

用户名填写 `astrbot`，密码填写日志中的 `Initial password`。首次登录后，请按照页面提示立即设置新的安全密码。

如果 WebUI 无法打开，请依次检查：

1. 是否已经手动进入 `我的项目`，并打开了正确的香港项目和 AstrBot 应用。
2. 应用详情页右上角的状态是否为 `运行中`。
3. 日志中是否已经出现 `WebUI is ready`，以及是否有内存不足、镜像拉取失败等错误。
4. 复制的是否为 `webui` 行中的公网地址，而不是 `onebot` 的内网地址。
5. 访问地址是否使用 `http://`，并包含 `6185` 右侧的外部端口。

## 云服务器

打开 [雨云官网](https://www.rainyun.com/NjU1ODg0_)。点击右上角的 “进入控制台”，如果没有注册或登录会先进行登录。

点击 “云服务器”，购买云服务器。根据你的喜好和预算，选择一个合适的服务器配置。建议选择中国香港或者海外的服务器，并且至少 2 核 CPU、4GB 内存的服务器，以确保 AstrBot 流畅运行。

在下面的 `系统和软件安装` 一节，选中 `AstrBot`，然后点击 `立即购买`。

如果余额不足，页面会跳转至充值页面。充值完成后，再返回并点击 `立即购买`。如果提示 “您购买的区域默认为 NAT 模式（端口访问）”，可以直接购买，后续按照本文配置端口映射即可；也可以根据需要在购买页附加独立公网 IP。

![AstrBot - 系统和软件安装](https://files.astrbot.app/docs/source/images/rainyun/image.png)

接下来，雨云会自动安装系统和 `AstrBot`。点击正在创建的服务器，进入 `管理云服务器` 页面，下拉会看到 `预装软件信息`：

![雨云服务器信息和预装软件信息](https://files.astrbot.app/docs/source/images/rainyun/rainyun-server-preinstall.png)

创建过程大致持续 10 分钟。等待创建完成之后，会看到下面的结果：

![AstrBot 安装完成信息](https://files.astrbot.app/docs/source/images/rainyun/rainyun-server-installed-redacted.png)

请保存安装结果中显示的用户名和随机初始密码。上图已经对密码进行了脱敏，您自己的页面会显示完整密码。

> [!WARNING]
> 初始密码仅用于首次登录，请勿截图分享或提交到公开仓库。登录 AstrBot 后，请立即按照页面提示修改密码。

### 配置防火墙

进入云服务器详情页的 `防火墙` 页面，点击 `新建防火墙规则`，为 AstrBot WebUI 添加放行规则：

- 是否启用：开启
- 动作：`允许`
- 源地址：留空表示允许所有来源；如果只允许固定设备访问，也可以填写该设备的公网 IP 或 CIDR
- 业务端口：填写 `6185`
- 源端口：通常留空
- 协议：选择 `TCP`；如果页面只有 `全部` 选项，也可以保持 `全部`
- 描述：例如填写 `AstrBot WebUI`

确认无误后点击 `确定`。

![为 AstrBot WebUI 放行 6185 端口](https://files.astrbot.app/docs/source/images/rainyun/rainyun-server-firewall-rule.png)

> [!TIP]
> 如果后续需要从公网接入 OneBot，再按实际需要放行对应端口。不要为了省事开放不使用的端口。

### 配置 NAT 端口映射

如果您**没有选择**购买带有公网 IP 地址的服务器（`公网 IP 列表` 为空），请在 `NAT 端口映射管理` 中点击 `端口设置`，然后新建规则：

- 协议：保持系统设置的默认值
- 内网端口：`6185`
- 外网端口：保持系统分配的默认值，并记住这个端口
- 标签：可选，例如填写 `AstrBot WebUI`

填写完成后，点击 `创建映射规则`。

![创建 AstrBot 的 NAT 端口映射规则](https://files.astrbot.app/docs/source/images/rainyun/rainyun-server-nat-rule.png)

创建完成后，点击 `映射公网地址` 右侧的复制按钮并妥善保存。若该地址无法访问，可以点击 `备用地址`，使用备用地址访问。

如果服务器带有独立公网 IP，则不需要配置 NAT 端口映射，可以直接进行下一步。

### 打开 AstrBot 管理面板

根据服务器的网络类型，在浏览器中打开对应地址：

- 带独立公网 IP：`http://<公网 IP>:6185`
- NAT 服务器：`http://<映射公网地址>`。如果复制结果不包含端口，请在地址末尾补上前面记录的外网端口，例如 `http://<IP>:<外网端口>`

默认情况下 AstrBot 使用 HTTP，请勿将地址开头改成 `https://`。

登录时，使用 `预装软件信息` 中显示的用户名和随机初始密码。用户名为 `astrbot`。首次登录后，页面会引导您设置一个新的安全密码。

如果管理面板无法打开，请依次检查：

1. 服务器状态是否为 `运行中`，预装软件状态是否为 `已成功安装`。
2. 防火墙是否允许访问 `6185` 端口。
3. NAT 服务器的映射内网端口是否为 `6185`，访问地址中是否包含正确的外网端口。
4. 是否使用了 `http://`；映射公网地址不可用时，可以改用雨云提供的 `备用地址`。

如果有疑问，请：

1. 点击雨云官网右下角 `咨询` 提交工单
2. 点击雨云官网上方 `交流社区` 添加雨云 QQ 群。
