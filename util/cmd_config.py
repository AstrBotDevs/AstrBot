import os
import json

class CmdConfig():
    def __init__(self) -> None:
        self.cpath = "cmd_config.json"
        if not os.path.exists(self.cpath):
            with open(self.cpath, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4)
                f.flush()
    def get(self, key, default=None):
        with open(self.cpath, "r", encoding="utf-8") as f:
            d = json.load(f)
            if key in d:
                return d[key]
            else:
                return default
    
    def get_all(self):
        with open(self.cpath, "r", encoding="utf-8") as f:
            return json.load(f)
        
    def put(self, key, value):
        with open(self.cpath, "r", encoding="utf-8") as f:
            d = json.load(f)
            d[key] = value
            with open(self.cpath, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=4)
                f.flush()

    def init_attributes(self, keys: list, init_val = ""):
        with open(self.cpath, "r", encoding="utf-8") as f:
            d = json.load(f)
            _tag = False
            for k in keys:
                if k not in d:
                    d[k] = init_val
                    _tag = True
            if _tag:
                with open(self.cpath, "w", encoding="utf-8") as f:
                    json.dump(d, f, indent=4)
                    f.flush()