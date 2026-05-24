from .cmd_bk import bk
from .cmd_conf import conf
from .cmd_init import init
from .cmd_migrate import migrate
from .cmd_plug import plug
from .cmd_run import run
from .cmd_service import service
from .cmd_uninstall import uninstall

config = conf

__all__ = [
    "bk",
    "conf",
    "config",
    "init",
    "migrate",
    "plug",
    "run",
    "service",
    "uninstall",
]
