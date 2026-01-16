import os, sqlite3, requests, telebot, datetime, mimetypes, cv2
from flask import Flask, request, render_template, jsonify, send_from_directory
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

# 环境与类型配置
mimetypes.add_type('video/mp4', '.mp4')
mimetypes.add_type('video/quicktime', '.mov')
app = Flask(__name__)

# 路径配置 (适配 Railway Volume)
DB_DIR = '/app/data' if os.path.exists('/app/data') else 'data'
UPLOAD_DIR = os.path.join(DB_DIR, 'uploads')
DB_PATH = os.path.join(DB_DIR, 'data.db')
os.makedirs(UPLOAD_DIR, exist_ok=True)

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
# 获取公网 URL 用于 Webhook (可选)
BASE_URL = os.environ.get("BASE_URL", "").rstrip('/')

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# --- 数据库管理 ---
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # 创建核心表
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                msg_id INTEGER UNIQUE, 
                text TEXT, 
                title TEXT, 
                date TEXT, 
                likes INTEGER DEFAULT 0, 
                media_group_id TEXT, 
                first_media TEXT, 
                is_approved INTEGER DEFAULT 1, 
                user_id INTEGER,
                blacklist_count INTEGER DEFAULT 0,
                custom_description TEXT
            );
            CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, date TEXT);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT);
            CREATE TABLE IF NOT EXISTS user_blacklist (user_id TEXT, post_id INTEGER, date TEXT, PRIMARY KEY (user_id, post_id));
            INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', '欢迎访问 Matrix Hub');
        ''')
        
        # 字段自动迁移逻辑 (安全处理旧数据库)
        cursor = conn.execute("PRAGMA table_info(posts)")
        columns = [c[1] for c in cursor.fetchall()]
        if 'user_id' not in columns:
            try: conn.execute("ALTER TABLE posts ADD COLUMN user_id INTEGER")
            except: pass
        if 'is_approved' not in columns:
            try: conn.execute("ALTER TABLE posts ADD COLUMN is_approved INTEGER DEFAULT 1")
            except: pass
        if 'blacklist_count' not in columns:
            try: conn.execute("ALTER TABLE posts ADD COLUMN blacklist_count INTEGER DEFAULT 0")
            except: pass
        if 'custom_description' not in columns:
            try: conn.execute("ALTER TABLE posts ADD COLUMN custom_description TEXT")
            except: pass
        if 'thumbnail' not in columns:
            try: conn.execute("ALTER TABLE posts ADD COLUMN thumbnail TEXT")
            except: pass

init_db()

# --- 媒体处理 ---
def generate_video_thumbnail(video_path, thumbnail_path):
    """使用 cv2 生成视频缩略图
    
    Args:
        video_path: 视频文件路径
        thumbnail_path: 缩略图保存路径
        
    Returns:
        bool: 成功返回True，失败返回False
    """
    cap = None
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Thumbnail generation error: Cannot open video file {video_path}")
            return False
            
        # 尝试定位到1秒位置，如果视频太短则使用第一帧
        cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
        success, frame = cap.read()
        
        # 如果1秒位置读取失败，尝试读取第一帧
        if not success:
            cap.set(cv2.CAP_PROP_POS_MSEC, 0)
            success, frame = cap.read()
        
        if success and frame is not None:
            # 调整大小到宽度320
            height, width = frame.shape[:2]
            new_width = 320
            new_height = int(height * (new_width / width))
            resized = cv2.resize(frame, (new_width, new_height))
            cv2.imwrite(thumbnail_path, resized)
            return True
        return False
    except Exception as e:
        print(f"Thumbnail generation error: {e}")
        return False
    finally:
        if cap is not None:
            cap.release()

def download_media(p):
    media_obj = p.photo[-1] if p.photo else (p.video if p.video else None)
    if not media_obj: return None, None
    
    # 获取后缀
    ext = ".jpg" if p.photo else ".mp4"
    save_name = f"{media_obj.file_id}{ext}"
    target_path = os.path.join(UPLOAD_DIR, save_name)
    thumbnail_path = None
    
    if os.path.exists(target_path): 
        # 检查缩略图是否存在
        if ext == ".mp4":
            thumb_name = f"{media_obj.file_id}_thumb.jpg"
            thumb_path = os.path.join(UPLOAD_DIR, thumb_name)
            if os.path.exists(thumb_path):
                thumbnail_path = f"/uploads/{thumb_name}"
        return f"/uploads/{save_name}", thumbnail_path
        
    try:
        file_info = bot.get_file(media_obj.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        with requests.get(file_url, stream=True, timeout=30) as r:
            if r.status_code == 200:
                with open(target_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                
                # 如果是视频，生成缩略图
                if ext == ".mp4":
                    thumb_name = f"{media_obj.file_id}_thumb.jpg"
                    thumb_path = os.path.join(UPLOAD_DIR, thumb_name)
                    if generate_video_thumbnail(target_path, thumb_path):
                        thumbnail_path = f"/uploads/{thumb_name}"
                
                return f"/uploads/{save_name}", thumbnail_path
    except Exception as e:
        print(f"Download Error: {e}")
    return None, None

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# --- Webhook 逻辑 ---
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        
        # 1. 审核回调
        if update.callback_query:
            try:
                action, target = update.callback_query.data.split('_', 1)
                with get_db() as conn:
                    if action == 'y':
                        sql = "UPDATE posts SET is_approved=1 WHERE " + ("media_group_id=?" if target.startswith('G') else "id=?")
                        conn.execute(sql, (target[1:] if target.startswith('G') else target,))
                        bot.answer_callback_query(update.callback_query.id, "审核通过")
                    else:
                        sql = "DELETE FROM posts WHERE " + ("media_group_id=?" if target.startswith('G') else "id=?")
                        conn.execute(sql, (target[1:] if target.startswith('G') else target,))
                        bot.answer_callback_query(update.callback_query.id, "已拒绝并删除")
                bot.edit_message_caption("【审核操作已完成】", MY_CHAT_ID, update.callback_query.message.message_id)
            except: pass
            return 'OK'

        p = update.channel_post or update.message or update.edited_channel_post or update.edited_message
        if not p: return 'OK'
        
        uid = p.from_user.id if p.from_user else None
        txt = p.text or p.caption or ""
        gid = p.media_group_id

        # 2. 管理员指令
        if str(uid) == str(MY_CHAT_ID) or str(p.chat.id) == str(MY_CHAT_ID):
            if txt.startswith('/notice '):
                with get_db() as conn: conn.execute("UPDATE settings SET value=? WHERE key='notice'", (txt[8:],))
                bot.send_message(MY_CHAT_ID, "✅ 公告已更新")
                return 'OK'
            
            if txt.startswith('/desc '):
                # 格式: /desc <post_id> <描述文字>
                parts = txt[6:].split(' ', 1)
                if len(parts) == 2:
                    post_id, desc = parts
                    with get_db() as conn: 
                        conn.execute("UPDATE posts SET custom_description=? WHERE id=?", (desc, int(post_id)))
                    bot.send_message(MY_CHAT_ID, f"✅ 已为帖子 {post_id} 设置自定义描述")
                else:
                    bot.send_message(MY_CHAT_ID, "❌ 格式错误，请使用: /desc <post_id> <描述文字>")
                return 'OK'
            
            if txt == '/sync':
                bot.send_message(MY_CHAT_ID, "🔄 正在同步频道...")
                history = bot.get_chat_history(CHANNEL_ID, limit=50)
                for h in history:
                    path, thumbnail = download_media(h)
                    if path:
                        with get_db() as conn:
                            conn.execute("INSERT OR IGNORE INTO posts (msg_id, text, title, date, media_group_id, first_media, thumbnail, is_approved) VALUES (?,?,?,?,?,?,?,1)",
                                         (h.message_id, (h.text or h.caption or ""), "官方", datetime.now().strftime("%Y-%m-%d"), h.media_group_id, path, thumbnail))
                bot.send_message(MY_CHAT_ID, "✅ 同步完成")
                return 'OK'

        # 3. 黑名单拦截
        if uid:
            with get_db() as conn:
                if conn.execute("SELECT 1 FROM blacklist WHERE user_id=?", (uid,)).fetchone(): return 'OK'

        # 4. 入库处理
        path, thumbnail = download_media(p)
        if path:
            if (update.edited_channel_post or update.edited_message):
                with get_db() as conn: conn.execute("UPDATE posts SET text=?, first_media=?, thumbnail=? WHERE msg_id=?", (txt, path, thumbnail, p.message_id))
            else:
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT OR IGNORE INTO posts (msg_id, text, title, date, media_group_id, first_media, thumbnail, is_approved, user_id) VALUES (?,?,?,?,?,?,?,?,?)",
                                   (p.message_id, txt, "官方" if update.channel_post else "投稿", datetime.now().strftime("%Y-%m-%d"), gid, path, thumbnail, 1 if update.channel_post else 0, uid))
                    new_id = cursor.lastrowid
                
                # 5. 投稿审核提醒
                if not update.channel_post and str(uid) != str(MY_CHAT_ID):
                    markup = InlineKeyboardMarkup().row(
                        InlineKeyboardButton("✅通过", callback_data=f"y_{'G'+gid if gid else new_id}"),
                        InlineKeyboardButton("❌拒绝", callback_data=f"n_{'G'+gid if gid else new_id}")
                    )
                    bot.send_message(MY_CHAT_ID, f"🔔 新投稿:\n{txt[:100]}", reply_markup=markup)
        
        return 'OK'
    return 'OK'

# --- 路由渲染 ---
@app.route('/')
def index():
    q = request.args.get('q', '')
    user_id = request.args.get('user_id', 'anonymous')
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        # 分组查询：如果是媒体组只显示一张，排除用户拉黑的内容
        sql = """SELECT p.* FROM posts p 
                 WHERE p.is_approved=1 AND p.text LIKE ? 
                 AND p.id NOT IN (SELECT post_id FROM user_blacklist WHERE user_id=?)
                 GROUP BY COALESCE(p.media_group_id, p.id) 
                 ORDER BY p.id DESC"""
        posts = conn.execute(sql, (f'%{q}%', user_id)).fetchall()
    return render_template('index.html', posts=posts, notice=notice['value'] if notice else "", q=q, user_id=user_id)

@app.route('/post/<int:post_id>')
def detail(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post: return "404", 404
        # 获取相册所有媒体
        all_media = []
        if post['media_group_id']:
            rows = conn.execute("SELECT first_media FROM posts WHERE media_group_id=? AND is_approved=1 ORDER BY id ASC", (post['media_group_id'],)).fetchall()
            all_media = [r['first_media'] for r in rows]
        else:
            all_media = [post['first_media']]
            
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

@app.route('/api/blacklist/<int:post_id>', methods=['POST'])
def blacklist_user(post_id):
    user_id = request.json.get('user_id', 'anonymous')
    with get_db() as conn:
        # Check if user already blacklisted this post
        existing = conn.execute("SELECT 1 FROM user_blacklist WHERE user_id=? AND post_id=?", (user_id, post_id)).fetchone()
        if not existing:
            conn.execute("INSERT INTO user_blacklist (user_id, post_id, date) VALUES (?,?,?)", (user_id, post_id, datetime.now().strftime("%Y-%m-%d")))
            conn.execute("UPDATE posts SET blacklist_count=blacklist_count+1 WHERE id=?", (post_id,))
    return jsonify({"status":"ok"})

if __name__ == '__main__':
    # 自动设置 Webhook
    if BASE_URL and BOT_TOKEN:
        bot.remove_webhook()
        bot.set_webhook(url=f"{BASE_URL}/webhook")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))