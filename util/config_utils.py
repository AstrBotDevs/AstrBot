import json, os
from util.cmd_config import CmdConfig

def try_migrate_config():
    '''
    将 cmd_config.json 迁移至 data/cmd_config.json (如果存在的话)
    '''
    if os.path.exists("cmd_config.json"):
        with open("cmd_config.json", "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        with open("data/cmd_config.json", "w", encoding="utf-8-sig") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            os.remove("cmd_config.json")
        except Exception as e:
            pass