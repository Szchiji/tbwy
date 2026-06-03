import os, sqlite3, requests, telebot, datetime, mimetypes, cv2, html
import urllib.parse, hashlib, hmac, json, random, uuid
from flask import Flask, request, render_template, jsonify, send_from_directory
from telebot.types import (InlineKeyboardMarkup, InlineKeyboardButton,
                            ReplyKeyboardMarkup, KeyboardButton, WebAppInfo)
from datetime import datetime
from collections import defaultdict
import time

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

# 路径配置 (适配 Railway Volume)
DB_DIR = '/app/data' if os.path.exists('/app/data') else 'data'
UPLOAD_DIR = os.path.join(DB_DIR, 'uploads')
DB_PATH = os.path.join(DB_DIR, 'data.db')
os.makedirs(UPLOAD_DIR, exist_ok=True)

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
# 获取公网 URL 用于 Webhook — 支持手动设置或从 Railway 自动检测
_railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
BASE_URL = (
    os.environ.get("BASE_URL", "").rstrip('/')
    or (f"https://{_railway_domain}" if _railway_domain else "")
)
if not BASE_URL:
    print("WARNING: BASE_URL is not set. Webhook cannot be registered and bot commands will not work.")
    print("  Set BASE_URL=https://<your-domain> in environment variables.")
# 管理员密钥（生产环境务必设置强密码）
ADMIN_KEY = os.environ.get("ADMIN_KEY", "matrix_admin_2024")
if ADMIN_KEY == "matrix_admin_2024":
    print("WARNING: Using default ADMIN_KEY. Please set ADMIN_KEY environment variable for production!")

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
            CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT, user_id TEXT);
            CREATE TABLE IF NOT EXISTS user_blacklist (user_id TEXT, post_id INTEGER, date TEXT, PRIMARY KEY (user_id, post_id));
            CREATE TABLE IF NOT EXISTS user_favorites (
                user_id TEXT, 
                post_id INTEGER, 
                date TEXT, 
                PRIMARY KEY (user_id, post_id)
            );
            CREATE TABLE IF NOT EXISTS users (
                tg_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                role TEXT DEFAULT 'client',
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER,
                name TEXT,
                number TEXT UNIQUE,
                region TEXT DEFAULT '',
                district TEXT DEFAULT '',
                price INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]',
                category TEXT DEFAULT '个人',
                contact TEXT DEFAULT '',
                description TEXT DEFAULT '',
                photos TEXT DEFAULT '[]',
                is_verified INTEGER DEFAULT 0,
                is_approved INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS profile_favorites (
                user_tg_id TEXT,
                profile_id INTEGER,
                date TEXT,
                PRIMARY KEY (user_tg_id, profile_id)
            );
            CREATE INDEX IF NOT EXISTS idx_posts_approved ON posts(is_approved);
            CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date DESC);
            CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
            CREATE INDEX IF NOT EXISTS idx_favorites_user ON user_favorites(user_id);
            CREATE INDEX IF NOT EXISTS idx_profiles_approved ON profiles(is_approved);
            CREATE INDEX IF NOT EXISTS idx_profiles_category ON profiles(category);
            CREATE INDEX IF NOT EXISTS idx_profiles_tg ON profiles(tg_id);
            INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', '欢迎访问 星搭 StarMatch');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('form_fields', '{"name":true,"region":true,"district":true,"price":true,"category":true,"tags":true,"contact":true,"description":true}');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('nav_tabs', '["全部","中圈","大圈","个人"]');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('app_name', '星搭 StarMatch');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('price_unit', 'P');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_contact', '');
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
        
        # 迁移 comments 表的 user_id 字段
        cursor = conn.execute("PRAGMA table_info(comments)")
        comment_columns = [c[1] for c in cursor.fetchall()]
        if 'user_id' not in comment_columns:
            try: conn.execute("ALTER TABLE comments ADD COLUMN user_id TEXT")
            except: pass

        # 迁移 profiles 表：添加 pin_type 字段
        cursor = conn.execute("PRAGMA table_info(profiles)")
        profile_columns = [c[1] for c in cursor.fetchall()]
        if 'pin_type' not in profile_columns:
            try: conn.execute("ALTER TABLE profiles ADD COLUMN pin_type INTEGER DEFAULT 0")
            except: pass

init_db()

# 注册 Webhook（在模块加载时执行，确保 Gunicorn 启动时也能注册）
if BASE_URL and BOT_TOKEN:
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{BASE_URL}/webhook")
        print(f"Webhook registered: {BASE_URL}/webhook")
    except Exception as e:
        print(f"WARNING: Failed to register webhook: {e}")

# --- 新系统辅助函数 ---

def verify_init_data(init_data_str):
    """验证 Telegram Mini App initData 签名 (HMAC-SHA256)"""
    if not init_data_str or not BOT_TOKEN:
        return None
    try:
        params = {}
        for pair in init_data_str.split('&'):
            if '=' in pair:
                k, v = pair.split('=', 1)
                params[urllib.parse.unquote(k)] = urllib.parse.unquote(v)
        received_hash = params.pop('hash', None)
        if not received_hash:
            return None
        data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(params.items()))
        secret_key = hmac.new(b'WebAppData', BOT_TOKEN.encode('utf-8'), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
        if computed_hash == received_hash:
            return json.loads(params.get('user', '{}'))
    except Exception as e:
        print(f"initData verification error: {e}")
    return None

def get_tg_id_from_request():
    """从请求中提取 tg_id（支持 initData 验证 或 fallback query param）"""
    data = request.json or {}
    init_data = data.get('initData', '') or request.args.get('initData', '')
    if init_data:
        user_data = verify_init_data(init_data)
        if user_data:
            return str(user_data.get('id', ''))
    # fallback: query param tg_id (仅用于开发/测试)
    return request.args.get('tg_id', '') or data.get('tg_id', '')

def get_or_create_user(tg_id, username='', first_name=''):
    """获取或创建用户记录，返回 role"""
    tg_id = int(tg_id)
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        if not user:
            role = 'admin' if str(tg_id) == str(MY_CHAT_ID) else 'client'
            conn.execute("INSERT OR IGNORE INTO users (tg_id, username, first_name, role, created_at) VALUES (?,?,?,?,?)",
                         (tg_id, username, first_name, role, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            return role
        return 'admin' if str(tg_id) == str(MY_CHAT_ID) else user['role']

def is_admin(tg_id):
    return str(tg_id) == str(MY_CHAT_ID)

def generate_profile_number():
    """生成唯一编号如 K49250"""
    for _ in range(20):
        num = f"K{random.randint(10000, 99999)}"
        with get_db() as conn:
            if not conn.execute("SELECT 1 FROM profiles WHERE number=?", (num,)).fetchone():
                return num
    return f"K{random.randint(100000, 999999)}"


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
    if request.headers.get('content-type') != 'application/json':
        return 'OK'
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        _process_update(update)
    except Exception as e:
        print(f"Webhook processing error: {e}")
    # 永远返回 200 OK，防止 Telegram 因重试而禁用 webhook
    return 'OK'

def _process_update(update):
    """处理单条 Telegram Update（独立函数便于测试与错误隔离）"""
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
            # 优先用 edit_message_text（文字通知），失败则尝试 edit_message_caption（媒体通知）
            try:
                bot.edit_message_text("【审核操作已完成】", MY_CHAT_ID, update.callback_query.message.message_id)
            except Exception:
                try:
                    bot.edit_message_caption("【审核操作已完成】", MY_CHAT_ID, update.callback_query.message.message_id)
                except Exception:
                    pass
        except Exception as e:
            print(f"Callback query error: {e}")
        return

    p = update.channel_post or update.message or update.edited_channel_post or update.edited_message
    if not p: return

    uid = p.from_user.id if p.from_user else None
    txt = p.text or p.caption or ""
    gid = p.media_group_id

    # 2a. /start 命令 — 三角色分流
    if txt.startswith('/start') and uid and not update.channel_post:
        role = get_or_create_user(uid,
                                  p.from_user.username or '',
                                  p.from_user.first_name or '')
        if role == 'admin':
            if BASE_URL:
                markup2 = InlineKeyboardMarkup()
                markup2.add(InlineKeyboardButton("🔧 管理员后台",
                    url=f"{BASE_URL}/admin?admin_key={ADMIN_KEY}"))
                bot.send_message(uid,
                    "👋 欢迎回来，管理员！\n\n"
                    "🔧 点击下方按钮进入 星搭 StarMatch 管理后台，可审核资料、配置表单、发布公告等。",
                    reply_markup=markup2)
            else:
                bot.send_message(uid,
                    "👋 欢迎回来，管理员！\n\n"
                    "🔧 请访问后台管理页面。")
        elif role == 'user':
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            if BASE_URL:
                markup.add(
                    KeyboardButton("📝 上传我的资料",
                                   web_app=WebAppInfo(url=f"{BASE_URL}/upload_profile")),
                    KeyboardButton("✏️ 修改我的资料",
                                   web_app=WebAppInfo(url=f"{BASE_URL}/edit_profile"))
                )
                markup.add(KeyboardButton("👁 查看我的资料"))
            else:
                markup.add(KeyboardButton("📝 上传我的资料"),
                           KeyboardButton("✏️ 修改我的资料"))
                markup.add(KeyboardButton("👁 查看我的资料"))
            bot.send_message(uid,
                "👋 欢迎！\n\n"
                "📝 请选择操作：\n"
                "• 上传资料后由管理员审核后展示\n"
                "• 审核通过前可随时修改\n\n"
                "🌟 欢迎使用 星搭 StarMatch",
                reply_markup=markup)
        else:  # client
            if BASE_URL:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🔍 进入小程序",
                    web_app=WebAppInfo(url=f"{BASE_URL}/")))
                bot.send_message(uid,
                    "👋 欢迎来到 星搭 StarMatch！\n\n点击下方按钮进入小程序，浏览所有内容 🎉",
                    reply_markup=markup)
            else:
                bot.send_message(uid,
                    "👋 欢迎来到 星搭 StarMatch！\n\n浏览所有内容 🎉")
        return

    # 2b. /help 命令
    if txt.startswith('/help') and uid and not update.channel_post:
        if BASE_URL:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔍 进入小程序", web_app=WebAppInfo(url=f"{BASE_URL}/")))
            bot.send_message(uid,
                "📖 帮助信息\n\n"
                "可用命令：\n"
                "/start — 开始使用\n"
                "/upload — 上传资料\n"
                "/help — 查看帮助\n\n"
                "点击下方按钮进入小程序 🎉",
                reply_markup=markup)
        else:
            bot.send_message(uid,
                "📖 帮助信息\n\n"
                "可用命令：\n"
                "/start — 开始使用\n"
                "/upload — 上传资料\n"
                "/help — 查看帮助")
        return

    # 2c. /upload 命令
    if txt.startswith('/upload') and uid and not update.channel_post:
        if BASE_URL:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📝 上传资料",
                web_app=WebAppInfo(url=f"{BASE_URL}/upload_profile")))
            bot.send_message(uid,
                "📝 点击下方按钮上传您的资料，审核通过后将展示在平台上。",
                reply_markup=markup)
        else:
            bot.send_message(uid, "📝 请联系管理员上传资料。")
        return

    # 2d. 用户角色：查看我的资料
    if txt == '👁 查看我的资料' and uid and not update.channel_post:
        with get_db() as conn:
            profile = conn.execute(
                "SELECT id FROM profiles WHERE tg_id=? ORDER BY id DESC LIMIT 1", (uid,)
            ).fetchone()
        if profile:
            url = f"{BASE_URL}/profile_detail/{profile['id']}"
            bot.send_message(uid, f"📋 您的资料链接：\n{url}")
        else:
            bot.send_message(uid, "❌ 您还没有上传资料。请先点击「📝 上传我的资料」")
        return

    # 2e. 管理员 /setrole 命令：/setrole <tg_id> <role>
    if txt.startswith('/setrole ') and str(uid) == str(MY_CHAT_ID):
        parts = txt[9:].strip().split()
        if len(parts) == 2:
            target_id, new_role = parts
            if new_role in ('admin', 'user', 'client'):
                with get_db() as conn:
                    conn.execute("INSERT OR IGNORE INTO users (tg_id, role, created_at) VALUES (?,?,?)",
                                 (int(target_id), new_role, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.execute("UPDATE users SET role=? WHERE tg_id=?", (new_role, int(target_id)))
                bot.send_message(MY_CHAT_ID, f"✅ 已将用户 {target_id} 的角色设为 {new_role}")
            else:
                bot.send_message(MY_CHAT_ID, "❌ 角色只能是 admin / user / client")
        else:
            bot.send_message(MY_CHAT_ID, "❌ 用法: /setrole <tg_id> <role>")
        return

    # 3. 管理员指令
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
            return

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
            return

        if txt.startswith('/notice '):
            with get_db() as conn: conn.execute("UPDATE settings SET value=? WHERE key='notice'", (txt[8:],))
            bot.send_message(MY_CHAT_ID, "✅ 公告已更新")
            return

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
            return

        if txt == '/setwebhook':
            if BASE_URL:
                try:
                    bot.remove_webhook()
                    bot.set_webhook(url=f"{BASE_URL}/webhook")
                    bot.send_message(MY_CHAT_ID, f"✅ Webhook 已重新注册：{BASE_URL}/webhook")
                except Exception as e:
                    bot.send_message(MY_CHAT_ID, f"❌ Webhook 注册失败: {e}")
            else:
                bot.send_message(MY_CHAT_ID, "❌ BASE_URL 未设置，无法注册 Webhook")
            return

        if txt == '/sync':
            bot.send_message(MY_CHAT_ID, "🔄 正在同步频道未读消息...")
            count = 0
            try:
                # 临时移除 Webhook，通过 getUpdates 获取未读消息
                bot.remove_webhook()
                time.sleep(1)
                updates = bot.get_updates(limit=100, allowed_updates=['channel_post'])
                for upd in updates:
                    h = upd.channel_post
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
            return

    # 4. 黑名单拦截
    if uid:
        with get_db() as conn:
            if conn.execute("SELECT 1 FROM blacklist WHERE user_id=?", (uid,)).fetchone(): return

    # 5. 入库处理
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

            # 6. 投稿审核提醒
            if not update.channel_post and str(uid) != str(MY_CHAT_ID):
                markup = InlineKeyboardMarkup().row(
                    InlineKeyboardButton("✅通过", callback_data=f"y_{'G'+gid if gid else new_id}"),
                    InlineKeyboardButton("❌拒绝", callback_data=f"n_{'G'+gid if gid else new_id}")
                )
                bot.send_message(MY_CHAT_ID, f"🔔 新投稿:\n{txt[:100]}", reply_markup=markup)

            # 7. 发送管理员链接
            if update.channel_post and new_id:
                admin_url = f"{BASE_URL}/post/{new_id}?admin_key={ADMIN_KEY}"
                bot.send_message(MY_CHAT_ID, f"📢 新帖子已发布！\n\n🔗 管理链接：{admin_url}")

# --- 保留旧系统路由（向后兼容）---
def _build_post_query_conditions(type_filter, sort, source=''):
    """根据类型过滤、来源过滤和排序参数构建 SQL 片段（均来自服务端枚举，非用户原始输入）。"""
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
    return type_condition, source_condition, order_clause

@app.route('/api/posts')
def api_posts():
    """JSON 接口（旧系统，保留向后兼容）"""
    q = request.args.get('q', '')
    user_id = request.args.get('user_id', 'anonymous')
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', '')
    sort = request.args.get('sort', 'latest')
    source = request.args.get('source', '')
    per_page = 20
    offset = (page - 1) * per_page
    type_condition, source_condition, order_clause = _build_post_query_conditions(type_filter, sort, source)

    with get_db() as conn:
        sql = f"""SELECT p.*, (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count
                 FROM posts p 
                 WHERE p.is_approved=1 AND p.text LIKE ? 
                 AND p.id NOT IN (SELECT post_id FROM user_blacklist WHERE user_id=?)
                 {type_condition}{source_condition}
                 GROUP BY COALESCE(p.media_group_id, p.id) 
                 ORDER BY {order_clause}
                 LIMIT ? OFFSET ?"""
        posts = conn.execute(sql, (f'%{q}%', user_id, per_page, offset)).fetchall()

        count_sql = f"""SELECT COUNT(DISTINCT COALESCE(p.media_group_id, p.id)) AS total FROM posts p 
                       WHERE p.is_approved=1 AND p.text LIKE ? 
                       AND p.id NOT IN (SELECT post_id FROM user_blacklist WHERE user_id=?)
                       {type_condition}{source_condition}"""
        total = conn.execute(count_sql, (f'%{q}%', user_id)).fetchone()['total']

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
    is_admin_view = (admin_key == ADMIN_KEY)
    
    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post: return "404", 404
        all_media = []
        if post['media_group_id']:
            rows = conn.execute("SELECT first_media FROM posts WHERE media_group_id=? AND is_approved=1 ORDER BY id ASC", (post['media_group_id'],)).fetchall()
            all_media = [r['first_media'] for r in rows]
        else:
            all_media = [post['first_media']]
        comments = conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY id DESC", (post_id,)).fetchall()
        is_favorited = conn.execute("SELECT 1 FROM user_favorites WHERE user_id=? AND post_id=?", (user_id, post_id)).fetchone() is not None
        
    return render_template('detail.html', post=post, all_media=all_media, comments=comments, 
                         is_favorited=is_favorited, user_id=user_id, is_admin=is_admin_view)

@app.route('/api/like/<int:post_id>', methods=['POST'])
def like(post_id):
    user_id = request.json.get('user_id', 'anonymous') if request.is_json else 'anonymous'
    if not check_rate_limit(f'like_{user_id}', max_requests=10, window_seconds=60):
        return jsonify({"status":"error", "message":"操作过于频繁，请稍后再试"}), 429
    with get_db() as conn: 
        conn.execute("UPDATE posts SET likes=likes+1 WHERE id=?", (post_id,))
    return jsonify({"status":"ok"})

@app.route('/api/comment/<int:post_id>', methods=['POST'])
def comment(post_id):
    content = request.json.get('content')
    user_id = request.json.get('user_id', 'anonymous')
    if not check_rate_limit(f'comment_{user_id}', max_requests=5, window_seconds=60):
        return jsonify({"status":"error", "message":"评论过于频繁，请稍后再试"}), 429
    if content:
        content = html.escape(content)
        date_str = datetime.now().strftime("%m-%d %H:%M")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO comments (post_id, content, date, user_id) VALUES (?,?,?,?)",
                           (post_id, content, date_str, user_id))
            new_id = cursor.lastrowid
        return jsonify({"status": "ok", "id": new_id, "date": date_str})
    return jsonify({"status":"ok"})

@app.route('/api/blacklist/<int:post_id>', methods=['POST'])
def blacklist_user(post_id):
    user_id = request.json.get('user_id', 'anonymous')
    with get_db() as conn:
        existing = conn.execute("SELECT 1 FROM user_blacklist WHERE user_id=? AND post_id=?", (user_id, post_id)).fetchone()
        if not existing:
            conn.execute("INSERT INTO user_blacklist (user_id, post_id, date) VALUES (?,?,?)", (user_id, post_id, datetime.now().strftime("%Y-%m-%d")))
            conn.execute("UPDATE posts SET blacklist_count=blacklist_count+1 WHERE id=?", (post_id,))
    return jsonify({"status":"ok"})

@app.route('/api/favorite/<int:post_id>', methods=['POST', 'DELETE'])
def toggle_favorite(post_id):
    user_id = request.json.get('user_id', 'anonymous')
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

@app.route('/upload')
def upload_guide():
    user_id = request.args.get('user_id', 'anonymous')
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
    return render_template('upload.html', user_id=user_id, notice=notice['value'] if notice else "")

@app.route('/my_profile')
def my_profile():
    user_id = request.args.get('user_id', 'anonymous')
    with get_db() as conn:
        favorites = conn.execute("""
            SELECT p.* FROM posts p 
            JOIN user_favorites f ON p.id = f.post_id 
            WHERE f.user_id = ? ORDER BY f.date DESC LIMIT 10
        """, (user_id,)).fetchall()
        comments = conn.execute("""
            SELECT c.*, p.id as post_id, p.text as post_text 
            FROM comments c 
            JOIN posts p ON c.post_id = p.id 
            WHERE c.user_id = ? ORDER BY c.id DESC LIMIT 10
        """, (user_id,)).fetchall()
    return render_template('profile.html', favorites=favorites, comments=comments, user_id=user_id)

@app.route('/api/admin/description/<int:post_id>', methods=['POST'])
def update_description(post_id):
    admin_key = request.json.get('admin_key', '')
    if admin_key != ADMIN_KEY:
        return jsonify({"status":"error", "message":"权限不足"}), 403
    description = request.json.get('description', '')
    with get_db() as conn:
        conn.execute("UPDATE posts SET custom_description=? WHERE id=?", (description, post_id))
    return jsonify({"status":"ok"})

@app.route('/api/admin/post/<int:post_id>', methods=['DELETE'])
def delete_post(post_id):
    admin_key = request.json.get('admin_key', '')
    if admin_key != ADMIN_KEY:
        return jsonify({"status":"error", "message":"权限不足"}), 403
    with get_db() as conn:
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

# ============================================================
# 新系统：Profiles 路由
# ============================================================

def _check_admin_auth():
    """检查管理员权限：支持 admin_key 或 tg_id"""
    data = request.json or {}
    if data.get('admin_key') == ADMIN_KEY or request.args.get('admin_key') == ADMIN_KEY:
        return True
    tg_id = get_tg_id_from_request()
    return tg_id and is_admin(tg_id)

@app.route('/api/register', methods=['POST'])
def api_register():
    """Mini App 登录/注册，验证 initData"""
    data = request.json or {}
    init_data = data.get('initData', '')
    user_info = verify_init_data(init_data) if init_data else None

    # fallback: 开发模式直接传 tg_id
    if not user_info:
        tg_id_raw = data.get('tg_id')
        if not tg_id_raw:
            return jsonify({"status": "error", "message": "验证失败"}), 401
        user_info = {'id': int(tg_id_raw), 'first_name': data.get('first_name', ''), 'username': data.get('username', '')}

    tg_id = user_info.get('id')
    role = get_or_create_user(tg_id, user_info.get('username', ''), user_info.get('first_name', ''))
    return jsonify({"status": "ok", "tg_id": tg_id, "role": role,
                    "first_name": user_info.get('first_name', ''),
                    "username": user_info.get('username', '')})

@app.route('/api/profiles')
def api_profiles():
    """资料列表（支持分类/地区/搜索/价格排序）"""
    q = request.args.get('q', '')
    category = request.args.get('category', '')
    region = request.args.get('region', '')
    sort = request.args.get('sort', 'latest')  # latest | price_asc | price_desc
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    conditions = ["p.is_approved=1"]
    params = []
    if q:
        conditions.append("(p.name LIKE ? OR p.number LIKE ? OR p.description LIKE ?)")
        params += [f'%{q}%', f'%{q}%', f'%{q}%']
    if category and category != '全部':
        conditions.append("p.category=?")
        params.append(category)
    if region:
        conditions.append("p.region=?")
        params.append(region)

    where = " AND ".join(conditions)
    if sort == 'price_asc':
        order = "p.price ASC"
    elif sort == 'price_desc':
        order = "p.price DESC"
    else:
        order = "p.id DESC"

    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM profiles p WHERE {where}", params).fetchone()[0]
        rows = conn.execute(f"SELECT * FROM profiles p WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                            params + [per_page, offset]).fetchall()

    profiles_data = []
    for r in rows:
        d = dict(r)
        try: d['photos'] = json.loads(d['photos'] or '[]')
        except: d['photos'] = []
        try: d['tags'] = json.loads(d['tags'] or '[]')
        except: d['tags'] = []
        profiles_data.append(d)

    total_pages = (total + per_page - 1) // per_page
    return jsonify({'profiles': profiles_data, 'total': total,
                    'total_pages': total_pages, 'page': page,
                    'has_more': page < total_pages})

@app.route('/api/profile/<int:profile_id>')
def api_profile_detail(profile_id):
    """单个资料详情"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
    if not row:
        return jsonify({"status": "error", "message": "not found"}), 404
    d = dict(row)
    try: d['photos'] = json.loads(d['photos'] or '[]')
    except: d['photos'] = []
    try: d['tags'] = json.loads(d['tags'] or '[]')
    except: d['tags'] = []
    return jsonify(d)

@app.route('/api/profile', methods=['POST'])
def api_create_profile():
    """用户提交新资料"""
    data = request.json or {}
    tg_id = get_tg_id_from_request()
    if not tg_id:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    # 黑名单检查
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM blacklist WHERE user_id=?", (int(tg_id),)).fetchone():
            return jsonify({"status": "error", "message": "您已被限制使用本服务"}), 403

    # 检查是否已有资料（一个用户一条）
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM profiles WHERE tg_id=?", (int(tg_id),)).fetchone()
        if existing:
            return jsonify({"status": "error", "message": "已有资料，请使用修改接口", "profile_id": existing['id']}), 409

    name = html.escape(data.get('name', '').strip())
    if not name:
        return jsonify({"status": "error", "message": "姓名不能为空"}), 400

    number = generate_profile_number()
    tags = json.dumps(data.get('tags', []))
    photos = json.dumps(data.get('photos', []))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO profiles
            (tg_id, name, number, region, district, price, tags, category, contact, description, photos, is_approved, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?)""",
            (int(tg_id), name, number,
             html.escape(data.get('region', '')),
             html.escape(data.get('district', '')),
             int(data.get('price', 0)),
             tags,
             data.get('category', '个人'),
             html.escape(data.get('contact', '')),
             html.escape(data.get('description', '')),
             photos, now_str, now_str))
        new_id = cursor.lastrowid

    # 通知管理员审核
    if MY_CHAT_ID:
        admin_url = f"{BASE_URL}/admin?admin_key={ADMIN_KEY}" if BASE_URL else f"/admin?admin_key={ADMIN_KEY}"
        try:
            bot.send_message(int(MY_CHAT_ID),
                f"🔔 新资料待审核\n\n"
                f"姓名: {name}\n编号: {number}\n"
                f"分类: {data.get('category','个人')}\n"
                f"价格: {data.get('price',0)}P\n"
                f"地区: {data.get('region','')}\n\n"
                f"🔗 后台: {admin_url}")
        except: pass

    return jsonify({"status": "ok", "profile_id": new_id, "number": number})

@app.route('/api/profile/<int:profile_id>', methods=['PUT'])
def api_update_profile(profile_id):
    """用户修改自己的资料"""
    data = request.json or {}
    tg_id = get_tg_id_from_request()
    if not tg_id:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    # 黑名单检查
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM blacklist WHERE user_id=?", (int(tg_id),)).fetchone():
            return jsonify({"status": "error", "message": "您已被限制使用本服务"}), 403

    with get_db() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
    if not row:
        return jsonify({"status": "error", "message": "资料不存在"}), 404
    if str(row['tg_id']) != str(tg_id) and not is_admin(tg_id):
        return jsonify({"status": "error", "message": "无权限"}), 403

    tags = json.dumps(data.get('tags', json.loads(row['tags'] or '[]')))
    photos = json.dumps(data.get('photos', json.loads(row['photos'] or '[]')))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        conn.execute("""UPDATE profiles SET
            name=?, region=?, district=?, price=?, tags=?,
            category=?, contact=?, description=?, photos=?,
            is_approved=0, updated_at=?
            WHERE id=?""",
            (html.escape(data.get('name', row['name'])),
             html.escape(data.get('region', row['region'] or '')),
             html.escape(data.get('district', row['district'] or '')),
             int(data.get('price', row['price'] or 0)),
             tags,
             data.get('category', row['category'] or '个人'),
             html.escape(data.get('contact', row['contact'] or '')),
             html.escape(data.get('description', row['description'] or '')),
             photos, now_str, profile_id))

    # 重新提交审核通知
    if MY_CHAT_ID:
        try:
            admin_url = f"{BASE_URL}/admin?admin_key={ADMIN_KEY}" if BASE_URL else f"/admin?admin_key={ADMIN_KEY}"
            bot.send_message(int(MY_CHAT_ID),
                f"✏️ 资料已修改，待重新审核\n\n"
                f"编号: {row['number']}\n🔗 {admin_url}")
        except: pass

    return jsonify({"status": "ok"})

@app.route('/api/profile/upload_photo', methods=['POST'])
def api_upload_photo():
    """上传资料图片"""
    tg_id = get_tg_id_from_request()
    if not tg_id:
        return jsonify({"status": "error", "message": "请先登录"}), 401
    if 'photo' not in request.files:
        return jsonify({"status": "error", "message": "没有文件"}), 400

    f = request.files['photo']
    allowed = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    # Use secure_filename then extract extension to avoid path injection
    from werkzeug.utils import secure_filename as _sfn
    safe_name = _sfn(f.filename or 'upload')
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in allowed:
        return jsonify({"status": "error", "message": "不支持的文件格式"}), 400

    # Use uuid for filename — no user-provided data in path
    filename = f"profile_{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)
    f.save(save_path)
    return jsonify({"status": "ok", "url": f"/uploads/{filename}"})

# --- 管理员 API ---

@app.route('/api/admin/profiles')
def api_admin_profiles():
    """管理员查看所有资料（含待审核）"""
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    status = request.args.get('status', 'pending')  # pending | approved | rejected | all
    page = request.args.get('page', 1, type=int)
    per_page = 20

    if status == 'pending':
        cond, params = "is_approved=0", []
    elif status == 'approved':
        cond, params = "is_approved=1", []
    elif status == 'rejected':
        cond, params = "is_approved=2", []
    else:
        cond, params = "1=1", []

    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM profiles WHERE {cond}", params).fetchone()[0]
        rows = conn.execute(f"SELECT * FROM profiles WHERE {cond} ORDER BY id DESC LIMIT ? OFFSET ?",
                            params + [per_page, (page-1)*per_page]).fetchall()

    profiles_data = []
    for r in rows:
        d = dict(r)
        try: d['photos'] = json.loads(d['photos'] or '[]')
        except: d['photos'] = []
        try: d['tags'] = json.loads(d['tags'] or '[]')
        except: d['tags'] = []
        profiles_data.append(d)

    return jsonify({'profiles': profiles_data, 'total': total, 'page': page,
                    'total_pages': (total + per_page - 1) // per_page})

@app.route('/api/admin/approve/<int:profile_id>', methods=['POST'])
def api_admin_approve(profile_id):
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    with get_db() as conn:
        conn.execute("UPDATE profiles SET is_approved=1 WHERE id=?", (profile_id,))
        row = conn.execute("SELECT tg_id, name, number FROM profiles WHERE id=?", (profile_id,)).fetchone()
    # 通知用户
    if row and row['tg_id']:
        try:
            url = f"{BASE_URL}/profile_detail/{profile_id}" if BASE_URL else f"/profile_detail/{profile_id}"
            bot.send_message(row['tg_id'],
                f"✅ 您的资料「{row['name']}（{row['number']}）」已通过审核！\n\n🔗 {url}")
        except: pass
    return jsonify({"status": "ok"})

@app.route('/api/admin/reject/<int:profile_id>', methods=['POST'])
def api_admin_reject(profile_id):
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    data = request.json or {}
    reason = html.escape(data.get('reason', '不符合要求'))
    with get_db() as conn:
        conn.execute("UPDATE profiles SET is_approved=2 WHERE id=?", (profile_id,))
        row = conn.execute("SELECT tg_id, name, number FROM profiles WHERE id=?", (profile_id,)).fetchone()
    if row and row['tg_id']:
        try:
            bot.send_message(row['tg_id'],
                f"❌ 您的资料「{row['name']}（{row['number']}）」未通过审核。\n原因: {reason}\n\n请修改后重新提交。")
        except: pass
    return jsonify({"status": "ok"})

@app.route('/api/admin/verify/<int:profile_id>', methods=['POST'])
def api_admin_verify(profile_id):
    """切换认证标志"""
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    with get_db() as conn:
        row = conn.execute("SELECT is_verified FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "不存在"}), 404
        new_val = 0 if row['is_verified'] else 1
        conn.execute("UPDATE profiles SET is_verified=? WHERE id=?", (new_val, profile_id))
    return jsonify({"status": "ok", "is_verified": new_val})

@app.route('/api/admin/delete_profile/<int:profile_id>', methods=['DELETE'])
def api_admin_delete_profile(profile_id):
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    with get_db() as conn:
        conn.execute("DELETE FROM profile_favorites WHERE profile_id=?", (profile_id,))
        conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
    return jsonify({"status": "ok"})

@app.route('/api/admin/settings', methods=['GET', 'POST'])
def api_admin_settings():
    if request.method == 'GET':
        with get_db() as conn:
            form_fields = conn.execute("SELECT value FROM settings WHERE key='form_fields'").fetchone()
            nav_tabs = conn.execute("SELECT value FROM settings WHERE key='nav_tabs'").fetchone()
            notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
            app_name = conn.execute("SELECT value FROM settings WHERE key='app_name'").fetchone()
            price_unit = conn.execute("SELECT value FROM settings WHERE key='price_unit'").fetchone()
            verify_desc = conn.execute("SELECT value FROM settings WHERE key='verify_description'").fetchone()
            admin_contact = conn.execute("SELECT value FROM settings WHERE key='admin_contact'").fetchone()
        return jsonify({
            "form_fields": json.loads(form_fields['value']) if form_fields else {},
            "nav_tabs": json.loads(nav_tabs['value']) if nav_tabs else [],
            "notice": notice['value'] if notice else '',
            "app_name": app_name['value'] if app_name else '星搭 StarMatch',
            "price_unit": price_unit['value'] if price_unit else 'P',
            "verify_description": verify_desc['value'] if verify_desc else '',
            "admin_contact": admin_contact['value'] if admin_contact else '',
        })
    # POST
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    data = request.json or {}
    with get_db() as conn:
        if 'form_fields' in data:
            # Merge with existing fields instead of replace
            existing = conn.execute("SELECT value FROM settings WHERE key='form_fields'").fetchone()
            merged = json.loads(existing['value']) if existing else {}
            merged.update(data['form_fields'])
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('form_fields', ?)",
                         (json.dumps(merged),))
        if 'nav_tabs' in data:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('nav_tabs', ?)",
                         (json.dumps(data['nav_tabs']),))
        if 'notice' in data:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('notice', ?)",
                         (html.escape(data['notice']),))
        if 'verify_description' in data:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('verify_description', ?)",
                         (html.escape(data['verify_description']),))
        if 'app_name' in data:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('app_name', ?)",
                         (html.escape(data['app_name']),))
        if 'price_unit' in data:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('price_unit', ?)",
                         (html.escape(data['price_unit']),))
        if 'admin_contact' in data:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_contact', ?)",
                         (html.escape(data['admin_contact']),))
    return jsonify({"status": "ok"})

@app.route('/api/admin/announcement', methods=['POST'])
def api_admin_announcement():
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    data = request.json or {}
    content = html.escape(data.get('content', '').strip())
    if not content:
        return jsonify({"status": "error", "message": "内容不能为空"}), 400
    # 关闭旧公告
    with get_db() as conn:
        conn.execute("UPDATE announcements SET is_active=0")
        conn.execute("INSERT INTO announcements (content, is_active, created_at) VALUES (?,1,?)",
                     (content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        # 同步更新 settings notice
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('notice', ?)", (content,))
    return jsonify({"status": "ok"})

@app.route('/api/admin/users')
def api_admin_users():
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 200").fetchall()
    return jsonify({"users": [dict(r) for r in rows]})

@app.route('/api/admin/user/<int:tg_id>/role', methods=['PUT'])
def api_admin_set_role(tg_id):
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    data = request.json or {}
    new_role = data.get('role', '')
    if new_role not in ('admin', 'user', 'client'):
        return jsonify({"status": "error", "message": "无效角色"}), 400
    with get_db() as conn:
        conn.execute("UPDATE users SET role=? WHERE tg_id=?", (new_role, tg_id))
    return jsonify({"status": "ok"})

# Alias: DELETE /api/admin/profile/<id> (used by admin panel JS)
@app.route('/api/admin/profile/<int:profile_id>', methods=['DELETE'])
def api_admin_delete_profile_alias(profile_id):
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    data = request.json or {}
    blacklist_uploader = data.get('blacklist', False)
    with get_db() as conn:
        if blacklist_uploader:
            row = conn.execute("SELECT tg_id FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if row and row['tg_id']:
                conn.execute("INSERT OR IGNORE INTO blacklist (user_id, date) VALUES (?,?)",
                             (row['tg_id'], datetime.now().strftime("%Y-%m-%d")))
        conn.execute("DELETE FROM profile_favorites WHERE profile_id=?", (profile_id,))
        conn.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
    return jsonify({"status": "ok"})

# POST /api/admin/set_role (used by admin panel JS)
@app.route('/api/admin/set_role', methods=['POST'])
def api_admin_set_role_post():
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    data = request.json or {}
    target = str(data.get('target_tg_id', ''))
    new_role = data.get('role', '')
    if new_role not in ('admin', 'user', 'client'):
        return jsonify({"status": "error", "message": "无效角色"}), 400
    with get_db() as conn:
        conn.execute("UPDATE users SET role=? WHERE tg_id=?", (new_role, target))
    return jsonify({"status": "ok"})

# GET/POST /api/admin/nav — nav tabs management
@app.route('/api/admin/nav', methods=['GET', 'POST'])
def api_admin_nav():
    if request.method == 'GET':
        with get_db() as conn:
            nav_tabs = conn.execute("SELECT value FROM settings WHERE key='nav_tabs'").fetchone()
        return jsonify({"nav_tabs": json.loads(nav_tabs['value']) if nav_tabs else []})
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    data = request.json or {}
    tabs = data.get('nav_tabs', [])
    if not isinstance(tabs, list):
        return jsonify({"status": "error", "message": "格式错误"}), 400
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('nav_tabs', ?)", (json.dumps(tabs),))
    return jsonify({"status": "ok"})

# POST /api/admin/pin/<profile_id> — 设置置顶类型
@app.route('/api/admin/pin/<int:profile_id>', methods=['POST'])
def api_admin_set_pin(profile_id):
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    data = request.json or {}
    pin_type = int(data.get('pin_type', 0))
    if pin_type not in (0, 1, 2):
        return jsonify({"status": "error", "message": "无效置顶类型"}), 400
    with get_db() as conn:
        conn.execute("UPDATE profiles SET pin_type=? WHERE id=?", (pin_type, profile_id))
    return jsonify({"status": "ok", "pin_type": pin_type})

# GET /api/admin/blacklisted_users — 黑名单用户列表
@app.route('/api/admin/blacklisted_users')
def api_admin_blacklisted_users():
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    with get_db() as conn:
        rows = conn.execute("""
            SELECT b.user_id, b.date,
                   u.username, u.first_name
            FROM blacklist b
            LEFT JOIN users u ON b.user_id = u.tg_id
            ORDER BY b.date DESC
        """).fetchall()
    return jsonify({"users": [dict(r) for r in rows]})

# POST /api/admin/blacklist_user — 拉黑用户
@app.route('/api/admin/blacklist_user', methods=['POST'])
def api_admin_blacklist_user():
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    data = request.json or {}
    tg_id = data.get('tg_id')
    if not tg_id:
        return jsonify({"status": "error", "message": "缺少 tg_id"}), 400
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO blacklist (user_id, date) VALUES (?,?)",
                     (int(tg_id), datetime.now().strftime("%Y-%m-%d")))
    return jsonify({"status": "ok"})

# DELETE /api/admin/blacklist_user/<tg_id> — 移出黑名单
@app.route('/api/admin/blacklist_user/<int:tg_id>', methods=['DELETE'])
def api_admin_unblacklist_user(tg_id):
    if not _check_admin_auth():
        return jsonify({"status": "error", "message": "无权限"}), 403
    with get_db() as conn:
        conn.execute("DELETE FROM blacklist WHERE user_id=?", (tg_id,))
    return jsonify({"status": "ok"})

# --- 资料收藏 ---

@app.route('/api/profile_favorite/<int:profile_id>', methods=['POST', 'DELETE'])
def toggle_profile_favorite(profile_id):
    tg_id = get_tg_id_from_request()
    if not tg_id:
        tg_id = (request.json or {}).get('tg_id', 'anon')
    with get_db() as conn:
        existing = conn.execute("SELECT 1 FROM profile_favorites WHERE user_tg_id=? AND profile_id=?",
                                (str(tg_id), profile_id)).fetchone()
        if request.method == 'POST' and not existing:
            conn.execute("INSERT INTO profile_favorites (user_tg_id, profile_id, date) VALUES (?,?,?)",
                         (str(tg_id), profile_id, datetime.now().strftime("%Y-%m-%d")))
            return jsonify({"status": "ok", "favorited": True})
        elif request.method == 'DELETE' and existing:
            conn.execute("DELETE FROM profile_favorites WHERE user_tg_id=? AND profile_id=?",
                         (str(tg_id), profile_id))
            return jsonify({"status": "ok", "favorited": False})
    return jsonify({"status": "ok"})

@app.route('/api/profile_favorites')
def api_profile_favorites():
    tg_id = request.args.get('tg_id', 'anon')
    with get_db() as conn:
        rows = conn.execute("""
            SELECT p.* FROM profiles p
            JOIN profile_favorites f ON p.id = f.profile_id
            WHERE f.user_tg_id=? ORDER BY f.date DESC
        """, (str(tg_id),)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try: d['photos'] = json.loads(d['photos'] or '[]')
        except: d['photos'] = []
        try: d['tags'] = json.loads(d['tags'] or '[]')
        except: d['tags'] = []
        result.append(d)
    return jsonify(result)

# --- 新页面路由 ---

@app.route('/profile_detail/<int:profile_id>')
def profile_detail(profile_id):
    tg_id = request.args.get('tg_id', '')
    with get_db() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id=? AND is_approved=1", (profile_id,)).fetchone()
        if not row:
            return "资料不存在或未审核", 404
        is_fav = False
        if tg_id:
            is_fav = conn.execute(
                "SELECT 1 FROM profile_favorites WHERE user_tg_id=? AND profile_id=?",
                (str(tg_id), profile_id)).fetchone() is not None
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
    d = dict(row)
    try: d['photos'] = json.loads(d['photos'] or '[]')
    except: d['photos'] = []
    try: d['tags'] = json.loads(d['tags'] or '[]')
    except: d['tags'] = []
    return render_template('profile_detail.html', profile=d, is_fav=is_fav, tg_id=tg_id,
                           notice=notice['value'] if notice else '')

@app.route('/upload_profile')
def upload_profile_page():
    tg_id = request.args.get('tg_id', '')
    with get_db() as conn:
        form_fields_row = conn.execute("SELECT value FROM settings WHERE key='form_fields'").fetchone()
        nav_tabs_row = conn.execute("SELECT value FROM settings WHERE key='nav_tabs'").fetchone()
        admin_contact_row = conn.execute("SELECT value FROM settings WHERE key='admin_contact'").fetchone()
    form_fields = json.loads(form_fields_row['value']) if form_fields_row else {}
    nav_tabs = json.loads(nav_tabs_row['value']) if nav_tabs_row else ["全部","中圈","大圈","个人"]
    categories = [t for t in nav_tabs if t != '全部']
    if not categories:
        categories = ["中圈", "大圈", "个人"]
    admin_contact = admin_contact_row['value'] if admin_contact_row else ''
    return render_template('upload_profile.html', tg_id=tg_id, form_fields=form_fields, categories=categories, admin_contact=admin_contact)

@app.route('/edit_profile')
def edit_profile_page():
    tg_id = request.args.get('tg_id', '')
    profile = None
    if tg_id:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE tg_id=? ORDER BY id DESC LIMIT 1",
                               (int(tg_id),)).fetchone()
            if row:
                profile = dict(row)
                try: profile['photos'] = json.loads(profile['photos'] or '[]')
                except: profile['photos'] = []
                try: profile['tags'] = json.loads(profile['tags'] or '[]')
                except: profile['tags'] = []
    with get_db() as conn:
        form_fields_row = conn.execute("SELECT value FROM settings WHERE key='form_fields'").fetchone()
        nav_tabs_row = conn.execute("SELECT value FROM settings WHERE key='nav_tabs'").fetchone()
        admin_contact_row = conn.execute("SELECT value FROM settings WHERE key='admin_contact'").fetchone()
    form_fields = json.loads(form_fields_row['value']) if form_fields_row else {}
    nav_tabs = json.loads(nav_tabs_row['value']) if nav_tabs_row else ["全部","中圈","大圈","个人"]
    categories = [t for t in nav_tabs if t != '全部']
    if not categories:
        categories = ["中圈", "大圈", "个人"]
    admin_contact = admin_contact_row['value'] if admin_contact_row else ''
    return render_template('upload_profile.html', tg_id=tg_id, form_fields=form_fields,
                           categories=categories, profile=profile, is_edit=True, admin_contact=admin_contact)

@app.route('/admin')
def admin_panel():
    admin_key = request.args.get('admin_key', '')
    tg_id = request.args.get('tg_id', '')
    if admin_key != ADMIN_KEY and not is_admin(tg_id):
        return "无权限", 403
    return render_template('admin_panel.html', admin_key=ADMIN_KEY, tg_id=tg_id)

# --- 更新首页路由使用 profiles ---

@app.route('/')
def index():
    q = request.args.get('q', '')
    tg_id = request.args.get('tg_id', 'anon')
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    region = request.args.get('region', '')
    sort = request.args.get('sort', 'latest')
    per_page = 20
    offset = (page - 1) * per_page

    conditions = ["p.is_approved=1"]
    params = []
    if q:
        conditions.append("(p.name LIKE ? OR p.number LIKE ? OR p.description LIKE ?)")
        params += [f'%{q}%', f'%{q}%', f'%{q}%']
    if category and category != '全部':
        conditions.append("p.category=?")
        params.append(category)
    if region:
        conditions.append("p.region=?")
        params.append(region)
    where = " AND ".join(conditions)
    order = "p.price ASC" if sort == 'price_asc' else ("p.price DESC" if sort == 'price_desc' else "p.id DESC")

    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        nav_tabs_row = conn.execute("SELECT value FROM settings WHERE key='nav_tabs'").fetchone()
        app_name_row = conn.execute("SELECT value FROM settings WHERE key='app_name'").fetchone()

        # 置顶逻辑 (仅第一页)
        pinned_profiles = []
        pinned_ids = []
        if page == 1:
            perm_pins = conn.execute(
                f"SELECT * FROM profiles p WHERE {where} AND p.pin_type=1 ORDER BY p.id DESC", params
            ).fetchall()
            rot_pin = conn.execute(
                f"SELECT * FROM profiles p WHERE {where} AND p.pin_type=2 ORDER BY RANDOM() LIMIT 1", params
            ).fetchone()
            raw_pinned = list(perm_pins) + ([rot_pin] if rot_pin else [])
            for r in raw_pinned:
                d = dict(r)
                try: d['photos'] = json.loads(d['photos'] or '[]')
                except: d['photos'] = []
                try: d['tags'] = json.loads(d['tags'] or '[]')
                except: d['tags'] = []
                pinned_profiles.append(d)
            pinned_ids = [d['id'] for d in pinned_profiles]

        # 普通资料（排除已置顶）
        excl = ""
        excl_params = list(params)
        if pinned_ids:
            placeholders = ','.join('?' * len(pinned_ids))
            excl = f" AND p.id NOT IN ({placeholders})"
            excl_params += pinned_ids

        total = conn.execute(
            f"SELECT COUNT(*) FROM profiles p WHERE {where}{excl}", excl_params
        ).fetchone()[0]
        profiles = conn.execute(
            f"SELECT * FROM profiles p WHERE {where}{excl} ORDER BY {order} LIMIT ? OFFSET ?",
            excl_params + [per_page, offset]
        ).fetchall()
        regions = conn.execute(
            "SELECT DISTINCT region FROM profiles WHERE is_approved=1 AND region!='' ORDER BY region"
        ).fetchall()

    app_name = app_name_row['value'] if app_name_row else '星搭 StarMatch'
    nav_tabs = json.loads(nav_tabs_row['value']) if nav_tabs_row else ["全部","中圈","大圈","个人"]
    profiles_list = []
    for r in profiles:
        d = dict(r)
        try: d['photos'] = json.loads(d['photos'] or '[]')
        except: d['photos'] = []
        try: d['tags'] = json.loads(d['tags'] or '[]')
        except: d['tags'] = []
        profiles_list.append(d)

    return render_template('index.html',
                           profiles=profiles_list,
                           pinned_profiles=pinned_profiles,
                           notice=notice['value'] if notice else '',
                           q=q, tg_id=tg_id, page=page,
                           total_pages=(total + per_page - 1) // per_page,
                           category=category, region=region, sort=sort,
                           nav_tabs=nav_tabs,
                           regions=[r['region'] for r in regions],
                           app_name=app_name)

@app.route('/api/index_profiles')
def api_index_profiles():
    """首页无限滚动 JSON 接口"""
    q = request.args.get('q', '')
    tg_id = request.args.get('tg_id', 'anon')
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    region = request.args.get('region', '')
    sort = request.args.get('sort', 'latest')
    per_page = 20

    conditions = ["p.is_approved=1"]
    params = []
    if q:
        conditions.append("(p.name LIKE ? OR p.number LIKE ? OR p.description LIKE ?)")
        params += [f'%{q}%', f'%{q}%', f'%{q}%']
    if category and category != '全部':
        conditions.append("p.category=?")
        params.append(category)
    if region:
        conditions.append("p.region=?")
        params.append(region)
    where = " AND ".join(conditions)
    order = "p.price ASC" if sort == 'price_asc' else ("p.price DESC" if sort == 'price_desc' else "p.id DESC")

    with get_db() as conn:
        # 置顶逻辑 (仅第一页)
        pinned_ids = []
        if page == 1:
            perm_pins = conn.execute(
                f"SELECT id FROM profiles p WHERE {where} AND p.pin_type=1", params
            ).fetchall()
            rot_pin = conn.execute(
                f"SELECT id FROM profiles p WHERE {where} AND p.pin_type=2 ORDER BY RANDOM() LIMIT 1", params
            ).fetchone()
            pinned_ids = [r['id'] for r in perm_pins]
            if rot_pin:
                pinned_ids.append(rot_pin['id'])

        excl = ""
        excl_params = list(params)
        if pinned_ids:
            placeholders = ','.join('?' * len(pinned_ids))
            excl = f" AND p.id NOT IN ({placeholders})"
            excl_params += pinned_ids

        total = conn.execute(
            f"SELECT COUNT(*) FROM profiles p WHERE {where}{excl}", excl_params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM profiles p WHERE {where}{excl} ORDER BY {order} LIMIT ? OFFSET ?",
            excl_params + [per_page, (page-1)*per_page]
        ).fetchall()

    profiles_data = []
    for r in rows:
        d = dict(r)
        try: d['photos'] = json.loads(d['photos'] or '[]')
        except: d['photos'] = []
        try: d['tags'] = json.loads(d['tags'] or '[]')
        except: d['tags'] = []
        profiles_data.append(d)

    total_pages = (total + per_page - 1) // per_page
    return jsonify({'profiles': profiles_data, 'total': total,
                    'total_pages': total_pages, 'page': page,
                    'has_more': page < total_pages})

@app.route('/favorites')
def favorites_page():
    tg_id = request.args.get('tg_id', request.args.get('user_id', 'anon'))
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        rows = conn.execute("""
            SELECT p.* FROM profiles p
            JOIN profile_favorites f ON p.id = f.profile_id
            WHERE f.user_tg_id=? ORDER BY f.date DESC
        """, (str(tg_id),)).fetchall()
    profiles_list = []
    for r in rows:
        d = dict(r)
        try: d['photos'] = json.loads(d['photos'] or '[]')
        except: d['photos'] = []
        try: d['tags'] = json.loads(d['tags'] or '[]')
        except: d['tags'] = []
        profiles_list.append(d)
    return render_template('favorites.html', profiles=profiles_list,
                           notice=notice['value'] if notice else '', tg_id=tg_id)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))