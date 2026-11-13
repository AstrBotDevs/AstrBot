# Deploy AstrBot with Kubernetes

> [!WARNING]
> You can deploy AstrBot in a high-availability setup using Kubernetes (K8s), allowing it to automatically recover from failures.
>
> Due to the current use of an SQLite database, this deployment does not support horizontal scaling with multiple replicas.
>
> The following tutorial assumes that you have `kubectl` installed and configured, and that you can connect to your K8s cluster.

## Prerequisites

Before you begin, make sure your Kubernetes cluster meets the following conditions:

1.  **Default StorageClass**: Used to dynamically create `PersistentVolumeClaim` (PVC). You can check this with `kubectl get sc`. If you don't have one, you need to manually create a `PersistentVolume` (PV) or install a corresponding storage plugin (e.g., `nfs-client-provisioner`).
2.  **Network Access**: Ensure that your cluster nodes can pull images from `docker.io` or your specified image repository.

## Deployment Methods

The manifests live in the `k8s/astrbot` directory and deploy only AstrBot. Deploy protocol implementations such as OneBot v11 separately and connect them to AstrBot.

---

### Deploy AstrBot

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

If you have difficulty pulling the `soulter/astrbot:latest` image, you can manually edit the corresponding `02-deployment.yaml` file and replace the `image` field with a domestic mirror address, for example:

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

```bash
kubectl logs -f -n astrbot-standalone-ns deployment/astrbot-standalone
```

## 🎉 All Done!

After deploying and exposing the service, you can access the AstrBot admin panel through the corresponding IP and port.

> New users must use the random password printed in the startup logs for the first login. Use the username shown in the logs (usually `astrbot`) and change it after logging in.
