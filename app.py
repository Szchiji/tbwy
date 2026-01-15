import os, sqlite3, requests, re, time, telebot, threading
from flask import Flask, request, render_template, jsonify
from datetime import datetime

app = Flask(__name__)

# --- 配置 ---
DB_DIR = '/app/data'
DB_PATH = os.path.join(DB_DIR, 'data.db')
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")

bot = telebot.TeleBot(BOT_TOKEN)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DB_DIR): os.makedirs(DB_DIR, exist_ok=True)
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            msg_id INTEGER, text TEXT, username TEXT, title TEXT, 
            date TEXT, likes INTEGER DEFAULT 0, 
            media_group_id TEXT, first_media TEXT, UNIQUE(msg_id, username))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, 
            content TEXT, date TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT UNIQUE)''')
init_db()

# 获取媒体缩略图链接
def get_file_link(file_id):
    try:
        file_info = bot.get_file(file_id)
        return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
    except: return None

@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    p = update.channel_post or update.message or update.edited_channel_post
    
    if p:
        text = p.text or p.caption or ""
        # 1. 多图去重逻辑
        mg_id = p.media_group_id
        if mg_id:
            with get_db() as conn:
                if conn.execute("SELECT id FROM posts WHERE media_group_id=?", (mg_id,)).fetchone():
                    return 'OK'

        # 2. 抓取首张媒体作为缩略图
        thumb = None
        if p.photo: 
            thumb = get_file_link(p.photo[-1].file_id)
        elif p.video: 
            thumb = get_file_link(p.video.thumb.file_id) if p.video.thumb else None

        # 3. 保存
        with get_db() as conn:
            conn.execute('''INSERT INTO posts (msg_id, text, username, title, date, media_group_id, first_media) 
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(msg_id, username) DO UPDATE SET 
                text=excluded.text, first_media=excluded.first_media''', 
                (p.message_id, text, p.chat.username or "Private", p.chat.title or "情报", 
                 datetime.now().strftime("%Y-%m-%d"), mg_id, thumb))
    return 'OK'

@app.route('/')
def index():
    bot_info = bot.get_me()
    with get_db() as conn:
        posts = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()
    return render_template('index.html', posts=posts, bot_name=bot_info.username)

@app.route('/post/<int:post_id>')
def detail(post_id):
    bot_info = bot.get_me()
    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        comments = conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY id DESC", (post_id,)).fetchall()
    return render_template('detail.html', post=post, comments=comments, bot_name=bot_info.username)

@app.route('/api/comment', methods=['POST'])
def add_comment():
    data = request.json
    with get_db() as conn:
        conn.execute("INSERT INTO comments (post_id, content, date) VALUES (?,?,?)",
                     (data['post_id'], data['content'], datetime.now().strftime("%m-%d %H:%M")))
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))