# GitHub 镜像

当前 fork **默认不提供** GitHub 镜像列表，Dashboard 也不再接受任意自定义镜像输入。

插件安装、插件更新和 Core 更新只会请求：

- GitHub 官方相关域名；
- Core 版本检查默认使用 `https://api.github.com/repos/Xero-Team/AstrBot/releases`，可用环境变量 `ASTRBOT_RELEASE_API` 覆盖；当前 fork 不发布可供 Dashboard 下载的 Core 包，托管包地址仅在设置 `ASTRBOT_CORE_PACKAGE_BASE_URL` 时启用；
- 插件市场默认先请求上游 GitHub 集合 `AstrBotDevs/AstrBot_Plugins_Collection`，然后是 jsDelivr CDN，最后才是 Soulter 兼容源（`api.soulter.top`、`astrbot-registry.soulter.top`）；这些都是上游服务，不是本 fork 运营的市场。默认市场没有 Soulter MD5 校验，每次打开都会重新拉取；自定义市场才使用对应的 `-md5.json`。JSON 请求会使用配置里的 `http_proxy`，不会读取进程环境变量代理。
- 通过后端校验的公开 HTTPS origin。

如果 API 传入镜像前缀，它必须是：

- 明确的 HTTPS origin；
- 不含用户名/密码；
- 解析结果全部为公网地址；
- 不能重定向到未校验的内部地址。

这不是普通 HTTP 正向代理。功能语义是“URL 前缀镜像”，每一跳都会重新校验。插件 `download_url` 即使来自已登录的安装权限，也会拒绝私网和非 HTTPS。
