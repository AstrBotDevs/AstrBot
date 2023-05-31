import os
import json

cpath = "cmd_config.json"

def check_exist():
    if not os.path.exists(cpath):
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)
            f.flush()

class CmdConfig():

    @staticmethod
    def get(key, default=None):
        check_exist()
        with open(cpath, "r", encoding="utf-8") as f:
            d = json.load(f)
            if key in d:
                return d[key]
            else:
                return default
            
    @staticmethod
    def get_all():
        check_exist()
        with open(cpath, "r", encoding="utf-8") as f:
            return json.load(f)
        
    @staticmethod
    def put(key, value):
        check_exist()
        with open(cpath, "r", encoding="utf-8") as f:
            d = json.load(f)
            d[key] = value
            with open(cpath, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=4)
                f.flush()

    @staticmethod
    def init_attributes(keys: list, init_val = ""):
        check_exist()
        with open(cpath, "r", encoding="utf-8") as f:
            d = json.load(f)
            _tag = False
            for k in keys:
                if k not in d:
                    d[k] = init_val
                    _tag = True
            if _tag:
                with open(cpath, "w", encoding="utf-8") as f:
                    json.dump(d, f, indent=4)
                    f.flush()