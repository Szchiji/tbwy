import os, sqlite3, requests, telebot, datetime, mimetypes, cv2, html, hmac, hashlib, json
from flask import Flask, request, render_template, jsonify, send_from_directory
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from datetime import datetime
from collections import defaultdict
import time
from credit import get_credit_tier, format_tier_badge, next_tier_info, add_credit_event
from ai import score_photo_authenticity

# 环境与类型配置
mimetypes.add_type('video/mp4', '.mp4')
mimetypes.add_type('video/quicktime', '.mov')
app = Flask(__name__)

# 简单的内存速率限制器
rate_limit_storage = defaultdict(lambda: {'count': 0, 'reset_time': time.time()})

def check_rate_limit(identifier, max_requests=10, window_seconds=60):
    """简单的速率限制检查
    
    注意：此实现使用共享的 defaultdict 且不是线程安全的。
    在生产环境中，建议使用 Redis 或其他线程安全的存储方案。
    
    Args:
        identifier: 用户标识符 (如 user_id 或 IP)
        max_requests: 时间窗口内最大请求数
        window_seconds: 时间窗口（秒）
    
    Returns:
        bool: True 表示允许请求，False 表示超过限制
    """
    current_time = time.time()
    limit_data = rate_limit_storage[identifier]
    
    # 如果时间窗口已过，重置计数
    if current_time > limit_data['reset_time']:
        limit_data['count'] = 0
        limit_data['reset_time'] = current_time + window_seconds
    
    # 检查是否超过限制
    if limit_data['count'] >= max_requests:
        return False
    
    # 增加计数
    limit_data['count'] += 1
    return True

def verify_telegram_data(init_data_str: str) -> bool:
    """Verify Telegram WebApp initData HMAC-SHA256 signature.
    
    Returns True in dev mode (ENV=dev), or when signature is valid.
    Returns False if the signature is missing or invalid in production.
    """
    if os.environ.get('ENV') == 'dev':
        return True
    if not BOT_TOKEN or not init_data_str:
        return False
    try:
        params = dict(
            kv.split('=', 1) for kv in init_data_str.split('&') if '=' in kv
        )
        data_hash = params.pop('hash', None)
        if not data_hash:
            return False
        data_check_string = '\n'.join(
            f'{k}={v}' for k, v in sorted(params.items())
        )
        secret_key = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, data_hash)
    except Exception:
        return False

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
# 管理员密钥（生产环境务必设置强密码）
ADMIN_KEY = os.environ.get("ADMIN_KEY", "matrix_admin_2024")
if ADMIN_KEY == "matrix_admin_2024":
    print("WARNING: Using default ADMIN_KEY. Please set ADMIN_KEY environment variable for production!")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# 获取机器人用户名（优先使用环境变量，否则通过 API 获取）
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
if not BOT_USERNAME and BOT_TOKEN:
    try:
        BOT_USERNAME = bot.get_me().username or ""
    except Exception as e:
        print(f"Warning: Could not fetch bot username: {e}")
        BOT_USERNAME = ""

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
            CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT, user_id TEXT);
            CREATE TABLE IF NOT EXISTS user_blacklist (user_id TEXT, post_id INTEGER, date TEXT, PRIMARY KEY (user_id, post_id));
            CREATE TABLE IF NOT EXISTS user_favorites (
                user_id TEXT, 
                post_id INTEGER, 
                date TEXT, 
                PRIMARY KEY (user_id, post_id)
            );
            CREATE TABLE IF NOT EXISTS users (
                tg_id TEXT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                photo_url TEXT,
                registered_at TEXT
            );
            CREATE TABLE IF NOT EXISTS bot_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT DEFAULT 'idle',
                data TEXT DEFAULT '{}',
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_posts_approved ON posts(is_approved);
            CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date DESC);
            CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
            CREATE INDEX IF NOT EXISTS idx_favorites_user ON user_favorites(user_id);
            INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', '欢迎访问 Matrix Hub');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('site_title', 'Matrix Hub');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('filter_tags', '[]');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('enable_comments', '1');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('enable_submissions', '1');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('submission_notice', '');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('accent_color', '#a78bfa');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('enable_ai_review', '0');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('ai_reject_threshold', '30');
        ''')
        
        # 字段自动迁移逻辑 (安全处理旧数据库)
        # 注意：这是简单的迁移方案，适合小型项目
        # 生产环境建议使用 Alembic 等专业的数据库迁移工具
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
        if 'tags' not in columns:
            try: conn.execute("ALTER TABLE posts ADD COLUMN tags TEXT DEFAULT ''")
            except: pass
        if 'ai_score' not in columns:
            try: conn.execute("ALTER TABLE posts ADD COLUMN ai_score REAL")
            except: pass
        
        # 迁移 comments 表的 user_id 字段
        cursor = conn.execute("PRAGMA table_info(comments)")
        comment_columns = [c[1] for c in cursor.fetchall()]
        if 'user_id' not in comment_columns:
            try: conn.execute("ALTER TABLE comments ADD COLUMN user_id TEXT")
            except: pass

        # 迁移 users 表的信用/速率字段
        cursor = conn.execute("PRAGMA table_info(users)")
        user_columns = [c[1] for c in cursor.fetchall()]
        if 'credit_score' not in user_columns:
            try: conn.execute("ALTER TABLE users ADD COLUMN credit_score INTEGER DEFAULT 100")
            except: pass
        if 'credit_history' not in user_columns:
            try: conn.execute("ALTER TABLE users ADD COLUMN credit_history TEXT DEFAULT '[]'")
            except: pass
        if 'rate_timestamps' not in user_columns:
            try: conn.execute("ALTER TABLE users ADD COLUMN rate_timestamps TEXT DEFAULT '{}'")
            except: pass

init_db()

# --- 设置辅助函数 ---
def get_setting(conn, key, default=''):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row['value'] if row else default

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
        # 检查缩略图是否存在，如果不存在则生成
        if ext == ".mp4":
            thumb_name = f"{media_obj.file_id}_thumb.jpg"
            thumb_path = os.path.join(UPLOAD_DIR, thumb_name)
            if os.path.exists(thumb_path):
                # 缩略图已存在
                thumbnail_path = f"/uploads/{thumb_name}"
            else:
                # 尝试生成缩略图
                if generate_video_thumbnail(target_path, thumb_path):
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
                        # Award +15 credit to post author
                        post_id_val = target[1:] if target.startswith('G') else target
                        if target.startswith('G'):
                            author_row = conn.execute("SELECT user_id FROM posts WHERE media_group_id=? LIMIT 1", (post_id_val,)).fetchone()
                        else:
                            author_row = conn.execute("SELECT user_id FROM posts WHERE id=?", (post_id_val,)).fetchone()
                        if author_row and author_row['user_id']:
                            add_credit_event(conn, str(author_row['user_id']), 'post_approved')
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
            # /admin - 获取最新帖子管理员链接
            if txt == '/admin':
                with get_db() as conn:
                    posts = conn.execute("SELECT id, text, date FROM posts WHERE is_approved=1 ORDER BY id DESC LIMIT 10").fetchall()
                
                if posts:
                    msg = "🔧 **管理员链接列表**\n\n"
                    for p_row in posts:
                        preview = (p_row['text'] or '无内容')[:25] + '...' if p_row['text'] and len(p_row['text']) > 25 else (p_row['text'] or '无内容')
                        admin_url = f"{BASE_URL}/post/{p_row['id']}?admin_key={ADMIN_KEY}"
                        msg += f"[{p_row['id']}] {preview}\n{admin_url}\n\n"
                    bot.send_message(MY_CHAT_ID, msg, parse_mode='Markdown', disable_web_page_preview=True)
                else:
                    bot.send_message(MY_CHAT_ID, "暂无帖子")
                return 'OK'
            
            # /admin <id> - 获取指定帖子管理员链接
            if txt.startswith('/admin '):
                try:
                    post_id = int(txt[7:].strip())
                    with get_db() as conn:
                        post = conn.execute("SELECT id, text, date FROM posts WHERE id=?", (post_id,)).fetchone()
                    
                    if post:
                        admin_url = f"{BASE_URL}/post/{post['id']}?admin_key={ADMIN_KEY}"
                        msg = f"🔧 帖子 #{post['id']} 管理员链接\n\n🔗 {admin_url}"
                        bot.send_message(MY_CHAT_ID, msg, disable_web_page_preview=True)
                    else:
                        bot.send_message(MY_CHAT_ID, f"❌ 帖子 #{post_id} 不存在")
                except ValueError:
                    bot.send_message(MY_CHAT_ID, "❌ 格式错误，请使用: /admin <帖子ID>")
                return 'OK'
            
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
                bot.send_message(MY_CHAT_ID, "🔄 正在同步频道未读消息...")
                count = 0
                try:
                    # 临时移除 Webhook，通过 getUpdates 获取未读消息
                    bot.remove_webhook()
                    time.sleep(1)
                    updates = bot.get_updates(limit=100, allowed_updates=['channel_post'])
                    for update in updates:
                        h = update.channel_post
                        if h and str(h.chat.id) == str(CHANNEL_ID):
                            path, thumbnail = download_media(h)
                            if path:
                                with get_db() as conn:
                                    conn.execute("INSERT OR IGNORE INTO posts (msg_id, text, title, date, media_group_id, first_media, thumbnail, is_approved) VALUES (?,?,?,?,?,?,?,1)",
                                                 (h.message_id, (h.text or h.caption or ""), "官方", datetime.now().strftime("%Y-%m-%d"), h.media_group_id, path, thumbnail))
                                count += 1
                    # 推进 offset，标记所有已获取的 updates 为已读，防止重新注册 Webhook 后重复投递
                    if updates:
                        bot.get_updates(offset=updates[-1].update_id + 1, limit=1)
                    bot.send_message(MY_CHAT_ID, f"✅ 同步完成，共同步 {count} 条新内容")
                except Exception as e:
                    bot.send_message(MY_CHAT_ID, f"❌ 同步失败: {e}")
                finally:
                    # 重新注册 Webhook
                    if BASE_URL:
                        bot.set_webhook(url=f"{BASE_URL}/webhook")
                return 'OK'

        # 3. 黑名单拦截
        if uid:
            with get_db() as conn:
                if conn.execute("SELECT 1 FROM blacklist WHERE user_id=?", (uid,)).fetchone(): return 'OK'

        # 4. FSM 分步投稿引导（仅对私聊用户消息，非频道帖）
        if update.message and uid and str(uid) != str(MY_CHAT_ID):
            with get_db() as conn:
                state_row = conn.execute(
                    "SELECT state, data FROM bot_states WHERE user_id=?", (uid,)
                ).fetchone()
            state = state_row['state'] if state_row else 'idle'
            fsm_data = {}
            try:
                fsm_data = json.loads(state_row['data'] or '{}') if state_row else {}
            except (json.JSONDecodeError, TypeError):
                pass

            def set_state(new_state, new_data=None):
                payload = json.dumps(new_data or {}, ensure_ascii=False)
                with get_db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO bot_states (user_id, state, data, updated_at) VALUES (?,?,?,?)",
                        (uid, new_state, payload, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )

            def clear_state():
                with get_db() as conn:
                    conn.execute("DELETE FROM bot_states WHERE user_id=?", (uid,))

            # /start 命令 — 显示欢迎 + 开始投稿按钮
            if txt in ('/start', '/投稿') or txt == '📸 开始投稿':
                kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                kb.add(KeyboardButton('📸 开始投稿'))
                if txt in ('/start',):
                    bot.send_message(uid,
                        "👋 欢迎使用 Matrix Hub 投稿机器人！\n\n"
                        "点击下方按钮开始分步投稿，或直接发送图片/视频快速投稿。",
                        reply_markup=kb)
                    return 'OK'
                # User tapped "开始投稿"
                set_state('waiting_media')
                bot.send_message(uid,
                    "📷 请发送你想投稿的图片或视频：\n\n"
                    "发送 /cancel 可随时取消。",
                    reply_markup=ReplyKeyboardRemove())
                return 'OK'

            # /cancel 取消投稿
            if txt == '/cancel':
                if state != 'idle':
                    clear_state()
                    bot.send_message(uid, "✅ 已取消投稿。", reply_markup=ReplyKeyboardRemove())
                else:
                    bot.send_message(uid, "当前没有进行中的投稿。")
                return 'OK'

            # FSM: waiting_media — 等待用户发送图片/视频
            if state == 'waiting_media':
                if p.photo or p.video:
                    path, thumbnail = download_media(p)
                    if not path:
                        bot.send_message(uid, "❌ 媒体下载失败，请重试。")
                        return 'OK'
                    # Optional AI scoring
                    ai_score = None
                    with get_db() as conn:
                        enable_ai = get_setting(conn, 'enable_ai_review', '0')
                        threshold = float(get_setting(conn, 'ai_reject_threshold', '30'))
                    if enable_ai == '1' and path:
                        full_url = f"{BASE_URL}{path}" if BASE_URL else path
                        ai_score = score_photo_authenticity(full_url)
                        if ai_score < threshold:
                            clear_state()
                            bot.send_message(uid,
                                f"❌ 内容质量评分过低（{ai_score:.0f}/100），无法投稿。\n"
                                "请确保内容清晰、原创，再重新投稿。",
                                reply_markup=ReplyKeyboardRemove())
                            return 'OK'
                    set_state('waiting_description', {
                        'media_path': path,
                        'thumbnail': thumbnail or '',
                        'ai_score': ai_score,
                        'msg_id': p.message_id,
                        'media_group_id': gid,
                    })
                    ai_note = f"\n\n🤖 AI 质量评分: {ai_score:.0f}/100" if ai_score is not None else ""
                    bot.send_message(uid,
                        f"✅ 媒体已收到！{ai_note}\n\n"
                        "📝 请发送投稿描述（标签用 #标签 格式），或发送 . 跳过描述：",
                        reply_markup=ReplyKeyboardRemove())
                    return 'OK'
                else:
                    bot.send_message(uid, "⚠️ 请发送图片或视频，或发送 /cancel 取消。")
                    return 'OK'

            # FSM: waiting_description — 等待用户输入描述
            if state == 'waiting_description':
                description = txt if txt and txt != '.' else ''
                fsm_data['description'] = description
                set_state('waiting_confirm', fsm_data)
                preview = f"📄 描述: {description}\n" if description else ""
                kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                kb.row(KeyboardButton('✅ 确认投稿'), KeyboardButton('❌ 取消'))
                bot.send_message(uid,
                    f"📋 投稿预览：\n\n{preview}"
                    "确认后将提交审核，管理员审核通过后即可发布。",
                    reply_markup=kb)
                return 'OK'

            # FSM: waiting_confirm — 等待用户确认
            if state == 'waiting_confirm':
                if txt == '✅ 确认投稿':
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT OR IGNORE INTO posts (msg_id, text, title, date, media_group_id, first_media, thumbnail, is_approved, user_id, ai_score) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (
                                fsm_data.get('msg_id', p.message_id),
                                fsm_data.get('description', ''),
                                '投稿',
                                datetime.now().strftime("%Y-%m-%d"),
                                fsm_data.get('media_group_id'),
                                fsm_data.get('media_path'),
                                fsm_data.get('thumbnail') or None,
                                0,
                                uid,
                                fsm_data.get('ai_score'),
                            )
                        )
                        new_id = cursor.lastrowid
                    clear_state()
                    markup = InlineKeyboardMarkup().row(
                        InlineKeyboardButton("✅通过", callback_data=f"y_{new_id}"),
                        InlineKeyboardButton("❌拒绝", callback_data=f"n_{new_id}")
                    )
                    desc_preview = (fsm_data.get('description') or '（无描述）')[:80]
                    ai_note = f"\n🤖 AI评分: {fsm_data['ai_score']:.0f}" if fsm_data.get('ai_score') is not None else ""
                    bot.send_message(MY_CHAT_ID,
                        f"🔔 新投稿 (FSM):\n{desc_preview}{ai_note}\n👤 用户: {uid}",
                        reply_markup=markup)
                    bot.send_message(uid,
                        "✅ 投稿已提交，等待审核！\n审核通过后将在平台上发布。",
                        reply_markup=ReplyKeyboardRemove())
                    return 'OK'
                else:
                    clear_state()
                    bot.send_message(uid, "❌ 已取消投稿。", reply_markup=ReplyKeyboardRemove())
                    return 'OK'

        # 5. 入库处理（频道帖或直接发送媒体的快速投稿）
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
                
                # 6. 发送管理员链接
                if update.channel_post and new_id:
                    admin_url = f"{BASE_URL}/post/{new_id}?admin_key={ADMIN_KEY}"
                    bot.send_message(MY_CHAT_ID, f"📢 新帖子已发布！\n\n🔗 管理链接：{admin_url}")
        
        return 'OK'
    return 'OK'

# --- 路由渲染 ---
def _build_post_query_conditions(type_filter, sort, source='', tag=''):
    """根据类型过滤、来源过滤、自定义标签和排序参数构建 SQL 片段（均来自服务端枚举，非用户原始输入）。"""
    if type_filter == 'video':
        type_condition = " AND (p.first_media LIKE '%.mp4' OR p.first_media LIKE '%.mov')"
    elif type_filter == 'image':
        type_condition = " AND (p.first_media LIKE '%.jpg' OR p.first_media LIKE '%.jpeg'" \
                         " OR p.first_media LIKE '%.png' OR p.first_media LIKE '%.gif'" \
                         " OR p.first_media LIKE '%.webp')"
    else:
        type_condition = ""
    if source == 'official':
        source_condition = " AND p.title = '官方'"
    elif source == 'user':
        source_condition = " AND p.title = '投稿'"
    else:
        source_condition = ""
    order_clause = "p.likes DESC, p.id DESC" if sort == 'hot' else "p.id DESC"
    # tag condition uses a bind parameter for safety
    tag_condition = " AND (',' || COALESCE(p.tags,'') || ',') LIKE '%,' || ? || ',%'" if tag else ""
    return type_condition, source_condition, order_clause, tag_condition

@app.route('/')
def index():
    q = request.args.get('q', '')
    user_id = request.args.get('user_id', 'anonymous')
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', '')
    sort = request.args.get('sort', 'latest')
    source = request.args.get('source', '')
    tag = request.args.get('tag', '')
    per_page = 20
    offset = (page - 1) * per_page
    type_condition, source_condition, order_clause, tag_condition = _build_post_query_conditions(type_filter, sort, source, tag)
    
    with get_db() as conn:
        notice = get_setting(conn, 'notice')
        site_title = get_setting(conn, 'site_title', 'Matrix Hub')
        accent_color = get_setting(conn, 'accent_color', '#a78bfa')
        import json as _json
        try:
            filter_tags = _json.loads(get_setting(conn, 'filter_tags', '[]'))
        except Exception:
            filter_tags = []
        # 分组查询：如果是媒体组只显示一张，排除用户拉黑的内容，附带评论数
        base_params = [f'%{q}%', user_id]
        if tag:
            base_params.append(tag)
        sql = f"""SELECT p.*, (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count
                 FROM posts p 
                 WHERE p.is_approved=1 AND p.text LIKE ? 
                 AND p.id NOT IN (SELECT post_id FROM user_blacklist WHERE user_id=?)
                 {type_condition}{source_condition}{tag_condition}
                 GROUP BY COALESCE(p.media_group_id, p.id) 
                 ORDER BY {order_clause}
                 LIMIT ? OFFSET ?"""
        posts = conn.execute(sql, base_params + [per_page, offset]).fetchall()
        
        # 获取总数用于分页
        count_sql = f"""SELECT COUNT(DISTINCT COALESCE(p.media_group_id, p.id)) AS total FROM posts p 
                       WHERE p.is_approved=1 AND p.text LIKE ? 
                       AND p.id NOT IN (SELECT post_id FROM user_blacklist WHERE user_id=?)
                       {type_condition}{source_condition}{tag_condition}"""
        total = conn.execute(count_sql, base_params).fetchone()['total']
        
    return render_template('index.html', posts=posts, notice=notice, 
                         q=q, user_id=user_id, page=page,
                         total_pages=(total + per_page - 1) // per_page,
                         type_filter=type_filter, sort=sort, source=source,
                         tag=tag, filter_tags=filter_tags,
                         site_title=site_title, accent_color=accent_color)

@app.route('/api/posts')
def api_posts():
    """JSON 接口，供前端无限滚动使用。"""
    q = request.args.get('q', '')
    user_id = request.args.get('user_id', 'anonymous')
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', '')
    sort = request.args.get('sort', 'latest')
    source = request.args.get('source', '')
    tag = request.args.get('tag', '')
    per_page = 20
    offset = (page - 1) * per_page
    type_condition, source_condition, order_clause, tag_condition = _build_post_query_conditions(type_filter, sort, source, tag)

    with get_db() as conn:
        base_params = [f'%{q}%', user_id]
        if tag:
            base_params.append(tag)
        sql = f"""SELECT p.*, (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count
                 FROM posts p 
                 WHERE p.is_approved=1 AND p.text LIKE ? 
                 AND p.id NOT IN (SELECT post_id FROM user_blacklist WHERE user_id=?)
                 {type_condition}{source_condition}{tag_condition}
                 GROUP BY COALESCE(p.media_group_id, p.id) 
                 ORDER BY {order_clause}
                 LIMIT ? OFFSET ?"""
        posts = conn.execute(sql, base_params + [per_page, offset]).fetchall()

        count_sql = f"""SELECT COUNT(DISTINCT COALESCE(p.media_group_id, p.id)) AS total FROM posts p 
                       WHERE p.is_approved=1 AND p.text LIKE ? 
                       AND p.id NOT IN (SELECT post_id FROM user_blacklist WHERE user_id=?)
                       {type_condition}{source_condition}{tag_condition}"""
        total = conn.execute(count_sql, base_params).fetchone()['total']

    total_pages = (total + per_page - 1) // per_page
    posts_data = [{
        'id': p['id'],
        'text': p['text'] or '',
        'title': p['title'] or '',
        'date': p['date'] or '',
        'likes': p['likes'] or 0,
        'first_media': p['first_media'] or '',
        'thumbnail': p['thumbnail'] or '',
        'comment_count': p['comment_count'] or 0,
        'custom_description': p['custom_description'] or '',
    } for p in posts]
    return jsonify({'posts': posts_data, 'total_pages': total_pages, 'page': page, 'has_more': page < total_pages})

@app.route('/post/<int:post_id>')
def detail(post_id):
    user_id = request.args.get('user_id', 'anonymous')
    admin_key = request.args.get('admin_key', '')
    is_admin = (admin_key == ADMIN_KEY)
    
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
        
        # 检查是否已收藏
        is_favorited = conn.execute("SELECT 1 FROM user_favorites WHERE user_id=? AND post_id=?", (user_id, post_id)).fetchone() is not None
        
    return render_template('detail.html', post=post, all_media=all_media, comments=comments, 
                         is_favorited=is_favorited, user_id=user_id, is_admin=is_admin)

@app.route('/api/like/<int:post_id>', methods=['POST'])
def like(post_id):
    data = request.json or {}
    user_id = data.get('user_id', 'anonymous')
    init_data = data.get('init_data', '')
    if not verify_telegram_data(init_data):
        return jsonify({"status":"error", "message":"签名验证失败"}), 403
    # Rate limiting: 10 likes per minute per user
    if not check_rate_limit(f'like_{user_id}', max_requests=10, window_seconds=60):
        return jsonify({"status":"error", "message":"操作过于频繁，请稍后再试"}), 429
    
    with get_db() as conn:
        conn.execute("UPDATE posts SET likes=likes+1 WHERE id=?", (post_id,))
        # Award +1 credit to post author
        post_row = conn.execute("SELECT user_id FROM posts WHERE id=?", (post_id,)).fetchone()
        if post_row and post_row['user_id']:
            add_credit_event(conn, str(post_row['user_id']), 'post_liked')
    return jsonify({"status":"ok"})

@app.route('/api/comment/<int:post_id>', methods=['POST'])
def comment(post_id):
    data = request.json or {}
    content = data.get('content')
    user_id = data.get('user_id', 'anonymous')
    init_data = data.get('init_data', '')
    if not verify_telegram_data(init_data):
        return jsonify({"status":"error", "message":"签名验证失败"}), 403
    
    # Rate limiting: 5 comments per minute per user
    if not check_rate_limit(f'comment_{user_id}', max_requests=5, window_seconds=60):
        return jsonify({"status":"error", "message":"评论过于频繁，请稍后再试"}), 429
    
    # XSS protection: escape HTML content
    if content:
        content = html.escape(content)
        date_str = datetime.now().strftime("%m-%d %H:%M")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO comments (post_id, content, date, user_id) VALUES (?,?,?,?)",
                           (post_id, content, date_str, user_id))
            new_id = cursor.lastrowid
            # Award +1 credit to the commenter
            if user_id.startswith('tg_'):
                add_credit_event(conn, user_id[3:], 'comment_posted')
        return jsonify({"status": "ok", "id": new_id, "date": date_str})
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

@app.route('/api/favorite/<int:post_id>', methods=['POST', 'DELETE'])
def toggle_favorite(post_id):
    data = request.json or {}
    user_id = data.get('user_id', 'anonymous')
    init_data = data.get('init_data', '')
    if not verify_telegram_data(init_data):
        return jsonify({"status":"error", "message":"签名验证失败"}), 403
    with get_db() as conn:
        existing = conn.execute("SELECT 1 FROM user_favorites WHERE user_id=? AND post_id=?", (user_id, post_id)).fetchone()
        if request.method == 'POST' and not existing:
            conn.execute("INSERT INTO user_favorites (user_id, post_id, date) VALUES (?,?,?)", 
                        (user_id, post_id, datetime.now().strftime("%Y-%m-%d")))
            return jsonify({"status":"ok", "favorited":True})
        elif request.method == 'DELETE' and existing:
            conn.execute("DELETE FROM user_favorites WHERE user_id=? AND post_id=?", (user_id, post_id))
            return jsonify({"status":"ok", "favorited":False})
    return jsonify({"status":"ok"})

@app.route('/api/favorites')
def get_favorites():
    user_id = request.args.get('user_id', 'anonymous')
    with get_db() as conn:
        posts = conn.execute("""
            SELECT p.* FROM posts p 
            JOIN user_favorites f ON p.id = f.post_id 
            WHERE f.user_id = ? ORDER BY f.date DESC
        """, (user_id,)).fetchall()
    return jsonify([dict(p) for p in posts])

@app.route('/favorites')
def favorites_page():
    user_id = request.args.get('user_id', 'anonymous')
    with get_db() as conn:
        notice = get_setting(conn, 'notice')
        # Get favorites with grouping similar to index
        posts = conn.execute("""
            SELECT p.* FROM posts p 
            JOIN user_favorites f ON p.id = f.post_id 
            WHERE f.user_id = ? 
            GROUP BY COALESCE(p.media_group_id, p.id)
            ORDER BY f.date DESC
        """, (user_id,)).fetchall()
    return render_template('favorites.html', posts=posts, notice=notice, user_id=user_id)

@app.route('/upload')
def upload_guide():
    user_id = request.args.get('user_id', 'anonymous')
    with get_db() as conn:
        notice = get_setting(conn, 'notice')
        submission_notice = get_setting(conn, 'submission_notice')
        enable_submissions = get_setting(conn, 'enable_submissions', '1')
    return render_template('upload.html', user_id=user_id, notice=notice,
                          submission_notice=submission_notice,
                          enable_submissions=(enable_submissions == '1'),
                          bot_username=BOT_USERNAME)

@app.route('/profile')
def profile():
    user_id = request.args.get('user_id', 'anonymous')
    with get_db() as conn:
        # 获取 TG 用户信息（如果已注册）
        tg_user = None
        if user_id.startswith('tg_'):
            tg_numeric = user_id[3:]
            tg_user = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_numeric,)).fetchone()

        # 获取用户收藏
        favorites = conn.execute("""
            SELECT p.* FROM posts p 
            JOIN user_favorites f ON p.id = f.post_id 
            WHERE f.user_id = ? ORDER BY f.date DESC LIMIT 10
        """, (user_id,)).fetchall()
        
        # 获取用户评论
        comments = conn.execute("""
            SELECT c.*, p.id as post_id, p.text as post_text 
            FROM comments c 
            JOIN posts p ON c.post_id = p.id 
            WHERE c.user_id = ? ORDER BY c.id DESC LIMIT 10
        """, (user_id,)).fetchall()

        # 获取用户投稿记录
        submissions = []
        if user_id.startswith('tg_'):
            tg_numeric = user_id[3:]
            submissions = conn.execute("""
                SELECT * FROM posts WHERE CAST(user_id AS TEXT)=? ORDER BY id DESC LIMIT 20
            """, (tg_numeric,)).fetchall()
        
    return render_template('profile.html', favorites=favorites, comments=comments,
                          submissions=submissions, tg_user=tg_user, user_id=user_id)

@app.route('/api/admin/description/<int:post_id>', methods=['POST'])
def update_description(post_id):
    admin_key = request.json.get('admin_key', '')
    if admin_key != ADMIN_KEY:
        return jsonify({"status":"error", "message":"权限不足"}), 403
    description = request.json.get('description', '')
    with get_db() as conn:
        conn.execute("UPDATE posts SET custom_description=? WHERE id=?", (description, post_id))
    return jsonify({"status":"ok"})

@app.route('/api/credit/stats')
def credit_stats():
    admin_key = request.args.get('admin_key', '')
    if admin_key != ADMIN_KEY:
        return jsonify({"status":"error", "message":"权限不足"}), 403
    with get_db() as conn:
        row = conn.execute(
            "SELECT AVG(COALESCE(credit_score,100)) as avg_score,"
            " SUM(CASE WHEN COALESCE(credit_score,100) >= 200 THEN 1 ELSE 0 END) as high_count,"
            " SUM(CASE WHEN COALESCE(credit_score,100) < 50 THEN 1 ELSE 0 END) as low_count"
            " FROM users"
        ).fetchone()
    return jsonify({
        "status": "ok",
        "avg_score": row['avg_score'],
        "high_count": row['high_count'] or 0,
        "low_count": row['low_count'] or 0,
    })

@app.route('/api/admin/post/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    admin_key = request.json.get('admin_key', '')
    if admin_key != ADMIN_KEY:
        return jsonify({"status":"error", "message":"权限不足"}), 403
    with get_db() as conn:
        # 删除帖子及相关数据（评论、收藏、拉黑记录）
        conn.execute("DELETE FROM comments WHERE post_id=?", (post_id,))
        conn.execute("DELETE FROM user_favorites WHERE post_id=?", (post_id,))
        conn.execute("DELETE FROM user_blacklist WHERE post_id=?", (post_id,))
        conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
    return jsonify({"status":"ok"})

@app.route('/api/admin/comment/<int:comment_id>', methods=['DELETE'])
def admin_delete_comment(comment_id):
    admin_key = request.json.get('admin_key', '')
    if admin_key != ADMIN_KEY:
        return jsonify({"status":"error", "message":"权限不足"}), 403
    with get_db() as conn:
        conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    return jsonify({"status":"ok"})

@app.route('/admin/panel')
def admin_panel():
    admin_key = request.args.get('admin_key', '')
    if admin_key != ADMIN_KEY:
        return "Access Denied — 请在 URL 中附加 ?admin_key=<你的密钥>", 403
    import json as _json
    with get_db() as conn:
        settings = {row['key']: row['value'] for row in conn.execute("SELECT key, value FROM settings").fetchall()}
        pending = conn.execute("SELECT COUNT(*) as c FROM posts WHERE is_approved=0").fetchone()['c']
        total_posts = conn.execute("SELECT COUNT(*) as c FROM posts WHERE is_approved=1").fetchone()['c']
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
        pending_posts = conn.execute("SELECT * FROM posts WHERE is_approved=0 ORDER BY id DESC LIMIT 20").fetchall()
    try:
        filter_tags = _json.loads(settings.get('filter_tags', '[]'))
    except Exception:
        filter_tags = []
    return render_template('admin.html', settings=settings, admin_key=admin_key,
                          pending=pending, total_posts=total_posts, total_users=total_users,
                          pending_posts=pending_posts, filter_tags=filter_tags)

@app.route('/api/admin/settings', methods=['GET', 'POST'])
def admin_settings_api():
    if request.method == 'GET':
        admin_key = request.args.get('admin_key', '')
    else:
        data = request.json or {}
        admin_key = data.get('admin_key', '')
    if admin_key != ADMIN_KEY:
        return jsonify({"status":"error", "message":"权限不足"}), 403
    if request.method == 'GET':
        with get_db() as conn:
            settings = {row['key']: row['value'] for row in conn.execute("SELECT key, value FROM settings").fetchall()}
        return jsonify(settings)
    allowed_keys = {'site_title', 'notice', 'filter_tags', 'enable_comments', 'enable_submissions', 'submission_notice', 'accent_color', 'enable_ai_review', 'ai_reject_threshold'}
    with get_db() as conn:
        for key, value in data.items():
            if key in allowed_keys:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    return jsonify({"status":"ok"})

@app.route('/api/admin/post/<int:post_id>/approve', methods=['POST'])
def admin_approve_post(post_id):
    admin_key = request.json.get('admin_key', '') if request.is_json else ''
    if admin_key != ADMIN_KEY:
        return jsonify({"status":"error", "message":"权限不足"}), 403
    with get_db() as conn:
        post_row = conn.execute("SELECT user_id FROM posts WHERE id=?", (post_id,)).fetchone()
        conn.execute("UPDATE posts SET is_approved=1 WHERE id=?", (post_id,))
        # Award +15 credit to post author
        if post_row and post_row['user_id']:
            add_credit_event(conn, str(post_row['user_id']), 'post_approved')
    return jsonify({"status":"ok"})

@app.route('/api/admin/post/<int:post_id>/tags', methods=['POST'])
def admin_set_post_tags(post_id):
    admin_key = request.json.get('admin_key', '') if request.is_json else ''
    if admin_key != ADMIN_KEY:
        return jsonify({"status":"error", "message":"权限不足"}), 403
    tags = request.json.get('tags', '')
    with get_db() as conn:
        conn.execute("UPDATE posts SET tags=? WHERE id=?", (tags, post_id))
    return jsonify({"status":"ok"})

@app.route('/api/user/init', methods=['POST'])
def user_init():
    data = request.json or {}
    tg_id = data.get('tg_id')
    if not tg_id:
        return jsonify({"status":"error", "message":"缺少 tg_id"}), 400
    # initData HMAC verification
    init_data = data.get('init_data', '')
    if not verify_telegram_data(init_data):
        return jsonify({"status":"error", "message":"签名验证失败"}), 403
    username = data.get('username', '')
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    photo_url = data.get('photo_url', '')
    with get_db() as conn:
        existing = conn.execute("SELECT tg_id FROM users WHERE tg_id=?", (str(tg_id),)).fetchone()
        if existing:
            conn.execute("UPDATE users SET username=?, first_name=?, last_name=? WHERE tg_id=?",
                        (username, first_name, last_name, str(tg_id)))
        else:
            conn.execute("INSERT INTO users (tg_id, username, first_name, last_name, photo_url, registered_at, credit_score, credit_history) VALUES (?,?,?,?,?,?,?,?)",
                        (str(tg_id), username, first_name, last_name, photo_url, datetime.now().strftime("%Y-%m-%d"), 100, '[]'))
    return jsonify({"status":"ok", "user_id": f"tg_{tg_id}"})

@app.route('/api/credit')
def get_credit():
    user_id = request.args.get('user_id', '')
    if not user_id.startswith('tg_'):
        return jsonify({"status":"error", "message":"需要 Telegram 登录"}), 400
    tg_id = user_id[3:]
    with get_db() as conn:
        row = conn.execute(
            "SELECT credit_score, credit_history FROM users WHERE tg_id=?", (tg_id,)
        ).fetchone()
    if not row:
        return jsonify({"status":"error", "message":"用户不存在"}), 404
    score = row['credit_score'] if row['credit_score'] is not None else 100
    try:
        history = json.loads(row['credit_history'] or '[]')
    except (json.JSONDecodeError, TypeError):
        history = []
    tier = get_credit_tier(score)
    nxt = next_tier_info(score)
    return jsonify({
        "status": "ok",
        "score": score,
        "tier": tier,
        "next_tier": nxt,
        "history": history[-10:],
    })

@app.route('/my-submissions')
def my_submissions():
    user_id = request.args.get('user_id', 'anonymous')
    submissions = []
    if user_id.startswith('tg_'):
        tg_numeric = user_id[3:]
        with get_db() as conn:
            submissions = conn.execute("""
                SELECT * FROM posts WHERE CAST(user_id AS TEXT)=? ORDER BY id DESC
            """, (tg_numeric,)).fetchall()
    return render_template('my_submissions.html', submissions=submissions, user_id=user_id)

# 自动设置 Webhook（模块级别，gunicorn 加载时也会执行）
if BASE_URL and BOT_TOKEN:
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{BASE_URL}/webhook")
        print(f"Webhook registered: {BASE_URL}/webhook")
    except Exception as e:
        print(f"Warning: Failed to set webhook: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))