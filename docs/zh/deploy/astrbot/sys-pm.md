# 通过系统包管理器安装
> [!WARNING]
> 目前仅提供AUR版本
> 如果你是windows用户/macos用户，建议通过uv来安装
> 如果你是Linux用户，强烈建议通过包管理器来安装

# 准备步骤

## AUR 是什么？
AUR允许用户从社区维护的软件仓库中安装软件。AUR的包通常是由社区成员维护的，而不是官方维护的。
常见的AUR助手有yay，paru。
以下教程以paru为例，yay同理，仅需将paru替换为yay。

# 安装过程

## AUR
```bash
paru -S astrbot-git
# 提示：
# 开始审阅步骤，按q可退出审阅，继续安装
# 安装后数据目录固定在：~/.local/share/astrbot
```
# 启动
>[!TIP]
> 你可以直接使用 astrbot init （首次运行）初始化
> 使用astrbot run运行
> 但是更加推荐使用systemctl启动，拥有自动重启，日志轮转等功能

```bash
systemctl --user start astrbot.service
```

# 开机自启
```bash
# 处于安全考虑，设计为以用户身份执行
systemctl --user enable astrbot.service
# 如果需要立即启动，加上--now
# systemctl --user enable --now astrbot.service
```
