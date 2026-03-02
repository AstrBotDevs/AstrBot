import json
from pathlib import Path

import pytest

from astrbot.core.platform.sources.kook.kook_types import (
    ActionGroupModule,
    ButtonElement,
    ContextModule,
    CountdownModule,
    DividerModule,
    FileModule,
    HeaderModule,
    ImageElement,
    ImageGroupModule,
    InviteModule,
    KmarkdownElement,
    KookCardMessage,
    ParagraphStructure,
    PlainTextElement,
    SectionModule,
    KookCardMessageContainer,
)
from tests.test_kook.shared import TEST_DATA_DIR


def test_kook_card_message_container_append():
    container = KookCardMessageContainer()
    container.append(KookCardMessage())
    assert len(container) == 1


@pytest.mark.parametrize(
    "input, expect_container_length",
    [
        ([KookCardMessage()], 1),
        ([KookCardMessage()] * 2, 2),
    ],
)
def test_kook_card_message_container_to_json(
    input: list[KookCardMessage], expect_container_length: int
):
    container = KookCardMessageContainer(input)
    json_output = container.to_json()
    output = json.loads(json_output)
    assert isinstance(output, list)
    assert len(output) == expect_container_length


def test_all_kook_card_type():
    expect_json_data = Path(TEST_DATA_DIR / "kook_card_data.json").read_text(
        encoding="utf-8"
    )
    json_output = KookCardMessage(
        theme="info",
        size="lg",
        modules=[
            HeaderModule(text=PlainTextElement(content="test1")),
            SectionModule(text=KmarkdownElement(content="test2")),
            DividerModule(),
            SectionModule(
                text=ParagraphStructure(
                    cols=2,
                    fields=[
                        KmarkdownElement(content="test3"),
                        KmarkdownElement(content="**test4**"),
                    ],
                )
            ),
            ImageGroupModule(
                elements=[
                    ImageElement(
                        src="https://img.kookapp.cn/attachments/2023-01/05/63b645851ff19.svg"
                    )
                ]
            ),
            FileModule(
                src="https://img.kookapp.cn/attachments/2023-01/05/63b645851ff19.svg",
                title="test5",
                type="file",
            ),
            CountdownModule(
                endTime=1772343427360,
                startTime=1772343378259,
                mode="second",
            ),
            ActionGroupModule(
                elements=[
                    ButtonElement(
                        value="btn_clicked",
                        text="点我测试回调",
                        click="return-val",
                        theme="primary",
                    ),
                    ButtonElement(
                        value="https://www.kookapp.cn",
                        text="访问官网",
                        click="link",
                        theme="danger",
                    ),
                ]
            ),
            ContextModule(elements=[PlainTextElement(content="test6")]),
            InviteModule(code="test7"),
        ],
    ).to_json(indent=4, ensure_ascii=False)
    assert json_output == expect_json_data
