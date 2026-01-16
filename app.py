import os, sqlite3, requests, telebot, datetime, mimetypes, cv2
from flask import Flask, request, render_template, jsonify, send_from_directory
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

# --- 基础配置 ---
mimetypes.add_type('video/mp4', '.mp4')
mimetypes.add_type('video/quicktime', '.mov')
app = Flask(__name__)

DB_DIR = '/app/data'
UPLOAD_DIR = os.path.join(DB_DIR, 'uploads')
THUMB_DIR = os.path.join(DB_DIR, 'thumbs')
DB_PATH = os.path.join(DB_DIR, 'data.db')

for d in [UPLOAD_DIR, THUMB_DIR]:
    os.makedirs(d, exist_ok=True)

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
bot = telebot.TeleBot(BOT_TOKEN)

# --- 数据库管理 ---
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                msg_id INTEGER UNIQUE, 
                text TEXT, 
                title TEXT, 
                date TEXT, 
                likes INTEGER DEFAULT 0, 
                views INTEGER DEFAULT 0, 
                media_group_id TEXT, 
                first_media TEXT, 
                thumb_url TEXT, 
                is_approved INTEGER DEFAULT 1, 
                user_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, date TEXT);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT);
            INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', 'Matrix Hub 终极完整版已上线');
        ''')
        # 兼容性检查：确保字段存在
        try: conn.execute("ALTER TABLE posts ADD COLUMN thumb_url TEXT")
        except: pass
        try: conn.execute("ALTER TABLE posts ADD COLUMN views INTEGER DEFAULT 0")
        except: pass
init_db()

# --- 媒体处理: OpenCV 截图 + 下载 ---
def generate_thumb(video_path, file_id):
    thumb_name = f"thumb_{file_id}.jpg"
    thumb_path = os.path.join(THUMB_DIR, thumb_name)
    if os.path.exists(thumb_path):
        return f"/thumbs/{thumb_name}"
    try:
        vidcap = cv2.VideoCapture(video_path)
        success, image = vidcap.read()
        if success:
            cv2.imwrite(thumb_path, image)
            vidcap.release()
            return f"/thumbs/{thumb_name}"
    except Exception as e:
        print(f"Thumbnail Generation Error: {e}")
    return None

def download_media(p):
    media_obj = p.photo[-1] if p.photo else (p.video if p.video else None)
    if not media_obj: return None, None
    ext = ".jpg" if p.photo else ".mp4"
    file_id = media_obj.file_id
    save_name = f"{file_id}{ext}"
    target_path = os.path.join(UPLOAD_DIR, save_name)
    
    if not os.path.exists(target_path):
        try:
            file_info = bot.get_file(file_id)
            with requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}", stream=True, timeout=30) as r:
                with open(target_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        except: return None, None

    media_url = f"/uploads/{save_name}"
    thumb_url = media_url
    if ext == ".mp4":
        thumb_url = generate_thumb(target_path, file_id) or media_url
    return media_url, thumb_url

# --- 路由 ---
@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route('/thumbs/<path:filename>')
def serve_thumbs(filename):
    return send_from_directory(THUMB_DIR, filename)

@app.route('/')
def index():
    q = request.args.get('q', '')
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
    return render_template('index.html', notice=notice['value'] if notice else "", q=q)

@app.route('/api/posts')
def api_posts():
    page = int(request.args.get('page', 1))
    q = request.args.get('q', '')
    limit = 10
    offset = (page - 1) * limit
    with get_db() as conn:
        posts = conn.execute('''
            SELECT * FROM posts WHERE is_approved=1 AND text LIKE ? 
            GROUP BY CASE WHEN media_group_id IS NOT NULL THEN media_group_id ELSE id END 
            ORDER BY id DESC LIMIT ? OFFSET ?
        ''', (f'%{q}%', limit, offset)).fetchall()
    return jsonify([dict(p) for p in posts])

@app.route('/post/<int:post_id>')
def detail(post_id):
    with get_db() as conn:
        conn.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))
        post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post: return "404", 404
        all_media = conn.execute("SELECT first_media, thumb_url FROM posts WHERE media_group_id=? AND is_approved=1 ORDER BY msg_id ASC", (post['media_group_id'],)).fetchall() if post['media_group_id'] else [{'first_media': post['first_media'], 'thumb_url': post['thumb_url']}]
        comments = conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY id DESC", (post_id,)).fetchall()
    return render_template('detail.html', post=post, all_media=all_media, comments=comments)

# --- Webhook: 指令与审核核心 ---
@app.route('/webhook', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
    
    # 1. 回调审核处理
    if update.callback_query:
        action, target = update.callback_query.data.split('_', 1)
        with get_db() as conn:
            if action == 'y':
                if target.startswith('G'): conn.execute("UPDATE posts SET is_approved=1 WHERE media_group_id=?", (target[1:],))
                else: conn.execute("UPDATE posts SET is_approved=1 WHERE id=?", (target,))
            else:
                if target.startswith('G'): conn.execute("DELETE FROM posts WHERE media_group_id=?", (target[1:],))
                else: conn.execute("DELETE FROM posts WHERE id=?", (target,))
        bot.edit_message_caption("【管理员已处理】", MY_CHAT_ID, update.callback_query.message.message_id)
        return 'OK'

    p = update.channel_post or update.message or update.edited_channel_post or update.edited_message
    if not p: return 'OK'
    
    uid, txt, gid = (p.from_user.id if p.from_user else None), (p.text or p.caption or ""), p.media_group_id

    # 2. 管理员指令
    if str(uid) == str(MY_CHAT_ID):
        if txt.startswith('/notice '):
            with get_db() as conn: conn.execute("UPDATE settings SET value=? WHERE key='notice'", (txt[8:],))
            bot.send_message(MY_CHAT_ID, "✅ 网站公告已更新")
            return 'OK'
        if txt == '/sync':
            history = bot.get_chat_history(CHANNEL_ID, limit=50)
            caps = {h.media_group_id: (h.text or h.caption) for h in history if h.media_group_id and (h.text or h.caption)}
            for h in history:
                path, thumb = download_media(h)
                with get_db() as conn:
                    conn.execute("INSERT OR IGNORE INTO posts (msg_id, text, title, date, media_group_id, first_media, thumb_url, is_approved) VALUES (?,?,?,?,?,?,?,1)",
                                 (h.message_id, (h.text or h.caption) or caps.get(h.media_group_id, ""), "官方", datetime.now().strftime("%Y-%m-%d"), h.media_group_id, path, thumb))
            bot.send_message(MY_CHAT_ID, "🔄 同步完成")
            return 'OK'
        if txt == '/ban' and p.reply_to_message:
            with get_db() as conn:
                res = conn.execute("SELECT user_id FROM posts WHERE msg_id=?", (p.reply_to_message.message_id,)).fetchone()
                if res and res['user_id']: 
                    conn.execute("INSERT OR IGNORE INTO blacklist (user_id, date) VALUES (?,?)", (res['user_id'], datetime.now().strftime("%Y-%m-%d")))
                    bot.send_message(MY_CHAT_ID, f"🚫 已拉黑用户 {res['user_id']}")
            return 'OK'
        if txt == '/del' and p.reply_to_message:
            with get_db() as conn: conn.execute("DELETE FROM posts WHERE msg_id=?", (p.reply_to_message.message_id,))
            try: bot.delete_message(CHANNEL_ID, p.reply_to_message.message_id)
            except: pass
            bot.send_message(MY_CHAT_ID, "🗑️ 内容已销毁")
            return 'OK'

    # 3. 拦截
    if uid:
        with get_db() as conn:
            if conn.execute("SELECT 1 FROM blacklist WHERE user_id=?", (uid,)).fetchone(): return 'OK'

    # 4. 入库
    path, thumb = download_media(p)
    if (update.edited_channel_post or update.edited_message):
        with get_db() as conn: conn.execute("UPDATE posts SET text=?, first_media=?, thumb_url=? WHERE msg_id=?", (txt, path, thumb, p.message_id))
        return 'OK'

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO posts (msg_id, text, title, date, media_group_id, first_media, thumb_url, is_approved, user_id) VALUES (?,?,?,?,?,?,?,?,?)",
                       (p.message_id, txt, "官方" if update.channel_post else "投稿", datetime.now().strftime("%Y-%m-%d"), gid, path, thumb, 1 if update.channel_post else 0, uid))
        new_id = cursor.lastrowid

    # 5. 审核通知
    if not update.channel_post and not txt.startswith('/'):
        is_first = True
        if gid:
            with get_db() as conn:
                if conn.execute("SELECT COUNT(*) FROM posts WHERE media_group_id=?", (gid,)).fetchone()[0] > 1: is_first = False
        if is_first:
            markup = InlineKeyboardMarkup().row(InlineKeyboardButton("✅通过", callback_query_data=f"y_{'G'+gid if gid else new_id}"), InlineKeyboardButton("❌拒绝", callback_query_data=f"n_{'G'+gid if gid else new_id}"))
            bot.send_message(MY_CHAT_ID, f"🔔 新投稿:\n{txt[:100]}", reply_markup=markup)
    return 'OK'

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