import threading
import time
import asyncio
import os, sys
import signal
import requests,json


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
    print('[System] 当前语言模型提供商: ' + provider)
    # 执行Bot
    qqBot.initBot(cfg, provider)

# 语言模型提供商选择器
# 目前有：OpenAI官方API、逆向库
def privider_chooser(cfg):
    if 'rev_ChatGPT' in cfg and cfg['rev_ChatGPT']['enable']:
        return 'rev_chatgpt'
    elif 'rev_ernie' in cfg and cfg['rev_ernie']['enable']:
        return 'rev_ernie'
    else:
        return 'openai_official'

# 仅支持linux
def hot_update():
    target = 'target.tar'
    time.sleep(5)
    while(True):
        if os.path.exists('version.txt'):
            version_file = open('version.txt', 'r', encoding='utf-8')
            vs = version_file.read()
            version = float(vs)
        else:
            version = 0
        if not os.path.exists(target):
            version = 0
        try:
            res = requests.get("https://soulter.top/channelbot/update.json")
            res_obj = json.loads(res.text)
            ol_version = float(res_obj['version'])
            if ol_version > version:
                print('发现新版本: ' + str(ol_version))
                res = requests.get(res_obj['linux-url'], stream=True)
                filesize = res.headers["Content-Length"]
                print('文件大小: ' + str(int(filesize) / 1024 / 1024) + 'MB')
                print('正在更新文件...')
                chunk_size = 1024
                times = int(filesize) // chunk_size
                show = 1 / times
                show2 = 1 / times
                start = 1
                with open(target, "wb") as pyFile:
                    for chunk in res.iter_content(chunk_size=chunk_size):
                        if chunk:
                            pyFile.write(chunk)
                        if start <= times:
                            print(f"\r下载进度: {show:.2%}",end="",flush=True)
                            start += 1
                            show += show2
                        else:
                            sys.stdout.write(f"下载进度: 100%\n")
                print('更新完成')
                print('解压覆盖')
                os.system(f"tar -zxvf {target}")
                version = ol_version
                version_file = open('version.txt', 'w+', encoding='utf-8')
                version_file.write(str(res_obj['version']))
                version_file.flush()
                version_file.close()

                try:
                    update_version(version)
                except BaseException as e:
                    print(e)
                
                print('自启动')
                py = sys.executable
                os.execl(py, py, *sys.argv)
            time.sleep(60*60*3)
        except BaseException as e:
            print(e)
            print("upd出现异常, 请联系QQ905617992")
            time.sleep(60*60*3)

def update_version(ver):
    if not os.path.exists('update_record'):
        object_id = ''
    else:
        object_id = open("update_record", 'r', encoding='utf-8').read()
    addr = 'unknown'
    try:
        addr = requests.get('http://myip.ipip.net', timeout=5).text
    except BaseException:
        pass
    try:
        ts = str(time.time())
        # md = hashlib.md5((ts+'REDACTED_LEANCLOUD_APP_KEY').encode())
        headers = {
            'X-LC-Id': 'REDACTED_LEANCLOUD_APP_ID',
            'X-LC-Key': 'REDACTED_LEANCLOUD_APP_KEY',
            'Content-Type': 'application/json'
        }
        d = {"data": {'version':'win-hot-update'+str(ver), 'addr': addr}}
        d = json.dumps(d).encode("utf-8")
        res = requests.put(f'https://uqfxtww1.lc-cn-n1-shared.com/1.1/classes/version_record/{object_id}', headers = headers, data = d)
        if json.loads(res.text)['code'] == 1:
            res = requests.post(f'https://uqfxtww1.lc-cn-n1-shared.com/1.1/classes/version_record', headers = headers, data = d)
            object_id = json.loads(res.text)['objectId']
            object_id_file = open("update_record", 'w+', encoding='utf-8')
            object_id_file.write(str(object_id))
            object_id_file.flush()
            object_id_file.close()
    except BaseException as e:
        print(e)

def check_env():
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 8):
        print("请使用Python3.8运行本项目")
        input("按任意键退出...")
        exit()
    try:
        import openai
        import botpy
        import yaml
    except Exception as e:
        # print(e)
        try:
            print("安装依赖库中...")
            os.system("pip3 install openai")
            os.system("pip3 install qq-botpy")
            os.system("pip3 install pyyaml")
            print("安装依赖库完毕...")
        except BaseException:
            print("\n安装第三方库异常.请自行安装或者联系QQ905617992.")
        
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
    global pid
    pid = os.getpid()
    global ma_type
    print("程序PID:"+str(pid))
    check_env()
    bot_event = threading.Event()
    loop = asyncio.get_event_loop()
    ma_type = get_platform()
    if ma_type == 'linux':
        threading.Thread(target=hot_update).start()
        
    main(loop, bot_event)