import os, sqlite3, requests, re
from flask import Flask, request, render_template, jsonify
from datetime import datetime
from textblob import TextBlob

app = Flask(__name__)
DB_PATH = 'data.db'
ADMIN_PWD = os.environ.get("ADMIN_PASSWORD", "admin888")

# 初始化数据库：包含情感值(sentiment)和热度(likes/views)字段
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS posts 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, msg_id INTEGER, text TEXT, 
             tags TEXT, username TEXT, title TEXT, date TEXT, 
             likes INTEGER DEFAULT 0, views INTEGER DEFAULT 0, sentiment REAL)''')
init_db()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    # 兼容频道消息和普通群组消息
    p = data.get('channel_post') or data.get('message')
    if p:
        msg_id = p.get('message_id')
        text = p.get('text') or p.get('caption') or ""
        chat = p.get('chat', {})
        username = chat.get('username', 'Private')
        title = chat.get('title', 'Channel')
        
        # 提取 #标签
        tags = ",".join(re.findall(r'#(\w+)', text))
        
        # AI 情感分析：计算内容极性 (-1.0 到 1.0)
        # 0.5以上为积极(橙色光), -0.5以下为消极(红色光), 其余为中性(蓝色光)
        try:
            sentiment = TextBlob(text).sentiment.polarity
        except:
            sentiment = 0.0
        
        with sqlite3.connect(DB_PATH) as conn:
            # 查重逻辑
            exist = conn.execute("SELECT id FROM posts WHERE msg_id=? AND username=?", (msg_id, username)).fetchone()
            if not exist:
                conn.execute("INSERT INTO posts (msg_id, text, tags, username, title, date, sentiment) VALUES (?,?,?,?,?,?,?)",
                             (msg_id, text, tags, username, title, datetime.now().strftime("%Y-%m-%d %H:%M"), sentiment))
    return 'OK'

@app.route('/')
def index():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        # 默认显示最新的 100 条
        posts = conn.execute("SELECT * FROM posts ORDER BY id DESC LIMIT 100").fetchall()
        tags_raw = conn.execute("SELECT tags FROM posts WHERE tags != ''").fetchall()
        tag_set = set()
        for r in tags_raw:
            for t in r['tags'].split(','): tag_set.add(t)
    return render_template('index.html', posts=posts, all_tags=sorted(list(tag_set)))

@app.route('/api/like/<int:msg_id>', methods=['POST'])
def like(msg_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE posts SET likes = likes + 1 WHERE msg_id=?", (msg_id,))
    return "OK"

if __name__ == '__main__':
    # 端口适配云平台
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
