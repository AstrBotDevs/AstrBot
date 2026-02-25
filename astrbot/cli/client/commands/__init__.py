"""命令注册模块 - 将所有子命令注册到主 CLI group"""

import click

from .conv import conv
from .debug import ping, status, test
from .interactive import interactive
from .log import log
from .plugin import plugin
from .provider import key, model, provider
from .send import send
from .session import session
from .tool import tool


def register_commands(group):
    """将所有子命令注册到 CLI group

    Args:
        group: click.Group 实例
    """
    # 核心命令
    group.add_command(send)
    group.add_command(log)

    # 会话管理
    group.add_command(conv)

    # 跨会话浏览
    group.add_command(session)

    # 插件管理
    group.add_command(plugin)

    # Provider/Model/Key
    group.add_command(provider)
    group.add_command(model)
    group.add_command(key)

    # 调试工具
    group.add_command(ping)
    group.add_command(status)
    group.add_command(test)

    # 函数工具管理
    group.add_command(tool)

    # 交互模式
    group.add_command(interactive)

    # 快捷别名（独立命令，映射到 send /cmd）
    _register_aliases(group)


def _register_aliases(group):
    """注册快捷别名命令"""
    from .. import connection, output

    @group.command(name="help", help="查看 AstrBot 内置命令帮助")
    @click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
    def help_cmd(use_json):
        response = connection.send_message("/help")
        output.output_response(response, use_json)

    @group.command(name="sid", help="查看当前会话 ID 和管理员 ID")
    @click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
    def sid_cmd(use_json):
        response = connection.send_message("/sid")
        output.output_response(response, use_json)

    @group.command(name="t2i", help="开关文字转图片（会话级别）")
    @click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
    def t2i_cmd(use_json):
        response = connection.send_message("/t2i")
        output.output_response(response, use_json)

    @group.command(name="tts", help="开关文字转语音（会话级别）")
    @click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
    def tts_cmd(use_json):
        response = connection.send_message("/tts")
        output.output_response(response, use_json)

    @group.command(name="batch", help="从文件批量执行命令")
    @click.argument("file", type=click.Path(exists=True))
    @click.option("-j", "--json", "use_json", is_flag=True, help="输出原始 JSON")
    def batch_cmd(file, use_json):
        """从文件逐行读取并执行命令

        \b
        示例:
          astr batch commands.txt     批量执行文件中的命令
        """
        with open(file, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                click.echo(f"[{line_num}] > {line}")
                response = connection.send_message(line)
                output.output_response(response, use_json)
                click.echo("")
