import os, sqlite3, requests, re, time, telebot
from flask import Flask, request, render_template, jsonify
from datetime import datetime
from textblob import TextBlob
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Flask(__name__)

# --- 配置 ---
DB_DIR = '/app/data'
DB_PATH = os.path.join(DB_DIR, 'data.db')
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = os.environ.get("MY_CHAT_ID")
ADMIN_PWD = os.environ.get("ADMIN_PASSWORD", "admin888")

bot = telebot.TeleBot(BOT_TOKEN)
user_last_action = {}

# --- 数据库工厂 (增加超时重试优化) ---
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DB_DIR): os.makedirs(DB_DIR, exist_ok=True)
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, msg_id INTEGER, text TEXT, tags TEXT, username TEXT, title TEXT, date TEXT, likes INTEGER DEFAULT 0, blocks INTEGER DEFAULT 0, is_pinned INTEGER DEFAULT 0, sentiment REAL, UNIQUE(msg_id, username))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, parent_id INTEGER DEFAULT 0, content TEXT, date TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS filters (id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT UNIQUE)''')
init_db()

def get_spam_words():
    with get_db() as conn:
        return [row['word'] for row in conn.execute("SELECT word FROM filters").fetchall()]

# --- 核心逻辑 ---
@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    
    if update.callback_query:
        handle_callback(update.callback_query)
        return 'OK'
        
    p = update.channel_post or update.message or update.edited_channel_post
    if p:
        text = p.text or p.caption or ""
        chat_id, user_id = str(p.chat.id), str(p.from_user.id if p.from_user else "")
        is_me = chat_id == MY_CHAT_ID or user_id == MY_CHAT_ID
        
        if is_me and text.startswith("/"):
            handle_admin_cmd(text)
        elif update.channel_post or (is_me and (p.forward_from or p.forward_from_chat)):
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

def handle_admin_cmd(text):
    if text.startswith("/add "):
        word = text.replace("/add ", "").strip()
        with get_db() as conn: conn.execute("INSERT OR IGNORE INTO filters (word) VALUES (?)", (word,))
        bot.send_message(MY_CHAT_ID, f"🚫 已加入黑名单: {word}")
    elif text == "/list":
        words = get_spam_words()
        bot.send_message(MY_CHAT_ID, f"📝 禁词库:\n" + "\n".join(words) if words else "空")
    elif text.startswith("/del "):
        word = text.replace("/del ", "").strip()
        with get_db() as conn: conn.execute("DELETE FROM filters WHERE word = ?", (word,))
        bot.send_message(MY_CHAT_ID, f"✅ 已移除禁词: {word}")

@app.route('/api/contribute', methods=['POST'])
def contribute():
    ip = request.remote_addr
    if ip in user_last_action and time.time() - user_last_action[ip] < 60: return "Too fast", 429
    content = request.json.get('content', '')
    if any(w in content for w in get_spam_words()): return "Spam detected", 400
    
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ 发布", callback_data="pub_ok"), InlineKeyboardButton("❌ 拒绝", callback_data="pub_no"))
    bot.send_message(MY_CHAT_ID, f"🔔 **新投稿**：\n\n{content}", reply_markup=markup, parse_mode="Markdown")
    user_last_action[ip] = time.time()
    return jsonify({"status": "success"})

def handle_callback(call):
    if call.data == "pub_ok":
        text = call.message.text.split("🔔 新投稿：\n\n")[1]
        save_post(int(time.time()), text, "User", "社区投稿")
        bot.edit_message_text(f"✅ 已发布\n\n{text}", call.message.chat.id, call.message.message_id)
    else:
        bot.edit_message_text("❌ 已拒绝", call.message.chat.id, call.message.message_id)

@app.route('/api/comment', methods=['POST'])
def add_comment():
    data = request.json
    if any(w in data.get('content','') for w in get_spam_words()): return "Blocked", 400
    with get_db() as conn:
        conn.execute("INSERT INTO comments (post_id, parent_id, content, date) VALUES (?,?,?,?)",
                     (data.get('post_id'), data.get('parent_id', 0), data.get('content'), datetime.now().strftime("%m-%d %H:%M")))
    return "OK"

@app.route('/')
def index():
    with get_db() as conn:
        posts = conn.execute("SELECT * FROM posts GROUP BY msg_id, username ORDER BY is_pinned DESC, id DESC").fetchall()
        comments = conn.execute("SELECT * FROM comments ORDER BY id ASC").fetchall()
    return render_template('index.html', posts=posts, comments=comments)

@app.route('/api/like/<int:id>', methods=['POST'])
def like(id):
    with get_db() as conn: conn.execute("UPDATE posts SET likes = likes + 1 WHERE id=?", (id,))
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))