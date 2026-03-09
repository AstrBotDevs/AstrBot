# Self-host the Text-to-Image Service

AstrBot uses [AstrBotDevs/astrbot-t2i-service](https://github.com/AstrBotDevs/astrbot-t2i-service) as the default text-to-image service. The default service endpoints are:

```plain
https://t2i.soulter.top/text2img
https://t2i.rcfortress.site/text2img
```

This interface can ensure normal response for most of the time. However, due to the deployment of servers in New York, the response speed may be slower in some areas.

> [!TIP]
> If you'd like to support us to help pay for server costs, please consider supporting us on [Afdian](https://afdian.com/a/astrbot_team).

You can choose to self-host the text-to-image service to improve response speed.

```bash
docker run -itd -p 8999:8999 soulter/astrbot-t2i-service:latest
```

After deployment, go to AstrBot Dashboard -> Config -> System, and change `Text-to-Image Service API Endpoint` to the URL you deployed (as shown below).

> If you deployed AstrBot using the Docker tutorial in this documentation, the URL should be `http://<t2i-service-container-name>:8999`.

> If you deployed on the same machine as AstrBot, the URL should be `http://localhost:8999`.

<img width="589" height="255" alt="image" src="https://github.com/user-attachments/assets/5ef09db2-1a33-440c-9986-c7b544325e34" />

