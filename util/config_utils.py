import json, os
from util.cmd_config import CmdConfig
from type.config import VERSION
from type.types import Context

def init_configs():
    '''
    初始化必需的配置项
    '''
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
    
    # aiocqhttp 适配器
    cc.init_attributes("aiocqhttp", {
        "enable": False,
        "ws_reverse_host": "",
        "ws_reverse_port": 0,
    })

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
        
def inject_to_context(context: Context):
    '''
    将配置注入到 Context 中。
    this method returns all the configs
    '''
    cc = CmdConfig()
    
    context.version = VERSION
    context.base_config = cc.get_all()
    
    cfg = context.base_config
    
    if 'reply_prefix' in cfg:
        # 适配旧版配置
        if isinstance(cfg['reply_prefix'], dict):
            context.reply_prefix = ""
            cfg['reply_prefix'] = ""
            cc.put("reply_prefix", "")
        else:
            context.reply_prefix = cfg['reply_prefix']

    default_personality_str = cc.get("default_personality_str", "")
    if default_personality_str == "":
        context.default_personality = None
    else:
        context.default_personality = {
            "name": "default",
            "prompt": default_personality_str,
        }

    if 'uniqueSessionMode' in cfg and cfg['uniqueSessionMode']:
        context.unique_session = True
    else:
        context.unique_session = False
        
    nick_qq = cc.get("nick_qq", None)
    if nick_qq == None:
        nick_qq = ("/", )
    if isinstance(nick_qq, str):
        nick_qq = (nick_qq, )
    if isinstance(nick_qq, list):
        nick_qq = tuple(nick_qq)
    context.nick = nick_qq
    context.t2i_mode = cc.get("qq_pic_mode", False)
    
    return cfg