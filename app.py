# fastapi
from typing import Union

from fastapi import FastAPI, Request

import pymysql
import re
import requests
from pydantic import BaseModel
import os
import threading
import time
import json


app = FastAPI()
db = pymysql.connect(
    host='localhost',
    port=3306,
    user='sorbot',
    password='REDACTED_DATABASE_PASSWORD',
    database='sorbot'
)

cnt_10m = 0
cnt_ips_10m = 0
url = 'http://localhost:9091/metrics/job/sorbot'
ip_ls = []

class Tick(BaseModel):
    version: str
    count: int
    ip: str
    others: str

def get_from_db(ip: str):
    db.ping()
    cursor = db.cursor()
    sql = f"SELECT * FROM bases WHERE ip = '{ip}'"
    print(sql)
    cursor.execute(sql)
    result = cursor.fetchone()
    cursor.close()
    return result

# 当前 IP：117.133.151.135  来自于：中国 北京 北京  移动
# def filter_ip(ori: str):
#     # 正则表达式得到ip
#     ip = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b', ori)[0]
#     return ip

def thread_total_cnt():
    global cnt_10m, cnt_ips_10m
    while True:
        try:
            metric_data = 'qqc_total ' + str(cnt_10m)
            cmd = "echo " + metric_data + " | curl --data-binary @- " + url
            print(cmd)
            res = os.system('echo \'' + metric_data + '\' | curl --data-binary @- ' + url)
            cnt_10m = 0
        except Exception as e:
            print(e)

        try:
            metric_data = 'qqc_ips_total ' + str(cnt_ips_10m)
            cmd = "echo " + metric_data + " | curl --data-binary @- " + url
            print(cmd)
            res = os.system('echo \'' + metric_data + '\' | curl --data-binary @- ' + url)
            cnt_ips_10m = 0
            ip_ls.clear()
        except Exception as e:
            print(e)
        print('thread_total_cnt sleep 5 min')
        time.sleep(610)


# 启动线程
t = threading.Thread(target=thread_total_cnt, daemon=True)
t.start()



def push_to_gateway(tick: Tick):
    # push to gateway
    ip = tick.ip
    others = json.loads(tick.others)
    admin = others['admin']
    if admin is None:
        admin = "unknown"
    if tick.version is None:
        tick.version = "unknown"
    metric_data = 'qqc_ips{version="' + tick.version + '",ip="' + ip + '",admin="' + admin + '"} ' + str(tick.count)
    print(metric_data)
    # r = requests.post(url, data=metric_data.encode('utf-8'), )
    # print(r.text)
    cmd = "echo " + metric_data + " | curl --data-binary @- " + url
    print(cmd)
    res = os.system('echo \'' + metric_data + '\' | curl --data-binary @- ' + url)



@app.post("/upload")
def upload(tick: Tick, request: Request):
    global cnt_ips_10m, cnt_10m
    # ip = filter_ip(tick.ip)
    ip = request.client.host
    print("IP", ip, "|", "TICK", tick.__dict__)
    tick.ip = ip
    result = get_from_db(ip)
    try:
        if result is None:
            # 插入数据库
            db.ping()
            cursor = db.cursor()
            sql = f"INSERT INTO bases (ip, count, version, others) VALUES ('{ip}', {tick.count}, '{tick.version}', '{tick.others}')"
            cursor.execute(sql)
            db.commit()
            cursor.close()
        else:
            # 更新数据库
            db.ping()
            cursor = db.cursor()
            cnt = result[1] + tick.count
            sql = f"UPDATE bases SET count = {cnt}, version = '{tick.version}', others = '{tick.others}' WHERE ip = '{ip}'"
            cursor.execute(sql)
            db.commit()
            cursor.close()
            # print(result)
    except Exception as e:
        print(e)
        raise e
    try:
        # insert 到 clicks 表。结构是：total_cnt, ip, timestamp, version
        db.ping()
        cursor = db.cursor()
        sql = f"INSERT INTO clicks (total_cnt, ip, timestamp, version) VALUES ({tick.count}, '{ip}', {int(time.time())}, '{tick.version}')"
        cursor.execute(sql)
        db.commit()
        cursor.close()
    except Exception as e:
        print(e)
        raise e
    cnt_10m += tick.count
    if ip not in ip_ls:
        cnt_ips_10m += 1
        ip_ls.append(ip)

    # push to gateway
    push_to_gateway(tick)

    return {
        "code": 200,
        "status": "ok",
    }


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}