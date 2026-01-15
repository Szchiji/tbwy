import os, sqlite3, requests, re, time, telebot, threading
from flask import Flask, request, render_template, jsonify
from datetime import datetime
from textblob import TextBlob
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Flask(__name__)

# --- 配置 (从环境变量读取) ---
DB_DIR = '/app/data'
DB_PATH = os.path.join(DB_DIR, 'data.db')
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
ADMIN_PWD = os.environ.get("ADMIN_PASSWORD", "admin888")

bot = telebot.TeleBot(BOT_TOKEN)
user_last_action = {}

# --- 数据库工厂 ---
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DB_DIR): os.makedirs(DB_DIR, exist_ok=True)
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            msg_id INTEGER, text TEXT, tags TEXT, username TEXT, title TEXT, 
            date TEXT, likes INTEGER DEFAULT 0, is_pinned INTEGER DEFAULT 0, 
            sentiment REAL, UNIQUE(msg_id, username))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, 
            parent_id INTEGER DEFAULT 0, content TEXT, date TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT UNIQUE)''')
init_db()

# --- 核心逻辑：同步删除 ---
def perform_sync():
    deleted_count = 0
    with get_db() as conn:
        posts = conn.execute("SELECT id, msg_id, username FROM posts").fetchall()
        for p in posts:
            if p['username'] == "Private": continue 
            try:
                # 探测 Telegram 帖子是否还在
                res = requests.get(f"https://t.me/{p['username']}/{p['msg_id']}?embed=1", timeout=5)
                if "Post not found" in res.text:
                    conn.execute("DELETE FROM posts WHERE id=?", (p['id'],))
                    conn.execute("DELETE FROM comments WHERE post_id=?", (p['id'],))
                    deleted_count += 1
            except: continue
    return deleted_count

# 后台自动同步线程 (每小时一次)
def auto_sync_worker():
    while True:
        time.sleep(3600)
        try: perform_sync()
        except: pass

threading.Thread(target=auto_sync_worker, daemon=True).start()

# --- Webhook 处理 ---
@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    
    # 1. 处理审核按钮回调
    if update.callback_query:
        handle_callback(update.callback_query)
        return 'OK'
        
    # 2. 处理消息逻辑
    p = update.channel_post or update.message or update.edited_channel_post
    if p:
        text = p.text or p.caption or ""
        chat_id, user_id = str(p.chat.id), str(p.from_user.id if p.from_user else "")
        is_me = chat_id == MY_CHAT_ID or user_id == MY_CHAT_ID
        
        # 管理员指令
        if is_me and text.startswith("/"):
            if text == "/sync":
                count = perform_sync()
                bot.send_message(MY_CHAT_ID, f"🧹 同步完成，清理了 {count} 条内容")
            elif text.startswith("/add "):
                word = text.replace("/add ", "").strip()
                with get_db() as conn: conn.execute("INSERT OR IGNORE INTO filters (word) VALUES (?)", (word,))
                bot.send_message(MY_CHAT_ID, f"🚫 已加禁词: {word}")
            elif text == "/list":
                with get_db() as conn:
                    words = [r['word'] for r in conn.execute("SELECT word FROM filters").fetchall()]
                bot.send_message(MY_CHAT_ID, "📝 禁词库:\n" + "\n".join(words) if words else "库为空")
            return 'OK'

        # 频道同步或本人转发 (支持图文视频)
        if update.channel_post or (is_me and (p.forward_from or p.forward_from_chat)):
            save_post(p.message_id, text, p.chat.username or "Private", p.chat.title or "情报站")
            
    return 'OK'

def save_post(mid, text, user, title):
    tags = ",".join(re.findall(r'#(\w+)', text))
    try: sentiment = TextBlob(text).sentiment.polarity
    except: sentiment = 0.0
    with get_db() as conn:
        conn.execute('''INSERT INTO posts (msg_id, text, tags, username, title, date, sentiment) 
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(msg_id, username) DO UPDATE SET
            text=excluded.text, tags=excluded.tags, sentiment=excluded.sentiment''', 
            (mid, text, tags, user, title, datetime.now().strftime("%Y-%m-%d %H:%M"), sentiment))

# --- 投稿审核逻辑 (支持照片/视频) ---
@bot.message_handler(content_types=['photo', 'video', 'text', 'animation'])
def handle_user_submission(message):
    if str(message.chat.id) == MY_CHAT_ID: return 
    
    markup = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ 审核通过", callback_data=f"pub_{message.message_id}"),
        InlineKeyboardButton("❌ 拒绝", callback_data="pub_no")
    )
    bot.forward_message(MY_CHAT_ID, message.chat.id, message.message_id)
    bot.send_message(MY_CHAT_ID, "🔔 收到新投稿，请审核。通过后请手动转发至频道。", reply_markup=markup)

def handle_callback(call):
    if call.data == "pub_no":
        bot.edit_message_text("❌ 已拒绝该投稿", call.message.chat.id, call.message.message_id)
    elif call.data.startswith("pub_"):
        bot.edit_message_text("✅ 审核已通过。请操作上方的转发消息进入你的频道，网页将自动同步。", call.message.chat.id, call.message.message_id)

# --- 前端接口 ---
@app.route('/')
def index():
    with get_db() as conn:
        posts = conn.execute("SELECT * FROM posts GROUP BY msg_id, username ORDER BY is_pinned DESC, id DESC").fetchall()
        comments = conn.execute("SELECT * FROM comments ORDER BY id ASC").fetchall()
    return render_template('index.html', posts=posts, comments=comments)

@app.route('/api/comment', methods=['POST'])
def add_comment():
    data = request.json
    with get_db() as conn:
        words = [r['word'] for r in conn.execute("SELECT word FROM filters").fetchall()]
        if any(w in data.get('content','') for w in words): return "Blocked", 400
        conn.execute("INSERT INTO comments (post_id, parent_id, content, date) VALUES (?,?,?,?)",
                     (data.get('post_id'), data.get('parent_id', 0), data.get('content'), datetime.now().strftime("%m-%d %H:%M")))
    return "OK"

@app.route('/api/like/<int:id>', methods=['POST'])
def like(id):
    with get_db() as conn: conn.execute("UPDATE posts SET likes = likes + 1 WHERE id=?", (id,))
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))