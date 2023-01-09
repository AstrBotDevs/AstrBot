import cores.qqbot.core as qqBot
from cores.openai.core import ChatGPT
def main():
    #实例化ChatGPT
    chatgpt = ChatGPT()
    # #执行qqBot
    qqBot.initBot(chatgpt)

if __name__ == "__main__":
    main()