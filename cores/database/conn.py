import sqlite3
import yaml
import time
from typing import Tuple

class dbConn():
    def __init__(self):
        # 读取参数,并支持中文
        conn = sqlite3.connect("data.db")
        conn.text_factory=str
        self.conn = conn
        c = conn.cursor()
        c.execute(
            '''
            CREATE TABLE IF NOT EXISTS tb_session(
                qq_id   VARCHAR(32) PRIMARY KEY,
                history TEXT
            );
            '''
        )
        c.execute(
            '''
            CREATE TABLE IF NOT EXISTS tb_stat_session(
                platform VARCHAR(32),
                session_id VARCHAR(32),
                cnt INTEGER
            );
            '''
        )
        c.execute(
            '''
            CREATE TABLE IF NOT EXISTS tb_stat_message(
                ts INTEGER,
                cnt INTEGER
            );
            '''
        )
        c.execute(
            '''
            CREATE TABLE IF NOT EXISTS tb_stat_platform(
                ts INTEGER,
                platform VARCHAR(32),
                cnt INTEGER
            );
            '''
        )
        
        conn.commit()

    def insert_session(self, qq_id, history):
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO tb_session(qq_id, history) VALUES (?, ?)
            ''', (qq_id, history)
        )
        conn.commit()

    def update_session(self, qq_id, history):
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            UPDATE tb_session SET history = ? WHERE qq_id = ?
            ''', (history, qq_id)
        )
        conn.commit()

    def get_session(self, qq_id):
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT * FROM tb_session WHERE qq_id = ?
            ''', (qq_id, )
        )
        return c.fetchone()
    
    def get_all_session(self):
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT * FROM tb_session
            '''
        )
        return c.fetchall()
    
    def check_session(self, qq_id):
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT * FROM tb_session WHERE qq_id = ?
            ''', (qq_id, )
        )
        return c.fetchone() is not None

    def delete_session(self, qq_id):
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            DELETE FROM tb_session WHERE qq_id = ?
            ''', (qq_id, )
        )
        conn.commit()


    def increment_stat_session(self, platform, session_id, cnt):
        # if not exist, insert
        conn = self.conn
        c = conn.cursor()

        if self.check_stat_session(platform, session_id):
            c.execute(
                '''
                UPDATE tb_stat_session SET cnt = cnt + ? WHERE platform = ? AND session_id = ?
                ''', (cnt, platform, session_id)
            )
            conn.commit()
        else:
            c.execute(
                '''
                INSERT INTO tb_stat_session(platform, session_id, cnt) VALUES (?, ?, ?)
                ''', (platform, session_id, cnt)
            )
            conn.commit()

    def check_stat_session(self, platform, session_id):
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT * FROM tb_stat_session WHERE platform = ? AND session_id = ?
            ''', (platform, session_id)
        )
        return c.fetchone() is not None
    
    def get_all_stat_session(self):
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT * FROM tb_stat_session
            '''
        )
        return c.fetchall()
    
    def get_session_cnt_total(self):
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT COUNT(*) FROM tb_stat_session
            '''
        )
        return c.fetchone()[0]
    
    def increment_stat_message(self, ts, cnt):
        # 以一个小时为单位。ts的单位是秒。
        # 找到最近的一个小时，如果没有，就插入

        conn = self.conn
        c = conn.cursor()

        ok, new_ts = self.check_stat_message(ts)

        if ok:
            c.execute(
                '''
                UPDATE tb_stat_message SET cnt = cnt + ? WHERE ts = ?
                ''', (cnt, new_ts)
            )
            conn.commit()
        else:
            c.execute(
                '''
                INSERT INTO tb_stat_message(ts, cnt) VALUES (?, ?)
                ''', (new_ts, cnt)
            )
            conn.commit()

    def check_stat_message(self, ts) -> Tuple[bool, int]:
        # 换算成当地整点的时间戳

        ts = ts - ts % 3600
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT * FROM tb_stat_message WHERE ts = ?
            ''', (ts, )
        )
        if c.fetchone() is not None:
            return True, ts
        else:
            return False, ts
        
    def get_last_24h_stat_message(self):
        # 获取最近24小时的消息统计
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT * FROM tb_stat_message WHERE ts > ?
            ''', (time.time() - 86400, )
        )
        return c.fetchall()
    
    def get_message_cnt_total(self) -> int:
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT SUM(cnt) FROM tb_stat_message
            '''
        )
        return c.fetchone()[0]

    def increment_stat_platform(self, ts, platform, cnt):
        # 以一个小时为单位。ts的单位是秒。
        # 找到最近的一个小时，如果没有，就插入

        conn = self.conn
        c = conn.cursor()

        ok, new_ts = self.check_stat_platform(ts, platform)

        if ok:
            c.execute(
                '''
                UPDATE tb_stat_platform SET cnt = cnt + ? WHERE ts = ? AND platform = ?
                ''', (cnt, new_ts, platform)
            )
            conn.commit()
        else:
            c.execute(
                '''
                INSERT INTO tb_stat_platform(ts, platform, cnt) VALUES (?, ?, ?)
                ''', (new_ts, platform, cnt)
            )
            conn.commit()

    def check_stat_platform(self, ts, platform):
        # 换算成当地整点的时间戳

        ts = ts - ts % 3600
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT * FROM tb_stat_platform WHERE ts = ? AND platform = ?
            ''', (ts, platform)
        )
        if c.fetchone() is not None:
            return True, ts
        else:
            return False, ts
        
    def get_last_24h_stat_platform(self):
        # 获取最近24小时的消息统计
        conn = self.conn
        c = conn.cursor()
        c.execute(
            '''
            SELECT * FROM tb_stat_platform WHERE ts > ?
            ''', (time.time() - 86400, )
        )
        return c.fetchall()
    

    def close(self):
        self.conn.close()
    