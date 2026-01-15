import os, sqlite3, requests, telebot, datetime, mimetypes
from flask import Flask, request, render_template, jsonify, send_from_directory
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

# 注册视频类型确保播放
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

# --- 数据库初始化与自动结构修复 ---
def init_db():
    with get_db() as conn:
        # 创建基础表
        conn.execute('''CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            msg_id INTEGER, text TEXT, title TEXT, date TEXT, 
            likes INTEGER DEFAULT 0, media_group_id TEXT, 
            first_media TEXT, admin_note TEXT, is_approved INTEGER DEFAULT 1, user_id INTEGER)''')
        
        # 强制修复：如果旧表缺少列，逐个尝试添加
        columns = {
            "is_approved": "INTEGER DEFAULT 1",
            "user_id": "INTEGER",
            "admin_note": "TEXT",
            "media_group_id": "TEXT",
            "first_media": "TEXT"
        }
        for col, dtype in columns.items():
            try: conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError: pass
            
        conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', '欢迎访问 Matrix Hub')")
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT)''')
    print("Database Initialized & Patched.")

init_db()

# --- 媒体下载逻辑 ---
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
    except Exception as e:
        print(f"Download Error: {e}")
        return None

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# --- Webhook 核心逻辑 ---
@app.route('/webhook', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
    
    # 1. 审核按钮处理
    if update.callback_query:
        data = update.callback_query.data
        action, target = data.split('_', 1)
        with get_db() as conn:
            if target.startswith('G'): # 组审核
                gid = target[1:]
                post = conn.execute("SELECT user_id FROM posts WHERE media_group_id=?", (gid,)).fetchone()
                if action == 'y': conn.execute("UPDATE posts SET is_approved=1 WHERE media_group_id=?", (gid,))
                else: conn.execute("DELETE FROM posts WHERE media_group_id=?", (gid,))
            else: # 单图/文本审核
                post = conn.execute("SELECT user_id FROM posts WHERE id=?", (target,)).fetchone()
                if action == 'y': conn.execute("UPDATE posts SET is_approved=1 WHERE id=?", (target,))
                else: conn.execute("DELETE FROM posts WHERE id=?", (target,))
            
            # 通知投稿者
            if post and post['user_id']:
                try: bot.send_message(post['user_id'], f"审核结果: {'✅已通过' if action=='y' else '❌已拒绝'}")
                except: pass
        bot.edit_message_caption(chat_id=MY_CHAT_ID, message_id=update.callback_query.message.message_id, caption="【审核处理完成】")
        return 'OK'

    # 2. 消息识别 (新消息、频道消息、编辑的消息)
    p = update.channel_post or update.message or update.edited_channel_post or update.edited_message
    if not p: return 'OK'

    uid = str(p.from_user.id) if p.from_user else ""
    is_edit = True if (update.edited_channel_post or update.edited_message) else False
    txt = p.text or p.caption or ""
    gid = p.media_group_id

    # --- 管理员指令 ---
    if uid == str(MY_CHAT_ID) and txt:
        if txt.startswith('/notice '):
            n = txt.split('/notice ', 1)[1]
            with get_db() as conn: conn.execute("UPDATE settings SET value=? WHERE key='notice'", (n,))
            bot.send_message(MY_CHAT_ID, "✅ 公告已更新")
            return 'OK'
        
        if txt == '/sync':
            bot.send_message(MY_CHAT_ID, "🔄 开始同步频道最近 50 条内容...")
            history = bot.get_chat_history(CHANNEL_ID, limit=50)
            for h in history:
                path = download_media(h)
                h_txt = h.text or h.caption or ""
                if not path and not h_txt: continue
                with get_db() as conn:
                    conn.execute('''INSERT INTO posts (msg_id, text, title, date, media_group_id, first_media, is_approved) 
                                    VALUES (?,?,?,?,?,?,1) ON CONFLICT(msg_id) DO UPDATE SET text=excluded.text''',
                                 (h.message_id, h_txt, "官方同步", datetime.now().strftime("%Y-%m-%d"), h.media_group_id, path))
            bot.send_message(MY_CHAT_ID, "✅ 同步完成")
            return 'OK'

        # 删除逻辑：回复消息发 /del 或直接发 /del ID
        if txt.startswith('/del'):
            target_mid = p.reply_to_message.message_id if p.reply_to_message else None
            if not target_mid:
                try: target_mid = int(txt.split(' ')[1])
                except: pass
            if target_mid:
                with get_db() as conn: conn.execute("DELETE FROM posts WHERE msg_id=?", (target_mid,))
                try: bot.delete_message(p.chat.id, target_mid)
                except: pass
                bot.send_message(MY_CHAT_ID, "🗑️ 网页内容已同步删除")
                return 'OK'

    # --- 核心同步逻辑 ---
    path = download_media(p)
    
    if is_edit: # 处理编辑同步
        with get_db() as conn:
            if path: conn.execute("UPDATE posts SET text=?, first_media=? WHERE msg_id=?", (txt, path, p.message_id))
            else: conn.execute("UPDATE posts SET text=? WHERE msg_id=?", (txt, p.message_id))
        return 'OK'

    # 发布新贴/处理投稿
    is_channel = True if update.channel_post else False
    status = 1 if is_channel else 0
    source = "Matrix官方" if is_channel else f"投稿:{p.from_user.first_name}"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO posts (msg_id, text, title, date, media_group_id, first_media, is_approved, user_id) VALUES (?,?,?,?,?,?,?,?)",
                       (p.message_id, txt, source, datetime.now().strftime("%Y-%m-%d"), gid, path, status, p.from_user.id if not is_channel else None))
        new_id = cursor.lastrowid

    # 网友投稿审核提醒
    if not is_channel and not txt.startswith('/'):
        is_first = True
        if gid:
            with get_db() as conn:
                if conn.execute("SELECT COUNT(*) FROM posts WHERE media_group_id=?", (gid,)).fetchone()[0] > 1: is_first = False
        if is_first:
            bot.send_message(p.chat.id, "📥 投稿已提交，请等待审核。")
            markup = InlineKeyboardMarkup()
            cid = f"G{gid}" if gid else str(new_id)
            markup.row(InlineKeyboardButton("✅通过", callback_query_data=f"y_{cid}"), InlineKeyboardButton("❌拒绝", callback_query_data=f"n_{cid}"))
            cap = f"🔔 新投稿 (ID:{new_id})\n内容: {txt[:100]}"
            if path:
                if path.endswith('.mp4'): bot.send_video(MY_CHAT_ID, open(f".{path}",'rb'), caption=cap, reply_markup=markup)
                else: bot.send_photo(MY_CHAT_ID, open(f".{path}",'rb'), caption=cap, reply_markup=markup)
            else: bot.send_message(MY_CHAT_ID, cap, reply_markup=markup)

    return 'OK'

# --- 路由 ---
@app.route('/')
def index():
    q = request.args.get('q', '')
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        # GROUP BY 确保多图组只显示一张，ORDER BY id DESC 确保最新在最前
        posts = conn.execute('''SELECT * FROM posts WHERE is_approved=1 AND text LIKE ? 
                                GROUP BY CASE WHEN media_group_id IS NOT NULL THEN media_group_id ELSE id END 
                                ORDER BY id DESC''', (f'%{q}%',)).fetchall()
    return render_template('index.html', posts=posts, notice=notice['value'] if notice else "", q=q)

@app.route('/post/<int:post_id>')
def detail(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post: return "404", 404
        if post['media_group_id']:
            all_media = conn.execute("SELECT first_media FROM posts WHERE media_group_id=? AND is_approved=1", (post['media_group_id'],)).fetchall()
        else:
            all_media = [{'first_media': post['first_media']}]
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
        with get_db() as conn:
            conn.execute("INSERT INTO comments (post_id, content, date) VALUES (?, ?, ?)",
                         (post_id, content, datetime.now().strftime("%m-%d %H:%M")))
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)