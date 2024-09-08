import os
import json
from type.config import DEFAULT_CONFIG

cpath = "data/cmd_config.json"

def check_exist():
    if not os.path.exists(cpath):
        with open(cpath, "w", encoding="utf-8-sig") as f:
            json.dump({}, f, ensure_ascii=False)
            f.flush()

class CmdConfig():
    def __init__(self) -> None:
        self.cached_config: dict = {}
        self.init_configs()
    
    def init_configs(self):
        '''
        初始化必需的配置项
        '''
        self.init_config_items(DEFAULT_CONFIG)

    @staticmethod
    def get(key, default=None):
        '''
        从文件系统中直接获取配置
        '''
        check_exist()
        with open(cpath, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
            if key in d:
                return d[key]
            else:
                return default

    def get_all(self):
        '''
        从文件系统中获取所有配置
        '''
        check_exist()
        with open(cpath, "r", encoding="utf-8-sig") as f:
            conf_str = f.read() 
        if conf_str.startswith(u'/ufeff'): # remove BOM
            conf_str = conf_str.encode('utf8')[3:].decode('utf8')
        conf = json.loads(conf_str)
        return conf

    def put(self, key, value):
        with open(cpath, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
            d[key] = value
            with open(cpath, "w", encoding="utf-8-sig") as f:
                json.dump(d, f, indent=2, ensure_ascii=False)
                f.flush()

        self.cached_config[key] = value

    @staticmethod
    def put_by_dot_str(key: str, value):
        '''
        根据点分割的字符串，将值写入配置文件
        '''
        with open(cpath, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
            _d = d
            _ks = key.split(".")
            for i in range(len(_ks)):
                if i == len(_ks) - 1:
                    _d[_ks[i]] = value
                else:
                    _d = _d[_ks[i]]
            with open(cpath, "w", encoding="utf-8-sig") as f:
                json.dump(d, f, indent=2, ensure_ascii=False)
                f.flush()

    def init_config_items(self, d: dict):
        conf = self.get_all()
        
        if not self.cached_config:
            self.cached_config = conf

        _tag = False

        for key, val in d.items():
            if key not in conf:
                conf[key] = val
                _tag = True
        if _tag:
            with open(cpath, "w", encoding="utf-8-sig") as f:
                json.dump(conf, f, indent=2, ensure_ascii=False)
                f.flush()
