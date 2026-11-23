# 使用 Kubernetes 部署 AstrBot

> [!WARNING]
> 通过 Kubernetes (K8s) 可以将 AstrBot 以高可用的方式部署在集群环境中，当出现故障时可以自动拉起恢复。
>
> 由于 AstrBot 当前使用 SQLite 数据库，此部署方案不支持多副本水平扩展。
>
> 以下教程默认您的环境已安装并配置好 `kubectl`，且能够连接到您的 K8s 集群。

## 准备工作

在开始之前，请确保您的 Kubernetes 集群满足以下条件：

1.  **拥有默认的 StorageClass**：用于动态创建 `PersistentVolumeClaim` (PVC)。您可以通过 `kubectl get sc` 查看。如果没有，您需要手动创建 `PersistentVolume` (PV) 或安装相应的存储插件 (如 `nfs-client-provisioner`)。
2.  **网络访问**：确保您的集群节点可以从 `docker.io` 或您指定的镜像仓库拉取镜像。

## 部署方式

清单位于 `k8s/astrbot` 目录，只部署 AstrBot；OneBot v11 等协议实现端需单独部署后连接到 AstrBot。

---

### 部署 AstrBot

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

如果拉取 `soulter/astrbot:latest` 镜像困难，可以手动修改对应的 `02-deployment.yaml` 文件，将 `image` 字段替换为国内的镜像加速地址，例如：

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

*   **独立部署模式:**

    ```bash
    kubectl logs -f -n astrbot-standalone-ns deployment/astrbot-standalone
    ```

## 🎉 大功告成

部署并暴露服务后，您就可以通过相应的 IP 和端口访问 AstrBot 管理面板了。

> 首次登录请使用启动日志中打印的随机初始密码（用户名通常为 `astrbot`）。登录后请立即修改密码。
