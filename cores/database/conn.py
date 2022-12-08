import pymysql
import yaml

# TODO: 数据库缓存prompt

class dbConn():
    def __init__(self):
        with open("./configs/config.yaml", 'r', encoding='utf-8') as ymlfile:
            cfg = yaml.safe_load(ymlfile)
            if cfg['database']['host'] != '' or cfg['database']['port'] or cfg['database']['user'] != '' or cfg['database']['password'] != '' or cfg['database']['db'] != '':
                print("读取数据库配置成功")
                self.db = pymysql.connect(
                    host=cfg['database']['host'],
                    port=cfg['database']['port'],
                    user=cfg['database']['user'],
                    password=cfg['database']['password'],
                    db=cfg['database']['db'],
                    charset='utf8mb4',
                )
            else:
                raise BaseException("请在config中完善你的数据库配置")

    def getCursor(self):
        return self.db.cursor()