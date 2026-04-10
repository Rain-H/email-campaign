# CRM PostgreSQL 数据库设置指南

本目录包含 CRM 系统的 PostgreSQL 数据库 schema 和迁移工具。

## 快速开始

### 1. 安装 PostgreSQL

**macOS (使用 Homebrew):**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**或使用 Postgres.app:**
- 下载：https://postgresapp.com/
- 安装后启动应用

**检查安装：**
```bash
psql --version
```

### 2. 创建数据库

打开终端，连接到 PostgreSQL：
```bash
# 使用 psql 命令行工具
psql postgres

# 在 psql 中执行：
CREATE DATABASE crm;
\q
```

或者在 **DBeaver** 中创建：
1. 打开 DBeaver
2. 连接到 PostgreSQL 服务器（通常是 localhost:5432）
3. 右键点击 "Databases" → "Create New Database"
4. 数据库名称输入 `crm`
5. 点击确定

### 3. 配置连接信息

在**项目根目录**（`email campaign/`）的 `.env` 文件中添加：

```bash
# PostgreSQL 配置
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=crm
PG_USER=postgres
PG_PASSWORD=your_password
```

**注意：** `.env` 文件应该在项目根目录，不是 `database/` 目录里。

### 4. 安装 Python 依赖

```bash
pip install psycopg2-binary python-dotenv
```

### 5. 初始化数据库

```bash
cd database
python init_db.py
```

你会看到：
```
============================================================
初始化 CRM 数据库
============================================================

数据库: PostgreSQL
  主机: localhost
  端口: 5432
  数据库: crm
  用户: postgres
  密码: ********

Schema 文件: .../schema.sql

正在连接数据库...
正在创建表、视图和触发器...

✅ 数据库初始化完成

创建的表:
  - contacts (联系人)
  - emails (邮件)
  - replies (回复)

创建的视图:
  - contact_status (当前状态)
  - status_summary (统计摘要)
```

### 6. 迁移现有数据

```bash
python migrate_from_json.py
```

输出：
```
============================================================
数据迁移工具
============================================================

数据库: PostgreSQL
  主机: localhost
  端口: 5432
  数据库: crm

源文件: .../crm.json
找到 4 条联系人记录

正在连接数据库...
✓ 连接成功

开始迁移数据...
  进度: 4/4

✅ 迁移完成!
   联系人: 4
   邮件: 4
   回复: 2

📊 当前状态统计:
   opened_no_reply: 1
   replied_interested: 1
   replied_not_interested: 1
   no_reply: 1
```

### 7. 在 DBeaver 中查看数据

1. 在 DBeaver 中，展开你的 PostgreSQL 连接
2. 展开 `crm` 数据库
3. 查看表：
   - `contacts` - 联系人
   - `emails` - 邮件
   - `replies` - 回复
4. 查看视图：
   - `contact_status` - 当前状态
   - `status_summary` - 统计摘要

**查看数据：**
右键点击表或视图 → "View Data"

---

## 数据库结构

### 表

#### 1. **contacts** - 联系人信息
| 字段 | 类型 | 说明 |
|------|------|------|
| email | TEXT (主键) | 邮箱地址 |
| name | TEXT | 姓名 |
| conference | TEXT | 会议名称 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### 2. **emails** - 发送的邮件
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL (主键) | 邮件ID |
| contact_email | TEXT (外键) | 联系人邮箱 |
| postmark_message_id | TEXT | Postmark消息ID |
| subject | TEXT | 邮件主题 |
| body_text | TEXT | 纯文本内容 |
| body_html | TEXT | HTML内容 |
| sent_at | TIMESTAMP | 发送时间 |
| delivered_at | TIMESTAMP | 送达时间 |
| bounced_at | TIMESTAMP | 退信时间 |
| bounce_type | TEXT | 退信类型 |
| opened_at | TIMESTAMP | 首次打开时间 |

#### 3. **replies** - 客户回复
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL (主键) | 回复ID |
| email_id | INTEGER (外键) | 邮件ID |
| replied_at | TIMESTAMP | 回复时间 |
| full_content | TEXT | 完整回复内容 |
| is_interested | BOOLEAN | 是否有兴趣 (true/false) |
| classification_confidence | REAL | AI分类置信度 |
| classification_reasoning | TEXT | 分类理由 |

### 视图

#### 1. **contact_status** - 每个联系人的当前状态

这个视图合并了 contacts, emails, replies 表的信息，显示每个联系人的最新状态。

**status 字段有 5 种值：**
1. `failed` - 邮件发送失败 (bounced/spam)
2. `no_reply` - 发送成功，未打开，未回复
3. `opened_no_reply` - 打开过但未回复
4. `replied_interested` - 回复了，有兴趣 ⭐
5. `replied_not_interested` - 回复了，没兴趣

#### 2. **status_summary** - 状态统计

每种状态的联系人数量。

---

## 常用 SQL 查询

### 查看所有联系人状态
```sql
SELECT * FROM contact_status
ORDER BY last_updated DESC;
```

### 查看状态统计
```sql
SELECT * FROM status_summary;
```

### 查看所有有兴趣的客户 ⭐
```sql
SELECT email, chair_name, conference, replied_at, reply_snippet
FROM contact_status
WHERE status = 'replied_interested'
ORDER BY replied_at DESC;
```

### 查看所有没兴趣的客户
```sql
SELECT email, chair_name, conference, replied_at, reply_snippet
FROM contact_status
WHERE status = 'replied_not_interested';
```

### 查看打开但未回复的客户（需要跟进）
```sql
SELECT email, chair_name, conference, opened_at
FROM contact_status
WHERE status = 'opened_no_reply'
ORDER BY opened_at DESC;
```

### 查看完全没反应的客户
```sql
SELECT email, chair_name, conference, sent_at
FROM contact_status
WHERE status = 'no_reply'
ORDER BY sent_at DESC;
```

### 查看发送失败的邮件
```sql
SELECT email, chair_name, bounce_type, bounced_at
FROM contact_status
WHERE status = 'failed'
ORDER BY bounced_at DESC;
```

### 查看某个联系人的完整邮件历史
```sql
SELECT * FROM emails
WHERE contact_email = '903900103@qq.com'
ORDER BY sent_at DESC;
```

### 计算回复率
```sql
SELECT
    COUNT(*) AS total_sent,
    SUM(CASE WHEN status LIKE 'replied%' THEN 1 ELSE 0 END) AS total_replied,
    ROUND(
        100.0 * SUM(CASE WHEN status LIKE 'replied%' THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) AS reply_rate_percent
FROM contact_status;
```

### 计算有兴趣率（在回复的人中）
```sql
SELECT
    SUM(CASE WHEN status LIKE 'replied%' THEN 1 ELSE 0 END) AS total_replied,
    SUM(CASE WHEN status = 'replied_interested' THEN 1 ELSE 0 END) AS interested,
    ROUND(
        100.0 * SUM(CASE WHEN status = 'replied_interested' THEN 1 ELSE 0 END) /
        NULLIF(SUM(CASE WHEN status LIKE 'replied%' THEN 1 ELSE 0 END), 0),
        2
    ) AS interested_rate_percent
FROM contact_status;
```

---

## 故障排除

### PostgreSQL 连接失败

**错误：** `psycopg2.OperationalError: could not connect to server`

**解决：**
1. 确认 PostgreSQL 服务已启动：
   ```bash
   brew services list  # macOS
   ```

2. 启动服务：
   ```bash
   brew services start postgresql@15
   ```

3. 检查端口是否正确（默认 5432）

4. 确认 `.env` 中的用户名和密码正确

### 权限错误

**错误：** `permission denied for database`

**解决：**
```sql
psql crm
GRANT ALL PRIVILEGES ON DATABASE crm TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_user;
```

### 模块未找到

**错误：** `ModuleNotFoundError: No module named 'psycopg2'`

**解决：**
```bash
pip install psycopg2-binary
```

### .env 文件位置错误

**错误：** 连接配置未生效

**解决：** 确保 `.env` 文件在**项目根目录**，而不是 `database/` 目录中。

```
email campaign/
├── .env           ← 在这里！
├── database/
│   ├── init_db.py
│   └── ...
└── ...
```

---

## 文件说明

- `schema.sql` - PostgreSQL 数据库 schema（表、视图、触发器）
- `db_config.py` - 数据库连接配置
- `init_db.py` - 初始化数据库脚本
- `migrate_from_json.py` - 从 crm.json 迁移数据
- `.env.example` - 配置文件示例
- `README.md` - 本文档

---

## 下一步

数据库设置完成后，你可以：

1. ✅ 在 DBeaver 中可视化浏览和查询数据
2. ✅ 运行 SQL 查询分析客户状态
3. ✅ 导出数据为 CSV/Excel
4. 🔜 修改现有 Python 脚本（`send_postmark.py`, `crm_check.py` 等）从数据库读写数据
