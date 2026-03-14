# 使用 Termux 部署 AstrBot

> [!WARNING]
> 本教程所使用的方法仅可在安卓机上使用，苹果设备并没有真正意义的`Termux`

>[!TIP]
>本教程中若未说明，`Do you want to continue?[Y/n]`(或类似)一律填`Y`或`y`
# 准备步骤

## Bash 基础（可跳过）

### 进入目录

```bash
cd /path/to/dir
```

### 列举目录

```bash
ls
```

### 删除文件或目录

```bash
rm -r /path/to/dir/or/file
```

### 运行 `.sh` (`Shell`) 文件

```bash
bash xxx.sh
```

## 安装 `Termux`

在[Termux 官网](https://termux.dev/cn) 可选择在[GitHub](https://github.com/termux/termux-app/releases)或[F-Droid](https://f-droid.org/en/packages/com.termux/)下载Termux

## 换源 (可选)

>[!TIP]
>建议更换源以获得更好的安装体验
>但此换源并不会使`git clone`变得更快

```bash
termux-change-repo
```
选择第一个`Mirror group Rotate between several mirrors`

随后选择第三个`Mirrors in Chinese Mainland    All in Chinese Mainland`等待跑完即可

# 正式部署

## 安装 `proot-distro` 及 其他必须组件

首先安装`uv`、`git`和`proot-distro`

```bash
pkg install uv git proot-distro wget
```

### 使用 `proot-distro` 安装 `ubuntu环境`

>[!TIP]
>中国大陆概率访问`GitHub`，故建议使用加速器或代理
>由于最新版本的ubuntu镜像缺少python3.12包，因此需要新增下载[旧版镜像](https://github.com/termux/proot-distro/releases/tag/v4.18.0),下面以ubuntu-noble-aarch64-pd-v4.18.0.tar.xz为例

```bash
wget https://github.com/termux/proot-distro/releases/download/v4.18.0/ubuntu-noble-aarch64-pd-v4.18.0.tar.xz
nano $PREFIX/etc/proot-distro/ubuntu-old.sh
```
插入
```
DISTRO_NAME="Ubuntu (old)"
DISTRO_COMMENT="Local Ubuntu rootfs"

# 指定本地文件路径（必须使用 file:// 协议）
DISTRO_ROOTFS_URL="file:///data/data/com.termux/files/home/ubuntu-noble-aarch64-pd-v4.18.0.tar.xz"
TARBALL_URL['aarch64']="file:///data/data/com.termux/files/home/ubuntu-noble-aarch64-pd-v4.18.0.tar.xz"
```

```bash
proot-distro install ubuntu-old
```

### 登录 `Ubuntu环境`

下载及配置完成会有提示`Log in with: proot-distro login ubuntu-old`,输入相同的即可登入

即：
```bash
proot-distro login ubuntu-old
```

此时便进入了`Ubuntu环境`，我们需使用`apt`命令安装软件包了

## 添加第三方PPA

>[!TIP]
>`Python 3.12`并不在官方的软件源中，而`uv`所要求的Python版本为3.12 ，所以进行此步为必须

 ### 使用`apt`安装`software-properties-common` (添加PPA前置)

<!--这里不直接放termux基础环境里运行是因为他会报错，而且proot-distro也不大，性能损耗也很小-->

<!--这里如果安装 miniconda 或者 anaconda 都会有报错，不知道为什么-->

```bash
apt update && apt install software-properties-common
```

### 添加`deadsnakes`PPA(Python官方维护)

```bash
add-apt-repository ppa:deadsnakes/ppa && apt update
```
添加时你可能会看到:`Press [ENTER] to continue or Ctrl-c to cancel.` ，此时按下回车(换行)即可

## 安装 `Python`

在进行完以上步骤后，即可安装`Python 3.12`

```bash
apt install python3.12
```

## 克隆 `AstrBot` 仓库

直到这里，您所处的路径应为 `~#` 而不是其他次级目录，以防找不到项目目录

```bash
git clone https://github.com/AstrBotDevs/AstrBot.git && cd AstrBot
```

如果一切顺利的话，您应该进入到了 `~/AstrBot#` 下，可以进入到下一步了

>[!NOTE]
>如果 `git clone` 失败，那么其后的 `cd` 命令也不会生效，故在运行命令时请注意路径是否正确
>
>如果需要再次执行如上命令，建议先执行
>
>```bash
>rm -r AstrBot
>```
>
>之后再运行上述命令

## 运行 `AstrBot`

```bash
export UV_LINK_MODE=copy
uv run main.py
```

>[!TIP]
>如果使用 `uv` 下载软件包时速度慢，可以更换源 (以 `清华源` 为例)
>```bash
>export UV_DEFAULT_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
>```

## 🎉 大功告成！

如果没有报错，那么你可以看到`uv`在安装所需的包后出现类似 `WebUI 已启动，可访问` 并附带了几条链接。

如果有，那么恭喜你，你已经部署好了`AstrBot`并且运行了

接下来你可以尝试访问[localhost:6185](http://localhost:6185)验证可用性

>[!TIP]
>`Termux`与主机共享一个网络，即：`Termux`的IP地址就是主机的IP地址，你也可使用`ifconfig`查看主机IP地址
>
> 默认用户名和密码是 `astrbot` 和 `astrbot`。

# 后记

## 退出

如需退出`proot-distro`，可以使用

```bash
exit
```

## 重新启动

每次重新进入`Termux`时需重新打开 `proot` 环境并启动 `AstrBot`

可以使用命令如下：

```bash
proot-distro login ubuntu-old
cd AstrBot && uv run main.py
```

## 挂后台

### 开启

如需在一个session里面同时运行多个进程(eg. `AstrBot` 和 `Napcat`)，可以使用

```bash
uv run main.py &
......
```

### 关闭

上文运行后会有类似`[1] 1145`的输出，如需关闭进程，则可使用

```bash
kill -9 1145
```

或

```bash
pkill -9  -f "uv run main.py"
```

<!--↑这东西不咋靠谱捏-->

>[!TIP]
>也可以使用`screen`命令，较`&`更易操控
>```bash
>apt install screen         #安装screen
>screen -S <name>           #创建新的会话
>screen -r <name>           #重新连接会话
>screen -ls                 #列举会话
>screen -X -S <name> quit   #关闭会话
>Ctrl + a + d               #退出当前窗口
>```

>[!WARNING]
> 在退出时，请注意保存自己的任务，以防数据丢失

## 后台存活

如需让服务端在后台存活，可以在`设置`->`应用和服务`->`应用启动管理`->`Termux`改为`手动管理`并`允许后台活动`(或类似选项)

接下来，你需要部署任何一个消息平台，才能够实现在消息平台上使用 AstrBot。
