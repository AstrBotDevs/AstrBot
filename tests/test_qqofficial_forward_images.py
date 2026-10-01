from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)

# 真实抓包的合并转发载荷：QQ 只把附件摊平成纯文本，没有 attachments/msg_elements。
FORWARD_CONTENT = (
    "[linyesantan的聊天记录]\n"
    "=== 消息 1 ===\n[发送者] linyesantan\n"
    "[附件1] 类型:图片 文件名:a.jpg 尺寸:1380x776 大小:38.6KB "
    "URL:https://multimedia.nt.qq.com.cn/download?appid=1406&fileid=AAA\n"
    "\n=== 消息 2 ===\n[发送者] linyesantan\n"
    "[附件1] 类型:图片 文件名:b.jpg 尺寸:714x669 大小:64.8KB "
    "URL:https://multimedia.nt.qq.com.cn/download?appid=1406&fileid=BBB\n"
    "\n=== 消息 3 ===\n[发送者] linyesantan\n"
    "[附件1] 类型:文件 文件名:c.pdf 大小:1.0MB "
    "URL:https://multimedia.nt.qq.com.cn/download?appid=1406&fileid=CCC\n"
)


def test_extracts_forward_image_urls_in_order():
    urls = QQOfficialPlatformAdapter._extract_forward_image_urls(FORWARD_CONTENT)

    assert urls == [
        "https://multimedia.nt.qq.com.cn/download?appid=1406&fileid=AAA",
        "https://multimedia.nt.qq.com.cn/download?appid=1406&fileid=BBB",
    ]


def test_keeps_urls_ending_with_backslash_or_n():
    # rstrip("\\n") 会削掉 URL 末尾的字面反斜杠和字母 n
    for suffix in ("n", "\\n"):
        url = f"https://example.com/image{suffix}"
        content = f"[附件1] 类型:图片 文件名:i.jpg URL:{url}"

        assert QQOfficialPlatformAdapter._extract_forward_image_urls(content) == [url]


def test_dedupes_repeated_urls():
    line = "[附件1] 类型:图片 文件名:a.jpg URL:https://example.com/a.jpg"

    urls = QQOfficialPlatformAdapter._extract_forward_image_urls(f"{line}\n{line}\n")

    assert urls == ["https://example.com/a.jpg"]


def test_ignores_non_image_attachments_and_bare_urls():
    content = (
        "[附件1] 类型:文件 文件名:a.pdf URL:https://example.com/a.pdf\n"
        "看看这个 https://example.com/bare.png\n"
    )

    assert QQOfficialPlatformAdapter._extract_forward_image_urls(content) == []


def test_caps_the_number_of_forward_images():
    lines = [
        f"[附件1] 类型:图片 文件名:{i}.jpg URL:https://example.com/{i}.jpg"
        for i in range(QQOfficialPlatformAdapter._MAX_FORWARD_IMAGES + 5)
    ]

    urls = QQOfficialPlatformAdapter._extract_forward_image_urls("\n".join(lines))

    assert len(urls) == QQOfficialPlatformAdapter._MAX_FORWARD_IMAGES
