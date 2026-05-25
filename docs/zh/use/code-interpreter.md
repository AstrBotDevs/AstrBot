# 基于 Docker 的代码执行器

> [!WARNING]
> 已过时，请参考最新的 [Agent 沙盒环境](/use/astrbot-agent-sandbox.md) 文档。在 v4.12.0 之后，该功能不可用。

在 `v3.4.2` 版本及之后，AstrBot 支持代码执行器以强化 LLM 的能力，并实现一些自动化的操作。

> [!TIP]
> 此功能目前处于实验阶段，可能会有一些问题。如果您遇到了问题，请在 [GitHub](https://github.com/AstrBotDevs/AstrBot/issues) 上提交 issue。欢迎加群讨论：[322154837](https://qm.qq.com/cgi-bin/qm/qr?k=EYGsuUTfe00_iOu9JTXS7_TEpMkXOvwv&jump_from=webapi&authKey=uUEMKCROfsseS+8IzqPjzV3y1tzy4AkykwTib2jNkOFdzezF9s9XknqnIaf3CDft)。

如果您要使用此功能，请确保您的机器安装了 `Docker`。因为此功能需要启动专用的 Docker 沙箱环境以执行代码，以防止 LLM 生成恶意代码对您的机器造成损害。


## Linux Docker 启动 AstrBot

如果您使用 Docker 部署了 AstrBot，需要多做一些工作。

1. 您需要在启动 Docker 容器时，请将 `/var/run/docker.sock` 挂载到容器内部。这样 AstrBot 才能够启动沙箱容器。

```bash
sudo docker run -itd -p 6180-6200:6180-6200 -p 11451:11451 -v $PWD/data:/AstrBot/data -v /var/run/docker.sock:/var/run/docker.sock --name astrbot soulter/astrbot:latest
```

2. 在聊天时使用 `/pi absdir <绝对路径地址>` 设置您宿主机上 AstrBot 的 data 目录的所在目录的绝对路径。

例子：

![image](https://files.astrbot.app/docs/source/images/code-interpreter/image-4.png)

## Linux 手动源码 启动 AstrBot

**如果你的 Docker 指令需要 sudo 权限来执行**，那么你需要在启动 AstrBot 时，使用 `sudo` 来启动，否则代码执行器会因为权限不足而无法调用 Docker。

```bash
sudo —E python3 main.py
```

## 使用

本功能使用的镜像是 `soulter/astrbot-code-interpreter-sandbox`，您可以在 [Docker Hub](https://hub.docker.com/r/soulter/astrbot-code-interpreter-sandbox) 上查看镜像的详细信息。

镜像中提供了常用的 Python 库：

- Pillow
- requests
- numpy
- matplotlib
- scipy
- scikit-learn
- beautifulsoup4
- pandas
- opencv-python
- python-docx
- python-pptx
- pymupdf
- mplfonts

基本上能够实现的任务：

- 图片编辑
- 网页抓取等
- 数据分析、简单的机器学习
- 文档处理，如读写 Word、PPT、PDF 等
- 数学计算，如画图、求解方程等

由于中国大陆无法访问 docker hub，因此如果您的环境在中国大陆，请使用 `/pi mirror` 来查看/设置镜像源。比如，截至本文档编写时，您可以使用 `cjie.eu.org` 作为镜像源。即设置 `/pi mirror cjie.eu.org`。

在第一次触发代码执行器时，AstrBot 会自动拉取镜像，这可能需要一些时间。请耐心等待。

镜像可能会不定时间更新以提供更多的功能，因此请定期查看镜像的更新。如果需要更新镜像，可以使用 `/pi repull` 命令重新拉取镜像。

> [!TIP]
> 如果一开始没有正常启动此功能，在启动成功之后，需要执行 `/tool on python_interpreter` 来开启此功能。
> 您可以通过 `/tool ls` 查看所有的工具以及它们的启用状态。

![image](https://files.astrbot.app/docs/source/images/code-interpreter/image-3.png)

## 图片和文件的输入

代码执行器除了能够识别和处理图片、文字任务，还能够识别您发送的文件，并且能够发送文件。

v3.4.34 后，使用 `/pi file` 指令开始上传文件。上传文件后，您可以使用 `/pi list` 查看您上传的文件，使用 `/pi clean` 清空您上传的文件。

上传的文件将会用于代码执行器的输入。

比如您希望对一张图片添加圆角，您可以使用 `/pi file` 上传图片，然后再提问：`请运行代码，对这张图片添加圆角`。

## Demo

![image](https://files.astrbot.app/docs/source/images/code-interpreter/a3cd3a0e-aca5-41b2-aa52-66b568bd955b.png)

![alt text](https://files.astrbot.app/docs/source/images/code-interpreter/image.png)

![image](https://files.astrbot.app/docs/source/images/code-interpreter/image-1.png)

![image](https://files.astrbot.app/docs/source/images/code-interpreter/image-2.png)
