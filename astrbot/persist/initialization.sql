CREATE TABLE IF NOT EXISTS tb_session(
    qq_id   VARCHAR(32) PRIMARY KEY,
    history TEXT
);
CREATE TABLE IF NOT EXISTS tb_stat_session(
    platform VARCHAR(32),
    session_id VARCHAR(32),
    cnt INTEGER
);
CREATE TABLE IF NOT EXISTS tb_stat_message(
    ts INTEGER,
    cnt INTEGER
);
CREATE TABLE IF NOT EXISTS tb_stat_platform(
    ts INTEGER,
    platform VARCHAR(32),
    cnt INTEGER
);