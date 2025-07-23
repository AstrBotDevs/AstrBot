import click
from astrbot.cli.conf.set import set_config
from astrbot.cli.conf.get import get

@click.group()
def conf():
    """配置管理命令

    支持的配置项:

    - timezone: 时区设置 (例如: Asia/Shanghai)

    - log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)

    - dashboard.port: Dashboard 端口

    - dashboard.username: Dashboard 用户名

    - dashboard.password: Dashboard 密码

    - callback_api_base: 回调接口基址
    """
    pass


conf.add_command(set_config) # conf set
conf.add_command(get) # conf get

if __name__ == "__main__":
    conf()
