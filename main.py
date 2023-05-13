import threading
import asyncio
import os, sys
from pip._internal import main as pipmain

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

    # 检查pip
    # pip_tag = "pip"
    # mm = os.system("pip -V")
    # if mm != 0:
    #     mm1 = os.system("pip3 -V")
    #     if mm1 != 0:
    #         print("未检测到pip, 请安装Python(版本应>=3.9)")
    #         input("按任意键退出...")
    #         exit()
    #     else:
    #         pip_tag = "pip3"
    
    if os.path.exists('requirements.txt'):
        pth = 'requirements.txt'
    else:
        pth = 'QQChannelChatGPT'+ os.sep +'requirements.txt'
    print("正在更新三方依赖库...")
    try:
        pipmain(['install', '-r', pth])
        print("依赖库安装完毕。")
    except BaseException as e:
        print(e)
        while True:
            res = input("依赖库可能安装失败了。\n如果是报错ValueError: check_hostname requires server_hostname，请尝试先关闭代理后重试。\n输入y回车重试\n输入c回车使用国内镜像源下载\n输入其他按键回车继续往下执行。")
            if res == "y":
                try:
                    pipmain(['install', '-r', pth])
                    print("依赖库安装完毕。")
                    break
                except BaseException as e:
                    print(e)
                    continue

            elif res == "c":
                try:
                    pipmain(['install', '-r', pth, '-i', 'https://mirrors.aliyun.com/pypi/simple/'])
                    print("依赖库安装完毕。")
                    break
                except BaseException as e:
                    print(e)
                    continue
            else:
                break

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

    # 获取参数
    args = sys.argv
    if len(args) > 1:
        if args[1] == '-replit':
            print("[System] 启动Replit Web保活服务...")
            try:
                from webapp_replit import keep_alive
                keep_alive()
            except BaseException as e:
                print(e)
                print(f"[System-err] Replit Web保活服务启动失败:{str(e)}")

    bot_event = threading.Event()
    loop = asyncio.get_event_loop()
    main(loop, bot_event)