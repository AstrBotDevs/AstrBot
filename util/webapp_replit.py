from flask import Flask
from threading import Thread
import datetime

app = Flask(__name__)


@app.route('/')
def main_func():
  content = "<h1>QQChannelChatGPT Web APP</h1>"

  content += "<p>" + "Online @ " + str(datetime.datetime.now()) + "</p>"
  content += "<p>欢迎Star本项目！！！</p>"
  return content


def run():
  app.run(host="0.0.0.0", port=8080)
  



def keep_alive():
  server = Thread(target=run)
  server.start()
