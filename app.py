import os, sqlite3, requests, re
from flask import Flask, request, render_template, jsonify
from datetime import datetime
from textblob import TextBlob

app = Flask(__name__)
DB_PATH = 'data.db'

# 环境变量读取
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
ADMIN_PWD = os.environ.get("ADMIN_PASSWORD", "admin888")

# 初始化数据库：增加评论表，并为帖子表增加唯一索引 UNIQUE 防止重复
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        # 帖子表：UNIQUE(msg_id, username) 确保同一消息不被存储两次
        conn.execute('''CREATE TABLE IF NOT EXISTS posts 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, msg_id INTEGER, text TEXT, 
             tags TEXT, username TEXT, title TEXT, date TEXT, 
             likes INTEGER DEFAULT 0, views INTEGER DEFAULT 0, sentiment REAL,
             UNIQUE(msg_id, username))''')
        # 评论表
        conn.execute('''CREATE TABLE IF NOT EXISTS comments 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT)''')
init_db()

# 1. 接收 Telegram 消息 (Webhook)
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    p = data.get('channel_post') or data.get('message')
    if p:
        msg_id = p.get('message_id')
        text = p.get('text') or p.get('caption') or ""
        chat = p.get('chat', {})
        username = chat.get('username', 'Private')
        title = chat.get('title', '情报站')
        # 提取标签
        tags = ",".join(re.findall(r'#(\w+)', text))
        
        # AI 情感分析
        try:
            sentiment = TextBlob(text).sentiment.polarity
        except:
            sentiment = 0.0
        
        with sqlite3.connect(DB_PATH) as conn:
            try:
                # INSERT OR IGNORE 配合 UNIQUE 索引，从源头切断重复显示的可能
                conn.execute("INSERT OR IGNORE INTO posts (msg_id, text, tags, username, title, date, sentiment) VALUES (?,?,?,?,?,?,?)",
                             (msg_id, text, tags, username, title, datetime.now().strftime("%Y-%m-%d %H:%M"), sentiment))
            except Exception as e:
                print(f"Database error: {e}")
    return 'OK'

# 2. 原生评论接口
@app.route('/api/comment', methods=['POST'])
def add_comment():
    data = request.json
    post_id = data.get('post_id')
    content = data.get('content')
    if not content: return "内容为空", 400
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO comments (post_id, content, date) VALUES (?,?,?)",
                     (post_id, content, datetime.now().strftime("%m-%d %H:%M")))
    # 评论私聊通知管理员
    if BOT_TOKEN and MY_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                          json={"chat_id": MY_CHAT_ID, "text": f"💬 新评论通知:\n内容: {content}\n关联消息ID: {post_id}"})
        except: pass
    return jsonify({"status": "success"})

# 3. 投稿接口
@app.route('/api/submit', methods=['POST'])
def submit_post():
    content = request.json.get('content')
    if not content or not BOT_TOKEN: return "配置缺失", 400
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    res = requests.post(url, json={"chat_id": MY_CHAT_ID, "text": f"📩 【收到新投稿】\n\n{content}"})
    return jsonify({"status": "success" if res.ok else "error"})

# 4. 同步删除接口
@app.route('/api/delete/<int:msg_id>', methods=['POST'])
def delete_post(msg_id):
    data = request.json
    if data.get('password') != ADMIN_PWD: return "拒绝访问", 403
    username = data.get('username')
    # 物理删除 Telegram 频道原消息
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage", 
                  json={"chat_id": f"@{username}", "message_id": msg_id})
    # 删除本地数据库
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM posts WHERE msg_id=?", (msg_id,))
        conn.execute("DELETE FROM comments WHERE post_id=?", (msg_id,))
    return jsonify({"status": "deleted"})

# 5. 点赞接口
@app.route('/api/like/<int:msg_id>', methods=['POST'])
def like(msg_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE posts SET likes = likes + 1 WHERE msg_id=?", (msg_id,))
    return "OK"

# 主页渲染
@app.route('/')
def index():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        posts = conn.execute("SELECT * FROM posts ORDER BY id DESC LIMIT 100").fetchall()
        comments = conn.execute("SELECT * FROM comments ORDER BY id ASC").fetchall()
        tags_raw = conn.execute("SELECT tags FROM posts WHERE tags != ''").fetchall()
        tag_set = set()
        for r in tags_raw:
            for t in r['tags'].split(','): tag_set.add(t)
    return render_template('index.html', posts=posts, all_tags=sorted(list(tag_set)), comments=comments)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)