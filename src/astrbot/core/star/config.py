"""
此功能已过时，参考 https://astrbot.app/dev/plugin.html#%E6%B3%A8%E5%86%8C%E6%8F%92%E4%BB%B6%E9%85%8D%E7%BD%AE-beta
"""

from typing import Union
import os
import json
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


def load_config(namespace: str) -> Union[dict, bool]:
    """
    从配置文件中加载配置。
    namespace: str, 配置的唯一识别符，也就是配置文件的名字。
    返回值: 当配置文件存在时，返回 namespace 对应配置文件的内容dict，否则返回 False。
    """
    path = os.path.join(get_astrbot_data_path(), "config", f"{namespace}.json")
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8-sig") as f:
        ret = {}
        data = json.load(f)
        for k in data:
            ret[k] = data[k]["value"]
        return ret


def put_config(namespace: str, name: str, key: str, value, description: str):
    """
    将配置项写入以namespace为名字的配置文件，如果key不存在于目标配置文件中。当前 value 仅支持 str, int, float, bool, list 类型（暂不支持 dict）。
    namespace: str, 配置的唯一识别符，也就是配置文件的名字。
    name: str, 配置项的显示名字。
    key: str, 配置项的键。
    value: str, int, float, bool, list, 配置项的值。
    description: str, 配置项的描述。
    注意：只有当 namespace 为插件名(info 函数中的 name)时，该配置才会显示到可视化面板上。
    注意：value一定要是该配置项对应类型的值，否则类型判断会乱。
    """
    if namespace == "":
        raise ValueError("namespace 不能为空。")
    if namespace.startswith("internal_"):
        raise ValueError("namespace 不能以 internal_ 开头。")
    if not isinstance(key, str):
        raise ValueError("key 只支持 str 类型。")
    if not isinstance(value, (str, int, float, bool, list)):
        raise ValueError("value 只支持 str, int, float, bool, list 类型。")

    config_dir = os.path.join(get_astrbot_data_path(), "config")
    path = os.path.join(config_dir, f"{namespace}.json")

    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write("{}")
    with open(path, "r", encoding="utf-8-sig") as f:
        d = json.load(f)
    assert isinstance(d, dict)
    if key not in d:
        d[key] = {
            "config_type": "item",
            "name": name,
            "description": description,
            "path": key,
            "value": value,
            "val_type": type(value).__name__,
        }
        with open(path, "w", encoding="utf-8-sig") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
            f.flush()


def update_config(namespace: str, key: str, value):
    """
    更新配置文件中的配置项。
    namespace: str, 配置的唯一识别符，也就是配置文件的名字。
    key: str, 配置项的键。
    value: str, int, float, bool, list, 配置项的值。
    """
    path = os.path.join(get_astrbot_data_path(), "config", f"{namespace}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件 {namespace}.json 不存在。")
    with open(path, "r", encoding="utf-8-sig") as f:
        d = json.load(f)
    assert isinstance(d, dict)
    if key not in d:
        raise KeyError(f"配置项 {key} 不存在。")
    d[key]["value"] = value
    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.flush()
