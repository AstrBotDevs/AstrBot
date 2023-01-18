import threading
import time
import asyncio
import os, sys

# 是否是windows打包。一般人不需要改这个，这个只是我为了方便加上的。
win_compile_mode = False
abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'

def main(loop, event):
    import cores.qqbot.core as qqBot
    from cores.openai.core import ChatGPT
    #实例化ChatGPT
    chatgpt = ChatGPT()
    # #执行qqBot
    qqBot.initBot(chatgpt)

# def hot_update(loop, event):
#     global main_thread
#     print("新更新")
#     # 结束线程
#     bot_event.set()
#     while main_thread.is_alive():
#         print('bot线程濒死')
#         time.sleep(1)
#     print("bot线程已结束")
#     time.sleep(3)
#     bot_event.clear()
#     print("bot线程重启")
#     main_thread = threading.Thread(target=main, daemon=True, args=(loop,bot_event))
#     main_thread.start()
#     time.sleep(5)

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
        print("安装依赖库中...")
        os.system("pip install openai")
        os.system("pip install qq-botpy")
        os.system("pip install pyyaml")
        print("安装依赖库完毕...")
    
    # 检查key
    with open(abs_path+"configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
        import yaml
        cfg = yaml.safe_load(ymlfile)
        if cfg['openai']['key'] == '' or cfg['openai']['key'] == None:
            print("请先在configs/config.yaml下添加一个可用的OpenAI Key。详情请前往https://beta.openai.com/account/api-keys")
        if cfg['qqbot']['appid'] == '' or cfg['qqbot']['token'] == '' or cfg['qqbot']['appid'] == None or cfg['qqbot']['token'] == None: 
            print("请先在configs/config.yaml下完善appid和token令牌(在https://q.qq.com/上注册一个QQ机器人即可获得)")
    

if __name__ == "__main__":
    check_env()
    bot_event = threading.Event()
    loop = asyncio.get_event_loop()
    main(loop, bot_event)