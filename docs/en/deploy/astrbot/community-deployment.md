# Community-Provided Deployment Methods

> [!WARNING]
> AstrBot official does not guarantee the security and stability of these deployment methods.

## Linux One-Click Deployment Script

Use `curl` to download the script and execute it using `bash`:

```bash
bash <(curl -sSL https://raw.githubusercontent.com/zhende1113/Antlia/refs/heads/main/Script/AstrBot/Antlia.sh)
```

If your system does not have `curl`, you can use `wget`:

```bash
wget -qO- https://raw.githubusercontent.com/zhende1113/Antlia/refs/heads/main/Script/AstrBot/Antlia.sh | bash
```

Repository Address: [zhende1113/Antlia](https://github.com/zhende1113/Antlia/)

## Linux One-Click Deployment Script (Based on Docker)

Supports AstrBot / NapCat.

> [!TIP]
> Use `sudo` for elevated permissions if you have insufficient privileges.

### Using `curl`

```bash
curl -sSL https://raw.githubusercontent.com/railgun19457/AstrbotScript/main/AstrbotScript.sh -o AstrbotScript.sh
chmod +x AstrbotScript.sh
sudo ./AstrbotScript.sh
```

### Using `wget`

```bash
wget -qO AstrbotScript.sh https://raw.githubusercontent.com/railgun19457/AstrbotScript/main/AstrbotScript.sh
chmod +x AstrbotScript.sh
sudo ./AstrbotScript.sh
```

> [!note]
> `sudo ./AstrbotScript.sh --no-color (Optional: disable color output)`

__Repository Address: [railgun19457/AstrbotScript](https://github.com/railgun19457/AstrbotScript)__

## AstrBot Android Deployment

Refer to [zz6zz666/AstrBot-Android-App](https://github.com/zz6zz666/AstrBot-Android-App)