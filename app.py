import os, sqlite3, requests, re
from flask import Flask, request, render_template, jsonify
from datetime import datetime
from textblob import TextBlob

app = Flask(__name__)
DB_PATH = 'data.db'

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
ADMIN_PWD = os.environ.get("ADMIN_PASSWORD", "admin888")

# 垃圾词过滤列表
SPAM_WORDS = ['贷款', '加群', '色情', '菠菜', '广告']

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        # 帖子表：增加 is_pinned (置顶) 字段
        conn.execute('''CREATE TABLE IF NOT EXISTS posts 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, msg_id INTEGER, text TEXT, 
             tags TEXT, username TEXT, title TEXT, date TEXT, 
             likes INTEGER DEFAULT 0, blocks INTEGER DEFAULT 0, 
             is_pinned INTEGER DEFAULT 0, sentiment REAL, UNIQUE(msg_id, username))''')
        # 评论表：增加 parent_id (盖楼回复) 字段
        conn.execute('''CREATE TABLE IF NOT EXISTS comments 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, parent_id INTEGER DEFAULT 0,
             content TEXT, date TEXT)''')
init_db()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    p = data.get('channel_post') or data.get('message')
    if p:
        msg_id = p.get('message_id'); chat = p.get('chat', {})
        text = p.get('text') or p.get('caption') or ""
        username = chat.get('username', 'Private'); title = chat.get('title', '情报站')
        tags = ",".join(re.findall(r'#(\w+)', text))
        try: sentiment = TextBlob(text).sentiment.polarity
        except: sentiment = 0.0
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT OR IGNORE INTO posts (msg_id, text, tags, username, title, date, sentiment) VALUES (?,?,?,?,?,?,?)",
                         (msg_id, text, tags, username, title, datetime.now().strftime("%Y-%m-%d %H:%M"), sentiment))
    return 'OK'

@app.route('/api/comment', methods=['POST'])
def add_comment():
    data = request.json
    content = data.get('content', '')
    # 垃圾过滤
    if any(word in content for word in SPAM_WORDS): return "含有违禁词", 400
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO comments (post_id, parent_id, content, date) VALUES (?,?,?,?)",
                     (data.get('post_id'), data.get('parent_id', 0), content, datetime.now().strftime("%m-%d %H:%M")))
    return jsonify({"status": "success"})

@app.route('/api/pin/<int:id>', methods=['POST'])
def toggle_pin(id):
    if request.json.get('password') != ADMIN_PWD: return "403", 403
    with sqlite3.connect(DB_PATH) as conn:
        # 切换置顶状态 (1 为置顶，0 为取消)
        conn.execute("UPDATE posts SET is_pinned = 1 - is_pinned WHERE id=?", (id,))
    return "OK"

@app.route('/api/like/<int:id>', methods=['POST'])
def like(id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE posts SET likes = likes + 1 WHERE id=?", (id,))
    return "OK"

@app.route('/api/delete/<int:msg_id>', methods=['POST'])
def delete_post(msg_id):
    if request.json.get('password') != ADMIN_PWD: return "403", 403
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM posts WHERE msg_id=?", (msg_id,))
    return "OK"

@app.route('/')
def index():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        # 先按置顶排序，再按 ID 降序
        posts = conn.execute("SELECT * FROM posts GROUP BY msg_id, username ORDER BY is_pinned DESC, id DESC").fetchall()
        comments = conn.execute("SELECT * FROM comments ORDER BY id ASC").fetchall()
    return render_template('index.html', posts=posts, comments=comments)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))