"""CLI Client 命令模块单元测试

使用 click.testing.CliRunner 测试 CLI 命令的参数解析和消息映射。
"""

import json
from unittest.mock import patch

from click.testing import CliRunner

from astrbot.cli.client.__main__ import main


def _mock_send(response_text="OK", status="success"):
    """创建 mock send_message 返回指定响应"""
    return {"status": status, "response": response_text, "images": []}


def _mock_send_error(error_text="Connection error"):
    """创建 mock send_message 返回错误"""
    return {"status": "error", "error": error_text}


class TestSendCommand:
    """send 命令测试"""

    @patch("astrbot.cli.client.commands.send.send_message")
    def test_basic_send(self, mock_send):
        """基本消息发送"""
        mock_send.return_value = _mock_send("你好!")
        runner = CliRunner()
        result = runner.invoke(main, ["send", "你好"])

        assert result.exit_code == 0
        assert "你好!" in result.output
        mock_send.assert_called_once_with("你好", None, 30.0)

    @patch("astrbot.cli.client.commands.send.send_message")
    def test_send_with_json(self, mock_send):
        """JSON 输出"""
        mock_send.return_value = _mock_send("hello")
        runner = CliRunner()
        result = runner.invoke(main, ["send", "-j", "hello"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["status"] == "success"

    @patch("astrbot.cli.client.commands.send.send_message")
    def test_send_multi_word(self, mock_send):
        """多个词拼接"""
        mock_send.return_value = _mock_send("response")
        runner = CliRunner()
        result = runner.invoke(main, ["send", "hello", "world"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("hello world", None, 30.0)

    @patch("astrbot.cli.client.commands.send.send_message")
    def test_implicit_send(self, mock_send):
        """astr 你好 隐式路由到 send"""
        mock_send.return_value = _mock_send("response")
        runner = CliRunner()
        result = runner.invoke(main, ["你好"])

        assert result.exit_code == 0
        mock_send.assert_called_once()

    @patch("astrbot.cli.client.commands.send.send_message")
    def test_implicit_json_flag(self, mock_send):
        """astr -j "test" 隐式路由到 send -j"""
        mock_send.return_value = _mock_send("response")
        runner = CliRunner()
        result = runner.invoke(main, ["-j", "test"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["status"] == "success"

    @patch("astrbot.cli.client.commands.send.send_message")
    def test_send_error(self, mock_send):
        """发送错误时退出码为 1"""
        mock_send.return_value = _mock_send_error("Connection refused")
        runner = CliRunner()
        result = runner.invoke(main, ["send", "hello"])

        assert result.exit_code == 1

    def test_send_no_message(self):
        """无消息内容时报错"""
        runner = CliRunner()
        result = runner.invoke(main, ["send"])

        assert result.exit_code == 1

    @patch("astrbot.cli.client.commands.send.send_message")
    def test_send_with_timeout(self, mock_send):
        """自定义超时时间"""
        mock_send.return_value = _mock_send("ok")
        runner = CliRunner()
        result = runner.invoke(main, ["send", "-t", "60", "hello"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("hello", None, 60.0)

    @patch("astrbot.cli.client.commands.send.send_message")
    def test_pipe_input(self, mock_send):
        """管道输入"""
        mock_send.return_value = _mock_send("piped")
        runner = CliRunner()
        result = runner.invoke(main, ["send"], input="hello from pipe")

        assert result.exit_code == 0
        mock_send.assert_called_once_with("hello from pipe", None, 30.0)


class TestLogCommand:
    """log 命令测试"""

    @patch("astrbot.cli.client.commands.log._read_log_from_file")
    def test_log_default(self, mock_read):
        """默认读取文件日志"""
        runner = CliRunner()
        result = runner.invoke(main, ["log"])

        assert result.exit_code == 0
        mock_read.assert_called_once_with(100, "", "", False)

    @patch("astrbot.cli.client.commands.log._read_log_from_file")
    def test_log_with_options(self, mock_read):
        """带选项读取日志"""
        runner = CliRunner()
        result = runner.invoke(
            main, ["log", "--lines", "50", "--level", "ERROR", "--pattern", "test"]
        )

        assert result.exit_code == 0
        mock_read.assert_called_once_with(50, "ERROR", "test", False)

    @patch("astrbot.cli.client.commands.log._read_log_from_file")
    def test_log_regex(self, mock_read):
        """正则匹配日志"""
        runner = CliRunner()
        result = runner.invoke(main, ["log", "--pattern", "ERR|WARN", "--regex"])

        assert result.exit_code == 0
        mock_read.assert_called_once_with(100, "", "ERR|WARN", True)

    @patch("astrbot.cli.client.commands.log._read_log_from_file")
    def test_log_compat_flag(self, mock_read):
        """--log 兼容旧用法"""
        runner = CliRunner()
        result = runner.invoke(main, ["--log"])

        assert result.exit_code == 0
        mock_read.assert_called_once()

    @patch("astrbot.cli.client.commands.log.get_logs")
    def test_log_socket_mode(self, mock_get_logs):
        """Socket 模式获取日志"""
        mock_get_logs.return_value = {
            "status": "success",
            "response": "log line 1\nlog line 2",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["log", "--socket"])

        assert result.exit_code == 0
        assert "log line 1" in result.output


class TestConvCommand:
    """conv 命令组测试"""

    @patch("astrbot.cli.client.commands.conv.send_message")
    def test_conv_ls(self, mock_send):
        """列出对话"""
        mock_send.return_value = _mock_send("对话列表...")
        runner = CliRunner()
        result = runner.invoke(main, ["conv", "ls"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/ls")

    @patch("astrbot.cli.client.commands.conv.send_message")
    def test_conv_ls_page(self, mock_send):
        """带页码列出对话"""
        mock_send.return_value = _mock_send("第2页")
        runner = CliRunner()
        result = runner.invoke(main, ["conv", "ls", "2"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/ls 2")

    @patch("astrbot.cli.client.commands.conv.send_message")
    def test_conv_new(self, mock_send):
        """创建新对话"""
        mock_send.return_value = _mock_send("已创建")
        runner = CliRunner()
        result = runner.invoke(main, ["conv", "new"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/new")

    @patch("astrbot.cli.client.commands.conv.send_message")
    def test_conv_switch(self, mock_send):
        """切换对话"""
        mock_send.return_value = _mock_send("已切换")
        runner = CliRunner()
        result = runner.invoke(main, ["conv", "switch", "3"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/switch 3")

    @patch("astrbot.cli.client.commands.conv.send_message")
    def test_conv_del(self, mock_send):
        """删除对话"""
        mock_send.return_value = _mock_send("已删除")
        runner = CliRunner()
        result = runner.invoke(main, ["conv", "del"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/del")

    @patch("astrbot.cli.client.commands.conv.send_message")
    def test_conv_rename(self, mock_send):
        """重命名对话"""
        mock_send.return_value = _mock_send("已重命名")
        runner = CliRunner()
        result = runner.invoke(main, ["conv", "rename", "新名称"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/rename 新名称")

    @patch("astrbot.cli.client.commands.conv.send_message")
    def test_conv_reset(self, mock_send):
        """重置 LLM 会话"""
        mock_send.return_value = _mock_send("已重置")
        runner = CliRunner()
        result = runner.invoke(main, ["conv", "reset"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/reset")

    @patch("astrbot.cli.client.commands.conv.send_message")
    def test_conv_history(self, mock_send):
        """查看对话记录"""
        mock_send.return_value = _mock_send("记录...")
        runner = CliRunner()
        result = runner.invoke(main, ["conv", "history"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/history")

    @patch("astrbot.cli.client.commands.conv.send_message")
    def test_conv_history_page(self, mock_send):
        """带页码查看记录"""
        mock_send.return_value = _mock_send("第2页")
        runner = CliRunner()
        result = runner.invoke(main, ["conv", "history", "2"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/history 2")


class TestPluginCommand:
    """plugin 命令组测试"""

    @patch("astrbot.cli.client.commands.plugin.send_message")
    def test_plugin_ls(self, mock_send):
        """列出插件"""
        mock_send.return_value = _mock_send("插件列表")
        runner = CliRunner()
        result = runner.invoke(main, ["plugin", "ls"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/plugin ls")

    @patch("astrbot.cli.client.commands.plugin.send_message")
    def test_plugin_on(self, mock_send):
        """启用插件"""
        mock_send.return_value = _mock_send("已启用")
        runner = CliRunner()
        result = runner.invoke(main, ["plugin", "on", "myplugin"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/plugin on myplugin")

    @patch("astrbot.cli.client.commands.plugin.send_message")
    def test_plugin_off(self, mock_send):
        """禁用插件"""
        mock_send.return_value = _mock_send("已禁用")
        runner = CliRunner()
        result = runner.invoke(main, ["plugin", "off", "myplugin"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/plugin off myplugin")

    @patch("astrbot.cli.client.commands.plugin.send_message")
    def test_plugin_help(self, mock_send):
        """获取插件帮助"""
        mock_send.return_value = _mock_send("帮助信息")
        runner = CliRunner()
        result = runner.invoke(main, ["plugin", "help", "myplugin"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/plugin help myplugin")

    @patch("astrbot.cli.client.commands.plugin.send_message")
    def test_plugin_help_no_name(self, mock_send):
        """获取通用插件帮助"""
        mock_send.return_value = _mock_send("通用帮助")
        runner = CliRunner()
        result = runner.invoke(main, ["plugin", "help"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/plugin help")


class TestProviderModelKey:
    """provider/model/key 命令测试"""

    @patch("astrbot.cli.client.commands.provider.send_message")
    def test_provider_list(self, mock_send):
        """查看 Provider 列表"""
        mock_send.return_value = _mock_send("provider list")
        runner = CliRunner()
        result = runner.invoke(main, ["provider"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/provider")

    @patch("astrbot.cli.client.commands.provider.send_message")
    def test_provider_switch(self, mock_send):
        """切换 Provider"""
        mock_send.return_value = _mock_send("switched")
        runner = CliRunner()
        result = runner.invoke(main, ["provider", "2"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/provider 2")

    @patch("astrbot.cli.client.commands.provider.send_message")
    def test_model_list(self, mock_send):
        """查看模型列表"""
        mock_send.return_value = _mock_send("model list")
        runner = CliRunner()
        result = runner.invoke(main, ["model"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/model")

    @patch("astrbot.cli.client.commands.provider.send_message")
    def test_model_switch(self, mock_send):
        """切换模型"""
        mock_send.return_value = _mock_send("switched")
        runner = CliRunner()
        result = runner.invoke(main, ["model", "gpt-4"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/model gpt-4")

    @patch("astrbot.cli.client.commands.provider.send_message")
    def test_key_list(self, mock_send):
        """查看 Key 列表"""
        mock_send.return_value = _mock_send("key list")
        runner = CliRunner()
        result = runner.invoke(main, ["key"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/key")

    @patch("astrbot.cli.client.commands.provider.send_message")
    def test_key_switch(self, mock_send):
        """切换 Key"""
        mock_send.return_value = _mock_send("switched")
        runner = CliRunner()
        result = runner.invoke(main, ["key", "1"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/key 1")


class TestDebugCommands:
    """调试命令测试"""

    @patch("astrbot.cli.client.commands.debug.send_message")
    def test_ping(self, mock_send):
        """ping 测试"""
        mock_send.return_value = _mock_send("help text")
        runner = CliRunner()
        result = runner.invoke(main, ["ping"])

        assert result.exit_code == 0
        assert "pong" in result.output

    @patch("astrbot.cli.client.commands.debug.send_message")
    def test_ping_count(self, mock_send):
        """多次 ping"""
        mock_send.return_value = _mock_send("help text")
        runner = CliRunner()
        result = runner.invoke(main, ["ping", "-c", "3"])

        assert result.exit_code == 0
        assert result.output.count("pong") == 3

    @patch("astrbot.cli.client.commands.debug.send_message")
    @patch("astrbot.cli.client.commands.debug.load_auth_token", return_value="tok123")
    @patch(
        "astrbot.cli.client.commands.debug.load_connection_info",
        return_value={"type": "tcp", "host": "127.0.0.1", "port": 12345},
    )
    def test_status(self, mock_conn, mock_token, mock_send):
        """status 命令"""
        mock_send.return_value = _mock_send("help text")
        runner = CliRunner()
        result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "TCP" in result.output
        assert "127.0.0.1" in result.output
        assert "在线" in result.output

    @patch("astrbot.cli.client.commands.debug.send_message")
    def test_test_echo(self, mock_send):
        """test echo 命令"""
        mock_send.return_value = _mock_send("echo response")
        runner = CliRunner()
        result = runner.invoke(main, ["test", "echo", "hello"])

        assert result.exit_code == 0
        assert "hello" in result.output
        assert "echo response" in result.output

    @patch("astrbot.cli.client.commands.debug.send_message")
    def test_test_plugin(self, mock_send):
        """test plugin 命令"""
        mock_send.return_value = _mock_send("plugin response")
        runner = CliRunner()
        result = runner.invoke(main, ["test", "plugin", "hello", "world"])

        assert result.exit_code == 0
        mock_send.assert_called_once_with("/hello world")


class TestAliasCommands:
    """快捷别名命令测试"""

    @patch("astrbot.cli.client.connection.send_message")
    def test_help_alias(self, mock_send):
        """help 别名"""
        mock_send.return_value = _mock_send("help text")
        runner = CliRunner()
        result = runner.invoke(main, ["help"])

        assert result.exit_code == 0
        mock_send.assert_called_with("/help")

    @patch("astrbot.cli.client.connection.send_message")
    def test_sid_alias(self, mock_send):
        """sid 别名"""
        mock_send.return_value = _mock_send("session_123")
        runner = CliRunner()
        result = runner.invoke(main, ["sid"])

        assert result.exit_code == 0
        mock_send.assert_called_with("/sid")

    @patch("astrbot.cli.client.connection.send_message")
    def test_t2i_alias(self, mock_send):
        """t2i 别名"""
        mock_send.return_value = _mock_send("toggled")
        runner = CliRunner()
        result = runner.invoke(main, ["t2i"])

        assert result.exit_code == 0
        mock_send.assert_called_with("/t2i")

    @patch("astrbot.cli.client.connection.send_message")
    def test_tts_alias(self, mock_send):
        """tts 别名"""
        mock_send.return_value = _mock_send("toggled")
        runner = CliRunner()
        result = runner.invoke(main, ["tts"])

        assert result.exit_code == 0
        mock_send.assert_called_with("/tts")


class TestBatchCommand:
    """batch 命令测试"""

    @patch("astrbot.cli.client.connection.send_message")
    def test_batch(self, mock_send, tmp_path):
        """批量执行"""
        mock_send.return_value = _mock_send("ok")

        batch_file = tmp_path / "commands.txt"
        batch_file.write_text("hello\n# comment\n/help\n\n/plugin ls\n")

        runner = CliRunner()
        result = runner.invoke(main, ["batch", str(batch_file)])

        assert result.exit_code == 0
        assert mock_send.call_count == 3
        mock_send.assert_any_call("hello")
        mock_send.assert_any_call("/help")
        mock_send.assert_any_call("/plugin ls")


class TestBackwardCompatibility:
    """向后兼容性测试"""

    @patch("astrbot.cli.client.commands.send.send_message")
    def test_astr_hello(self, mock_send):
        """astr 你好 → astr send 你好"""
        mock_send.return_value = _mock_send("hi")
        runner = CliRunner()
        result = runner.invoke(main, ["你好"])

        assert result.exit_code == 0
        mock_send.assert_called_once()

    @patch("astrbot.cli.client.commands.log._read_log_from_file")
    def test_astr_log_flag(self, mock_read):
        """astr --log → astr log"""
        runner = CliRunner()
        result = runner.invoke(main, ["--log"])

        assert result.exit_code == 0
        mock_read.assert_called_once()

    def test_help_output(self):
        """帮助输出包含新命令"""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "send" in result.output
        assert "log" in result.output
        assert "conv" in result.output
        assert "plugin" in result.output
        assert "provider" in result.output
        assert "ping" in result.output


class TestSessionCommand:
    """session 命令组测试"""

    @patch("astrbot.cli.client.commands.session.list_sessions")
    def test_session_ls(self, mock_list):
        """列出所有会话"""
        mock_list.return_value = {
            "status": "success",
            "sessions": [
                {
                    "session_id": "cli:FriendMessage:cli_session",
                    "conversation_id": "conv-123",
                    "title": "测试对话",
                    "persona_id": None,
                    "persona_name": None,
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 20,
            "total_pages": 1,
            "response": "共 1 个会话",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["session", "ls"])

        assert result.exit_code == 0
        assert "cli_session" in result.output
        mock_list.assert_called_once()

    @patch("astrbot.cli.client.commands.session.list_sessions")
    def test_session_ls_with_platform(self, mock_list):
        """按平台过滤会话"""
        mock_list.return_value = {
            "status": "success",
            "sessions": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
            "response": "共 0 个会话",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["session", "ls", "-P", "qq"])

        assert result.exit_code == 0
        mock_list.assert_called_once_with(
            page=1, page_size=20, platform="qq", search_query=None
        )

    @patch("astrbot.cli.client.commands.session.list_sessions")
    def test_session_ls_json(self, mock_list):
        """JSON 输出"""
        mock_list.return_value = {
            "status": "success",
            "sessions": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
            "response": "共 0 个会话",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["session", "ls", "-j"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["status"] == "success"

    @patch("astrbot.cli.client.commands.session.list_sessions")
    def test_session_ls_error(self, mock_list):
        """错误响应"""
        mock_list.return_value = {"status": "error", "error": "未初始化"}
        runner = CliRunner()
        result = runner.invoke(main, ["session", "ls"])

        assert result.exit_code == 1

    @patch("astrbot.cli.client.commands.session.list_session_conversations")
    def test_session_convs(self, mock_convs):
        """查看指定会话的对话列表"""
        mock_convs.return_value = {
            "status": "success",
            "conversations": [
                {
                    "cid": "conv-abc",
                    "title": "测试对话",
                    "persona_id": None,
                    "created_at": 1700000000,
                    "updated_at": 1700000000,
                    "token_usage": 100,
                    "is_current": True,
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 20,
            "total_pages": 1,
            "current_cid": "conv-abc",
            "response": "共 1 个对话",
        }
        runner = CliRunner()
        result = runner.invoke(
            main, ["session", "convs", "cli:FriendMessage:cli_session"]
        )

        assert result.exit_code == 0
        assert "conv-abc" in result.output
        assert "测试对话" in result.output

    @patch("astrbot.cli.client.commands.session.list_session_conversations")
    def test_session_convs_json(self, mock_convs):
        """对话列表 JSON 输出"""
        mock_convs.return_value = {
            "status": "success",
            "conversations": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
            "current_cid": None,
            "response": "共 0 个对话",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["session", "convs", "test_session", "-j"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["status"] == "success"

    @patch("astrbot.cli.client.commands.session.get_session_history")
    def test_session_history(self, mock_history):
        """查看指定会话的聊天记录"""
        mock_history.return_value = {
            "status": "success",
            "history": [
                {"role": "user", "text": "你好"},
                {"role": "assistant", "text": "你好！"},
            ],
            "total_pages": 1,
            "page": 1,
            "conversation_id": "conv-abc",
            "session_id": "cli:FriendMessage:cli_session",
            "response": "",
        }
        runner = CliRunner()
        result = runner.invoke(
            main, ["session", "history", "cli:FriendMessage:cli_session"]
        )

        assert result.exit_code == 0
        assert "You: 你好" in result.output
        assert "AI: 你好！" in result.output

    @patch("astrbot.cli.client.commands.session.get_session_history")
    def test_session_history_with_cid(self, mock_history):
        """指定对话 ID 查看聊天记录"""
        mock_history.return_value = {
            "status": "success",
            "history": [],
            "total_pages": 0,
            "page": 1,
            "conversation_id": "conv-xyz",
            "session_id": "test_session",
            "response": "(无记录)",
        }
        runner = CliRunner()
        result = runner.invoke(
            main, ["session", "history", "test_session", "-c", "conv-xyz"]
        )

        assert result.exit_code == 0
        mock_history.assert_called_once_with(
            session_id="test_session",
            conversation_id="conv-xyz",
            page=1,
            page_size=10,
        )

    @patch("astrbot.cli.client.commands.session.list_sessions")
    def test_session_ls_empty(self, mock_list):
        """空会话列表"""
        mock_list.return_value = {
            "status": "success",
            "sessions": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
            "response": "共 0 个会话",
        }
        runner = CliRunner()
        result = runner.invoke(main, ["session", "ls"])

        assert result.exit_code == 0
        assert "没有找到会话" in result.output
