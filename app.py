import os, sqlite3, secrets, zipfile, io
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", "/tmp/pavel_bot_hosting")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(48)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB upload limit
DB_PATH = os.path.join(DATA_DIR, "hosting.db")
ALLOWED = {".py", ".zip"}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bot_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            original_name TEXT NOT NULL,
            requirements TEXT DEFAULT '',
            status TEXT DEFAULT 'Stopped',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")

init_db()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) < 3 or len(username) > 24:
            flash("Username 3–24 characters হতে হবে।", "error")
        elif len(password) < 8:
            flash("Password কমপক্ষে 8 characters হতে হবে।", "error")
        else:
            try:
                with db() as con:
                    con.execute("INSERT INTO users(username,password_hash) VALUES(?,?)",
                                (username, generate_password_hash(password)))
                flash("Account তৈরি হয়েছে। এখন Login করো।", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("এই Username আগে থেকেই ব্যবহার করা হয়েছে।", "error")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Username অথবা Password ভুল।", "error")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    with db() as con:
        bots = con.execute("SELECT * FROM bots WHERE user_id=? ORDER BY id DESC",
                           (session["user_id"],)).fetchall()
    return render_template("dashboard.html", bots=bots)

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("botfile")
    reqs = request.form.get("requirements", "").strip()
    if not f or not f.filename:
        flash("একটি .py অথবা .zip ফাইল নির্বাচন করো।", "error")
        return redirect(url_for("dashboard"))
    original = secure_filename(f.filename)
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED:
        flash("শুধু .py অথবা .zip ফাইল গ্রহণ করা হয়।", "error")
        return redirect(url_for("dashboard"))
    if ext == ".zip":
        try:
            data = f.read()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                members = zf.infolist()
                if len(members) > 150:
                    raise ValueError()
                for item in members:
                    name = item.filename.replace("\\", "/")
                    if name.startswith("/") or ".." in name.split("/") or item.is_dir():
                        continue
                    if item.file_size > 10 * 1024 * 1024:
                        raise ValueError()
            f.stream.seek(0)
        except Exception:
            flash("ZIP ফাইলটি পড়া যাচ্ছে না অথবা এর গঠন গ্রহণযোগ্য নয়।", "error")
            return redirect(url_for("dashboard"))
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM bots WHERE user_id=?",
                            (session["user_id"],)).fetchone()[0]
        if count >= 2:
            flash("তোমার Free Plan-এর ২টি Bot Slot পূর্ণ। নতুন Bot Upload করতে একটি Delete করো।", "error")
            return redirect(url_for("dashboard"))
        stored = secrets.token_hex(16) + ext
        user_dir = os.path.join(UPLOAD_DIR, str(session["user_id"]))
        os.makedirs(user_dir, exist_ok=True)
        f.save(os.path.join(user_dir, stored))
        bot_name = os.path.splitext(original)[0][:60] or "My Bot"
        con.execute("""INSERT INTO bots(user_id,bot_name,stored_name,original_name,requirements)
                       VALUES(?,?,?,?,?)""",
                    (session["user_id"], bot_name, stored, original, reqs[:5000]))
    flash("ফাইল Upload হয়েছে। নিরাপদ Runner যুক্ত না হওয়া পর্যন্ত Bot Execute করা হবে না।", "success")
    return redirect(url_for("dashboard"))

@app.route("/bot/<int:bot_id>/<action>", methods=["POST"])
@login_required
def bot_action(bot_id, action):
    if action not in {"start", "stop", "restart"}:
        flash("অজানা Action।", "error")
    else:
        flash("Bot Runner এই Free Web Service-এ Configure করা নেই। তাই Bot চালু/বন্ধ করা হয়নি। আলাদা isolated worker প্রয়োজন।", "warning")
    return redirect(url_for("dashboard"))

@app.route("/bot/<int:bot_id>/delete", methods=["POST"])
@login_required
def delete_bot(bot_id):
    with db() as con:
        bot = con.execute("SELECT * FROM bots WHERE id=? AND user_id=?",
                          (bot_id, session["user_id"])).fetchone()
        if bot:
            path = os.path.join(UPLOAD_DIR, str(session["user_id"]), bot["stored_name"])
            if os.path.isfile(path):
                os.remove(path)
            con.execute("DELETE FROM bots WHERE id=? AND user_id=?",
                        (bot_id, session["user_id"]))
            flash("Bot ও Upload করা ফাইল Delete হয়েছে। Slot খালি হয়েছে।", "success")
        else:
            flash("Bot পাওয়া যায়নি।", "error")
    return redirect(url_for("dashboard"))

@app.errorhandler(413)
def too_large(_):
    flash("ফাইল 20 MB-এর বেশি হতে পারবে না।", "error")
    return redirect(url_for("dashboard"))

@app.errorhandler(500)
def server_error(_):
    return render_template("error.html"), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
