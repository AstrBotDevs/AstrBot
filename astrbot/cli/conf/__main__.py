import click

@click.group(invoke_without_command=True)
@click.option("--timezone","-tz", default="Asia/Shanghai", help="设置时区，默认 Asia/Shanghai")
@click.option("--log-level", "-l", default="INFO", help="设置日志级别，默认 INFO")
@click.option("--dashboard-port", "-dp", default=8080, help="设置仪表盘端口，默认 8080")
@click.option("--dashboard-username", "-du", default="admin", help="设置仪表盘用户名，默认 admin")
@click.option("--dashboard-password", "-dpw", default="admin", help="设置仪表盘密码，默认 admin")
@click.option("--callback-api-base", "-cab", default="http://localhost:5000", help="设置回调 API 基础 URL，默认 http://localhost:5000")
@click.pass_context
def conf(ctx, timezone: str, log_level: str, dashboard_port: int, dashboard_username: str, dashboard_password: str, callback_api_base: str):
    """配置管理子命令组"""
    if ctx.invoked_subcommand is None:
        # 检查是否有参数被设置为非默认值
        defaults = {
            "timezone": "Asia/Shanghai",
            "log_level": "INFO",
            "dashboard_port": 8080,
            "dashboard_username": "admin",
            "dashboard_password": "admin",
            "callback_api_base": "http://localhost:5000"
        }

        current_values = {
            "timezone": timezone,
            "log_level": log_level,
            "dashboard_port": dashboard_port,
            "dashboard_username": dashboard_username,
            "dashboard_password": dashboard_password,
            "callback_api_base": callback_api_base
        }

        # 找出所有与默认值不同的配置项
        changed_configs = {}
        for key, current_value in current_values.items():
            if current_value != defaults[key]:
                # 将参数名转换为配置键格式
                config_key = key.replace("_", ".") if "dashboard" in key else key
                changed_configs[config_key] = current_value

        if changed_configs:
            # 如果有配置项被修改，则自动保存
            click.echo(click.style("检测到配置参数变更，正在保存...", fg="yellow"))
            click.echo()

            try:
                from .utils import load_config, save_config, set_nested_item
                config = load_config()

                for config_key, value in changed_configs.items():
                    set_nested_item(config, config_key, value)
                    if config_key == "dashboard.password":
                        click.echo(click.style(f"✓ 已保存: {config_key} = ********", fg="green"))
                    else:
                        click.echo(click.style(f"✓ 已保存: {config_key} = {value}", fg="green"))

                save_config(config)
                click.echo()
                click.echo(click.style("配置已成功保存！", fg="green", bold=True))

            except Exception as e:
                click.echo(click.style(f"保存配置时发生错误: {str(e)}", fg="red"))
        else:
            # 显示帮助信息
            click.echo(click.style("AstrBot 配置管理", fg="blue", bold=True))
            click.echo(click.style("=" * 30, fg="green"))
            click.echo("可用的配置命令:")
            click.echo(f"  {click.style('set', fg='magenta')}    设置配置项")
            click.echo(f"  {click.style('get', fg='magenta')}    获取配置项")
            click.echo()
            click.echo("使用 'astrbot conf <command> --help' 查看具体命令的帮助信息")
            click.echo()
            click.echo("也可以通过选项快速设置配置:")
            click.echo("  astrbot conf --timezone Asia/Tokyo")
            click.echo("  astrbot conf --dashboard-port 9090")
            click.echo(" astrbot conf --help 或者 astrbot help conf 查看支持哪些快捷配置")
        return

    ctx.ensure_object(dict)
    ctx.obj["timezone"] = timezone
    ctx.obj["log_level"] = log_level
    ctx.obj["dashboard_port"] = dashboard_port
    ctx.obj["dashboard_username"] = dashboard_username
    ctx.obj["dashboard_password"] = dashboard_password
    ctx.obj["callback_api_base"] = callback_api_base


# 名字比较特殊就这样吧
from astrbot.cli.conf.set import set_config
conf.add_command(set_config) # conf set

from astrbot.cli.conf.get import get
conf.add_command(get) # conf get

if __name__ == "__main__":
    conf()
