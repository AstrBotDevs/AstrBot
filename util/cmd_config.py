import os
import json
import yaml
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


def init_astrbot_config_items():
    # 加载默认配置
    cc = CmdConfig()
    cc.init_attributes("qq_forward_threshold", 200)
    cc.init_attributes("qq_welcome", "")
    cc.init_attributes("qq_pic_mode", False)
    cc.init_attributes("gocq_host", "127.0.0.1")
    cc.init_attributes("gocq_http_port", 5700)
    cc.init_attributes("gocq_websocket_port", 6700)
    cc.init_attributes("gocq_react_group", True)
    cc.init_attributes("gocq_react_guild", True)
    cc.init_attributes("gocq_react_friend", True)
    cc.init_attributes("gocq_react_group_increase", True)
    cc.init_attributes("other_admins", [])
    cc.init_attributes("CHATGPT_BASE_URL", "")
    cc.init_attributes("qqbot_secret", "")
    cc.init_attributes("qqofficial_enable_group_message", False)
    cc.init_attributes("admin_qq", "")
    cc.init_attributes("nick_qq", ["!", "！", "ai"])
    cc.init_attributes("admin_qqchan", "")
    cc.init_attributes("llm_env_prompt", "")
    cc.init_attributes("llm_wake_prefix", "")
    cc.init_attributes("default_personality_str", "")
    cc.init_attributes("openai_image_generate", {
        "model": "dall-e-3",
        "size": "1024x1024",
        "style": "vivid",
        "quality": "standard",
    })
    cc.init_attributes("http_proxy", "")
    cc.init_attributes("https_proxy", "")
    cc.init_attributes("dashboard_username", "")
    cc.init_attributes("dashboard_password", "")



def try_migrate_config():
    '''
    将 cmd_config.json 迁移至 data/cmd_config.json
    '''
    print("try migrate configs")
    if os.path.exists("cmd_config.json"):
        with open("cmd_config.json", "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        with open("data/cmd_config.json", "w", encoding="utf-8-sig") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            os.remove("cmd_config.json")
        except Exception as e:
            pass
    if not os.path.exists("cmd_config.json") and not os.path.exists("data/cmd_config.json"):
        # 从 configs/config.yaml 上拿数据
        configs_pth = os.path.abspath(os.path.join(os.path.abspath(__file__), "../../configs/config.yaml"))
        with open(configs_pth, encoding='utf-8') as f:
            data = yaml.load(f, Loader=yaml.Loader)
            print(data)
            with open("data/cmd_config.json", "w", encoding="utf-8-sig") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
