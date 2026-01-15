import os, sqlite3, requests, telebot, datetime, mimetypes
from flask import Flask, request, render_template, jsonify, send_from_directory
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

# 注册视频格式
mimetypes.add_type('video/mp4', '.mp4')
mimetypes.add_type('video/quicktime', '.mov')

app = Flask(__name__)

# --- 基础配置 ---
DB_DIR = '/app/data'
UPLOAD_DIR = os.path.join(DB_DIR, 'uploads')
DB_PATH = os.path.join(DB_DIR, 'data.db')
os.makedirs(UPLOAD_DIR, exist_ok=True)

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
ADMIN_PWD = os.environ.get("ADMIN_PASSWORD", "admin888")
bot = telebot.TeleBot(BOT_TOKEN)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            msg_id INTEGER, text TEXT, title TEXT, date TEXT, 
            likes INTEGER DEFAULT 0, media_group_id TEXT, 
            first_media TEXT, admin_note TEXT, is_approved INTEGER DEFAULT 1, user_id INTEGER)''')
        # 自动补全缺失字段
        try:
            conn.execute("ALTER TABLE posts ADD COLUMN is_approved INTEGER DEFAULT 1")
            conn.execute("ALTER TABLE posts ADD COLUMN user_id INTEGER")
        except: pass
        conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', '欢迎访问 Matrix Hub')")
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT)''')
init_db()

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

@app.route('/webhook', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
    
    # 1. 处理按钮审核
    if update.callback_query:
        data = update.callback_query.data
        action, target = data.split('_', 1)
        with get_db() as conn:
            if target.startswith('G'):
                gid = target[1:]
                post = conn.execute("SELECT user_id FROM posts WHERE media_group_id=?", (gid,)).fetchone()
                if action == 'y':
                    conn.execute("UPDATE posts SET is_approved=1 WHERE media_group_id=?", (gid,))
                    res = "✅ 已发布"
                else:
                    conn.execute("DELETE FROM posts WHERE media_group_id=?", (gid,))
                    res = "❌ 已拒绝"
            else:
                post = conn.execute("SELECT user_id FROM posts WHERE id=?", (target,)).fetchone()
                if action == 'y':
                    conn.execute("UPDATE posts SET is_approved=1 WHERE id=?", (target,))
                    res = "✅ 已发布"
                else:
                    conn.execute("DELETE FROM posts WHERE id=?", (target,))
                    res = "❌ 已拒绝"
            if post and post['user_id']:
                try: bot.send_message(post['user_id'], f"投稿审核结果：{res}")
                except: pass
        bot.edit_message_caption(chat_id=MY_CHAT_ID, message_id=update.callback_query.message.message_id, caption=f"【处理完成】\n{res}")
        return 'OK'

    # 2. 识别消息类型（新消息、频道消息、编辑消息）
    p = update.channel_post or update.message or update.edited_channel_post or update.edited_message
    if not p: return 'OK'

    is_edit = True if (update.edited_channel_post or update.edited_message) else False
    path = download_media(p)
    txt = p.text or p.caption or ""
    gid = p.media_group_id

    # 处理编辑逻辑
    if is_edit:
        with get_db() as conn:
            if path:
                conn.execute("UPDATE posts SET text=?, first_media=? WHERE msg_id=?", (txt, path, p.message_id))
            else:
                conn.execute("UPDATE posts SET text=? WHERE msg_id=?", (txt, p.message_id))
        return 'OK'

    # 处理管理员指令
    if p.text == '/sync' and str(p.from_user.id) == str(MY_CHAT_ID):
        # 此处省略已有的同步代码，INSERT 改为 INSERT OR REPLACE 即可支持同步更新
        return 'OK'

    # 处理新投稿/发布
    is_channel = True if update.channel_post else False
    status = 1 if is_channel else 0
    source = "Matrix官方" if is_channel else f"投稿:{p.from_user.first_name}"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO posts (msg_id, text, title, date, media_group_id, first_media, is_approved, user_id) VALUES (?,?,?,?,?,?,?,?)",
                       (p.message_id, txt, source, datetime.now().strftime("%Y-%m-%d"), gid, path, status, p.from_user.id if not is_channel else None))
        new_id = cursor.lastrowid

    if not is_channel and not (p.text and p.text.startswith('/')):
        is_first = True
        if gid:
            with get_db() as conn:
                if conn.execute("SELECT COUNT(*) FROM posts WHERE media_group_id=?", (gid,)).fetchone()[0] > 1: is_first = False
        if is_first:
            bot.send_message(p.chat.id, "📥 投稿已接收，等待审核...")
            markup = InlineKeyboardMarkup()
            cid = f"G{gid}" if gid else str(new_id)
            markup.row(InlineKeyboardButton("✅ 通过", callback_query_data=f"y_{cid}"), InlineKeyboardButton("❌ 拒绝", callback_query_data=f"n_{cid}"))
            cap = f"🔔 新投稿\n内容: {txt[:100]}"
            if path:
                if path.endswith('.mp4'): bot.send_video(MY_CHAT_ID, open(f".{path}",'rb'), caption=cap, reply_markup=markup)
                else: bot.send_photo(MY_CHAT_ID, open(f".{path}",'rb'), caption=cap, reply_markup=markup)
            else: bot.send_message(MY_CHAT_ID, cap, reply_markup=markup)
    return 'OK'

@app.route('/')
def index():
    q = request.args.get('q', '')
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        posts = conn.execute('''SELECT * FROM posts WHERE is_approved=1 AND text LIKE ? 
                                GROUP BY CASE WHEN media_group_id IS NOT NULL THEN media_group_id ELSE id END 
                                ORDER BY id DESC''', (f'%{q}%',)).fetchall()
    return render_template('index.html', posts=posts, notice=notice['value'] if notice else "", q=q)

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
    with get_db() as conn: conn.execute("UPDATE posts SET likes = likes + 1 WHERE id = ?", (post_id,))
    return jsonify({"status": "success"})

@app.route('/api/comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    content = request.json.get('content')
    if content:
        with get_db() as conn: conn.execute("INSERT INTO comments (post_id, content, date) VALUES (?, ?, ?)", (post_id, content, datetime.now().strftime("%m-%d %H:%M")))
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)