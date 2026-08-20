# AstrBot 管理面板

基于 CodedThemes/Berry 模板开发。

## 环境变量

- `VITE_ASTRBOT_RELEASE_BASE_URL`（可选，构建时）
  - 默认值：`https://github.com/Xero-Team/AstrBot/releases`
  - 用途：集成方（例如 Desktop）可用来覆盖外部 Release 页地址。当前 Dashboard 运行时版本检查走后端 `ASTRBOT_RELEASE_API`，不读取该变量。
  - 建议传入仓库的 `.../releases` 基地址（不带 `/latest`）。
