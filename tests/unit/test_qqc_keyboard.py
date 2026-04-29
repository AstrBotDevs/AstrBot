"""Tests for QQ official platform keyboard components (QQCKeyboard / QQCButton)."""

import pytest

from astrbot.core.platform.sources.qqofficial.components import (
    QQCButton,
    QQCKeyboard,
    QQCPermission,
)


class TestQQCPermission:
    def test_default_is_everyone(self):
        perm = QQCPermission()
        assert perm.to_dict() == {"type": 2}

    def test_specify_users(self):
        perm = QQCPermission(type=0, specify_user_ids=["u1", "u2"])
        assert perm.to_dict() == {
            "type": 0,
            "specify_user_ids": ["u1", "u2"],
        }

    def test_specify_roles(self):
        perm = QQCPermission(type=3, specify_role_ids=["r1"])
        assert perm.to_dict() == {"type": 3, "specify_role_ids": ["r1"]}

    def test_empty_lists_are_omitted_when_none(self):
        perm = QQCPermission(type=1)
        assert "specify_user_ids" not in perm.to_dict()
        assert "specify_role_ids" not in perm.to_dict()


class TestQQCButton:
    def test_minimal_callback_button(self):
        btn = QQCButton(id="1", label="点我", data="payload")
        d = btn.to_dict()
        assert d["id"] == "1"
        assert d["render_data"] == {
            "label": "点我",
            "visited_label": "点我",
            "style": 1,
        }
        assert d["action"]["type"] == 1
        assert d["action"]["data"] == "payload"
        assert d["action"]["permission"] == {"type": 2}

    def test_url_button(self):
        btn = QQCButton(
            id="url",
            label="官网",
            data="https://example.com",
            action_type=0,
            style=0,
        )
        d = btn.to_dict()
        assert d["render_data"]["style"] == 0
        assert d["action"]["type"] == 0
        assert d["action"]["data"] == "https://example.com"

    def test_visited_label_default_follows_label(self):
        btn = QQCButton(id="1", label="确认")
        assert btn.to_dict()["render_data"]["visited_label"] == "确认"

    def test_visited_label_override(self):
        btn = QQCButton(id="1", label="确认", visited_label="已确认")
        assert btn.to_dict()["render_data"]["visited_label"] == "已确认"

    def test_optional_action_fields_omitted_when_default(self):
        btn = QQCButton(id="1", label="x")
        action = btn.to_dict()["action"]
        for optional in (
            "reply",
            "enter",
            "anchor",
            "unsupport_tips",
            "click_limit",
            "at_bot_show_channel_list",
        ):
            assert optional not in action

    def test_optional_action_fields_emitted_when_set(self):
        btn = QQCButton(
            id="1",
            label="x",
            reply=True,
            enter=True,
            anchor=1,
            unsupport_tips="升级客户端",
            click_limit=3,
            at_bot_show_channel_list=True,
        )
        action = btn.to_dict()["action"]
        assert action["reply"] is True
        assert action["enter"] is True
        assert action["anchor"] == 1
        assert action["unsupport_tips"] == "升级客户端"
        assert action["click_limit"] == 3
        assert action["at_bot_show_channel_list"] is True

    def test_custom_permission(self):
        btn = QQCButton(
            id="1",
            label="仅管理员",
            permission=QQCPermission(type=1),
        )
        assert btn.to_dict()["action"]["permission"] == {"type": 1}

    def test_command_button(self):
        """action_type=2 向当前会话发送命令。"""
        btn = QQCButton(id="cmd", label="/help", data="/help", action_type=2)
        action = btn.to_dict()["action"]
        assert action["type"] == 2
        assert action["data"] == "/help"


class TestQQCKeyboard:
    def test_single_row_single_button(self):
        kb = QQCKeyboard(rows=[[QQCButton(id="1", label="a", data="x")]])
        d = kb.to_dict()
        assert d == {
            "content": {
                "rows": [
                    {
                        "buttons": [
                            {
                                "id": "1",
                                "render_data": {
                                    "label": "a",
                                    "visited_label": "a",
                                    "style": 1,
                                },
                                "action": {
                                    "type": 1,
                                    "data": "x",
                                    "permission": {"type": 2},
                                },
                            }
                        ]
                    }
                ]
            }
        }

    def test_multi_row_structure(self):
        kb = QQCKeyboard(
            rows=[
                [
                    QQCButton(id="1", label="确认", data="ok"),
                    QQCButton(id="2", label="取消", data="cancel"),
                ],
                [QQCButton(id="3", label="官网", data="https://x", action_type=0)],
            ]
        )
        d = kb.to_dict()
        rows = d["content"]["rows"]
        assert len(rows) == 2
        assert len(rows[0]["buttons"]) == 2
        assert len(rows[1]["buttons"]) == 1
        assert rows[1]["buttons"][0]["action"]["type"] == 0

    def test_too_many_rows_raises(self):
        row = [QQCButton(id="x", label="x")]
        with pytest.raises(ValueError, match="行数超限"):
            QQCKeyboard(rows=[row] * (QQCKeyboard.MAX_ROWS + 1))

    def test_too_many_buttons_per_row_raises(self):
        buttons = [
            QQCButton(id=str(i), label=str(i))
            for i in range(QQCKeyboard.MAX_BUTTONS_PER_ROW + 1)
        ]
        with pytest.raises(ValueError, match="按钮数超限"):
            QQCKeyboard(rows=[buttons])

    def test_at_row_limit_is_ok(self):
        row = [QQCButton(id="x", label="x")]
        kb = QQCKeyboard(rows=[row] * QQCKeyboard.MAX_ROWS)
        assert len(kb.to_dict()["content"]["rows"]) == QQCKeyboard.MAX_ROWS

    def test_at_column_limit_is_ok(self):
        buttons = [
            QQCButton(id=str(i), label=str(i))
            for i in range(QQCKeyboard.MAX_BUTTONS_PER_ROW)
        ]
        kb = QQCKeyboard(rows=[buttons])
        assert (
            len(kb.to_dict()["content"]["rows"][0]["buttons"])
            == QQCKeyboard.MAX_BUTTONS_PER_ROW
        )

    def test_empty_rows_allowed(self):
        """空 keyboard 不报错（上层负责判断是否有意义）。"""
        kb = QQCKeyboard(rows=[])
        assert kb.to_dict() == {"content": {"rows": []}}
