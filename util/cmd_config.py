import os
import json
from typing import Union

cpath = "data/cmd_config.json"

def check_exist():
    if not os.path.exists(cpath):
        with open(cpath, "w", encoding="utf-8-sig") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
            f.flush()

class CmdConfig():

    @staticmethod
    def get(key, default=None):
        check_exist()
        with open(cpath, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
            if key in d:
                return d[key]
            else:
                return default

    @staticmethod
    def get_all():
        check_exist()
        with open(cpath, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    @staticmethod
    def put(key, value):
        check_exist()
        with open(cpath, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
            d[key] = value
            with open(cpath, "w", encoding="utf-8-sig") as f:
                json.dump(d, f, indent=4, ensure_ascii=False)
                f.flush()

    @staticmethod
    def put_by_dot_str(key: str, value):
        '''
        根据点分割的字符串，将值写入配置文件
        '''
        check_exist()
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
                json.dump(d, f, indent=4, ensure_ascii=False)
                f.flush()

    @staticmethod
    def init_attributes(key: Union[str, list], init_val=""):
        check_exist()
        conf_str = ''
        with open(cpath, "r", encoding="utf-8-sig") as f:
            conf_str = f.read()
        if conf_str.startswith(u'/ufeff'):
            conf_str = conf_str.encode('utf8')[3:].decode('utf8')
        d = json.loads(conf_str)
        _tag = False

        if isinstance(key, str):
            if key not in d:
                d[key] = init_val
                _tag = True
        elif isinstance(key, list):
            for k in key:
                if k not in d:
                    d[k] = init_val
                    _tag = True
        if _tag:
            with open(cpath, "w", encoding="utf-8-sig") as f:
                json.dump(d, f, indent=4, ensure_ascii=False)
                f.flush()
