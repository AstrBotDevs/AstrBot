# 项目启动指南

本文档详细介绍 AstrBot 项目的启动流程、初始化步骤以及相关配置。

## 环境要求

- Python 3.10 - 3.13
- uv 包管理器（推荐）

## 安装方式

### 方式一：使用 uv 一键安装（推荐）

```bash
# 安装 AstrBot
uv tool install astrbot

# 初始化项目（仅首次需要）
astrbot init

# 启动项目
astrbot run
```

### 方式二：开发模式安装

```bash
# 克隆项目
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot

# 安装开发版本
uv tool install git+https://github.com/AstrBotDevs/AstrBot@dev

# 初始化
astrbot init

# 启动
astrbot run
```

### 方式三：从源码运行

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot

# 创建虚拟环境
uv venv --seed
source .venv/bin/activate  # Linux/macOS
# 或: .venv\Scripts\activate  # Windows

# 安装依赖
uv pip install -e .

# 初始化
astrbot init

# 启动
astrbot run
```

## 初始化详解

`astrbot init` 命令执行以下操作：

1. **创建 `.astrbot` 标记文件** - 标识 AstrBot 根目录
2. **创建数据目录结构**：
   - `data/` - 主数据目录
   - `data/config/` - 配置文件目录
   - `data/plugins/` - 插件目录
   - `data/temp/` - 临时文件目录
   - `data/skills/` - 技能目录
3. **生成配置文件** `data/cmd_config.json`
4. **生成环境变量文件** `.env`（从 `config.template` 模板）
5. **安装 Dashboard**（可选，非服务器模式）

### 初始化参数

| 参数 | 说明 |
|------|------|
| `-y, --yes` | 跳过确认提示 |
| `-b, --backend-only` | 仅初始化后端，不安装 Dashboard |
| `-u, --admin-username` | 设置 Dashboard 管理员用户名 |
| `--root` | 指定 AstrBot 根目录 |

## 启动详解

`astrbot run` 命令启动 AstrBot 服务。

### 启动参数

| 参数 | 说明 |
|------|------|
| `-H, --host` | Dashboard 绑定地址 |
| `-p, --port` | Dashboard 绑定端口 |
| `-r, --reload` | 启用插件自动重载 |
| `-b, --backend-only` | 仅启动后端，不启动 WebUI |
| `-l, --log-level` | 日志级别（DEBUG, INFO, WARNING, ERROR） |
| `--ssl-cert` | SSL 证书路径 |
| `--ssl-key` | SSL 私钥路径 |
| `--ssl-ca` | SSL CA 证书路径 |
| `--debug` | 调试模式 |
| `-c, --service-config` | 服务配置文件路径 |

### 启动输出

启动成功后会显示：

```
AstrBot is running...
Visit the dashboard at : https://dash.astrbot.men/
Backend Requests : localhost or based on https
```

## 环境变量

### 核心配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ASTRBOT_ROOT` | AstrBot 根目录 | 自动检测 |
| `ASTRBOT_LOG_LEVEL` | 日志级别 | INFO |
| `ASTRBOT_RELOAD` | 启用插件热重载 | - |
| `ASTRBOT_DISABLE_METRICS` | 禁用指标上传 | - |

### Dashboard 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ASTRBOT_DASHBOARD_ENABLE` | 启用 Dashboard | True |
| `ASTRBOT_HOST` | Dashboard 绑定地址 | 0.0.0.0 |
| `ASTRBOT_PORT` | Dashboard 绑定端口 | 8000 |

### SSL 配置

| 变量 | 说明 |
|------|------|
| `ASTRBOT_SSL_ENABLE` | 启用 SSL |
| `ASTRBOT_SSL_CERT` | SSL 证书路径 |
| `ASTRBOT_SSL_KEY` | SSL 私钥路径 |
| `ASTRBOT_SSL_CA_CERTS` | CA 证书路径 |

### 代理配置

| 变量 | 说明 |
|------|------|
| `http_proxy` | HTTP 代理地址 |
| `https_proxy` | HTTPS 代理地址 |
| `no_proxy` | 不使用代理的地址列表 |

### 平台集成

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key（用于 Rerank） |
| `COZE_API_KEY` | Coze API Key |
| `COZE_BOT_ID` | Coze Bot ID |
| `BAY_DATA_DIR` | Computer Use 数据目录 |

## 目录结构

```
AstrBot/
├── .astrbot              # AstrBot 根目录标记
├── .env                  # 环境变量配置
├── data/                 # 数据目录
│   ├── config/
│   │   └── cmd_config.json  # 主配置文件
│   ├── plugins/          # 插件目录
│   ├── skills/          # 技能目录
│   └── temp/            # 临时文件目录
├── astrbot/             # 核心代码
│   ├── cli/             # 命令行工具
│   ├── core/            # 核心模块
│   ├── dashboard/       # Dashboard 前端
│   └── ...
└── ...
```

## 配置文件

主配置文件位于 `data/cmd_config.json`，包含：

- LLM 提供商配置
- 平台适配器配置
- 插件设置
- Dashboard 设置
- 代理设置

## 常见问题

### 端口被占用

如果启动时提示端口被占用：

```bash
# 查看占用端口的进程
lsof -i :8000

# 或使用其他端口启动
astrbot run --port 8080
```

### 多个实例冲突

AstrBot 使用锁文件机制防止同时运行多个实例。如需强制启动：

```bash
# 删除锁文件
rm astrbot.lock

# 重新启动
astrbot run
```

### Dashboard 无法访问

1. 确认 `ASTRBOT_DASHBOARD_ENABLE` 为 `True`
2. 检查防火墙设置
3. 确认端口未被阻止

### 查看日志

```bash
# 以调试模式启动查看详细日志
astrbot run --debug --log-level DEBUG
```

## 下一步

- [配置模型提供商](../providers/llm.md)
- [安装插件](../use/plugin.md)
- [使用技能](../use/skills.md)
- [部署到服务器](./deploy/astrbot/docker.md)
