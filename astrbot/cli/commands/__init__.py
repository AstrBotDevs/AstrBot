from .cmd_bk import bk
from .cmd_conf import conf as config
from .cmd_init import init
from .cmd_password import password
from .cmd_plug import plug as plugin
from .cmd_run import run
from .cmd_service import service
from .cmd_uninstall import uninstall

conf = config
plug = plugin

__all__ = [
    "bk",
    "conf",
    "config",
    "init",
    "password",
    "plug",
    "plugin",
    "run",
    "service",
    "uninstall",
]
