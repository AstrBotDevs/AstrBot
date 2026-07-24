import pytest

from astrbot.core.agent.semantic_state import infer_semantic_state


def _cases() -> list[tuple[str, str]]:
    """Build a bounded Chinese semantic smoke set from common user phrasings."""

    cases: list[tuple[str, str]] = []
    groups = {
        "search": [
            "今日金价",
            "金价呢",
            "今天天气",
            "最新新闻",
            "现在的黄金价格",
            "查一下最新版本",
            "这个消息可信吗",
            "实时价格是多少",
            "最近有什么新闻",
            "帮我核验这个事实",
        ],
        "vision": [
            "上面的图什么意思",
            "看看这张图片",
            "这个表情包是什么情绪",
            "解释一下截图",
            "读一下图片里的字",
            "帮我看图",
            "这张照片有什么",
            "分析刚才的图片",
            "这个梗图怎么理解",
            "看看上面那张图",
        ],
        "video": [
            "总结这个BV视频",
            "提取这个B站视频",
            "这个视频讲了什么",
            "解析一下BV1abc123",
            "看看这个哔哩哔哩视频",
            "给我视频摘要",
            "提取视频字幕",
            "视频内容概括一下",
            "这个BV值得看吗",
            "帮我总结B站内容",
        ],
        "memory": [
            "帮我记住我喜欢蓝色",
            "记住我的称呼",
            "读取我的偏好",
            "我的资料是什么",
            "以前我说过什么",
            "把这个加入记忆",
            "删除我的记忆",
            "我之前的偏好呢",
            "记一下这个习惯",
            "查看我的长期记忆",
        ],
        "audio": [
            "听一下这段语音",
            "语音里说了什么",
            "帮我转写音频",
            "理解刚才的录音",
            "分析这段声音",
            "这条语音是什么意思",
            "把音频内容告诉我",
            "识别语音里的文字",
            "听懂这个录音",
            "音频需要翻译",
        ],
    }
    for intent, phrases in groups.items():
        cases.extend((phrase, intent) for phrase in phrases)
        cases.extend((f"亚托莉，{phrase}", intent) for phrase in phrases)
    cases.extend(
        (phrase, "chat")
        for phrase in [
            "你好",
            "在吗",
            "今天心情不错",
            "哈哈哈哈",
            "你觉得呢",
            "我有点困",
            "晚安",
            "早上好",
            "谢谢你",
            "随便聊聊",
        ]
    )
    return cases


@pytest.mark.parametrize("text, expected", _cases())
def test_semantic_state_benchmark(text: str, expected: str) -> None:
    """Verify representative intent classes before any model or tool call."""

    state = infer_semantic_state(text, has_image=expected == "vision")
    assert state.intent == expected, (text, state.as_dict())
