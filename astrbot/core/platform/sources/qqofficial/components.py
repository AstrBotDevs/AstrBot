"""QQ 官方平台消息按钮（Keyboard）组件。

字段集对齐 botpy 的 TypedDict 定义，
发送时产出的 dict 可直接作为 QQ OpenAPI `keyboard` 字段。
"""

from __future__ import annotations

import sys
from typing import ClassVar

from astrbot.core.message.components import BaseMessageComponent

if sys.version_info >= (3, 14):
    from pydantic import BaseModel
else:
    from pydantic.v1 import BaseModel


class QQCPermission(BaseModel):
    """按钮可操作权限。

    permission.type:
      0 - 指定用户可操作（需 specify_user_ids）
      1 - 仅管理员可操作
      2 - 所有人可操作
      3 - 指定身份组可操作（需 specify_role_ids）
    """

    type: int = 2
    specify_user_ids: list[str] | None = None
    specify_role_ids: list[str] | None = None

    def to_dict(self) -> dict:
        data: dict = {"type": self.type}
        if self.specify_user_ids is not None:
            data["specify_user_ids"] = self.specify_user_ids
        if self.specify_role_ids is not None:
            data["specify_role_ids"] = self.specify_role_ids
        return data


class QQCButton(BaseMessageComponent):
    """QQ 官方平台按钮组件。

    action_type:
      0 - 跳转 URL（data 为 URL）
      1 - 回调（data 为 callback 数据，点击后服务端收 INTERACTION_CREATE）
      2 - 发送命令（data 为命令文本）

    style:
      0 - 灰色边框（secondary）
      1 - 蓝色边框（primary，默认）
    """

    type: str = "qqc_button"  # type: ignore[assignment]
    id: str = ""
    label: str = ""
    visited_label: str | None = None
    style: int = 1
    action_type: int = 1
    data: str = ""
    reply: bool = False
    enter: bool = False
    anchor: int | None = None
    unsupport_tips: str | None = None
    permission: QQCPermission | None = None
    click_limit: int | None = None  # 已废弃
    at_bot_show_channel_list: bool | None = None  # 已废弃

    def __init__(
        self,
        id: str,
        label: str,
        data: str = "",
        visited_label: str | None = None,
        style: int = 1,
        action_type: int = 1,
        reply: bool = False,
        enter: bool = False,
        anchor: int | None = None,
        unsupport_tips: str | None = None,
        permission: QQCPermission | None = None,
        click_limit: int | None = None,
        at_bot_show_channel_list: bool | None = None,
    ) -> None:
        super().__init__(
            id=id,
            label=label,
            visited_label=visited_label if visited_label is not None else label,
            style=style,
            action_type=action_type,
            data=data,
            reply=reply,
            enter=enter,
            anchor=anchor,
            unsupport_tips=unsupport_tips,
            permission=permission,
            click_limit=click_limit,
            at_bot_show_channel_list=at_bot_show_channel_list,
        )

    def to_dict(self) -> dict:  # type: ignore[override]
        render_data = {
            "label": self.label,
            "visited_label": self.visited_label,
            "style": self.style,
        }
        action: dict = {
            "type": self.action_type,
            "data": self.data,
            "permission": (self.permission or QQCPermission(type=2)).to_dict(),
        }
        if self.reply:
            action["reply"] = True
        if self.enter:
            action["enter"] = True
        if self.anchor is not None:
            action["anchor"] = self.anchor
        if self.unsupport_tips is not None:
            action["unsupport_tips"] = self.unsupport_tips
        if self.click_limit is not None:
            action["click_limit"] = self.click_limit
        if self.at_bot_show_channel_list is not None:
            action["at_bot_show_channel_list"] = self.at_bot_show_channel_list
        return {
            "id": self.id,
            "render_data": render_data,
            "action": action,
        }


class QQCKeyboard(BaseMessageComponent):
    """自定义按钮键盘。

    rows: 二维列表，每行是一组按钮。QQ 限制最多 5 行、每行最多 5 个按钮。
    """

    type: str = "qqc_keyboard"  # type: ignore[assignment]
    rows: list[list[QQCButton]]

    MAX_ROWS: ClassVar[int] = 5
    MAX_BUTTONS_PER_ROW: ClassVar[int] = 5

    def __init__(self, rows: list[list[QQCButton]]) -> None:
        if len(rows) > self.MAX_ROWS:
            raise ValueError(f"QQCKeyboard 行数超限：{len(rows)} > {self.MAX_ROWS}")
        for idx, row in enumerate(rows):
            if len(row) > self.MAX_BUTTONS_PER_ROW:
                raise ValueError(
                    f"QQCKeyboard 第 {idx + 1} 行按钮数超限："
                    f"{len(row)} > {self.MAX_BUTTONS_PER_ROW}"
                )
        super().__init__(rows=rows)

    def to_dict(self) -> dict:  # type: ignore[override]
        return {
            "content": {
                "rows": [
                    {"buttons": [btn.to_dict() for btn in row]} for row in self.rows
                ],
            },
        }
