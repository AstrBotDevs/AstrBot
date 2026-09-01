# 备份、恢复与升级演练

升级或迁移前备份运行数据。本 fork 不提供托管备份。

运行数据默认在进程工作目录下的 `data/`。设置 `ASTRBOT_ROOT` 后位于 `$ASTRBOT_ROOT/data`。配置、SQLite、插件、Skills、知识库、临时文件和备份都可能在这里，应作为整体对待。

## 不要做的事

- 服务仍在写入时，不要直接 `cp` SQLite 主库文件（默认 WAL 模式）。
- 不要只拷贝 `data/data_v4.db` 而丢掉知识库、插件与配置。
- 不要把含密钥的备份提交进 Git 或发到公开频道。
- 不要在开发者真实 `data/` 上做演练；用副本或临时根目录。
- 不要把 [Persona JSON 导出](../../use/persona) 当作完整备份。

## 推荐：WebUI 备份 ZIP

打开 Dashboard 的 **设置 → 维护**，再点 **数据备份与恢复** / **备份管理**。导出器把主库表写成 JSON，并打包：

- 主数据库表（`data/data_v4.db` 的导出，而不是复制正在打开的文件）
- 知识库元数据、向量文档与多媒体文件
- `cmd_config.json`、`config/`、插件与插件数据、Skills、WebChat、附件
- `t2i_templates/` 与 `temp/`

在 WebUI 中创建备份，把 ZIP 拷到仓库外。导入走同一对话框。解压时会拒绝逃出目标目录的路径穿越。

导入是破坏性 **替换**，不是事务回滚。ZIP 的 `major.minor` 必须与正在运行的 AstrBot 版本一致；`4.26` 的备份不能导入 `4.27`。补丁号不同（例如 `4.27.4` 导入 `4.27.5`）可以在确认后导入。

替换目录（`plugins/`、`plugin_data/`、`config/`、`skills/`、`webchat/`、`t2i_templates/`、`temp/`）前，导入器会把现有目录挪到 `{directory}.bak`，并覆盖上一次的 `.bak`。`cmd_config.json` 会复制为 `cmd_config.json.bak`。主库表和知识库存储是原地清空，没有快照。清空之后如果导入失败，从仓库外的副本恢复，不要把 `{directory}.bak` 当成主库回滚。导入成功后界面会要求重启。

## 停写后整目录拷贝

无法使用 WebUI 时：

1. 停止 AstrBot（源码部署停进程；Compose 用 `docker compose stop`）。
2. 拷贝整个 `data/` 到仓库外。
3. 确认副本含 `data_v4.db`、`data_v4.db-wal` / `-shm`（若存在）、`knowledge_base/`、`plugins/`、`plugin_data/`、`skills/`、`config/`、`cmd_config.json`。

## 升级前恢复演练

至少做一次并记录日期与结果：

1. 按上面其中一种方式取出备份。
2. 停服务。
3. 在隔离目录或新卷上恢复：导入 ZIP，或把 `data/` 副本放到运行根。
4. 启动。
5. 用原管理员登录，确认会话、人格、插件、知识库检索、Provider 配置仍在。恢复后核对插件、MCP、Skills、Provider 名称是否仍能解析。

当前 `master` 上的破坏性主库重建不会从旧 `data_v4.db` 迁移行。跨越该类 changelog 条目时，先读 `changelogs/`，再决定是恢复兼容快照还是按文档切空库。

## 日志红线

失败路径可记错误码与任务 id。禁止出现密码、API Key、完整 Authorization、Cookie、备份 ZIP 内的密钥明文。用户可见失败保持泛化，见仓库安全不变量。
