import json, os, shutil
import logging

logger = logging.getLogger("astrbot")

def try_migrate_config():
    '''
    将 cmd_config.json 迁移至 data/cmd_config.json (如果存在的话)
    '''
    if os.path.exists("cmd_config.json") and not os.path.exists("data/cmd_config.json"):
        try:
            shutil.move("cmd_config.json", "data/cmd_config.json")
        except:
            logger.error("迁移 cmd_config.json 失败。AstrBot 将不会读取配置文件，你可以手动将 cmd_config.json 迁移至 data/cmd_config.json。")
        