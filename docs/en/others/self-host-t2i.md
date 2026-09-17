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

After deployment, go to AstrBot Dashboard -> Settings -> Appearance. Under "Text-to-Image," set `Text-to-Image Strategy` to `remote`. The `Text-to-Image Service API Endpoint` field will then appear; set it to the URL of your deployed service.

> If you deployed AstrBot using the Docker tutorial in this documentation, the URL should be `http://<t2i-service-container-name>:8999`.

> If you deployed on the same machine as AstrBot, the URL should be `http://localhost:8999`.
