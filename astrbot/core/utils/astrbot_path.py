"""
Astrbot统一路径获取

项目路径：固定为源码所在路径
根目录路径：默认为当前工作目录，可通过环境变量 ASTRBOT_ROOT 指定
配置文件路径：固定为根目录下的 config 目录
插件目录路径：固定为根目录下的 plugins 目录
临时目录路径：固定为根目录下的 temp 目录
缓存目录路径：固定为根目录下的 cache 目录

前端路径：固定为根目录下的 webroot 目录
"""
from __future__ import annotations
import os
from pathlib import Path
from pydantic import BaseModel

def get_astrbot_path() -> Path:
    """获取Astrbot项目路径，即将弃用"""
    # return os.path.realpath(
    #     os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../")
    # )
    return Path(__file__).resolve().parent.parent.parent.parent


def get_astrbot_root() -> Path:
    """获取Astrbot根目录路径，即将弃用"""

    if path := os.environ.get("ASTRBOT_ROOT"):
        return Path(path).absolute()
    else:
        return Path.home() / ".astrbot"

def check_astrbot_root(path: Path) -> bool:
    """检查路径是否为Astrbot根目录 ，即将弃用"""
    if path.is_dir():
        return (path / ".astrbot").exists()
    return False

def get_astrbot_webroot_path() -> Path:
    """获取Astrbot dashboard目录路径，即将弃用"""
    return get_astrbot_root() / "webroot"

def get_astrbot_dist_path() -> Path:
    """获取Astrbot dashboard dist路径，即将弃用"""
    return get_astrbot_webroot_path() / "dist"

def get_astrbot_config_path() -> Path:
    """获取Astrbot配置文件路径，即将弃用"""
    return get_astrbot_root() / "config"

def get_astrbot_plugin_path() -> Path:
    """获取Astrbot插件目录路径，即将弃用"""
    return get_astrbot_root() / "plugins"

def get_astrbot_temp_path() -> Path:
    """获取临时目录路径，即将弃用"""
    return get_astrbot_root() / "temp"

def get_astrbot_data_path() -> Path:
    """获取Astrbot数据目录路径（已弃用，请使用 get_astrbot_root）"""
    return get_astrbot_root()
"""
弃用说明
在没有astrbot_root ,cwd/data/即为根目录
data数据目录现在变更为astrbot_root
如果在astrbot_root下又新建了data目录
可能会导致误会
于是干脆就不要data文件夹了，或者data文件夹改为真正的数据目录
（astrbot_root本身就是数据目录，区别于源代码目录）

"""



# 缓存和临时目录的区别
# 缓存目录用于加速程序 / 减少内存占用 避免重复计算
# 临时目录则单纯用于存储一些临时文件


def get_astrbot_cache_path() -> Path:
    """获取缓存目录路径，即将弃用"""
    return get_astrbot_root() / "cache"


# 新版过渡 逐步淘汰以上写法
class AstrbotFS(BaseModel):
    """Astrbot路径类"""
    root: Path
    instance : AstrbotFS | None = None

    @property
    def dot_astrbot(self) -> Path:
        """获取Astrbot根目录下的 .astrbot 标记文件"""
        return self.root / ".astrbot"

    @property
    def is_astrbot_root(self) -> bool:
        """检查当前路径是否为Astrbot根目录"""
        return self.dot_astrbot.exists()

    @property
    def webroot(self) -> Path:
        """获取Astrbot dashboard目录路径"""
        return self.root / "webroot"
    
    @property
    def dist(self) -> Path:
        """获取Astrbot dashboard dist路径"""
        return self.webroot / "dist"

    @property   
    def config(self) -> Path:
        """获取Astrbot配置文件路径"""
        return self.root / "config"

    @property
    def plugins(self) -> Path:
        """获取Astrbot插件目录路径"""
        return self.root / "plugins"
    
    @property
    def temp(self) -> Path:
        """获取临时目录路径"""
        return self.root / "temp"

    @property
    def cache(self) -> Path:
        """获取缓存目录路径"""
        return self.root / "cache"

    def get_path(self, path: str) -> Path:
        """输入相对于根目录的路径，返回绝对路径
        请使用 / 作为路径分隔符
        """
        if path.startswith("/"):
            path = path[1:]
        return self.root / path


    def init(self) -> None:
        """初始化路径"""
        self.root.mkdir(parents=True, exist_ok=True)
        self.webroot.mkdir(parents=True, exist_ok=True)
        self.config.mkdir(parents=True, exist_ok=True)
        self.plugins.mkdir(parents=True, exist_ok=True)
        self.temp.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> AstrbotFS:
        """从环境变量获取Astrbot路径"""
        path = os.environ.get("ASTRBOT_ROOT")
        if not path:
            raise ValueError("ASTRBOT_ROOT environment variable is not set")
        cls.instance = cls(root=Path(path))
        return cls.instance


    @classmethod
    def from_path(cls,path: Path | str ) -> "AstrbotFS":
        """从路径获取Astrbot路径"""
        if isinstance(path, str):
            path = Path(path)
        if path.is_dir():
            cls.instance = cls(root=path)
            return cls.instance
        raise ValueError(f"{path} is not a directory")

    @classmethod
    def from_cwd(cls) -> AstrbotFS:
        """从当前工作目录获取Astrbot路径"""
        cls.instance = cls(root=Path.cwd())
        return cls.instance

    @classmethod
    def from_default(cls) -> AstrbotFS:
        """从默认路径获取Astrbot路径"""
        cls.instance = cls(root=Path.home() / ".astrbot")
        return cls.instance

    @classmethod
    def getAstrbotRoot(cls,path: Path | str | None = None) -> AstrbotFS:
        """获取Astrbot路径管理器"""
        if path:
            return cls.from_path(path) 
        if cls.instance:
            return cls.instance
        return cls.from_env() if os.environ.get("ASTRBOT_ROOT") else cls.from_default()

"""
AstrbotFS使用方法：
和logger logger = logging.getLogger("astrbot") 一样
astrbot_fs = AstrbotFS.getAstrbotRoot()
全局单例

获取路径：
root = astrbot_fs.root
config = astrbot_fs.config
plugins = astrbot_fs.plugins
webroot = astrbot_fs.webroot
temp = astrbot_fs.temp
cache = astrbot_fs.cache


any_path = astrbot_fs.get_path("path/to/file") - > root / path/to/file

"""