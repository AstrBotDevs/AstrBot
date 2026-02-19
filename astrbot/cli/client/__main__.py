#!/usr/bin/env python3
"""
AstrBot CLI Client - 跨平台Socket客户端

支持Unix Socket和TCP Socket连接到CLIPlatformAdapter

用法:
    astr "你好"
    astr "/help"
    echo "你好" | astr
"""

# 抑制框架导入时的日志输出（必须在所有导入之前执行）
import logging

# 禁用所有 astrbot 相关日志
logging.getLogger("astrbot").setLevel(logging.CRITICAL + 1)
logging.getLogger("astrbot.core").setLevel(logging.CRITICAL + 1)
# 禁用根日志记录器的控制台输出
root = logging.getLogger()
root.setLevel(logging.CRITICAL + 1)
# 移除可能存在的控制台处理器
for handler in root.handlers[:]:
    if isinstance(handler, logging.StreamHandler):
        root.removeHandler(handler)

import io  # noqa: E402
import sys  # noqa: E402

import click  # noqa: E402

# 仅使用标准库导入，不导入astrbot框架
# Windows UTF-8 输出支持（仅在非测试环境下替换，避免与 pytest capture 冲突）
if sys.platform == "win32" and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


EPILOG = """
命令总览 (所有命令均支持 -j/--json 输出原始 JSON):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [发送消息]
    astr <message>                  直接发送消息（隐式调用 send）
    astr send <message>             显式发送消息给 AstrBot
    astr send -t 60 <message>      设置超时（秒），默认 30
    echo "msg" | astr               从管道读取消息

  [会话管理] astr conv <子命令>
    astr conv ls [page]             列出所有对话（可翻页）
    astr conv new                   创建新对话并切换到该对话
    astr conv switch <index>        按序号切换对话（序号见 conv ls）
    astr conv del                   删除当前对话
    astr conv rename <name>         重命名当前对话
    astr conv reset                 清除当前对话的 LLM 上下文
    astr conv history [page]        查看当前对话的聊天记录

  [插件管理] astr plugin <子命令>
    astr plugin ls                  列出已安装插件及状态
    astr plugin on <name>           启用指定插件
    astr plugin off <name>          禁用指定插件
    astr plugin help [name]         查看插件帮助（省略 name 则查看全部）

  [LLM 配置]
    astr provider [index]           查看 Provider 列表 / 按序号切换
    astr model [index|name]         查看模型列表 / 按序号或名称切换
    astr key [index]                查看 API Key 列表 / 按序号切换

  [快捷命令]
    astr help                       查看 AstrBot 服务端内置指令帮助
    astr sid                        查看当前会话 ID 和管理员 ID
    astr t2i                        开关文字转图片（会话级别）
    astr tts                        开关文字转语音（会话级别）

  [日志查看]
    astr log                        读取最近 100 行日志（直接读文件）
    astr log --lines 50             指定行数
    astr log --level ERROR          按级别过滤 (DEBUG/INFO/WARNING/ERROR)
    astr log --pattern "关键词"     按关键词过滤（--regex 启用正则）
    astr log --socket               通过 Socket 从服务端获取日志

  [调试工具]
    astr ping [-c N]                测试连通性和延迟（-c 指定次数）
    astr status                     查看连接配置、Token、服务状态
    astr test echo <message>        发送消息并查看完整回环响应
    astr test plugin <cmd> <args>   测试插件命令（发送 /<cmd> <args>）
                                    例: astr test plugin probe cpu
                                    → 实际发送 /probe cpu

  [函数工具] astr tool <子命令>
    astr tool ls                    列出所有注册的函数工具
    astr tool ls -o plugin          按来源过滤（plugin/mcp/builtin）
    astr tool info <name>           查看工具详细信息和参数
    astr tool call <name> [json]    调用工具，例: astr tool call my_func '{"k":"v"}'

  [交互模式]
    astr interactive                进入 REPL 模式（支持命令历史）
    astr -i                         同上（快捷方式）

  [批量执行]
    astr batch <file>               从文件逐行读取并执行命令
                                    （# 开头为注释，空行跳过）

兼容旧用法: astr --log = astr log | astr -j "msg" = astr send -j "msg"

连接: 自动读取 data/.cli_connection 和 data/.cli_token
      需在 AstrBot 根目录运行，或设置 ASTRBOT_ROOT 环境变量
"""


class RawEpilogGroup(click.Group):
    """保留 epilog 原始格式的 Group，同时支持默认子命令路由"""

    def format_epilog(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        if self.epilog:
            formatter.write("\n")
            for line in self.epilog.split("\n"):
                formatter.write(line + "\n")

    # send 子命令的 option 前缀，用于识别 astr -j "你好" 等旧用法
    _send_opts = {"-j", "--json", "-t", "--timeout", "-s", "--socket"}
    # --log 旧用法映射到 log 子命令
    _log_flag = {"--log"}
    # -i 快捷方式映射到 interactive 子命令
    _interactive_flag = {"-i"}

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args:
            first = args[0]
            if first in self._log_flag:
                # astr --log ... → astr log ...
                args = ["log"] + args[1:]
            elif first in self._interactive_flag:
                # astr -i → astr interactive
                args = ["interactive"] + args[1:]
            elif first not in self.commands:
                if not first.startswith("-") or first in self._send_opts:
                    # astr 你好 / astr -j "你好" → astr send ...
                    args = ["send"] + args
        return super().parse_args(ctx, args)


@click.group(
    cls=RawEpilogGroup,
    invoke_without_command=True,
    epilog=EPILOG,
)
@click.pass_context
def main(ctx: click.Context) -> None:
    """AstrBot CLI Client - 与 AstrBot 交互的命令行工具"""
    if ctx.invoked_subcommand is None:
        # 无子命令时，检查 stdin 是否有管道输入
        if not sys.stdin.isatty():
            message = sys.stdin.read().strip()
            if message:
                from .commands.send import do_send

                do_send(message, None, 30.0, False)
                return
        click.echo(ctx.get_help())


# 注册所有子命令
from .commands import register_commands  # noqa: E402

register_commands(main)


if __name__ == "__main__":
    main()
