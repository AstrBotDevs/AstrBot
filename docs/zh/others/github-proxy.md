# GitHub 镜像

当前 fork **默认不提供** GitHub 镜像列表，Dashboard 也不再接受任意自定义镜像输入。

插件安装和插件更新只会请求：

- GitHub 官方相关域名；
- 插件市场默认先请求上游 `cloud.astrbot.app` 市场 JSON，失败后再请求 GitHub 集合 `AstrBotDevs/AstrBot_Plugins_Collection` 和 jsDelivr CDN；这些都是上游服务，不是本 fork 运营的市场。默认市场没有 MD5 校验，每次打开都会重新拉取；自定义市场才使用对应的 `-md5.json`。JSON 请求会使用配置里的 `http_proxy`，不会读取进程环境变量代理。
- 通过后端校验的公开 HTTPS origin。

如果 API 传入镜像前缀，它必须是：

- 明确的 HTTPS origin；
- 不含用户名/密码；
- 解析结果全部为公网地址；
- 不能重定向到未校验的内部地址。

这不是普通 HTTP 正向代理。功能语义是“URL 前缀镜像”，每一跳都会重新校验。插件 `download_url` 即使来自已登录的安装权限，也会拒绝私网和非 HTTPS。
