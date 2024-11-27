CREATE TABLE IF NOT EXISTS platform(
    name VARCHAR(32),
    count INTEGER,
    timestamp INTEGER
);
CREATE TABLE IF NOT EXISTS llm(
    name VARCHAR(32),
    count INTEGER,
    timestamp INTEGER
);
CREATE TABLE IF NOT EXISTS plugin(
    name VARCHAR(32),
    count INTEGER,
    timestamp INTEGER
);
CREATE TABLE IF NOT EXISTS command(
    name VARCHAR(32),
    count INTEGER,
    timestamp INTEGER
);
CREATE TABLE IF NOT EXISTS llm_history(
    session_id VARCHAR(32),
    content TEXT
);