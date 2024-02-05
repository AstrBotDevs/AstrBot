import os, sys
from pip._internal import main as pipmain
import warnings
import traceback
import threading

warnings.filterwarnings("ignore")
abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'

def main():
    # config.yaml 配置文件加载和环境确认
    try:
        import cores.qqbot.core as qqBot
        import yaml
        import util.general_utils as gu
        ymlfile =  open(abs_path+"configs/config.yaml", 'r', encoding='utf-8')
        cfg = yaml.safe_load(ymlfile)
    except ImportError as import_error:
        traceback.print_exc()
        print(import_error)
        input("第三方库未完全安装完毕，请退出程序重试。")
    except FileNotFoundError as file_not_found:
        print(file_not_found)
        input("配置文件不存在，请检查是否已经下载配置文件。")
    except BaseException as e:
        print(e)
        
    # 设置代理
    if 'http_proxy' in cfg and cfg['http_proxy'] != '':
        os.environ['HTTP_PROXY'] = cfg['http_proxy']
    if 'https_proxy' in cfg and cfg['https_proxy'] != '':
        os.environ['HTTPS_PROXY'] = cfg['https_proxy']
    
    os.environ['NO_PROXY'] = 'https://api.sgroup.qq.com'

    # 检查并创建 temp 文件夹
    if not os.path.exists(abs_path + "temp"):
        os.mkdir(abs_path+"temp")

    # 启动主程序（cores/qqbot/core.py）
    qqBot.initBot(cfg)

def check_env(ch_mirror=False):
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 9):
        print("请使用Python3.9+运行本项目")
        input("按任意键退出...")
        exit()
    
    if os.path.exists('requirements.txt'):
        pth = 'requirements.txt'
    else:
        pth = 'QQChannelChatGPT'+ os.sep +'requirements.txt'
    print("正在检查或下载第三方库，请耐心等待...")
    try:
        if ch_mirror:
            print("使用阿里云镜像")
            pipmain(['install', '-r', pth, '-i', 'https://mirrors.aliyun.com/pypi/simple/'])
        else:
            pipmain(['install', '-r', pth])
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

if __name__ == "__main__":
    args = sys.argv

    if '-cn' in args:
        check_env(True)
    else:
        check_env()
    
    t = threading.Thread(target=main, daemon=False)
    t.start()
    t.join()
