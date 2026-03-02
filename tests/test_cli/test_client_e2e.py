"""CLI Client 端到端测试

不使用 mock，直接通过真实 socket 连接到运行中的 AstrBot 服务端。
测试前提：AstrBot 已启动并开启 CLI 平台适配器（socket 模式）。

设计原则：
  - 零重复：每个命令在整个文件中只发送一次
  - 行为测试与命令测试分离：行为测试（稳定性/并发）不重复验证命令内容
  - 纯函数用 fake 数据，不调服务端

运行方式（已从默认 pytest 排除，需手动指定）：
  pytest tests/test_cli/test_client_e2e.py -v --override-ini="addopts="
"""

import os
import time

import pytest

from astrbot.cli.client.connection import (
    call_tool,
    get_data_path,
    get_logs,
    get_session_history,
    list_session_conversations,
    list_sessions,
    list_tools,
    load_auth_token,
    load_connection_info,
    send_message,
)
from astrbot.cli.client.output import format_response


def _server_reachable() -> bool:
    """检查服务端是否可达（整个文件唯一的探测调用）"""
    try:
        resp = send_message("/help", timeout=10.0)
        return resp.get("status") == "success"
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(
        not _server_reachable(),
        reason="AstrBot 服务端未运行，跳过端到端测试",
    ),
    pytest.mark.e2e,
]


# ============================================================
# 第一层：连接基础设施（纯本地检查，0 次服务端调用）
# ============================================================


class TestConnectionInfra:
    """验证本地配置文件：数据目录、连接信息、Token"""

    def test_data_path_exists(self):
        data_dir = get_data_path()
        assert os.path.isdir(data_dir), f"数据目录不存在: {data_dir}"

    def test_connection_info_valid(self):
        data_dir = get_data_path()
        info = load_connection_info(data_dir)
        assert info is not None, ".cli_connection 不存在"
        assert info["type"] in ("unix", "tcp"), f"未知连接类型: {info['type']}"
        if info["type"] == "tcp":
            assert "host" in info and isinstance(info["port"], int)
        elif info["type"] == "unix":
            assert "path" in info

    def test_auth_token_configured(self):
        token = load_auth_token()
        assert token and len(token) > 8, "Token 未配置或过短"


# ============================================================
# 第二层：命令管道（每个命令只调用一次）
#
# 服务端调用：/help, /sid ×2, /model, /key, /plugin ls,
#             /plugin help builtin_commands = 8 次
# ============================================================


class TestCommandPipeline:
    """每个内置命令只测一次，一次性验证结构+内容+认证"""

    def test_help(self):
        """/help — 响应结构、内容、延迟、认证（最全面的单命令测试）"""
        start = time.time()
        resp = send_message("/help")
        elapsed = time.time() - start

        assert resp["status"] == "success"
        assert "response" in resp and "images" in resp and "request_id" in resp
        assert isinstance(resp["images"], list)
        assert len(resp["request_id"]) > 0
        assert "/help" in resp["response"]
        assert elapsed < 10.0, f"延迟过大: {elapsed:.2f}s"
        assert resp.get("error_code") != "AUTH_FAILED"

    def test_sid_and_consistency(self):
        """/sid — 内容正确 + 两次调用返回相同结果（会话一致性）"""
        resp1 = send_message("/sid")
        resp2 = send_message("/sid")
        assert resp1["status"] == "success" and resp2["status"] == "success"
        text = resp1["response"]
        assert "cli_session" in text or "cli_user" in text or "UMO" in text
        assert resp1["response"] == resp2["response"], "会话信息不一致"

    def test_model(self):
        """/model — 模型列表"""
        resp = send_message("/model")
        assert resp["status"] == "success"
        assert resp["response"] or resp["images"]

    def test_key(self):
        """/key — Key 信息"""
        resp = send_message("/key")
        assert resp["status"] == "success"
        text = resp["response"]
        assert "Key" in text or "key" in text.lower() or "当前" in text

    def test_plugin_ls(self):
        """/plugin ls — 插件列表"""
        resp = send_message("/plugin ls")
        assert resp["status"] == "success"
        assert "插件" in resp["response"] or "plugin" in resp["response"].lower()

    def test_plugin_help(self):
        """/plugin help — 指定插件帮助"""
        resp = send_message("/plugin help builtin_commands")
        assert resp["status"] == "success"
        text = resp["response"]
        assert "指令" in text or "帮助" in text or "help" in text.lower()


# ============================================================
# 第三层：会话管理生命周期
#
# 服务端调用：/new, /rename, /ls, /reset, /history, /del,
#             /new, /switch 1, /del = 9 次
# ============================================================


class TestSessionManagement:
    """会话操作：创建、重命名、列表、重置、历史、删除、切换"""

    def test_full_lifecycle(self):
        """new → rename → ls → reset → history → del"""
        resp = send_message("/new")
        assert resp["status"] == "success"

        resp = send_message("/rename e2e_lifecycle_test")
        assert resp["status"] == "success"

        resp = send_message("/ls")
        assert resp["status"] == "success"
        assert "e2e_lifecycle_test" in resp["response"]

        resp = send_message("/reset")
        assert resp["status"] == "success"

        resp = send_message("/history")
        assert resp["status"] == "success"

        resp = send_message("/del")
        assert resp["status"] == "success"

    def test_switch(self):
        """new → switch → del"""
        send_message("/new")
        resp = send_message("/switch 1")
        assert resp["status"] == "success"
        assert "切换" in resp["response"]
        send_message("/del")


# ============================================================
# 第四层：日志子系统
#
# 服务端调用：get_logs ×3 = 3 次
# ============================================================


class TestLogSubsystem:
    """日志获取、级别过滤、模式过滤"""

    def test_get_logs(self):
        resp = get_logs(lines=10)
        assert resp["status"] == "success"
        assert "response" in resp

    def test_level_filter(self):
        resp = get_logs(lines=50, level="INFO")
        assert resp["status"] == "success"
        text = resp.get("response", "")
        for line in text.strip().split("\n"):
            if line.strip():
                assert "[INFO]" in line, f"非 INFO 日志: {line}"

    def test_pattern_filter(self):
        resp = get_logs(lines=50, pattern="CLI")
        assert resp["status"] == "success"
        text = resp.get("response", "")
        for line in text.strip().split("\n"):
            if line.strip():
                assert "CLI" in line or "cli" in line


# ============================================================
# 第4.5层：函数工具管理（通过 socket action 协议，2 次服务端调用）
# ============================================================


class TestFunctionTools:
    """测试 list_tools 和 call_tool socket action"""

    def test_list_tools(self):
        """列出所有注册的函数工具"""
        resp = list_tools()
        assert resp["status"] == "success"
        # tools 可能在 tools 字段或 response 字段
        tools = resp.get("tools", [])
        if not tools:
            import json

            raw = resp.get("response", "")
            if raw:
                tools = json.loads(raw)
        # 应该是列表类型
        assert isinstance(tools, list)
        # 每个工具应有 name 字段
        for t in tools:
            assert "name" in t

    def test_call_nonexistent_tool(self):
        """调用不存在的工具应返回错误"""
        resp = call_tool("__nonexistent_tool_xyz__")
        assert resp["status"] == "error"
        assert "未找到" in resp.get("error", "")


# ============================================================
# 第5层：跨会话浏览（通过 socket action 协议）
#
# 服务端调用：list_sessions ×2, list_session_conversations ×1,
#             get_session_history ×2 = 5 次
# ============================================================


class TestCrossSessionBrowse:
    """跨会话浏览功能端到端测试"""

    def test_list_sessions(self):
        """列出所有会话 — 响应结构完整"""
        resp = list_sessions()
        assert resp["status"] == "success"
        assert "sessions" in resp
        assert isinstance(resp["sessions"], list)
        assert "total" in resp
        assert isinstance(resp["total"], int)
        assert "total_pages" in resp
        # 至少应有 CLI 管理员会话
        if resp["total"] > 0:
            s = resp["sessions"][0]
            assert "session_id" in s
            assert "conversation_id" in s

    def test_list_sessions_pagination(self):
        """会话列表分页参数正确回传"""
        resp = list_sessions(page=1, page_size=5)
        assert resp["status"] == "success"
        assert resp["page"] == 1
        assert resp["page_size"] == 5
        assert "total_pages" in resp

    def test_list_sessions_platform_filter(self):
        """按平台过滤 — 不崩溃，结果与总数一致"""
        resp = list_sessions(platform="cli")
        assert resp["status"] == "success"
        for s in resp["sessions"]:
            assert s["session_id"].startswith("cli:")

    def test_list_sessions_search(self):
        """搜索过滤 — 不崩溃"""
        resp = list_sessions(search_query="cli_session")
        assert resp["status"] == "success"

    def test_list_session_conversations(self):
        """列出 CLI 管理员会话的对话列表"""
        resp = list_session_conversations("cli:FriendMessage:cli_session")
        assert resp["status"] == "success"
        assert "conversations" in resp
        assert isinstance(resp["conversations"], list)
        assert "current_cid" in resp
        # 每个对话应有 cid/title/is_current
        for c in resp["conversations"]:
            assert "cid" in c
            assert "title" in c
            assert "is_current" in c

    def test_list_session_conversations_empty(self):
        """不存在的会话 — 返回空对话列表，不报错"""
        resp = list_session_conversations("nonexistent:FriendMessage:no_one")
        assert resp["status"] == "success"
        assert resp["conversations"] == []

    def test_get_session_history_admin(self):
        """获取管理员 CLI 会话的聊天记录 — 新格式验证"""
        resp = get_session_history("cli:FriendMessage:cli_session")
        assert resp["status"] == "success"
        assert "history" in resp
        assert isinstance(resp["history"], list)
        assert "total_pages" in resp
        assert "total" in resp
        # 验证消息格式（每条是 dict 含 role/text）
        for msg in resp["history"]:
            assert isinstance(msg, dict)
            assert "role" in msg
            assert msg["role"] in ("user", "assistant")
            assert "text" in msg

    def test_get_session_history_pagination(self):
        """聊天记录分页"""
        resp = get_session_history("cli:FriendMessage:cli_session", page=1, page_size=2)
        assert resp["status"] == "success"
        assert resp["page"] == 1
        assert len(resp["history"]) <= 2

    def test_get_session_history_nonexistent(self):
        """获取不存在会话的聊天记录（应返回空记录）"""
        resp = get_session_history("nonexistent:FriendMessage:no_session")
        assert resp["status"] == "success"
        assert resp["history"] == []


# ============================================================


class TestClientOutput:
    """format_response 纯函数测试，使用 fake 数据"""

    def test_format_success(self):
        fake_ok = {
            "status": "success",
            "response": "测试内容",
            "images": [],
            "request_id": "fake-id",
        }
        assert len(format_response(fake_ok)) > 0

    def test_format_with_images(self):
        fake_img = {
            "status": "success",
            "response": "",
            "images": ["base64data"],
            "request_id": "fake-id",
        }
        formatted = format_response(fake_img)
        assert "图片" in formatted or len(formatted) > 0

    def test_format_error(self):
        fake_err = {"status": "error", "error": "test"}
        assert format_response(fake_err) == ""


# ============================================================
# 第六层：边界条件（每个 case 唯一，3 次服务端调用）
# ============================================================


class TestEdgeCases:
    """缺少参数、无效参数、不存在的命令"""

    def test_empty_command_args(self):
        resp = send_message("/switch")
        assert resp["status"] == "success"

    def test_invalid_switch_index(self):
        resp = send_message("/switch 99999")
        assert resp["status"] == "success"

    def test_unknown_slash_command(self):
        resp = send_message("/nonexistent_cmd_xyz_123")
        assert resp["status"] == "success"


# ============================================================
# 第七层：健壮性（测试行为而非命令内容）
#
# 用 /ls 做轻量探测（不与上方命令测试重复验证内容）
# 服务端调用：/ls ×9 = 9 次
# ============================================================


class TestRobustness:
    """并发稳定性和响应隔离（只验证机制，不验证命令内容）"""

    def test_rapid_fire_no_mixing(self):
        """4次快速请求，request_id 全部唯一"""
        responses = [send_message("/ls") for _ in range(4)]
        for r in responses:
            assert r["status"] == "success"
        ids = [r["request_id"] for r in responses]
        assert len(set(ids)) == len(ids), "request_id 不唯一"

    def test_stability(self):
        """5次请求至少4次成功"""
        success = sum(1 for _ in range(5) if send_message("/ls")["status"] == "success")
        assert success >= 4, f"稳定性不足: {success}/5"
