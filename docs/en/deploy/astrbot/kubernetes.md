# Deploy AstrBot with Kubernetes

> [!WARNING]
> You can deploy AstrBot in a high-availability setup using Kubernetes (K8s), allowing it to automatically recover from failures.
>
> Due to the current use of an SQLite database, this deployment does not support horizontal scaling with multiple replicas. Additionally, if using the Sidecar mode, pay special attention to the persistence of NapCat's login state.
>
> The following tutorial assumes that you have `kubectl` installed and configured, and that you can connect to your K8s cluster.

## Prerequisites

Before you begin, make sure your Kubernetes cluster meets the following conditions:

1.  **Default StorageClass**: Used to dynamically create `PersistentVolumeClaim` (PVC). You can check this with `kubectl get sc`. If you don't have one, you need to manually create a `PersistentVolume` (PV) or install a corresponding storage plugin (e.g., `nfs-client-provisioner`).
2.  **Network Access**: Ensure that your cluster nodes can pull images from `docker.io` or your specified image repository.

## Deployment Methods

We offer two deployment options:

*   **Integrated Deployment (Sidecar Mode)**: Deploy AstrBot and NapCat in the same Pod. Recommended for personal QQ accounts.
*   **Standalone Deployment**: Deploy only AstrBot. Suitable for other platforms or if you want to manage NapCat independently.

---

### Method 1: Deploy with NapCatQQ (Sidecar)

This method is located in the `k8s/astrbot_with_napcat` directory.

#### 1. Deploy

```bash
# 1. Create namespace
kubectl apply -f k8s/astrbot_with_napcat/00-namespace.yaml

# 2. Create Persistent Volume Claim
# Note: astrbot-data-shared-pvc requires ReadWriteMany (RWX) access mode.
# If your cluster does not support RWX, you need to configure shared storage such as NFS and modify the storageClassName in 01-pvc.yaml.
kubectl apply -f k8s/astrbot_with_napcat/01-pvc.yaml

# 3. Deploy the application
kubectl apply -f k8s/astrbot_with_napcat/02-deployment.yaml
```

#### 2. Expose Service (Choose one)

*   **Option A: NodePort**

    ```bash
    kubectl apply -f k8s/astrbot_with_napcat/03-service-nodeport.yaml
    ```

    The service will be exposed via the node IP and a port automatically assigned by Kubernetes. You can find the port with the following command:

    ```bash
    kubectl get svc -n astrbot-ns
    ```

    In the output, find the `PORT(S)` column for `astrbot-webui-svc` and `napcat-web-svc`. The format is `<internal-port>:<NodePort>/TCP`. For example, if you see `8080:30185/TCP`, the access address is `http://<NodeIP>:30185`.

*   **Option B: LoadBalancer**

    If your cluster supports `LoadBalancer` type services (usually provided in K8s services from cloud providers), you can use this method.

    ```bash
    kubectl apply -f k8s/astrbot_with_napcat/04-service-loadbalancer.yaml
    ```

    After execution, check the assigned external IP (EXTERNAL-IP) with `kubectl get svc -n astrbot-ns`.

#### 3. Configure Connection

Since AstrBot and NapCat are in the same Pod, they can communicate directly via `localhost`.

1.  **Add a message platform in AstrBot:**
    *   Go to the AstrBot WebUI, select `Settings` -> `Message Platform` -> `Add`.
    *   **Select Message Platform Category**: `aiocqhttp`
    *   **Bot Name**: `napcat` (or custom)
    *   **Reverse Websocket Host**: `0.0.0.0`
    *   **Reverse Websocket Port**: `6199`
    *   Save the configuration.


2.  **Configure Websocket Client in NapCat:**
    *   Go to the NapCat WebUI, select `Settings` -> `Reverse WS` -> `Add`.
    *   **Enable**: On
    *   **URL**: `ws://localhost:6199/ws`
    *   **Message Format**: `Array`
    *   Save the configuration.


---

### Method 2: Deploy AstrBot Only (General Purpose)

This method is located in the `k8s/astrbot` directory.

#### 1. Deploy

```bash
# 1. Create namespace
kubectl apply -f k8s/astrbot/00-namespace.yaml

# 2. Create Persistent Volume Claim
kubectl apply -f k8s/astrbot/01-pvc.yaml

# 3. Deploy the application
kubectl apply -f k8s/astrbot/02-deployment.yaml
```

#### 2. Expose Service (Choose one)

*   **Option A: NodePort**

    ```bash
    kubectl apply -f k8s/astrbot/03-service-nodeport.yaml
    ```

    The service will be exposed via the node IP and a port automatically assigned by Kubernetes. You can find the port with the following command:

    ```bash
    kubectl get svc -n astrbot-standalone-ns
    ```

    In the output, find the `PORT(S)` column for `astrbot-webui-svc`. The format is `<internal-port>:<NodePort>/TCP`. For example, if you see `8080:30185/TCP`, the access address is `http://<NodeIP>:30185`.

*   **Option B: LoadBalancer**

    ```bash
    kubectl apply -f k8s/astrbot/04-service-loadbalancer.yaml
    ```

    After execution, check the assigned external IP (EXTERNAL-IP) with `kubectl get svc -n astrbot-standalone-ns`.

---

## Advanced Configuration

### Image Mirror (for users in mainland China)

If you have difficulty pulling the `soulter/astrbot:latest` or `mlikiowa/napcat-docker:latest` images, you can manually edit the corresponding `02-deployment.yaml` file and replace the `image` field with a domestic mirror address, for example:

```yaml
# Example:
# image: soulter/astrbot:latest
# Replace with:
image: m.daocloud.io/docker.io/soulter/astrbot:latest
```

### Enable Docker Sandbox Code Executor

If you need to use the sandbox code executor, you need to mount the Docker socket file into the Pod.

Edit the `02-deployment.yaml` file and add `volumes` and `volumeMounts` under `spec.template.spec`:

1.  **Add the following to the `volumeMounts` list of the `astrbot` container:**

    ```yaml
    - name: docker-sock
      mountPath: /var/run/docker.sock
    ```

2.  **Add the following to the `spec.template.spec.volumes` list:**

    ```yaml
    - name: docker-sock
      hostPath:
        path: /var/run/docker.sock
        type: Socket
    ```

> [!WARNING]
> Mounting the Docker socket into a Pod poses a security risk. Please ensure you understand the implications.

## View Logs

*   **Sidecar Deployment Mode:**

    ```bash
    # View AstrBot logs
    kubectl logs -f -n astrbot-ns deployment/astrbot-stack -c astrbot

    # View NapCat logs
    kubectl logs -f -n astrbot-ns deployment/astrbot-stack -c napcat
    ```

*   **Standalone Deployment Mode:**

    ```bash
    kubectl logs -f -n astrbot-standalone-ns deployment/astrbot-standalone
    ```

## 🎉 All Done!

After deploying and exposing the service, you can access the AstrBot admin panel through the corresponding IP and port.

> The default username and password are `astrbot` and `astrbot`.