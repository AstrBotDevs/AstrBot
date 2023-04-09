import threading
import asyncio
import os, sys

abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'

def main(loop, event):
    import cores.qqbot.core as qqBot
    import yaml
    ymlfile =  open(abs_path+"configs/config.yaml", 'r', encoding='utf-8')
    cfg = yaml.safe_load(ymlfile)

    if 'http_proxy' in cfg:
        os.environ['HTTP_PROXY'] = cfg['http_proxy']
    if 'https_proxy' in cfg:
        os.environ['HTTPS_PROXY'] = cfg['https_proxy']

    provider = privider_chooser(cfg)
    print('[System] 当前语言模型提供商: ' + str(provider))
    # 执行Bot
    qqBot.initBot(cfg, provider)

# 语言模型提供商选择器
# 目前有：OpenAI官方API、逆向库
def privider_chooser(cfg):
    l = []
    if 'rev_ChatGPT' in cfg and cfg['rev_ChatGPT']['enable']:
        l.append('rev_chatgpt')
    if 'rev_ernie' in cfg and cfg['rev_ernie']['enable']:
        l.append('rev_ernie')
    if 'rev_edgegpt' in cfg and cfg['rev_edgegpt']['enable']:
        l.append('rev_edgegpt')
    if 'openai' in cfg and cfg['openai']['key'] != None and len(cfg['openai']['key'])>0:
        l.append('openai_official')
    return l

def check_env():
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 8):
        print("请使用Python3.8运行本项目")
        input("按任意键退出...")
        exit()
    try:
        print("检查依赖库中...")
        if os.path.exists('requirements.txt'):
            os.system("pip3 install -r requirements.txt")
        elif os.path.exists('QQChannelChatGPT'+ os.sep +'requirements.txt'):
            os.system('QQChannelChatGPT'+ os.sep +'requirements.txt')
        os.system("clear")
        print("安装依赖库完毕...")
    except BaseException as e:
        print("安装依赖库失败，请手动安装依赖库。")
        print(e)
        input("按任意键退出...")
        exit()
    
    # 检查key
    with open(abs_path+"configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
        import yaml
        cfg = yaml.safe_load(ymlfile)
        if cfg['openai']['key'] == '' or cfg['openai']['key'] == None:
            print("请先在configs/config.yaml下添加一个可用的OpenAI Key。详情请前往https://beta.openai.com/account/api-keys")
        if cfg['qqbot']['appid'] == '' or cfg['qqbot']['token'] == '' or cfg['qqbot']['appid'] == None or cfg['qqbot']['token'] == None: 
            print("请先在configs/config.yaml下完善appid和token令牌(在https://q.qq.com/上注册一个QQ机器人即可获得)")

def get_platform():
    import platform
    sys_platform = platform.platform().lower()
    if "windows" in sys_platform:
        return "win"
    elif "macos" in sys_platform:
        return "mac"
    elif "linux" in sys_platform:
        return "linux"
    else:
        print("other")

if __name__ == "__main__":
    check_env()
    bot_event = threading.Event()
    loop = asyncio.get_event_loop()
    main(loop, bot_event)