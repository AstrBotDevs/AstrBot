# AstrBot 管理面板

基于 CodedThemes/Berry 模板开发。

## 本地开发

先在项目根目录启动后端：

```bash
uv sync
uv run main.py
```

在另一个终端启动 WebUI：

```bash
cd dashboard
pnpm install
pnpm dev
```

开发服务器默认运行在 `http://localhost:3000`，将 `/api` 请求代理到 `http://127.0.0.1:6185`。后端地址不同时，请修改 `vite.config.ts` 中的 `server.proxy`。

## 构建与 API 客户端

```bash
pnpm build
```

此命令检查 TypeScript 类型并生成 `dist/`。当后端 API 路由、请求/响应结构或 OpenAPI 定义发生变化时，在本目录运行 `pnpm generate:api` 重新生成前端客户端。

## 发布更新入口

WebUI 顶部的更新入口会打开更新对话框，通过后端 API 获取版本信息。`VITE_ASTRBOT_RELEASE_BASE_URL` 当前没有被前端代码读取，设置此变量不会改变更新入口。
