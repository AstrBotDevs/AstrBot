"""CLI Client 长链条端到端测试

对框架各子模块按 SDK 粒度进行端到端测试。
不使用 mock，直接通过真实 socket 连接到运行中的 AstrBot 服务端。

测试前提：AstrBot 已启动并开启 CLI 平台适配器（socket 模式）。

测试链路覆盖：
  客户端 connection 模块
    → TCP/Unix Socket 连接
    → Token 认证
    → SocketClientHandler.handle()
    → MessageConverter.convert()
    → CLIMessageEvent (事件创建/提交/finalize)
    → Pipeline (内置命令/LLM/插件)
    → ResponseBuilder.build_success/build_error
    → 客户端 output 模块解析

运行方式：
  pytest tests/test_cli/test_client_e2e.py -v        # 需要 AstrBot 服务端运行
  pytest tests/test_cli/ --ignore=tests/test_cli/test_client_e2e.py  # 只跑单元测试
"""

import os
import time

import pytest

from astrbot.cli.client.connection import (
    get_data_path,
    get_logs,
    load_auth_token,
    load_connection_info,
    send_message,
)
from astrbot.cli.client.output import format_response

# 默认超时（秒）：内置命令应在此时间内返回
_CMD_TIMEOUT = 30.0
# LLM 管道超时（秒）：触发 LLM 的命令可能更慢
_LLM_TIMEOUT = 60.0


def _server_reachable() -> bool:
    """检查 AstrBot 服务端是否可达"""
    try:
        resp = send_message("/help", timeout=10.0)
        return resp.get("status") == "success"
    except Exception:
        return False


# 如果服务端不可达，跳过所有测试
pytestmark = [
    pytest.mark.skipif(
        not _server_reachable(),
        reason="AstrBot 服务端未运行，跳过端到端测试",
    ),
    pytest.mark.e2e,
]


# ============================================================
# 第一层：连接基础设施测试
# ============================================================


class TestConnectionInfra:
    """连接基础设施端到端测试

    验证链路：客户端 → 连接文件 → Token → Socket 建立
    """

    def test_data_path_exists(self):
        """数据目录存在且可读"""
        data_dir = get_data_path()
        assert os.path.isdir(data_dir), f"数据目录不存在: {data_dir}"

    def test_connection_info_valid(self):
        """连接信息文件存在且格式正确"""
        data_dir = get_data_path()
        info = load_connection_info(data_dir)
        assert info is not None, "连接信息文件 .cli_connection 不存在"
        assert "type" in info, "连接信息缺少 type 字段"
        assert info["type"] in ("unix", "tcp"), f"未知连接类型: {info['type']}"

        if info["type"] == "tcp":
            assert "host" in info
            assert "port" in info
            assert isinstance(info["port"], int)
        elif info["type"] == "unix":
            assert "path" in info

    def test_auth_token_configured(self):
        """Token 已配置且非空"""
        token = load_auth_token()
        assert token, "Token 未配置（.cli_token 为空或不存在）"
        assert len(token) > 8, f"Token 过短（{len(token)} 字符），疑似无效"

    def test_socket_roundtrip_latency(self):
        """Socket 往返延迟合理（<10s）"""
        start = time.time()
        resp = send_message("/help")
        elapsed = time.time() - start

        assert resp["status"] == "success"
        assert elapsed < 10.0, f"Socket 往返延迟过大: {elapsed:.2f}s"


# ============================================================
# 第二层：Token 认证链路测试
# ============================================================


class TestTokenAuth:
    """Token 认证端到端测试

    验证链路：
      客户端 auth_token → SocketClientHandler → TokenManager.validate()
    """

    def test_valid_token_accepted(self):
        """正确 Token 通过认证"""
        resp = send_message("/help")
        assert resp["status"] == "success"
        # 如果 Token 无效会返回 AUTH_FAILED
        assert resp.get("error_code") != "AUTH_FAILED"

    def test_response_has_request_id(self):
        """响应包含 request_id（证明请求通过了完整链路）"""
        resp = send_message("/help")
        assert "request_id" in resp, "响应缺少 request_id"
        assert len(resp["request_id"]) > 0


# ============================================================
# 第三层：消息转换与事件链路测试
# ============================================================


class TestMessagePipeline:
    """消息处理管道端到端测试

    验证链路：
      MessageConverter.convert() → CLIMessageEvent 创建
      → event_committer 提交 → Pipeline 处理
      → CLIMessageEvent.send() 缓冲 → finalize()
      → ResponseBuilder.build_success()
    """

    def test_internal_command_help(self):
        """/help 命令走完整管道并返回内置命令列表"""
        resp = send_message("/help")
        assert resp["status"] == "success"
        text = resp["response"]
        # /help 应返回内置指令列表
        assert "/help" in text, "响应中应包含 /help 指令说明"
        assert "内置指令" in text or "帮助" in text or "AstrBot" in text

    def test_internal_command_sid(self):
        """/sid 返回会话信息，验证 MessageConverter 的 session_id 设置"""
        resp = send_message("/sid")
        assert resp["status"] == "success"
        text = resp["response"]
        # /sid 应返回会话 ID 信息
        assert "cli_session" in text or "cli_user" in text or "UMO" in text

    def test_response_structure(self):
        """响应结构符合 ResponseBuilder 输出格式"""
        resp = send_message("/help")
        assert resp["status"] == "success"
        # ResponseBuilder.build_success 输出这些字段
        assert "response" in resp
        assert "images" in resp
        assert isinstance(resp["images"], list)
        assert "request_id" in resp

    @pytest.mark.timeout(_LLM_TIMEOUT)
    def test_plain_text_message(self):
        """普通文本消息走 LLM 管道"""
        resp = send_message("echo test 12345", timeout=_LLM_TIMEOUT)
        assert resp["status"] == "success"
        # LLM 或插件应该返回某种响应（不是空的）
        assert resp["response"] or resp["images"]

    def test_empty_response_for_unknown_command(self):
        """不存在的斜杠命令返回某种错误提示"""
        resp = send_message("/nonexistent_cmd_xyz_123")
        assert resp["status"] == "success"
        # 内置命令系统通常会返回 "未知指令" 之类的提示
        # 或者当作普通消息走 LLM 管道


# ============================================================
# 第四层：会话管理端到端测试
# ============================================================


class TestSessionManagement:
    """会话管理端到端测试

    验证链路：
      /new → /ls → /switch → /rename → /history → /reset → /del
      所有命令在同一个 cli_session 上操作对话列表

    会话逻辑说明：
      - 默认 use_isolated_sessions=False
      - 所有 CLI 请求使用同一个 session_id: "cli_session"
      - /new, /switch, /del 等操作的是"对话"（LLM上下文），不是 socket 会话
    """

    def test_conversation_full_lifecycle(self):
        """完整对话生命周期：创建 → 列表 → 重命名 → 历史 → 重置 → 删除"""

        # 1. 记住初始状态
        resp_ls_before = send_message("/ls")
        assert resp_ls_before["status"] == "success"

        # 2. 创建新对话
        resp_new = send_message("/new")
        assert resp_new["status"] == "success"
        text_new = resp_new["response"]
        assert "新对话" in text_new or "切换" in text_new

        # 3. 重命名
        test_name = "e2e_lifecycle_test"
        resp_rename = send_message(f"/rename {test_name}")
        assert resp_rename["status"] == "success"
        assert "重命名" in resp_rename["response"] or "成功" in resp_rename["response"]

        # 4. 列表中应该能看到新对话
        resp_ls = send_message("/ls")
        assert resp_ls["status"] == "success"
        assert test_name in resp_ls["response"]

        # 5. 重置 LLM 会话
        resp_reset = send_message("/reset")
        assert resp_reset["status"] == "success"
        assert "清除" in resp_reset["response"] or "成功" in resp_reset["response"]

        # 6. 查看历史（重置后应为空或只有系统消息）
        resp_history = send_message("/history")
        assert resp_history["status"] == "success"

        # 7. 删除对话
        resp_del = send_message("/del")
        assert resp_del["status"] == "success"
        assert "删除" in resp_del["response"] or "成功" in resp_del["response"]

    def test_conversation_switch(self):
        """对话切换：创建新对话后切换回旧对话"""

        # 确保有至少一个对话
        send_message("/new")

        # 列表
        resp_ls = send_message("/ls")
        assert resp_ls["status"] == "success"

        # 切换到序号 1
        resp_switch = send_message("/switch 1")
        assert resp_switch["status"] == "success"
        assert "切换" in resp_switch["response"]

        # 清理
        send_message("/del")

    def test_session_id_consistency(self):
        """/sid 在多次请求间返回相同会话信息（证明使用同一会话）"""
        resp1 = send_message("/sid")
        resp2 = send_message("/sid")
        assert resp1["status"] == "success"
        assert resp2["status"] == "success"
        # 两次 /sid 应返回相同的会话信息
        assert resp1["response"] == resp2["response"]


# ============================================================
# 第五层：插件系统端到端测试
# ============================================================


class TestPluginSystem:
    """插件系统端到端测试

    验证链路：消息 → Pipeline → 插件路由 → 插件执行 → 响应
    """

    def test_plugin_list(self):
        """/plugin ls 返回已加载插件列表"""
        resp = send_message("/plugin ls")
        assert resp["status"] == "success"
        text = resp["response"]
        assert "插件" in text or "plugin" in text.lower()
        # 至少有内置插件
        assert "astrbot" in text.lower() or "builtin" in text.lower()

    def test_plugin_help(self):
        """/plugin help 返回插件帮助"""
        resp = send_message("/plugin help")
        assert resp["status"] == "success"

    def test_plugin_help_specific(self):
        """/plugin help <name> 返回特定插件帮助"""
        # 先获取插件列表找到一个可用插件
        resp_ls = send_message("/plugin ls")
        assert resp_ls["status"] == "success"

        # builtin_commands 一定存在
        resp_help = send_message("/plugin help builtin_commands")
        assert resp_help["status"] == "success"
        text = resp_help["response"]
        assert "指令" in text or "帮助" in text or "help" in text.lower()


# ============================================================
# 第六层：Provider/Model 管理端到端测试
# ============================================================


class TestProviderModel:
    """Provider/Model 管理端到端测试

    验证链路：/provider, /model, /key 命令的完整管道处理
    """

    def test_model_list(self):
        """/model 返回可用模型列表"""
        resp = send_message("/model")
        assert resp["status"] == "success"
        text = resp["response"]
        # 应该包含模型列表或图片
        assert text or resp["images"]

    def test_key_list(self):
        """/key 返回 Key 信息"""
        resp = send_message("/key")
        assert resp["status"] == "success"
        text = resp["response"]
        assert "Key" in text or "key" in text.lower() or "当前" in text


# ============================================================
# 第七层：日志子系统端到端测试
# ============================================================


class TestLogSubsystem:
    """日志子系统端到端测试

    验证链路（Socket 模式）：
      get_logs 请求 → SocketClientHandler._get_logs()
      → 读取日志文件 → 过滤 → 返回

    验证链路（文件直读）：
      _read_log_from_file() → 读取 data/logs/astrbot.log
    """

    def test_get_logs_via_socket(self):
        """通过 Socket 获取日志"""
        resp = get_logs(lines=10)
        assert resp["status"] == "success"
        # 应该返回一些日志内容
        assert "response" in resp

    def test_get_logs_with_level_filter(self):
        """日志级别过滤"""
        resp = get_logs(lines=50, level="INFO")
        assert resp["status"] == "success"
        text = resp.get("response", "")
        # 如果有日志，每行都应包含 [INFO]
        if text.strip():
            for line in text.strip().split("\n"):
                if line.strip():
                    assert "[INFO]" in line, f"过滤后仍有非 INFO 日志: {line}"

    def test_get_logs_with_pattern(self):
        """日志模式过滤"""
        resp = get_logs(lines=50, pattern="CLI")
        assert resp["status"] == "success"
        text = resp.get("response", "")
        if text.strip():
            for line in text.strip().split("\n"):
                if line.strip():
                    assert "CLI" in line or "cli" in line


# ============================================================
# 第八层：客户端输出模块测试
# ============================================================


class TestClientOutput:
    """客户端输出格式化端到端测试

    验证 format_response 正确解析真实服务端响应
    """

    def test_format_text_response(self):
        """格式化纯文本响应"""
        resp = send_message("/help")
        formatted = format_response(resp)
        assert len(formatted) > 0
        assert "help" in formatted.lower() or "指令" in formatted

    @pytest.mark.timeout(_LLM_TIMEOUT)
    def test_format_image_response(self):
        """格式化含图片的响应"""
        resp = send_message("/provider", timeout=_LLM_TIMEOUT)
        if resp.get("images"):
            formatted = format_response(resp)
            assert "图片" in formatted

    def test_format_error_response(self):
        """错误响应格式化为空字符串"""
        fake_error = {"status": "error", "error": "test"}
        formatted = format_response(fake_error)
        assert formatted == ""


# ============================================================
# 第九层：长链条场景测试
# ============================================================


class TestLongChainScenarios:
    """长链条场景端到端测试

    模拟真实用户操作序列，验证多步骤跨模块交互。
    """

    def test_scenario_new_user_onboarding(self):
        """场景：新用户首次使用

        链路：status → help → sid → plugin ls → model
        """
        # 1. 检查连接状态
        resp = send_message("/help")
        assert resp["status"] == "success"

        # 2. 查看帮助
        resp = send_message("/help")
        assert resp["status"] == "success"
        assert "/help" in resp["response"]

        # 3. 获取会话信息
        resp = send_message("/sid")
        assert resp["status"] == "success"
        assert "cli" in resp["response"].lower()

        # 4. 查看插件
        resp = send_message("/plugin ls")
        assert resp["status"] == "success"

        # 5. 查看模型
        resp = send_message("/model")
        assert resp["status"] == "success"

    @pytest.mark.timeout(_LLM_TIMEOUT)
    def test_scenario_conversation_workflow(self):
        """场景：完整对话工作流

        链路：new → rename → ls → send msg → history → reset → del
        """
        # 1. 创建新对话
        resp = send_message("/new")
        assert resp["status"] == "success"

        # 2. 重命名
        resp = send_message("/rename e2e_workflow_test")
        assert resp["status"] == "success"

        # 3. 确认在列表中
        resp = send_message("/ls")
        assert resp["status"] == "success"
        assert "e2e_workflow_test" in resp["response"]

        # 4. 发送消息（触发 LLM 管道）
        resp = send_message("请回复OK", timeout=_LLM_TIMEOUT)
        assert resp["status"] == "success"

        # 5. 查看历史（应该有刚才的对话）
        resp = send_message("/history")
        assert resp["status"] == "success"
        history_text = resp["response"]
        assert (
            "OK" in history_text or "请回复" in history_text or "历史" in history_text
        )

        # 6. 重置
        resp = send_message("/reset")
        assert resp["status"] == "success"

        # 7. 删除
        resp = send_message("/del")
        assert resp["status"] == "success"

    def test_scenario_plugin_inspection(self):
        """场景：逐一检查插件信息

        链路：plugin ls → 解析插件名 → plugin help <name>
        """
        # 1. 获取插件列表
        resp = send_message("/plugin ls")
        assert resp["status"] == "success"

        # 2. 对 builtin_commands 查看帮助
        resp = send_message("/plugin help builtin_commands")
        assert resp["status"] == "success"
        assert "指令" in resp["response"] or "帮助" in resp["response"]

    def test_scenario_rapid_fire_commands(self):
        """场景：快速连续发送多条命令

        验证服务端能正确处理串行请求，不混淆响应。
        """
        commands = ["/help", "/sid", "/ls", "/model", "/key"]
        responses = []

        for cmd in commands:
            resp = send_message(cmd)
            assert resp["status"] == "success", f"命令 {cmd} 失败: {resp}"
            responses.append(resp)

        # 验证每个响应的 request_id 都不同
        request_ids = [r["request_id"] for r in responses]
        assert len(set(request_ids)) == len(request_ids), "request_id 不唯一"

        # 验证响应内容合理（不混淆）
        # /help 的响应应包含 "指令"
        assert "指令" in responses[0]["response"] or "帮助" in responses[0]["response"]
        # /sid 的响应应包含 "cli"
        assert "cli" in responses[1]["response"].lower()

    @pytest.mark.timeout(_LLM_TIMEOUT)
    def test_scenario_conversation_isolation(self):
        """场景：对话切换后上下文隔离

        验证 /new 创建新对话后，/history 应该为空或不含前一个对话内容。
        """
        # 1. 创建新对话
        resp = send_message("/new")
        assert resp["status"] == "success"

        # 2. 发消息
        resp = send_message("isolation_marker_abc", timeout=_LLM_TIMEOUT)
        assert resp["status"] == "success"

        # 3. 创建另一个新对话
        resp = send_message("/new")
        assert resp["status"] == "success"

        # 4. 查看历史（新对话应该没有 isolation_marker_abc）
        resp = send_message("/history")
        assert resp["status"] == "success"
        assert "isolation_marker_abc" not in resp["response"]

        # 清理：删除两个测试对话
        send_message("/del")
        send_message("/switch 1")  # 可能需要先切换
        # 找到并删除之前的对话
        resp_ls = send_message("/ls")
        if "isolation_marker" in resp_ls.get("response", ""):
            send_message("/del")


# ============================================================
# 第十层：错误处理与边界条件测试
# ============================================================


class TestErrorHandling:
    """错误处理与边界条件端到端测试"""

    @pytest.mark.timeout(_LLM_TIMEOUT)
    def test_very_long_message(self):
        """超长消息不导致崩溃"""
        long_msg = "A" * 10000
        resp = send_message(long_msg, timeout=_LLM_TIMEOUT)
        # 应该成功处理或返回合理错误，不能崩溃
        assert resp["status"] in ("success", "error")

    @pytest.mark.timeout(_LLM_TIMEOUT)
    def test_unicode_message(self):
        """Unicode 消息正确处理"""
        resp = send_message("你好世界 🌍 こんにちは мир", timeout=_LLM_TIMEOUT)
        assert resp["status"] == "success"

    @pytest.mark.timeout(_LLM_TIMEOUT)
    def test_special_characters(self):
        """特殊字符消息"""
        resp = send_message('hello "world" <>&{}[]', timeout=_LLM_TIMEOUT)
        assert resp["status"] == "success"

    def test_empty_command_args(self):
        """/switch 无参数"""
        resp = send_message("/switch")
        assert resp["status"] == "success"
        # 应该返回错误提示而不是崩溃

    def test_invalid_switch_index(self):
        """/switch 无效序号"""
        resp = send_message("/switch 99999")
        assert resp["status"] == "success"
        # 应该返回错误提示

    def test_concurrent_stability(self):
        """多次快速请求稳定性（允许偶发失败但大多数应成功）"""
        success_count = 0
        total = 5
        for i in range(total):
            resp = send_message("/help")
            if resp["status"] == "success":
                success_count += 1
        # 至少 80% 成功
        assert success_count >= total * 0.8, (
            f"并发稳定性不足: {success_count}/{total} 成功"
        )
