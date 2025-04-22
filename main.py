from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash
from werkzeug.utils import secure_filename
import mariadb
import bcrypt
import os
from datetime import timedelta
from PIL import Image

app = Flask(__name__)
# Serve per le sessioni e per cookie persistenti
app.secret_key = "supersecretkey"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Cartella per gli upload di immagini
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Connessione al database
def connct():
    try:
        return mariadb.connect(
            host="127.0.0.1",
            user="root",
            password="",
            database="user_auth"
        )
    except mariadb.Error as e:
        print(f"Database connection failed: {e}")
        return None

# Genera hash password
def generate_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode("utf-8")

# Controlla estensione file
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# Home
@app.route("/")
def index():
    return render_template("index.html")

# Registrazione
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user_type = request.form.get("user_type", "Student")
        hashed_password = generate_password_hash(password)
        conn = connct()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO users (email, password, user_type) VALUES (?, ?, ?)",
                    (email, hashed_password, user_type)
                )
                conn.commit()
                return redirect(url_for("login"))
            except mariadb.Error as e:
                flash(f"Error: {e}")
            finally:
                cur.close(); conn.close()
    return render_template("signup.html")

# Login con "ricordami"
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        remember = request.form.get("remember")

        conn = connct()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT id, password, user_type, profile_pic, bio FROM users WHERE email = ?", (email,))
                user = cur.fetchone()
                if user and bcrypt.checkpw(password.encode('utf-8'), user[1].encode('utf-8')):
                    session.permanent = bool(remember)
                    session["user_id"] = user[0]
                    session["user_type"] = user[2]
                    return redirect(url_for("profile"))
                else:
                    flash("Email o password sbagliati")
            finally:
                cur.close(); conn.close()
    return render_template("login.html")

# Serve immagini caricate
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Profilo e personalizzazione
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    conn = connct()
    if not conn:
        flash("Connessione al database fallita")
        return redirect(url_for("login"))

    if request.method == "POST":
        bio = request.form.get("bio", "")
        file = request.files.get("profile_pic")
        filename_db = None

        if file and allowed_file(file.filename):
            filename = secure_filename(f"user_{user_id}.png")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            # Ridimensiona a 200x200
            img = Image.open(file)
            img = img.convert("RGB")
            img.thumbnail((200, 200), Image.Resampling.LANCZOS)
            img.save(filepath)
            filename_db = filename

        try:
            cur = conn.cursor()
            if filename_db:
                cur.execute(
                    "UPDATE users SET bio = ?, profile_pic = ? WHERE id = ?",
                    (bio, filename_db, user_id)
                )
            else:
                cur.execute(
                    "UPDATE users SET bio = ? WHERE id = ?",
                    (bio, user_id)
                )
            conn.commit()
            flash("Icona profilo aggiornata con successo")
        except mariadb.Error as e:
            flash(f"Errore nel aggiornare l'icona: {e}")
        finally:
            cur.close(); conn.close()
        return redirect(url_for("profile"))

    # GET: recupera dati esistenti
    try:
        cur = conn.cursor()
        cur.execute("SELECT email, user_type, profile_pic, bio FROM users WHERE id = ?", (user_id,))
        email, user_type, profile_pic, bio = cur.fetchone()
    finally:
        cur.close(); conn.close()

    return render_template("profile.html", email=email, user_type=user_type, profile_pic=profile_pic, bio=bio)

@app.route("/view_database")
def view_database():
    # Se non sei Admin, rimandi al profilo
    if session.get("user_type") != "Admin":
        return redirect(url_for("profile"))

    db = connct()
    if not db:
        flash("Database connection failed")
        return redirect(url_for("profile"))

    cur = db.cursor()
    cur.execute("SELECT id, email, user_type FROM users")
    users = [{"id": r[0], "email": r[1], "user_type": r[2]} for r in cur.fetchall()]
    cur.close()
    db.close()

    return render_template("view_database.html", users=users)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
