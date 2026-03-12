# Agent 沙盒环境 ⛵️

> [!TIP]
> 此功能目前处于技术预览阶段，可能会存在一些 Bug。如果您遇到了问题，请在 [GitHub](https://github.com/AstrBotDevs/AstrBot/issues) 上提交 issue。

在 `v4.12.0` 版本及之后，AstrBot 引入了 Agent 沙盒环境，以替代之前的代码执行器功能。沙盒环境给 Agent 提供了更安全、更灵活的代码执行和自动化操作能力。

![](https://files.astrbot.app/docs/source/images/astrbot-agent-sandbox/image.png)

## 启用沙盒环境

目前，沙盒环境仅支持通过 Docker 来运行。我们目前使用了 [Shipyard](https://github.com/AstrBotDevs/shipyard) 项目作为 AstrBot 的沙盒环境驱动器。未来，我们会支持更多类型的沙盒环境驱动器，如 e2b。

## 性能要求

AstrBot 给每个沙盒环境限制最高 1 CPU 和 512 MB 内存。

我们建议您的宿主机至少有 2 个 CPU 和 4 GB 内存，并开启 Swap，以保证多个沙盒环境实例可以稳定运行。

### 使用 Docker Compose 部署 AstrBot 和 Shipyard

如果您还没有部署 AstrBot，或者想更换为我们推荐的带沙盒环境的部署方式，推荐使用 Docker Compose 来部署 AstrBot，代码如下：

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot
# 修改 compose-with-shipyard.yml 文件中的环境变量配置，例如 Shipyard 的 access token 等
docker compose -f compose-with-shipyard.yml up -d
docker pull soulter/shipyard-ship:latest
```

这会启动一个包含 AstrBot 主程序和沙盒环境的 Docker Compose 服务。

### 单独部署 Shipyard

如果您已经部署了 AstrBot，但没有部署沙盒环境，可以单独部署 Shipyard。

代码如下：

```bash
mkdir astrbot-shipyard
cd astrbot-shipyard
wget https://raw.githubusercontent.com/AstrBotDevs/shipyard/refs/heads/main/pkgs/bay/docker-compose.yml -O docker-compose.yml
# 修改 compose-with-shipyard.yml 文件中的环境变量配置，例如 Shipyard 的 access token 等
docker compose -f docker-compose.yml up -d
docker pull soulter/shipyard-ship:latest
```

部署成功后，上述命令会启动一个 Shipyard 服务，默认监听在 `http://<your-host>:8156`。

> [!TIP]
> 如果您使用 Docker 部署 AstrBot，您也可以修改上面的 Compose 文件，将 Shipyard 的网络与 AstrBot 放在同一个 Docker 网络中，这样就不需要暴露 Shipyard 的端口到宿主机。

## 配置 AstrBot 使用沙盒环境

> [!TIP]
> 请确保您的 AstrBot 版本在 `v4.12.0` 及之后。

在 AstrBot 控制台，进入 “配置文件” 页面，找到 “Agent 沙箱环境”，启用沙箱环境开关。

在出现的配置项中，

对于 `Shipyard API Endpoint`，如果您使用上述的 Docker Compose 部署方式，填写 `http://shipyard:8156` 即可。如果您是单独部署的 Shipyard，请填写对应的地址，例如 `http://<your-host>:8156`。

对于 `Shipyard Access Token`，请填写您在部署 Shipyard 时配置的访问令牌。

对于 `Shipyard Ship 存活时间(秒)`，这个定义了每个沙箱环境实例的存活时间，默认值为 3600 秒（1 小时）。您可以根据需要调整这个值。

对于 `Shipyard Ship 会话复用上限`，这个定义了每个沙箱环境实例可以复用的最大会话数，默认值为 10。也就是 10 个会话会共享同一个沙箱环境实例。您可以根据需要调整这个值。

填写好之后，点击右下角 “保存” 即可。

## 关于 `Shipyard Ship 存活时间(秒)`

沙箱环境实例的存活时间定义了每个实例在被销毁之前可以存在的最长时间，这个时间的设置需要根据您的使用场景以及资源来决定。

- 新的会话加入已有的沙箱环境实例时，该实例会自动延长存活时间到这个会话请求的 TTL。
- 当对沙箱环境实例执行操作后，该实例会自动延长存活时间到当前时间加上 TTL。

## 关于沙盒环境的数据持久化

Shipyard 会给每个会话分配一个工作目录，在 `/home/<会话唯一 ID>` 目录下。

Shipyard 会自动将沙盒环境中的 /home 目录挂载到宿主机的 `${PWD}/data/shipyard/ship_mnt_data` 目录下，当沙盒环境实例被销毁后，如果某个会话继续请求调用沙箱，Shipyard 会重新创建一个新的沙盒环境实例，并将之前持久化的数据重新挂载进去，保证数据的连续性。

## 其他同类社区插件

### luosheng520qaq/astrobot_plugin_code_executor

如果您资源有限，不希望使用沙盒环境来执行代码，可以尝试 luosheng520qaq 开发的 [astrobot_plugin_code_executor](https://github.com/luosheng520qaq/astrobot_plugin_code_executor) 插件。该插件会直接在宿主机上执行代码。插件已经尽力提升安全性，但仍需留意代码安全性问题。