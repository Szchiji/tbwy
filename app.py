import os
import sqlite3
import datetime
import requests
import cv2
from flask import Flask, render_template, request, send_from_directory, jsonify
import telebot
from telebot import types

# --- 核心配置 ---
TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "") 
MY_CHAT_ID = os.getenv("MY_CHAT_ID", "")   
BASE_URL = os.getenv("BASE_URL", "").rstrip('/') 

app = Flask(__name__)
bot = telebot.TeleBot(TOKEN, threaded=False)

# 路径设置 (Volume 挂载点)
DATA_DIR = "/app/data" if os.path.exists("/app/data") else "data"
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "data.db")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """ 
    初始化数据库并处理自动迁移。
    如果缺少某些列，程序会自动尝试 ALTER TABLE 补齐。
    """
    conn = get_db()
    # 1. 创建基础表（如果不存在）
    conn.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_msg_id INTEGER,
        media_group_id TEXT,
        content TEXT,
        file_path TEXT,
        file_type TEXT,
        thumb_url TEXT,
        is_approved INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # 2. 动态检查并补齐缺失的列
    cursor = conn.execute("PRAGMA table_info(posts)")
    existing_columns = [column[1] for column in cursor.fetchall()]
    
    # 需要检查的所有新列及其默认值定义
    required_columns = {
        'is_approved': "INTEGER DEFAULT 1",
        'media_group_id': "TEXT",
        'thumb_url': "TEXT",
        'created_at': "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'tg_msg_id': "INTEGER"
    }
    
    for col, definition in required_columns.items():
        if col not in existing_columns:
            print(f"Migrating database: Adding column {col}")
            try:
                conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {definition}")
            except Exception as e:
                print(f"Migration error on {col}: {e}")
        
    conn.commit()
    conn.close()

# 执行数据库初始化
init_db()

# --- 辅助工具 ---

def generate_thumb(video_path):
    """ 生成视频缩略图 """
    thumb_name = "thumb_" + os.path.basename(video_path).rsplit('.', 1)[0] + ".jpg"
    thumb_path = os.path.join(UPLOAD_FOLDER, thumb_name)
    if os.path.exists(thumb_path):
        return thumb_name
    
    try:
        cap = cv2.VideoCapture(video_path)
        success, frame = cap.read()
        if success:
            cv2.imwrite(thumb_path, frame)
            cap.release()
            return thumb_name
    except Exception as e:
        print(f"Thumbnail error: {e}")
    return None

def download_tg_file(file_id, custom_name=None):
    """ 下载 Telegram 文件 """
    try:
        file_info = bot.get_file(file_id)
        ext = file_info.file_path.split('.')[-1]
        filename = custom_name if custom_name else f"{file_id}.{ext}"
        local_path = os.path.join(UPLOAD_FOLDER, filename)
        
        if not os.path.exists(local_path):
            downloaded_file = bot.download_file(file_info.file_path)
            with open(local_path, 'wb') as f:
                f.write(downloaded_file)
        return filename
    except Exception as e:
        print(f"Download error: {e}")
        return None

# --- Bot 交互逻辑 ---

@bot.message_handler(commands=['sync'])
def sync_history(message):
    """ 管理员手动同步最近记录 """
    if str(message.chat.id) != str(MY_CHAT_ID): return
    
    bot.reply_to(message, "🔄 正在从频道同步最近 50 条消息...")
    try:
        history = bot.get_chat_history(CHANNEL_ID, limit=50)
        conn = get_db()
        
        for msg in history:
            exists = conn.execute("SELECT id FROM posts WHERE tg_msg_id = ?", (msg.message_id,)).fetchone()
            if exists: continue
            
            content = msg.caption or msg.text or ""
            file_id, file_type = None, None
            
            if msg.photo:
                file_id, file_type = msg.photo[-1].file_id, "image"
            elif msg.video:
                file_id, file_type = msg.video.file_id, "video"
                
            if file_id:
                fname = download_tg_file(file_id)
                thumb = generate_thumb(os.path.join(UPLOAD_FOLDER, fname)) if file_type == "video" else None
                conn.execute("INSERT INTO posts (tg_msg_id, content, file_path, file_type, thumb_url, is_approved) VALUES (?,?,?,?,?,?)",
                             (msg.message_id, content, fname, file_type, thumb, 1))
        
        conn.commit()
        conn.close()
        bot.reply_to(message, "✅ 同步完成！")
    except Exception as e:
        bot.reply_to(message, f"❌ 同步失败: {e}")

@bot.message_handler(content_types=['photo', 'video'])
def handle_submission(message):
    """ 处理普通用户投稿与管理员直发 """
    is_admin = str(message.chat.id) == str(MY_CHAT_ID)
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    file_type = "image" if message.photo else "video"
    caption = message.caption or ""
    
    fname = download_tg_file(file_id)
    thumb = generate_thumb(os.path.join(UPLOAD_FOLDER, fname)) if file_type == "video" else None
    
    conn = get_db()
    approved = 1 if is_admin else 0
    cursor = conn.execute("INSERT INTO posts (content, file_path, file_type, thumb_url, is_approved) VALUES (?,?,?,?,?)",
                         (caption, fname, file_type, thumb, approved))
    post_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    if not is_admin:
        bot.reply_to(message, "📩 投稿已进入审核队列。")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ 通过", callback_data=f"approve_{post_id}"),
                   types.InlineKeyboardButton("❌ 拒绝", callback_data=f"reject_{post_id}"))
        
        try:
            if file_type == "image":
                bot.send_photo(MY_CHAT_ID, file_id, caption=f"新投稿审核：\n{caption}", reply_markup=markup)
            else:
                bot.send_video(MY_CHAT_ID, file_id, caption=f"新投稿审核：\n{caption}", reply_markup=markup)
        except Exception as e:
            print(f"Error sending admin notification: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
def admin_action(call):
    action, post_id = call.data.split('_')
    conn = get_db()
    if action == "approve":
        conn.execute("UPDATE posts SET is_approved = 1 WHERE id = ?", (post_id,))
        bot.answer_callback_query(call.id, "已发布")
        bot.edit_message_caption(f"{call.message.caption}\n\n[状态: 已批准 ✅]", call.message.chat.id, call.message.message_id)
    else:
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        bot.answer_callback_query(call.id, "已拒绝并删除")
        bot.edit_message_caption(f"{call.message.caption}\n\n[状态: 已拒绝 ❌]", call.message.chat.id, call.message.message_id)
    conn.commit()
    conn.close()

# --- 路由 ---

@app.route('/')
def index():
    try:
        conn = get_db()
        query = "SELECT * FROM posts WHERE is_approved = 1 ORDER BY created_at DESC"
        posts = conn.execute(query).fetchall()
        conn.close()
        return render_template('index.html', posts=posts)
    except sqlite3.OperationalError as e:
        # 如果还是报错，说明列没补全，强制重试初始化
        init_db()
        return "数据库结构正在升级，请刷新页面...", 503

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return jsonify({"status": "forbidden"}), 403

if __name__ == '__main__':
    if BASE_URL:
        bot.remove_webhook()
        bot.set_webhook(url=f"{BASE_URL}/webhook")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))