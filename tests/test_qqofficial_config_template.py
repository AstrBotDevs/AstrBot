from astrbot.core.config.default import CONFIG_METADATA_2


def _platform_template(name: str) -> dict:
    templates = CONFIG_METADATA_2["platform_group"]["metadata"]["platform"][
        "config_template"
    ]
    return templates[name]


def test_qqofficial_templates_both_expose_use_markdown():
    # 两个 QQ 官方适配器的配置模板必须一致地暴露 use_markdown 字段，
    # 否则新建 Webhook 平台时 WebUI 看不到/保存不了该配置（评审 #9914 指出）。
    websocket = _platform_template("QQ 官方机器人(Websocket, 推荐)")
    webhook = _platform_template("QQ 官方机器人(Webhook)")

    assert websocket["use_markdown"] is True
    assert webhook["use_markdown"] is True
