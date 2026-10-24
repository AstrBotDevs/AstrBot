# 社区提供的部署方式

> [!WARNING]
> AstrBot 官方不保证这些部署方式的安全性和稳定性。

## Linux 一键部署脚本

使用 `curl` 去下载脚本并且使用 `bash` 执行脚本：

```bash
bash <(curl -sSL https://raw.githubusercontent.com/zhende1113/Antlia/refs/heads/main/Script/AstrBot/Antlia.sh)
```

如果你的系统没有 `curl`，你可以使用 `wget`：

```bash
wget -qO- https://raw.githubusercontent.com/zhende1113/Antlia/refs/heads/main/Script/AstrBot/Antlia.sh | bash
```

仓库地址：[zhende1113/Antlia](https://github.com/zhende1113/Antlia/)

## Linux 一键部署脚本（基于Docker）

支持 AstrBot / NapCat

> [!TIP]
> 权限不足时请使用 `sudo` 提权

### 使用 `curl`

```bash
curl -sSL https://raw.githubusercontent.com/railgun19457/AstrbotScript/main/AstrbotScript.sh -o AstrbotScript.sh
chmod +x AstrbotScript.sh
sudo ./AstrbotScript.sh
```

### 使用 `wget`

```bash
wget -qO AstrbotScript.sh https://raw.githubusercontent.com/railgun19457/AstrbotScript/main/AstrbotScript.sh
chmod +x AstrbotScript.sh
sudo ./AstrbotScript.sh
```

> [!note]
> `sudo ./AstrbotScript.sh --no-color (可选禁用彩色输出)`

__仓库地址：[railgun19457/AstrbotScript](https://github.com/railgun19457/AstrbotScript)__

## AstrBot Android 部署

参考 [zz6zz666/AstrBot-Android-App](https://github.com/zz6zz666/AstrBot-Android-App)

## Pethost 一键模板

[Pethost](https://pethost.dev) 提供一键部署模板，使用官方 `soulter/astrbot` 镜像，数据保存在持久化卷中，并提供带 HTTPS 的独立地址。

1. 打开 [AstrBot 模板](https://pethost.dev/templates/astrbot/)，点击 Deploy on Pethost。
2. 填写 WebUI 密码：需要包含大写字母、小写字母和数字。
3. 项目上线后，打开其地址，使用用户名 `astrbot` 和该密码登录。首次登录时 AstrBot 会要求设置新密码。
