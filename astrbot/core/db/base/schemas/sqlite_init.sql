-- This table is used to store the tick metrics of platform message events
CREATE TABLE IF NOT EXISTS platform(
    name VARCHAR(32),
    count INTEGER,
    timestamp INTEGER
);

-- This table is used to store the tick metrics of llm usage events
CREATE TABLE IF NOT EXISTS llm(
    name VARCHAR(32),
    count INTEGER,
    timestamp INTEGER
);

CREATE TABLE IF NOT EXISTS command(
    name VARCHAR(32),
    count INTEGER,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_webchat_conversation ON webchat_conversation(user_id, cid);

CREATE TABLE IF NOT EXISTS shared_preferences(
    key TEXT PRIMARY KEY,
    value TEXT
);

PRAGMA encoding = 'UTF-8';