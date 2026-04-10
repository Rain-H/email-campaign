-- CRM Database Schema - PostgreSQL 版本
-- 状态分类：
--   1. failed - 邮件发送失败 (bounced/spam)
--   2. no_reply - 发送成功，未打开，未回复
--   3. opened_no_reply - 打开过，但未回复
--   4. clicked_no_reply - 点击过链接，但未回复
--   5. replied_interested - 回复了，有兴趣
--   6. replied_not_interested - 回复了，没兴趣

-- ============================================
-- 1. 联系人表
-- ============================================
CREATE TABLE IF NOT EXISTS contacts (
    email TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    conference TEXT,
    source_platform TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 2. 邮件表 (每封发送的邮件)
-- ============================================
CREATE TABLE IF NOT EXISTS emails (
    id SERIAL PRIMARY KEY,
    contact_email TEXT NOT NULL,
    postmark_message_id TEXT UNIQUE,
    subject TEXT NOT NULL,
    body_text TEXT,
    body_html TEXT,
    sent_at TIMESTAMP NOT NULL,

    -- 发送状态
    delivered_at TIMESTAMP,
    bounced_at TIMESTAMP,
    bounce_type TEXT,

    -- 打开追踪
    opened_at TIMESTAMP,
    open_count INTEGER DEFAULT 0,

    -- 点击追踪
    clicked_at TIMESTAMP,

    FOREIGN KEY (contact_email) REFERENCES contacts(email) ON DELETE CASCADE
);

-- ============================================
-- 3. 回复表
-- ============================================
CREATE TABLE IF NOT EXISTS replies (
    id SERIAL PRIMARY KEY,
    email_id INTEGER NOT NULL,
    replied_at TIMESTAMP NOT NULL,
    full_content TEXT NOT NULL,

    -- 简化分类：只有两种
    is_interested BOOLEAN NOT NULL,

    -- AI分类的辅助信息
    classification_confidence REAL,
    classification_reasoning TEXT,

    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
);

-- ============================================
-- 4. 对话消息表 (完整邮件线程)
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    contact_email TEXT NOT NULL,
    
    -- 消息方向: 'outbound' (我们发出) 或 'inbound' (收到)
    direction TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
    
    -- 消息内容
    subject TEXT,
    body_text TEXT,
    body_html TEXT,
    
    -- 时间戳
    message_at TIMESTAMP NOT NULL,
    
    -- 关联到原始邮件 (如果是 outbound 且有 postmark_message_id)
    postmark_message_id TEXT,
    
    -- 线程顺序 (1 = 首封邮件, 2 = 第一次回复, ...)
    thread_order INTEGER DEFAULT 1,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (contact_email) REFERENCES contacts(email) ON DELETE CASCADE
);

-- ============================================
-- 索引
-- ============================================
CREATE INDEX IF NOT EXISTS idx_emails_contact ON emails(contact_email);
CREATE INDEX IF NOT EXISTS idx_emails_sent_at ON emails(sent_at);
CREATE INDEX IF NOT EXISTS idx_replies_email ON replies(email_id);
CREATE INDEX IF NOT EXISTS idx_replies_interested ON replies(is_interested);
CREATE INDEX IF NOT EXISTS idx_conversations_contact ON conversations(contact_email);
CREATE INDEX IF NOT EXISTS idx_conversations_direction ON conversations(direction);
CREATE INDEX IF NOT EXISTS idx_conversations_message_at ON conversations(message_at);

-- ============================================
-- 视图：联系人当前状态
-- ============================================
CREATE OR REPLACE VIEW contact_status AS
SELECT
    c.email,
    c.name AS chair_name,
    c.conference,
    e.id AS email_id,
    e.postmark_message_id,
    e.subject,
    e.sent_at,
    e.delivered_at,
    e.opened_at,
    e.open_count,
    e.clicked_at,
    e.bounced_at,
    e.bounce_type,
    r.replied_at,
    r.is_interested,
    SUBSTR(r.full_content, 1, 300) AS reply_snippet,

    CASE
        WHEN e.bounced_at IS NOT NULL THEN 'failed'
        WHEN r.replied_at IS NOT NULL AND r.is_interested = false THEN 'replied_not_interested'
        WHEN r.replied_at IS NOT NULL AND r.is_interested = true THEN 'replied_interested'
        WHEN e.clicked_at IS NOT NULL THEN 'clicked_no_reply'
        WHEN e.opened_at IS NOT NULL THEN 'opened_no_reply'
        ELSE 'no_reply'
    END AS status,

    c.updated_at AS last_updated

FROM contacts c
LEFT JOIN LATERAL (
    SELECT * FROM emails
    WHERE contact_email = c.email
    ORDER BY sent_at DESC
    LIMIT 1
) e ON true
LEFT JOIN replies r ON r.email_id = e.id;

-- ============================================
-- 视图：统计报表
-- ============================================
CREATE OR REPLACE VIEW status_summary AS
SELECT
    status,
    COUNT(*) AS count
FROM contact_status
GROUP BY status;

-- ============================================
-- 触发器函数：自动更新时间戳
-- ============================================
CREATE OR REPLACE FUNCTION update_contact_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 创建触发器
DROP TRIGGER IF EXISTS trigger_update_contact_timestamp ON contacts;
CREATE TRIGGER trigger_update_contact_timestamp
    BEFORE UPDATE ON contacts
    FOR EACH ROW
    EXECUTE FUNCTION update_contact_timestamp();
