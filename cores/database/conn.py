import sqlite3
import yaml

# TODO: 数据库缓存prompt

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
            )
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

    def close(self):
        self.conn.close()
    