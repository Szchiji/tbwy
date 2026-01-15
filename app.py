import os, sqlite3, requests, telebot, datetime
from flask import Flask, request, render_template, jsonify
from datetime import datetime

app = Flask(__name__)

# --- 配置 ---
DB_DIR = '/app/data'
DB_PATH = os.path.join(DB_DIR, 'data.db')
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
ADMIN_PWD = os.environ.get("ADMIN_PASSWORD", "admin888")

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
            media_group_id TEXT, first_media TEXT, admin_note TEXT, UNIQUE(msg_id, username))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', '欢迎访问 Matrix Hub 情报站')")
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT)''')
        
        # 自动补全可能缺失的列
        existing = [row['name'] for row in conn.execute("PRAGMA table_info(posts)").fetchall()]
        for col in [("media_group_id", "TEXT"), ("first_media", "TEXT"), ("admin_note", "TEXT")]:
            if col[0] not in existing: conn.execute(f"ALTER TABLE posts ADD COLUMN {col[0]} {col[1]}")
init_db()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
    p = update.channel_post or update.message
    if p:
        text = p.text or p.caption or ""
        is_me = str(p.chat.id) == MY_CHAT_ID or str(p.from_user.id if p.from_user else "") == MY_CHAT_ID
        
        # 指令：改公告
        if is_me and text.startswith("/notice "):
            val = text.replace("/notice ", "").strip()
            with get_db() as conn: conn.execute("UPDATE settings SET value=? WHERE key='notice'", (val,))
            return 'OK'

        # 获取媒体链接
        media_url = None
        if p.photo:
            f = bot.get_file(p.photo[-1].file_id)
            media_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f.file_path}"
        elif p.video:
            f = bot.get_file(p.video.file_id)
            media_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f.file_path}"
        
        with get_db() as conn:
            conn.execute('''INSERT INTO posts (msg_id, text, username, title, date, media_group_id, first_media) 
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(msg_id, username) DO UPDATE SET text=excluded.text''', 
                (p.message_id, text, p.chat.username or "Private", p.chat.title or "Channel", 
                 datetime.now().strftime("%Y-%m-%d"), p.media_group_id, media_url))
    return 'OK'

@app.route('/')
def index():
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        # 首页去重：按 media_group_id 分组，保证一组图只显示一个卡片
        posts = conn.execute('''SELECT * FROM posts GROUP BY CASE WHEN media_group_id IS NOT NULL 
                                THEN media_group_id ELSE id END ORDER BY id DESC''').fetchall()
    return render_template('index.html', posts=posts, notice=notice['value'], bot_name=bot.get_me().username)

@app.route('/post/<int:post_id>')
def detail(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        # 瀑布流查询：同一个组的所有图片/视频
        all_media = []
        if post['media_group_id']:
            all_media = conn.execute("SELECT first_media FROM posts WHERE media_group_id=? AND first_media IS NOT NULL", (post['media_group_id'],)).fetchall()
        comments = conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY id DESC", (post_id,)).fetchall()
    return render_template('detail.html', post=post, notice=notice['value'], all_media=all_media, comments=comments)

@app.route('/api/set_note', methods=['POST'])
def set_note():
    data = request.json
    if data.get('password') != ADMIN_PWD: return "Error", 401
    with get_db() as conn:
        conn.execute("UPDATE posts SET admin_note = ? WHERE id = ?", (data.get('content'), data.get('post_id')))
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)