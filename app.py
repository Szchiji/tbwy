import os, sqlite3, requests, re, time, telebot, threading
from flask import Flask, request, render_template, jsonify
from datetime import datetime

app = Flask(__name__)

# --- 配置 (请确保 Railway 环境变量中已设置这些项) ---
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
        # 1. 创建帖子表
        conn.execute('''CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            msg_id INTEGER, text TEXT, username TEXT, title TEXT, 
            date TEXT, likes INTEGER DEFAULT 0, is_pinned INTEGER DEFAULT 0,
            media_group_id TEXT, first_media TEXT, admin_note TEXT, UNIQUE(msg_id, username))''')
        
        # 2. 创建配置表（存公告）
        conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', '欢迎访问 Matrix Hub 情报站')")
        
        # 3. 创建评论表
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT)''')

        # 4. 自动检查并补全缺失列
        existing = [row['name'] for row in conn.execute("PRAGMA table_info(posts)").fetchall()]
        cols_to_add = [
            ("media_group_id", "TEXT"), 
            ("first_media", "TEXT"), 
            ("admin_note", "TEXT"),
            ("is_pinned", "INTEGER DEFAULT 0")
        ]
        for col, col_type in cols_to_add:
            if col not in existing:
                conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {col_type}")
init_db()

# --- 辅助：获取图片 ---
def get_file_link(file_id):
    try:
        file_info = bot.get_file(file_id)
        return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
    except: return None

# --- Webhook 逻辑 ---
@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    p = update.channel_post or update.message
    
    if p:
        text = p.text or p.caption or ""
        is_me = str(p.chat.id) == MY_CHAT_ID or str(p.from_user.id if p.from_user else "") == MY_CHAT_ID

        # 机器人指令：修改公告
        if is_me and text.startswith("/notice "):
            val = text.replace("/notice ", "").strip()
            with get_db() as conn: conn.execute("UPDATE settings SET value=? WHERE key='notice'", (val,))
            bot.reply_to(p, f"✅ 顶部公告已更新")
            return 'OK'

        # 机器人指令：删除内容
        if is_me and text.startswith("/del "):
            pid = text.replace("/del ", "").strip()
            with get_db() as conn: conn.execute("DELETE FROM posts WHERE id=?", (pid,))
            bot.reply_to(p, f"🗑️ 已删除 ID:{pid}")
            return 'OK'

        # 多图去重
        mg_id = p.media_group_id
        if mg_id:
            with get_db() as conn:
                if conn.execute("SELECT id FROM posts WHERE media_group_id=?", (mg_id,)).fetchone(): return 'OK'

        # 提取首图
        thumb = None
        if p.photo: thumb = get_file_link(p.photo[-1].file_id)
        elif p.video: thumb = get_file_link(p.video.thumb.file_id) if p.video.thumb else None

        # 入库
        with get_db() as conn:
            conn.execute('''INSERT INTO posts (msg_id, text, username, title, date, media_group_id, first_media) 
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(msg_id, username) DO UPDATE SET text=excluded.text''', 
                (p.message_id, text, p.chat.username or "Private", p.chat.title or "Channel", 
                 datetime.now().strftime("%Y-%m-%d"), mg_id, thumb))
    return 'OK'

# --- 网页路由 ---
@app.route('/')
def index():
    q = request.args.get('q', '')
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        if q:
            posts = conn.execute("SELECT * FROM posts WHERE text LIKE ? ORDER BY is_pinned DESC, id DESC", (f'%{q}%',)).fetchall()
        else:
            posts = conn.execute("SELECT * FROM posts ORDER BY is_pinned DESC, id DESC").fetchall()
    return render_template('index.html', posts=posts, notice=notice['value'], bot_name=bot.get_me().username, q=q)

@app.route('/post/<int:post_id>')
def detail(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        comments = conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY id DESC", (post_id,)).fetchall()
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
    return render_template('detail.html', post=post, comments=comments, notice=notice['value'], bot_name=bot.get_me().username)

@app.route('/api/set_note', methods=['POST'])
def set_note():
    data = request.json
    if data.get('password') != ADMIN_PWD: return "Unauthorized", 401
    with get_db() as conn:
        conn.execute("UPDATE posts SET admin_note = ? WHERE id = ?", (data.get('content'), data.get('post_id')))
    return "OK"

@app.route('/api/like/<int:id>', methods=['POST'])
def like(id):
    with get_db() as conn: conn.execute("UPDATE posts SET likes = likes + 1 WHERE id=?", (id,))
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)