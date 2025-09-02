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
    provider_type VARCHAR(32),
    session_id VARCHAR(32),
    content TEXT
);

-- ATRI
CREATE TABLE IF NOT EXISTS atri_vision(
    id TEXT,
    url_or_path TEXT,
    caption TEXT,
    is_meme BOOLEAN,
    keywords TEXT,
    platform_name VARCHAR(32),
    session_id VARCHAR(32),
    sender_nickname VARCHAR(32),
    timestamp INTEGER
);

CREATE TABLE IF NOT EXISTS webchat_conversation(
    user_id TEXT, -- 会话 id
    cid TEXT, -- 对话 id
    history TEXT,
    created_at INTEGER,
    updated_at INTEGER,
    title TEXT,
    persona_id TEXT
);

PRAGMA encoding = 'UTF-8';