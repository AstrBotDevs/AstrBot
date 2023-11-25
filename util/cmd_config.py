import os
import json

cpath = "cmd_config.json"

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
    def init_attributes(keys: list, init_val = ""):
        check_exist()
        conf_str = ''
        with open(cpath, "r", encoding="utf-8-sig") as f:
             conf_str = f.read()
        if conf_str.startswith(u'/ufeff'):
            conf_str = conf_str.encode('utf8')[3:].decode('utf8')
        d = json.loads(conf_str)
        _tag = False
        for k in keys:
            if k not in d:
                d[k] = init_val
                _tag = True
        if _tag:
            with open(cpath, "w", encoding="utf-8-sig") as f:
                json.dump(d, f, indent=4, ensure_ascii=False)
                f.flush()