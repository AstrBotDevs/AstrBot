import json

from astrbot.core.message.components import Json, Plain
from astrbot.core.message.json_card import (
    coalesce_prompt_with_json_cards,
    format_json_card_prompt,
    json_card_prompt_from_components,
)


def test_format_json_card_prompt_renders_detail_and_news_fields():
    detail_card = Json(
        data={
            "meta": {
                "detail_1": {
                    "title": "WeChat AI models",
                    "desc": "AI learning\nwith examples",
                    "qqdocurl": "https://example.com/detail",
                }
            }
        }
    )
    news_card = Json(
        data={
            "data": json.dumps(
                {
                    "meta": {
                        "news": {
                            "title": "Wrapped card",
                            "jumpUrl": "https://example.com/news",
                        }
                    }
                }
            )
        }
    )

    assert format_json_card_prompt(detail_card) == (
        "[Shared Card: Title: WeChat AI models; Description: AI learning "
        "with examples; URL: https://example.com/detail]"
    )
    assert format_json_card_prompt(news_card) == (
        "[Shared Card: Title: Wrapped card; URL: https://example.com/news]"
    )


def test_format_json_card_prompt_renders_real_qq_news_and_music_shares():
    news = Json(
        data={
            "app": "com.tencent.tuwen.lua",
            "bizsrc": "qqconnect.sdkshare",
            "config": {
                "ctime": 1787406967,
                "forward": 1,
                "token": "09df09c19da3bc29ea3904bd788cf073",
                "type": "normal",
            },
            "extra": {"app_type": 1, "appid": 100951776, "uin": 3606513229},
            "meta": {
                "news": {
                    "app_type": 1,
                    "appid": 100951776,
                    "ctime": 1787406967,
                    "desc": "UP主：极客湾Geekerwan-房间号：544843",
                    "jumpUrl": "https://b23.tv/SwLHhZD",
                    "preview": "https://pic.ugcimg.cn/28f871f0a9c71dc9182cf3020a57a394/jpg1",
                    "tag": "哔哩哔哩",
                    "tagIcon": "https://open.gtimg.cn/open/app_icon/00/95/17/76/100951776_100_m.png?t=1787131481",
                    "title": "每周六晚9点，陪你聊科技",
                    "uin": 3606513229,
                }
            },
            "prompt": "[分享]每周六晚9点，陪你聊科技",
            "ver": "0.0.0.1",
            "view": "news",
        }
    )
    music_jump = (
        "https://y.music.163.com/m/song?id=1467632845"
        "&uct2=dzbP%2Fk87FIBPNebq%2B66afw%3D%3D&fx-wechatnew=t1&fx-wxqd="
        "&fx-wordtest=&fx-listentest=t3&H5_DownloadVIPGift="
        "&playerUIModeId=76001&PlayerStyles_SynchronousSharing=t3"
        "&dlt=0846&app_version=9.5.25"
    )
    music = Json(
        data={
            "app": "com.tencent.music.lua",
            "bizsrc": "qqconnect.sdkshare_music",
            "config": {
                "ctime": 1787407052,
                "forward": 1,
                "token": "a1dcde2a0bce2ed282d59194d33a5f31",
                "type": "normal",
            },
            "extra": {
                "app_type": 1,
                "appid": 100495085,
                "msg_seq": 7676854833274144632,
                "uin": 2794005593,
            },
            "meta": {
                "music": {
                    "app_type": 1,
                    "appid": 100495085,
                    "ctime": 1787407052,
                    "desc": "JigglePuff/陈睿凡",
                    "jumpUrl": music_jump,
                    "musicUrl": (
                        "http://music.163.com/song/media/outer/url?"
                        "id=1467632845&userid=5130412789&sc=wm&tn="
                    ),
                    "preview": (
                        "https://p2.music.126.net/clA8qQVAYrXBCR4j7Hth-w==/"
                        "109951165193274471.jpg?imageView=1&thumbnail=600x0"
                    ),
                    "tag": "网易云音乐",
                    "tagIcon": (
                        "https://i.gtimg.cn/open/app_icon/00/49/50/85/"
                        "100495085_100_m.png"
                    ),
                    "title": "Saccharin (Acoustic)",
                    "uin": 2794005593,
                }
            },
            "prompt": "[分享]Saccharin (Acoustic)",
            "ver": "0.0.0.1",
            "view": "music",
        }
    )

    news_prompt = format_json_card_prompt(news)
    assert news_prompt == (
        "[Shared Card: Title: 每周六晚9点，陪你聊科技; "
        "Description: UP主：极客湾Geekerwan-房间号：544843; "
        "URL: https://b23.tv/SwLHhZD; Tag: 哔哩哔哩]"
    )
    assert "09df09c19da3bc29ea3904bd788cf073" not in news_prompt
    assert "100951776" not in news_prompt

    music_prompt = format_json_card_prompt(music)
    assert music_prompt.startswith(
        "[Shared Card: Title: Saccharin (Acoustic); "
        "Description: JigglePuff/陈睿凡; URL: "
    )
    assert "Tag: 网易云音乐]" in music_prompt
    assert music_jump[:200] + "..." in music_prompt
    assert "a1dcde2a0bce2ed282d59194d33a5f31" not in music_prompt
    assert "musicUrl" not in music_prompt
    assert "5130412789" not in music_prompt


def test_format_json_card_prompt_keeps_unknown_cards():
    assert (
        format_json_card_prompt(Json(data={"app": "com.example.unknown"}))
        == "[Shared Card]"
    )


def test_format_json_card_prompt_truncates_long_fields():
    rendered = format_json_card_prompt(
        Json(data={"meta": {"news": {"desc": "a" * 201}}})
    )

    assert f"Description: {'a' * 200}..." in rendered
    assert "a" * 201 not in rendered


def test_json_card_prompt_from_components_joins_cards_and_ignores_other_types():
    cards = [
        Plain("hello"),
        Json(data={"meta": {"news": {"title": "One"}}}),
        Json(data={"app": "unknown"}),
    ]

    assert json_card_prompt_from_components(cards) == (
        "[Shared Card: Title: One] [Shared Card]"
    )
    assert json_card_prompt_from_components([]) == ""
    assert json_card_prompt_from_components(None) == ""
    assert json_card_prompt_from_components("not-a-chain") == ""


def test_coalesce_prompt_with_json_cards_only_fills_blank_prompts():
    event = type(
        "Event",
        (),
        {
            "message_obj": type(
                "MessageObj",
                (),
                {"message": [Json(data={"meta": {"news": {"title": "News"}}})]},
            )()
        },
    )()

    assert coalesce_prompt_with_json_cards(event, "keep me") == "keep me"
    assert coalesce_prompt_with_json_cards(event, "   ") == "[Shared Card: Title: News]"
    assert coalesce_prompt_with_json_cards(event, "") == "[Shared Card: Title: News]"
