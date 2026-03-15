# Agent Sandbox Environment ⛵️

> [!TIP]
> This feature is currently in technical preview and may have some bugs. If you encounter any issues, please submit an issue on [GitHub](https://github.com/AstrBotDevs/AstrBot/issues).

Starting from version `v4.12.0`, AstrBot introduced the Agent sandbox environment to replace the previous code executor functionality. The sandbox environment provides Agents with safer and more flexible code execution and automation capabilities.

![](https://files.astrbot.app/docs/source/images/astrbot-agent-sandbox/image.png)

## Enabling the Sandbox Environment

Currently, the sandbox environment only supports running through Docker. We are currently using the [Shipyard](https://github.com/AstrBotDevs/shipyard) project as AstrBot's sandbox environment driver. In the future, we will support more types of sandbox environment drivers, such as e2b.

### Deploying AstrBot and Shipyard with Docker Compose

If you haven't deployed AstrBot yet, or want to switch to our recommended deployment method with sandbox environment, we recommend using Docker Compose to deploy AstrBot with the following code:

```bash
git clone https://github.com/AstrBotDevs/AstrBot
cd AstrBot
# Modify the environment variable configuration in the compose-with-shipyard.yml file, such as Shipyard's access token, etc.
docker compose -f compose-with-shipyard.yml up -d
docker pull soulter/shipyard-ship:latest
```

This will start a Docker Compose service that includes AstrBot main program and the sandbox environment.

### Deploying Shipyard Separately

If you have already deployed AstrBot but haven't deployed the sandbox environment, you can deploy Shipyard separately.

Code as follows:

```bash
mkdir astrbot-shipyard
cd astrbot-shipyard
wget https://raw.githubusercontent.com/AstrBotDevs/shipyard/refs/heads/main/pkgs/bay/docker-compose.yml -O docker-compose.yml
# Modify the environment variable configuration in the compose-with-shipyard.yml file, such as Shipyard's access token, etc.
docker compose -f docker-compose.yml up -d
# pull the latest Shipyard ship image
docker pull soulter/shipyard-ship:latest
```

After successful deployment, the above command will start a Shipyard service that listens on `http://<your-host>:8156` by default.

> [!TIP]
> If you deploy AstrBot using Docker, you can also modify the Compose file above to place Shipyard's network in the same Docker network as AstrBot, so you don't need to expose Shipyard's port to the host machine.

## Configuring AstrBot to Use the Sandbox Environment

In the AstrBot console, go to the "Configuration Files" page and find "Agent Sandbox Environment", then enable the sandbox environment switch.

In the configuration options that appear:

For `Shipyard API Endpoint`, if you use the Docker Compose deployment method above, fill in `http://shipyard:8156`. If you deployed Shipyard separately, please fill in the corresponding address, such as `http://<your-host>:8156`.

For `Shipyard Access Token`, please fill in the access token you configured when deploying Shipyard.

For `Shipyard Ship Lifetime (seconds)`, this defines the lifetime of each sandbox environment instance, with a default value of 3600 seconds (1 hour). You can adjust this value as needed.

For `Shipyard Ship Session Reuse Limit`, this defines the maximum number of sessions that each sandbox environment instance can reuse, with a default value of 10. This means that 10 sessions will share the same sandbox environment instance. You can adjust this value as needed.

After configuring, click the "Save" button at the bottom of the page to save the configuration.

## About `Shipyard Ship Lifetime (seconds)`

The lifetime of a sandbox environment instance defines the maximum time each instance can exist before being destroyed. This setting needs to be determined based on your usage scenario and resources.

- When a new session joins an existing sandbox environment instance, the instance will automatically extend its lifetime to the TTL requested by this session.
- When an operation is performed on a sandbox environment instance, the instance will automatically extend its lifetime to the current time plus the TTL.

## About Data Persistence in the Sandbox Environment

Shipyard allocates a working directory for each session under the `/home/<unique session ID>` directory.

Shipyard automatically mounts the /home directory in the sandbox environment to the `${PWD}/data/shipyard/ship_mnt_data` directory on the host machine. When a sandbox environment instance is destroyed, if a session continues to request the sandbox, Shipyard will recreate a new sandbox environment instance and remount the previously persisted data to ensure data continuity.
