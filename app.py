import os, sqlite3, requests, telebot, datetime, mimetypes
from flask import Flask, request, render_template, jsonify, send_from_directory
from datetime import datetime

# 强制注册视频类型，解决部分浏览器不识别视频的问题
mimetypes.add_type('video/mp4', '.mp4')
mimetypes.add_type('video/quicktime', '.mov')

app = Flask(__name__)

# --- 路径配置 ---
DB_DIR = '/app/data'
UPLOAD_DIR = os.path.join(DB_DIR, 'uploads')
DB_PATH = os.path.join(DB_DIR, 'data.db')
os.makedirs(UPLOAD_DIR, exist_ok=True)

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
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
            msg_id INTEGER, text TEXT, username TEXT, title TEXT, 
            date TEXT, likes INTEGER DEFAULT 0, 
            media_group_id TEXT, first_media TEXT, admin_note TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notice', '欢迎访问 Matrix Hub')")
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, content TEXT, date TEXT)''')
init_db()

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
    p = update.channel_post or update.message
    if p:
        text = p.text or p.caption or ""
        local_path = None
        media_obj = p.photo[-1] if p.photo else (p.video if p.video else None)
        ext = ".jpg" if p.photo else (".mp4" if p.video else "")

        if media_obj:
            file_info = bot.get_file(media_obj.file_id)
            save_name = f"{media_obj.file_id}{ext}"
            target_path = os.path.join(UPLOAD_DIR, save_name)
            if not os.path.exists(target_path):
                r = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}")
                with open(target_path, 'wb') as f: f.write(r.content)
            local_path = f"/uploads/{save_name}"
        
        with get_db() as conn:
            conn.execute('''INSERT INTO posts (msg_id, text, username, title, date, media_group_id, first_media) 
                VALUES (?,?,?,?,?,?,?)''', (p.message_id, text, "Admin", "Matrix", 
                datetime.now().strftime("%Y-%m-%d"), p.media_group_id, local_path))
    return 'OK'

@app.route('/')
def index():
    q = request.args.get('q', '')
    with get_db() as conn:
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        posts = conn.execute("SELECT * FROM posts WHERE text LIKE ? GROUP BY CASE WHEN media_group_id IS NOT NULL THEN media_group_id ELSE id END ORDER BY id DESC", (f'%{q}%',)).fetchall()
    return render_template('index.html', posts=posts, notice=notice['value'] if notice else "", q=q)

@app.route('/post/<int:post_id>')
def detail(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        notice = conn.execute("SELECT value FROM settings WHERE key='notice'").fetchone()
        all_media = conn.execute("SELECT first_media FROM posts WHERE media_group_id=? AND first_media IS NOT NULL", (post['media_group_id'],)).fetchall() if post['media_group_id'] else [{'first_media': post['first_media']}]
        comments = conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY id DESC", (post_id,)).fetchall()
    return render_template('detail.html', post=post, notice=notice['value'] if notice else "", all_media=all_media, comments=comments)

@app.route('/api/like/<int:post_id>', methods=['POST'])
def like(post_id):
    with get_db() as conn: conn.execute("UPDATE posts SET likes = likes + 1 WHERE id = ?", (post_id,))
    return jsonify({"status": "success"})

@app.route('/api/comment', methods=['POST'])
def add_comment():
    data = request.json
    with get_db() as conn: conn.execute("INSERT INTO comments (post_id, content, date) VALUES (?, ?, ?)", (data['post_id'], data['content'], datetime.now().strftime("%m-%d %H:%M")))
    return jsonify({"status": "success"})

@app.route('/api/delete_comment', methods=['POST'])
def delete_comment():
    data = request.json
    if data.get('password') != ADMIN_PWD: return "Error", 401
    with get_db() as conn: conn.execute("DELETE FROM comments WHERE id = ?", (data.get('comment_id'),))
    return "OK"

@app.route('/api/set_note', methods=['POST'])
def set_note():
    data = request.json
    if data.get('password') != ADMIN_PWD: return "Error", 401
    with get_db() as conn: conn.execute("UPDATE posts SET admin_note = ? WHERE id = ?", (data.get('content'), data.get('post_id')))
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)