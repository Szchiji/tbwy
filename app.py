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

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS posts 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, msg_id INTEGER, text TEXT, 
             tags TEXT, username TEXT, title TEXT, date TEXT, 
             likes INTEGER DEFAULT 0, views INTEGER DEFAULT 0, sentiment REAL)''')
init_db()

# 1. 接收电报消息 (Webhook)
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    p = data.get('channel_post') or data.get('message')
    if p:
        msg_id = p.get('message_id')
        text = p.get('text') or p.get('caption') or ""
        chat = p.get('chat', {})
        username = chat.get('username', 'Private')
        title = chat.get('title', 'Channel')
        tags = ",".join(re.findall(r'#(\w+)', text))
        
        try:
            sentiment = TextBlob(text).sentiment.polarity
        except: sentiment = 0.0
        
        with sqlite3.connect(DB_PATH) as conn:
            exist = conn.execute("SELECT id FROM posts WHERE msg_id=? AND username=?", (msg_id, username)).fetchone()
            if not exist:
                conn.execute("INSERT INTO posts (msg_id, text, tags, username, title, date, sentiment) VALUES (?,?,?,?,?,?,?)",
                             (msg_id, text, tags, username, title, datetime.now().strftime("%Y-%m-%d %H:%M"), sentiment))
    return 'OK'

# 2. 网页端投稿 -> 发送给管理员私聊审核
@app.route('/api/submit', methods=['POST'])
def submit_post():
    content = request.json.get('content')
    if not content or not BOT_TOKEN: return "Config Missing", 400
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    res = requests.post(url, json={"chat_id": MY_CHAT_ID, "text": f"📩 【新投稿】\n\n{content}"})
    return jsonify({"status": "success" if res.ok else "error"})

# 3. 删帖同步 (网页删，频道也删)
@app.route('/api/delete/<int:msg_id>', methods=['POST'])
def delete_post(msg_id):
    data = request.json
    if data.get('password') != ADMIN_PWD: return "Forbidden", 403
    # 同步删除 Telegram 频道消息
    username = data.get('username')
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage", 
                  json={"chat_id": f"@{username}", "message_id": msg_id})
    # 删除本地数据库
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM posts WHERE msg_id=?", (msg_id,))
    return jsonify({"status": "deleted"})

# 4. 生成日报并回发频道
@app.route('/api/daily_report', methods=['GET'])
def daily_report():
    today = datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        posts = conn.execute("SELECT * FROM posts WHERE date LIKE ? LIMIT 5", (f"{today}%",)).fetchall()
    if not posts: return "No posts today"
    
    report = f"📊 今日情报摘要 ({today})\n" + "\n".join([f"• {p['text'][:30]}..." for p in posts])
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                  json={"chat_id": f"@{posts[0]['username']}", "text": report})
    return "Report Sent"

@app.route('/')
def index():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        posts = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()
        tag_set = set()
        for r in conn.execute("SELECT tags FROM posts WHERE tags != ''").fetchall():
            for t in r['tags'].split(','): tag_set.add(t)
    return render_template('index.html', posts=posts, all_tags=sorted(list(tag_set)))

@app.route('/api/like/<int:msg_id>', methods=['POST'])
def like(msg_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE posts SET likes = likes + 1 WHERE msg_id=?", (msg_id,))
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
