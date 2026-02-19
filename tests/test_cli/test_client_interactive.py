"""CLI Client 交互模式单元测试"""

from unittest.mock import patch

from astrbot.cli.client.commands.interactive import _resolve_repl_command


class TestResolveReplCommand:
    """REPL 命令解析测试"""

    def setup_method(self):
        """设置命令映射表"""
        self.command_map = {
            "conv ls": "/ls",
            "conv new": "/new",
            "conv switch": "/switch",
            "conv del": "/del",
            "conv rename": "/rename",
            "conv reset": "/reset",
            "conv history": "/history",
            "plugin ls": "/plugin ls",
            "plugin on": "/plugin on",
            "plugin off": "/plugin off",
            "plugin help": "/plugin help",
            "provider": "/provider",
            "model": "/model",
            "key": "/key",
            "help": "/help",
            "sid": "/sid",
            "t2i": "/t2i",
            "tts": "/tts",
        }

    def test_conv_ls(self):
        """conv ls 映射到 /ls"""
        assert _resolve_repl_command("conv ls", self.command_map) == "/ls"

    def test_conv_ls_with_page(self):
        """conv ls 2 映射到 /ls 2"""
        assert _resolve_repl_command("conv ls 2", self.command_map) == "/ls 2"

    def test_conv_switch(self):
        """conv switch 3 映射到 /switch 3"""
        assert _resolve_repl_command("conv switch 3", self.command_map) == "/switch 3"

    def test_conv_rename(self):
        """conv rename 新名称 映射"""
        assert (
            _resolve_repl_command("conv rename 新名称", self.command_map)
            == "/rename 新名称"
        )

    def test_plugin_ls(self):
        """plugin ls 映射"""
        assert _resolve_repl_command("plugin ls", self.command_map) == "/plugin ls"

    def test_plugin_on(self):
        """plugin on name 映射"""
        assert (
            _resolve_repl_command("plugin on myplugin", self.command_map)
            == "/plugin on myplugin"
        )

    def test_provider(self):
        """provider 映射"""
        assert _resolve_repl_command("provider", self.command_map) == "/provider"

    def test_provider_with_index(self):
        """provider 1 映射"""
        assert _resolve_repl_command("provider 1", self.command_map) == "/provider 1"

    def test_model(self):
        """model 映射"""
        assert _resolve_repl_command("model", self.command_map) == "/model"

    def test_model_with_name(self):
        """model gpt-4 映射"""
        assert _resolve_repl_command("model gpt-4", self.command_map) == "/model gpt-4"

    def test_help(self):
        """help 映射"""
        assert _resolve_repl_command("help", self.command_map) == "/help"

    def test_sid(self):
        """sid 映射"""
        assert _resolve_repl_command("sid", self.command_map) == "/sid"

    def test_passthrough_message(self):
        """普通消息原样传递"""
        assert _resolve_repl_command("你好", self.command_map) == "你好"

    def test_passthrough_slash_command(self):
        """斜杠命令原样传递"""
        assert _resolve_repl_command("/help", self.command_map) == "/help"

    def test_passthrough_unknown(self):
        """未知命令原样传递"""
        assert _resolve_repl_command("unknown cmd", self.command_map) == "unknown cmd"

    def test_exact_match_priority(self):
        """精确匹配优先于前缀匹配"""
        assert _resolve_repl_command("conv ls", self.command_map) == "/ls"

    def test_key(self):
        """key 映射"""
        assert _resolve_repl_command("key", self.command_map) == "/key"

    def test_key_with_index(self):
        """key 1 映射"""
        assert _resolve_repl_command("key 1", self.command_map) == "/key 1"

    def test_t2i(self):
        """t2i 映射"""
        assert _resolve_repl_command("t2i", self.command_map) == "/t2i"

    def test_tts(self):
        """tts 映射"""
        assert _resolve_repl_command("tts", self.command_map) == "/tts"


class TestInteractiveRepl:
    """交互模式 REPL 测试"""

    @patch("astrbot.cli.client.commands.interactive.send_message")
    def test_quit(self, mock_send):
        """输入 /quit 退出"""
        from click.testing import CliRunner

        from astrbot.cli.client.commands.interactive import interactive

        runner = CliRunner()
        result = runner.invoke(interactive, input="/quit\n")

        assert result.exit_code == 0
        assert "再见" in result.output

    @patch("astrbot.cli.client.commands.interactive.send_message")
    def test_exit(self, mock_send):
        """输入 exit 退出"""
        from click.testing import CliRunner

        from astrbot.cli.client.commands.interactive import interactive

        runner = CliRunner()
        result = runner.invoke(interactive, input="exit\n")

        assert result.exit_code == 0
        assert "再见" in result.output

    @patch("astrbot.cli.client.commands.interactive.send_message")
    def test_send_message(self, mock_send):
        """在 REPL 中发送消息"""
        from click.testing import CliRunner

        from astrbot.cli.client.commands.interactive import interactive

        mock_send.return_value = {"status": "success", "response": "hi", "images": []}

        runner = CliRunner()
        result = runner.invoke(interactive, input="你好\n/quit\n")

        assert result.exit_code == 0
        mock_send.assert_any_call("你好")

    @patch("astrbot.cli.client.commands.interactive.send_message")
    def test_empty_line_ignored(self, mock_send):
        """空行被忽略"""
        from click.testing import CliRunner

        from astrbot.cli.client.commands.interactive import interactive

        runner = CliRunner()
        result = runner.invoke(interactive, input="\n\n/quit\n")

        assert result.exit_code == 0
        mock_send.assert_not_called()

    @patch("astrbot.cli.client.commands.interactive.send_message")
    def test_repl_command_mapping(self, mock_send):
        """REPL 中子命令映射"""
        from click.testing import CliRunner

        from astrbot.cli.client.commands.interactive import interactive

        mock_send.return_value = {"status": "success", "response": "ok", "images": []}

        runner = CliRunner()
        result = runner.invoke(interactive, input="conv ls\n/quit\n")

        assert result.exit_code == 0
        mock_send.assert_any_call("/ls")

    @patch("astrbot.cli.client.commands.interactive.send_message")
    def test_error_response(self, mock_send):
        """错误响应显示"""
        from click.testing import CliRunner

        from astrbot.cli.client.commands.interactive import interactive

        mock_send.return_value = {"status": "error", "error": "Connection failed"}

        runner = CliRunner()
        result = runner.invoke(interactive, input="hello\n/quit\n")

        assert result.exit_code == 0
        assert "Connection failed" in result.output
