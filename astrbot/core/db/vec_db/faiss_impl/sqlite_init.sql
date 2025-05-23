-- 创建文档存储表，包含 faiss 中文档的 id，文档文本，create_at，updated_at
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE documents
ADD COLUMN group_id TEXT GENERATED ALWAYS AS (json_extract(metadata, '$.group_id')) STORED;
ALTER TABLE documents
ADD COLUMN user_id TEXT GENERATED ALWAYS AS (json_extract(metadata, '$.user_id')) STORED;

CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_group_id ON documents(group_id);