import os, sys
from pip._internal import main as pipmain
import warnings
import traceback
import threading
import logging

warnings.filterwarnings("ignore")
abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S',
    )
    # config.yaml 配置文件加载和环境确认
    try:
        import cores.qqbot.core as qqBot
        import yaml
        from yaml.scanner import ScannerError
        import util.general_utils as gu
        ymlfile =  open(abs_path+"configs/config.yaml", 'r', encoding='utf-8')
        cfg = yaml.safe_load(ymlfile)
    except ImportError as import_error:
        print(import_error)
        input("第三方库未完全安装完毕，请退出程序重试。")
    except FileNotFoundError as file_not_found:
        print(file_not_found)
        input("配置文件不存在，请检查是否已经下载配置文件。")
    except ScannerError as e:
        print(traceback.format_exc())
        input("config.yaml 配置文件格式错误，请遵守 yaml 格式。")

    # 设置代理
    if 'http_proxy' in cfg and cfg['http_proxy'] != '':
        os.environ['HTTP_PROXY'] = cfg['http_proxy']
    if 'https_proxy' in cfg and cfg['https_proxy'] != '':
        os.environ['HTTPS_PROXY'] = cfg['https_proxy']
    
    os.environ['NO_PROXY'] = 'cn.bing.com,https://api.sgroup.qq.com'

    # 检查并创建 temp 文件夹
    if not os.path.exists(abs_path + "temp"):
        os.mkdir(abs_path+"temp")

    # 选择默认模型
    provider = privider_chooser(cfg)
    if len(provider) == 0:
        gu.log("注意：您目前未开启任何语言模型。", gu.LEVEL_WARNING)

    # 启动主程序（cores/qqbot/core.py）
    qqBot.initBot(cfg, provider)

# 语言模型提供商选择器
def privider_chooser(cfg):
    l = []
    if 'rev_ChatGPT' in cfg and cfg['rev_ChatGPT']['enable']:
        l.append('rev_chatgpt')
    if 'rev_ernie' in cfg and cfg['rev_ernie']['enable']:
        l.append('rev_ernie')
    if 'rev_edgegpt' in cfg and cfg['rev_edgegpt']['enable']:
        l.append('rev_edgegpt')
    if 'openai' in cfg and len(cfg['openai']['key']) > 0 and cfg['openai']['key'][0] is not None:
        l.append('openai_official')
    return l

def check_env(ch_mirror=False):
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 9):
        print("请使用Python3.9+运行本项目")
        input("按任意键退出...")
        exit()
    
    if os.path.exists('requirements.txt'):
        pth = 'requirements.txt'
    else:
        pth = 'QQChannelChatGPT'+ os.sep +'requirements.txt'
    print("正在检查更新第三方库...")
    try:
        if ch_mirror:
            print("使用阿里云镜像")
            pipmain(['install', '-r', pth, '-i', 'https://mirrors.aliyun.com/pypi/simple/', '--quiet'])
        else:
            pipmain(['install', '-r', pth, '--quiet'])
    except BaseException as e:
        print(e)
        while True:
            res = input("安装失败。\n如报错ValueError: check_hostname requires server_hostname，请尝试先关闭代理后重试。\n1.输入y回车重试\n2. 输入c回车使用国内镜像源下载\n3. 输入其他按键回车继续往下执行。")
            if res == "y":
                try:
                    pipmain(['install', '-r', pth])
                    break
                except BaseException as e:
                    print(e)
                    continue
            elif res == "c":
                try:
                    pipmain(['install', '-r', pth, '-i', 'https://mirrors.aliyun.com/pypi/simple/'])
                    break
                except BaseException as e:
                    print(e)
                    continue
            else:
                break
    print("第三方库检查完毕。")

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
    args = sys.argv

    if '-cn' in args:
        check_env(True)
    else:
        check_env()

    if '-replit' in args:
        print("[System] 启动Replit Web保活服务...")
        try:
            from util.webapp_replit import keep_alive
            keep_alive()
        except BaseException as e:
            print(e)
            print(f"[System-err] Replit Web保活服务启动失败:{str(e)}")
    
    t = threading.Thread(target=main, daemon=False)
    t.start()
    t.join()
