import os, sqlite3, requests, telebot, datetime, mimetypes
from flask import Flask, request, render_template, jsonify, send_from_directory
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

# 基础类型注册
mimetypes.add_type('video/mp4', '.mp4')
mimetypes.add_type('video/quicktime', '.mov')

app = Flask(__name__)

# --- 核心路径与配置 ---
DB_DIR = '/app/data'
UPLOAD_DIR = os.path.join(DB_DIR, 'uploads')
DB_PATH = os.path.join(DB_DIR, 'data.db')
os.makedirs(UPLOAD_DIR, exist_ok=True)

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
bot = telebot.TeleBot(BOT_TOKEN)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

# --- 数据库自修复与全字段初始化 ---
def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            msg_id INTEGER UNIQUE, text TEXT, title TEXT, date TEXT, 
            likes INTEGER DEFAULT 0, media_group_id TEXT, 
            first_media TEXT, admin_note TEXT, is_approved INTEGER DEFAULT 1, user_id INTEGER)''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, date TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', '欢迎访问 Matrix Hub')")
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT)''')
        
        # 补齐所有可能缺失的字段
        expected_cols = {"is_approved": "INTEGER DEFAULT 1", "user_id": "INTEGER", "media_group_id": "TEXT", "first_media": "TEXT"}
        for col, dtype in expected_cols.items():
            try: conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {dtype}")
            except: pass
init_db()

# --- 增强版下载与清理 ---
def download_media(p):
    media_obj = p.photo[-1] if p.photo else (p.video if p.video else None)
    if not media_obj: return None
    ext = ".jpg" if p.photo else ".mp4"
    try:
        file_info = bot.get_file(media_obj.file_id)
        save_name = f"{media_obj.file_id}{ext}"
        target_path = os.path.join(UPLOAD_DIR, save_name)
        if not os.path.exists(target_path):
            r = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}", timeout=20)
            with open(target_path, 'wb') as f: f.write(r.content)
        return f"/uploads/{save_name}"
    except: return None

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# --- 核心 Webhook 处理 ---
@app.route('/webhook', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
    
    # 1. 审核回调 (GID 为图组，普通 ID 为单帖)
    if update.callback_query:
        data = update.callback_query.data
        action, target = data.split('_', 1)
        with get_db() as conn:
            if action == 'y': # 通过
                if target.startswith('G'): conn.execute("UPDATE posts SET is_approved=1 WHERE media_group_id=?", (target[1:],))
                else: conn.execute("UPDATE posts SET is_approved=1 WHERE id=?", (target,))
            else: # 拒绝并物理删除
                if target.startswith('G'): conn.execute("DELETE FROM posts WHERE media_group_id=?", (target[1:],))
                else: conn.execute("DELETE FROM posts WHERE id=?", (target,))
        bot.edit_message_caption(chat_id=MY_CHAT_ID, message_id=update.callback_query.message.message_id, caption="【已处理完成】")
        return 'OK'

    p = update.channel_post or update.message or update.edited_channel_post or update.edited_message
    if not p: return 'OK'

    uid = p.from_user.id if p.from_user else None
    txt = p.text or p.caption or ""
    gid = p.media_group_id
    is_edit = True if (update.edited_channel_post or update.edited_message) else False

    # --- 管理员指令集 ---
    if str(uid) == str(MY_CHAT_ID):
        # 公告更新
        if txt.startswith('/notice '):
            n_val = txt.split(' ', 1)[1]
            with get_db() as conn: conn.execute("UPDATE settings SET value=? WHERE key='notice'", (n_val,))
            bot.send_message(MY_CHAT_ID, "✅ 网页公告已同步")
            return 'OK'
            
        # 同步历史
        if txt == '/sync':
            history = bot.get_chat_history(CHANNEL_ID, limit=50)
            for h in history:
                path = download_media(h)
                with get_db() as conn:
                    conn.execute('''INSERT INTO posts (msg_id, text, title, date, media_group_id, first_media, is_approved) 
                        VALUES (?,?,?,?,?,?,1) ON CONFLICT(msg_id) DO UPDATE SET text=excluded.text''',
                        (h.message_id, h.text or h.caption or "", "官方", datetime.now().strftime("%Y-%m-%d"), h.media_group_id, path))
            bot.send_message(MY_CHAT_ID, "✅ 历史记录补齐成功")
            return 'OK'

        # 物理同步删除
        if txt == '/del' and p.reply_to_message:
            mid = p.reply_to_message.message_id
            with get_db() as conn: conn.execute("DELETE FROM posts WHERE msg_id=?", (mid,))
            try: bot.delete_message(CHANNEL_ID, mid)
            except: pass
            bot.send_message(MY_CHAT_ID, "🗑️ 网页与频道已同步销毁")
            return 'OK'

        # 黑名单封禁
        if txt == '/ban' and p.reply_to_message:
            with get_db() as conn:
                res = conn.execute("SELECT user_id FROM posts WHERE msg_id=?", (p.reply_to_message.message_id,)).fetchone()
                if res and res['user_id']:
                    conn.execute("INSERT OR IGNORE INTO blacklist (user_id, date) VALUES (?,?)", (res['user_id'], datetime.now().strftime("%Y-%m-%d")))
                    bot.send_message(MY_CHAT_ID, f"🚫 用户 {res['user_id']} 已拉黑")
            return 'OK'

    # --- 拦截拦截 ---
    if uid:
        with get_db() as conn:
            if conn.execute("SELECT 1 FROM blacklist WHERE user_id=?", (uid,)).fetchone(): return 'OK'

    # --- 常规入库与编辑 ---
    path = download_media(p)
    if is_edit:
        with get_db() as conn: conn.execute("UPDATE posts SET text=?, first_media=? WHERE msg_id=?", (txt, path, p.message_id))
        return 'OK'

    is_channel = True if update.channel_post else False
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO posts (msg_id, text, title, date, media_group_id, first_media, is_approved, user_id) VALUES (?,?,?,?,?,?,?,?)",
                       (p.message_id, txt, "官方" if is_channel else f"投稿:{p.from_user.first_name}", datetime.now().strftime("%Y-%m-%d"), gid, path, 1 if is_channel else 0, uid))
        new_id = cursor.lastrowid

    # 审核提醒
    if not is_channel and not txt.startswith('/'):
        is_first = True
        if gid:
            with get_db() as conn:
                if conn.execute("SELECT COUNT(*) FROM posts WHERE media_group_id=?", (gid,)).fetchone()[0] > 1: is_first = False
        if is_first:
            markup = InlineKeyboardMarkup()
            cid = f"G{gid}" if gid else str(new_id)
            markup.row(InlineKeyboardButton("✅通过", callback_query_data=f"y_{cid}"), InlineKeyboardButton("❌拒绝", callback_query_data=f"n_{cid}"))
            cap = f"🔔 新投稿通知\n{txt[:100]}"
            if path:
                if path.endswith('.mp4'): bot.send_video(MY_CHAT_ID, open(f".{path}",'rb'), caption=cap, reply_markup=markup)
                else: bot.send_photo(MY_CHAT_ID, open(f".{path}",'rb'), caption=cap, reply_markup=markup)
            else: bot.send_message(MY_CHAT_ID, cap, reply_markup=markup)

    return 'OK'

# --- 网页渲染 (保持逻辑一致性) ---
@app.route('/')
def index():
    q = request.args.get('q', '')
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        posts = conn.execute('''SELECT * FROM posts WHERE is_approved=1 AND text LIKE ? 
                                GROUP BY CASE WHEN media_group_id IS NOT NULL THEN media_group_id ELSE id END 
                                ORDER BY id DESC''', (f'%{q}%',)).fetchall()
    return render_template('index.html', posts=posts, notice=notice['value'] if notice else "")

@app.route('/post/<int:post_id>')
def detail(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post: return "404", 404
        all_media = conn.execute("SELECT first_media FROM posts WHERE media_group_id=? AND is_approved=1", (post['media_group_id'],)).fetchall() if post['media_group_id'] else [{'first_media': post['first_media']}]
        comments = conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY id DESC", (post_id,)).fetchall()
    return render_template('detail.html', post=post, all_media=all_media, comments=comments)

@app.route('/api/like/<int:post_id>', methods=['POST'])
def like(post_id):
    with get_db() as conn: conn.execute("UPDATE posts SET likes=likes+1 WHERE id=?", (post_id,))
    return jsonify({"status":"ok"})

@app.route('/api/comment/<int:post_id>', methods=['POST'])
def comment(post_id):
    content = request.json.get('content')
    if content:
        with get_db() as conn: conn.execute("INSERT INTO comments (post_id, content, date) VALUES (?,?,?)", (post_id, content, datetime.now().strftime("%m-%d %H:%M")))
    return jsonify({"status":"ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)