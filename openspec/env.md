# 环境变量规范

## 概述

本文档定义 AstrBot 环境变量的规范，所有环境变量以 `ASTRBOT_` 为前缀。

## 变量分类

| 分类 | 前缀 | 说明 |
|------|------|------|
| 实例标识 | `ASTRBOT_INSTANCE_*` | 实例相关配置 |
| 核心配置 | `ASTRBOT_*` | 核心功能配置 |
| 网络配置 | `ASTRBOT_NET_*` | 网络相关配置 |
| SSL/TLS | `ASTRBOT_SSL_*` | 安全连接配置 |
| 代理配置 | `*_PROXY` | 代理相关配置 |
| 平台配置 | 平台特定 | 第三方平台集成 |

---

## 实例标识 / Instance Identity

### `ASTRBOT_INSTANCE_NAME`

| 属性 | 值 |
|------|-----|
| 说明 | 实例名称，用于日志和服务名 |
| 类型 | string |
| 默认 | `AstrBot` |

---

## 核心配置 / Core Configuration

### `ASTRBOT_ROOT`

| 属性 | 值 |
|------|-----|
| 说明 | AstrBot 根目录路径 |
| 类型 | path |
| 默认 | 当前工作目录 |

**特殊路径**：
- 桌面客户端：`~/.astrbot`
- 服务器：`/var/lib/astrbot/<instance>/`

### `ASTRBOT_LOG_LEVEL`

| 属性 | 值 |
|------|-----|
| 说明 | 日志等级 |
| 类型 | enum |
| 默认 | `INFO` |
| 可选值 | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

### `ASTRBOT_RELOAD`

| 属性 | 值 |
|------|-----|
| 说明 | 启用插件热重载 |
| 类型 | boolean (0/1) |
| 默认 | `0` (禁用) |

### `ASTRBOT_DISABLE_METRICS`

| 属性 | 值 |
|------|-----|
| 说明 | 禁用匿名使用统计 |
| 类型 | boolean (0/1) |
| 默认 | `0` (启用统计) |

### `ASTRBOT_PYTHON`

| 属性 | 值 |
|------|-----|
| 说明 | 覆盖 Python 可执行文件路径（用于本地代码执行） |
| 类型 | path |
| 示例 | `/usr/bin/python3`, `/home/user/.pyenv/shims/python` |

### `ASTRBOT_DEMO_MODE`

| 属性 | 值 |
|------|-----|
| 说明 | 启用演示模式（可能限制部分功能） |
| 类型 | boolean |
| 默认 | `False` |

### `ASTRBOT_TESTING`

| 属性 | 值 |
|------|-----|
| 说明 | 启用测试模式（影响日志和部分行为） |
| 类型 | boolean |
| 默认 | `False` |

### `ASTRBOT_DESKTOP_CLIENT`

| 属性 | 值 |
|------|-----|
| 说明 | 标记是否通过桌面客户端执行（内部使用） |
| 类型 | boolean (0/1) |
| 默认 | `0` |

### `ASTRBOT_SYSTEMD`

| 属性 | 值 |
|------|-----|
| 说明 | 标记是否通过 systemd 服务执行 |
| 类型 | boolean (0/1) |
| 默认 | `0` |

---

## 管理面板 / Dashboard

### `ASTRBOT_DASHBOARD_ENABLE`

| 属性 | 值 |
|------|-----|
| 说明 | 启用或禁用 WebUI 管理面板 |
| 类型 | boolean |
| 默认 | `True` |

---

## 国际化 / Internationalization

### `ASTRBOT_CLI_LANG`

| 属性 | 值 |
|------|-----|
| 说明 | CLI 界面语言 |
| 类型 | enum |
| 默认 | `zh` (跟随系统 locale) |
| 可选值 | `zh` (中文), `en` (英文) |

---

## 网络配置 / Network

### `ASTRBOT_HOST`

| 属性 | 值 |
|------|-----|
| 说明 | API 绑定主机 |
| 类型 | string |
| 示例 | `0.0.0.0` (所有接口), `127.0.0.1` (仅本地) |

### `ASTRBOT_PORT`

| 属性 | 值 |
|------|-----|
| 说明 | API 绑定端口 |
| 类型 | integer |
| 示例 | `3000`, `6185`, `8080` |

---

## SSL/TLS 配置

### `ASTRBOT_SSL_ENABLE`

| 属性 | 值 |
|------|-----|
| 说明 | 启用 SSL/TLS |
| 类型 | boolean |
| 默认 | `false` |

### `ASTRBOT_SSL_CERT`

| 属性 | 值 |
|------|-----|
| 说明 | SSL 证书路径（PEM 格式） |
| 类型 | path |
| 示例 | `/etc/astrbot/certs/myinstance/fullchain.pem` |

### `ASTRBOT_SSL_KEY`

| 属性 | 值 |
|------|-----|
| 说明 | SSL 私钥路径（PEM 格式） |
| 类型 | path |
| 示例 | `/etc/astrbot/certs/myinstance/privkey.pem` |

### `ASTRBOT_SSL_CA_CERTS`

| 属性 | 值 |
|------|-----|
| 说明 | SSL CA 证书链路径（可选，用于客户端验证） |
| 类型 | path |
| 示例 | `/etc/ssl/certs/ca-certificates.crt` |

---

## 代理配置
### 通用
### `http_proxy` / `HTTP_PROXY`

| 属性 | 值 |
|------|-----|
| 说明 | HTTP 代理地址 |
| 类型 | url |
| 示例 | `http://127.0.0.1:7890`, `socks5://127.0.0.1:1080` |

### `https_proxy` / `HTTPS_PROXY`

| 属性 | 值 |
|------|-----|
| 说明 | HTTPS 代理地址 |
| 类型 | url |
| 示例 | `http://127.0.0.1:7890`, `socks5://127.0.0.1:1080` |

### `no_proxy` / `NO_PROXY`

| 属性 | 值 |
|------|-----|
| 说明 | 不走代理的主机列表（逗号分隔） |
| 类型 | string |
| 示例 | `localhost,127.0.0.1,192.168.0.0/16,.local` |

---

## 第三方集成 / Third-party Integrations

### `DASHSCOPE_API_KEY`

| 属性 | 值 |
|------|-----|
| 说明 | 阿里云 DashScope API 密钥（用于 Rerank 服务） |
| 类型 | string |
| 获取地址 | https://dashscope.console.aliyun.com/ |
| 示例 | `sk-xxxxxxxxxxxx` |

### `COZE_API_KEY`

| 属性 | 值 |
|------|-----|
| 说明 | Coze API 密钥 |
| 类型 | string |
| 获取地址 | https://www.coze.com/ |

### `COZE_BOT_ID`

| 属性 | 值 |
|------|-----|
| 说明 | Coze Bot ID |
| 类型 | string |

### `BAY_DATA_DIR`

| 属性 | 值 |
|------|-----|
| 说明 | 计算机控制相关的数据目录（用于截图/文件存储） |
| 类型 | path |
| 示例 | `/var/lib/astrbot/bay_data` |

---

## 平台特定配置 / Platform-specific

### `TEST_MODE`

| 属性 | 值 |
|------|-----|
| 说明 | QQ 官方机器人测试模式开关 |
| 类型 | enum |
| 默认 | `off` |
| 可选值 | `on`, `off` |

---

## 命名规范

### 前缀规则

| 前缀 | 用途 |
|------|------|
| `ASTRBOT_` | AstrBot 核心配置 |
| `ASTRBOT_SSL_` | SSL/TLS 配置 |
| `ASTRBOT_INSTANCE_` | 实例相关 |
| `http_proxy`, `https_proxy`, `no_proxy` | 标准代理变量（无前缀） |

### 布尔值

布尔值使用以下格式之一：

| 格式 | 示例 |
|------|------|
| 整数 (0/1) | `ASTRBOT_RELOAD=0` |
| 字符串 (true/false) | `ASTRBOT_SSL_ENABLE=false` |
| 枚举 | `TEST_MODE=on/off` |

---

## 配置文件优先级

1. 环境变量（最高优先级）
2. `.env` 文件
3. 默认值（最低优先级）

---

## 特殊变量展开

支持 `${VAR_NAME}` 格式的变量展开：

```bash
INSTANCE_NAME="my-bot"
ASTRBOT_ROOT="${ASTRBOT_ROOT:-/var/lib/astrbot}"
```

### 支持的展开语法

| 语法 | 说明 |
|------|------|
| `${VAR}` | 展开 VAR 的值 |
| `${VAR:-default}` | 如果 VAR 未设置或为空，使用 default |
| `${VAR:=default}` | 如果 VAR 未设置或为空，设置为 default 并展开 |
