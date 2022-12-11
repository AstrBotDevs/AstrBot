import cores.qqbot.core as qqBot
from cores.openai.core import ChatGPT
import asyncio
import yaml
# from cores.database.conn import dbConn
def main():
    # 读取参数
    # with open('configs/config.yaml', 'r', encoding='utf-8') as f:
    #     cfg = yaml.safe_load(f)
    # chatGPT_configs = cfg['openai']['chatGPTConfigs']
    # print(chatGPT_configs)
    #实例化ChatGPT
    chatgpt = ChatGPT()
    # db = dbConn()
    # #执行qqBot
    # qqBot.initBot(chatgpt, db)
    qqBot.initBot(chatgpt)
if __name__ == "__main__":
    main()