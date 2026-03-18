# 使用 Kubernetes 部署 AstrBot

> [!WARNING]
> 通过 Kubernetes (K8s) 可以将 AstrBot 以高可用的方式部署在集群环境中，当出现故障时可以自动拉起恢复。
>
> 由于 AstrBot 当前使用 SQLite 数据库，此部署方案不支持多副本水平扩展。同时，若采用 Sidecar 模式，NapCat 的登录状态持久化需要您特别关注。
>
> 以下教程默认您的环境已安装并配置好 `kubectl`，且能够连接到您的 K8s 集群。

## 准备工作

在开始之前，请确保您的 Kubernetes 集群满足以下条件：

1.  **拥有默认的 StorageClass**：用于动态创建 `PersistentVolumeClaim` (PVC)。您可以通过 `kubectl get sc` 查看。如果没有，您需要手动创建 `PersistentVolume` (PV) 或安装相应的存储插件 (如 `nfs-client-provisioner`)。
2.  **网络访问**：确保您的集群节点可以从 `docker.io` 或您指定的镜像仓库拉取镜像。

## 部署方式

我们提供两种部署方案：

*   **集成部署 (Sidecar 模式)**：将 AstrBot 和 NapCat 部署在同一个 Pod 中，推荐用于 QQ 个人号。
*   **独立部署**：只部署 AstrBot，适用于其他平台或您希望独立管理 NapCat 的场景。

---

### 方式一：和 NapCatQQ 一起部署 (Sidecar)

此方式位于 `k8s/astrbot_with_napcat` 目录。

#### 1. 部署

```bash
# 1. 创建命名空间
kubectl apply -f k8s/astrbot_with_napcat/00-namespace.yaml

# 2. 创建持久化存储卷
# 注意：astrbot-data-shared-pvc 需要 ReadWriteMany (RWX) 访问模式。
# 如果您的集群不支持 RWX，您需要配置 NFS 等共享存储，并修改 01-pvc.yaml 中的 storageClassName。
kubectl apply -f k8s/astrbot_with_napcat/01-pvc.yaml

# 3. 部署应用
kubectl apply -f k8s/astrbot_with_napcat/02-deployment.yaml
```

#### 2. 暴露服务 (二选一)

*   **方式 A: NodePort**

    ```bash
    kubectl apply -f k8s/astrbot_with_napcat/03-service-nodeport.yaml
    ```

    服务将通过节点 IP 和一个由 Kubernetes 自动分配的端口暴露。您可以通过以下命令查看端口：

    ```bash
    kubectl get svc -n astrbot-ns
    ```

    在输出中找到 `astrbot-webui-svc` 和 `napcat-web-svc` 的 `PORT(S)` 列，格式为 `<内部端口>:<NodePort端口>/TCP`。例如 `8080:30185/TCP`，则访问地址为 `http://<NodeIP>:30185`。

*   **方式 B: LoadBalancer**

    如果您的集群支持 `LoadBalancer` 类型的服务 (通常在云厂商的 K8s 服务中提供)，可以使用此方式。

    ```bash
    kubectl apply -f k8s/astrbot_with_napcat/04-service-loadbalancer.yaml
    ```

    执行后，通过 `kubectl get svc -n astrbot-ns` 查看分配到的外部 IP (EXTERNAL-IP)。

#### 3. 配置连接

由于 AstrBot 和 NapCat 在同一个 Pod 中，它们可以通过 `localhost` 直接通信。

1.  **在 AstrBot 中添加消息平台：**
    *   进入 AstrBot WebUI，选择 `机器人` -> `添加`。
    *   **选择消息平台类别**: `aiocqhttp`
    *   **机器人名称**: `napcat` (或自定义)
    *   **反向 Websocket 主机**: `0.0.0.0`
    *   **反向 Websocket 端口**: `6199`
    *   保存配置。


2.  **在 NapCat 中配置 Websocket Client：**
    *   进入 NapCat WebUI，选择 `设置` -> `反向WS` -> `添加`。
    *   **启用**: 开启
    *   **URL**: `ws://localhost:6199/ws`
    *   **消息格式**: `Array`
    *   保存配置。


---

### 方式二：只部署 AstrBot (通用方式)

此方式位于 `k8s/astrbot` 目录。

#### 1. 部署

```bash
# 1. 创建命名空间
kubectl apply -f k8s/astrbot/00-namespace.yaml

# 2. 创建持久化存储卷
kubectl apply -f k8s/astrbot/01-pvc.yaml

# 3. 部署应用
kubectl apply -f k8s/astrbot/02-deployment.yaml
```

#### 2. 暴露服务 (二选一)

*   **方式 A: NodePort**

    ```bash
    kubectl apply -f k8s/astrbot/03-service-nodeport.yaml
    ```

    服务将通过节点 IP 和一个由 Kubernetes 自动分配的端口暴露。您可以通过以下命令查看端口：

    ```bash
    kubectl get svc -n astrbot-standalone-ns
    ```

    在输出中找到 `astrbot-webui-svc` 的 `PORT(S)` 列，格式为 `<内部端口>:<NodePort端口>/TCP`。例如 `8080:30185/TCP`，则访问地址为 `http://<NodeIP>:30185`。

*   **方式 B: LoadBalancer**

    ```bash
    kubectl apply -f k8s/astrbot/04-service-loadbalancer.yaml
    ```

    执行后，通过 `kubectl get svc -n astrbot-standalone-ns` 查看分配到的外部 IP (EXTERNAL-IP)。

---

## 高级配置

### 镜像加速 (中国大陆用户)

如果拉取 `soulter/astrbot:latest` 或 `mlikiowa/napcat-docker:latest` 镜像困难，可以手动修改对应的 `02-deployment.yaml` 文件，将 `image` 字段替换为国内的镜像加速地址，例如：

```yaml
# 示例：
# image: soulter/astrbot:latest
# 替换为
image: m.daocloud.io/docker.io/soulter/astrbot:latest
```

### 启用 Docker 沙箱代码执行器

如果您需要使用沙箱代码执行器，需要将 Docker 的 socket 文件挂载到 Pod 中。

编辑 `02-deployment.yaml` 文件，在 `spec.template.spec` 下添加 `volumes` 和 `volumeMounts`：

1.  **在 `astrbot` 容器的 `volumeMounts` 列表下添加以下内容：**

    ```yaml
    - name: docker-sock
      mountPath: /var/run/docker.sock
    ```

2.  **在 `spec.template.spec.volumes` 列表下添加以下内容：**

    ```yaml
    - name: docker-sock
      hostPath:
        path: /var/run/docker.sock
        type: Socket
    ```

> [!WARNING]
> 将 Docker socket 挂载到 Pod 中存在安全风险，请确保您了解其影响。

## 查看日志

*   **Sidecar 部署模式:**

    ```bash
    # 查看 AstrBot 日志
    kubectl logs -f -n astrbot-ns deployment/astrbot-stack -c astrbot

    # 查看 NapCat 日志
    kubectl logs -f -n astrbot-ns deployment/astrbot-stack -c napcat
    ```

*   **独立部署模式:**

    ```bash
    kubectl logs -f -n astrbot-standalone-ns deployment/astrbot-standalone
    ```

## 🎉 大功告成

部署并暴露服务后，您就可以通过相应的 IP 和端口访问 AstrBot 管理面板了。

> 默认用户名和密码是 `astrbot` 和 `astrbot`。
