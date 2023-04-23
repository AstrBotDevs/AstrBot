import threading
import asyncio
import os, sys

abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'

def main(loop, event):
    try:
        import cores.qqbot.core as qqBot
        import yaml
        ymlfile =  open(abs_path+"configs/config.yaml", 'r', encoding='utf-8')
        cfg = yaml.safe_load(ymlfile)
    except BaseException as e:
        print(e)
        input("yaml库未导入或者配置文件格式错误，请退出程序重试。")
        exit()

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

    if os.path.exists('requirements.txt'):
        pth = 'requirements.txt'
    else:
        pth = 'QQChannelChatGPT'+ os.sep +'requirements.txt'
    print("正在更新三方依赖库...")
    mm = os.system('pip install -r '+pth)
    if mm == 0:
        print("依赖库安装完毕。")
    else:
        while True:
            res = input("依赖库可能安装失败了。\n如果是报错ValueError: check_hostname requires server_hostname，请尝试先关闭代理后重试。\n输入y回车重试\n输入c回车使用国内镜像源下载\n输入其他按键回车继续往下执行。")
            if res == "y":
                mm = os.system('pip install -r '+pth)
                if mm == 0:
                    print("依赖库安装完毕。")
                    break
            elif res == "c":
                mm = os.system(f'pip install -r {pth} -i https://mirrors.aliyun.com/pypi/simple/')
                if mm == 0:
                    print("依赖库安装完毕。")
                    break
            else:
                break
    
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