from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash, g
from werkzeug.utils import secure_filename
import mariadb
import bcrypt
import os
from datetime import timedelta
from PIL import Image
import json
import smtplib
import ssl
from email.message import EmailMessage
import random
from email_validator import validate_email, EmailNotValidError
import time
from datetime import datetime
from jinja2 import Environment

app = Flask(__name__)
# Serve per le sessioni e per cookie persistenti
app.secret_key = "supersecretkey"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30) # Fai log out dopo 30 giorni

# Cartella per gli upload di immagini
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configurazioni
try:
    with open("config.json", "r") as configurazioni:
        configurazioni = json.load(configurazioni);
except Exception as errore:
    print("Impossibile leggere i dati di configurazione: %s" % errore)
    exit(1);

# Connessione al database
def connct():
    try:
        return mariadb.connect(
            host=configurazioni['sql_host'],
            user=configurazioni['sql_user'],
            password=configurazioni['sql_password'],
            database=configurazioni['sql_database']
        )
    except mariadb.Error as e:
        print("Errore, connessione al database fallita: %s" % e)
        return None

# Invio di codice per email

def email_sender(email: str, soggetto: str="Iu-ventus | Codice verifica") -> str:
    # Genera il codice a 6 cifre
    code = "".join(str(random.randint(0, 9)) for _ in range(6))

    # Prepara il messaggio
    msg = EmailMessage()
    msg["Subject"] = soggetto
    msg["From"] = configurazioni['smtp_user']
    msg["To"] = email

    # Contenuto testuale se non carica l'HTML
    text = f"""\
Il tuo codice di verifica per Iu-ventus è: {code}

Se non vedi questa email, controlla la cartella Spam.
"""
    msg.set_content(text)

    # Contenuto HTML
    html = f"""\
<!DOCTYPE html>
<html lang="it">
    <head>
        <meta charset="UTF-8" />
        <title>Iu-ventus</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin:0; padding:0;">
        <table align="center" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px; background-color:#ffffff; margin: 20px auto; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
        <tr>
            <td style="background-color:#1e40af; padding:20px; text-align:center;">
            <h1 style="color:#ffffff; margin:0; font-size:24px;">Iu-ventus</h1>
            </td>
        </tr>
        <tr>
            <td style="padding:30px; color:#333333;">
            <p style="font-size:16px; margin-top:0;">Ciao,</p>
            <p style="font-size:16px;">
                Ecco il tuo <strong>codice di verifica</strong>:
            </p>
            <div style="text-align:center; margin:30px 0;">
                <span style="display:inline-block; padding:15px 25px; font-size:20px; letter-spacing:4px; background-color:#1e40af; color:#ffffff; border-radius:6px;">
                {code}
                </span>
            </div>
            <p style="font-size:14px; color:#555555;">
                Se non vedi questa email nella posta in arrivo, controlla la cartella “Spam” o “Posta indesiderata”.
            </p>
            <p style="font-size:14px; color:#555555; margin-bottom:0;">
                Se non hai richiesto questo codice, ignora pure questa email.
            </p>
            </td>
        </tr>
        <tr>
            <td style="background-color:#f4f4f4; text-align:center; padding:20px; font-size:12px; color:#888888;">
            © {datetime.now().year} Iu-ventus. Tutti i diritti riservati.
            </td>
        </tr>
        </table>
    </body>
</html>
"""
    msg.add_alternative(html, subtype="html")

    # Invia
    context = ssl.create_default_context()
    server = None
    try:
        server = smtplib.SMTP(configurazioni['smtp_server'], configurazioni['smtp_port'])
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(configurazioni['smtp_user'], configurazioni['smtp_password'])
        server.send_message(msg)
    except Exception as e:
        print(f"Errore durante l'invio dell'email: {e}")
    finally:
        if server:
            server.quit()
    return code

# Genera hash password
def generate_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

# Controlla estensione file
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_or_create_tag(name):
    cur = g.db.cursor()
    cur.execute("SELECT id FROM tags WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    g.db.commit()
    return cur.lastrowid

def datetimeformat(value, format='%b %d, %Y %H:%M'):
    return value.strftime(format)
app.jinja_env.filters['datetimeformat'] = datetimeformat

@app.route("/create_post", methods=["POST"])
def create_post():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    tags = request.form.get("tags", "").strip()
    file = request.files.get("image")
    
    if not content:
        flash("I post non possono essere vuoti", "error")
        return redirect(url_for("index"))
    
    try:
        # Inserisci il post
        cur = g.db.cursor()
        cur.execute("""
            INSERT INTO posts (title, content, user_id, creation_date, image)
            VALUES (?, ?, ?, ?, ?)
        """, (title[:100], content, session['user_id'], datetime.now(), None))
        post_id = cur.lastrowid

        image_filename = None
        if file and allowed_file(file.filename):
            image_filename = secure_filename(f"post_{post_id}_{int(time.time())}.png")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            
            img = Image.open(file.stream)
            img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            img.save(filepath)
            
            cur.execute("UPDATE posts SET image = ? WHERE id = ?", (image_filename, post_id))
            
        # Gestisci i tag
        tag_list = [t.strip() for t in tags.split(",") if t.strip()][:5]
        for tag in tag_list:
            tag_id = get_or_create_tag(tag)
            cur.execute("""
                INSERT INTO post_tags (post_id, tag_id)
                VALUES (?, ?)
            """, (post_id, tag_id))
        
        g.db.commit()
        flash("Post carico con successo!", "success")
    except Exception as e:
        g.db.rollback()
        flash(f"Errore nella creazione del post: {str(e)}", "error")
    
    return redirect(url_for("index"))

@app.route("/delete_post/<int:post_id>", methods=["POST"])
def delete_post(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    try:
        cur = g.db.cursor()
        # Verifica che l'utente sia il proprietario
        cur.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,))
        result = cur.fetchone()
        if result and result[0] == session['user_id']:
            cur.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            cur.execute("DELETE FROM post_tags WHERE post_id = ?", (post_id,))
            g.db.commit()
            flash("Post eliminato con successo", "success")
        else:
            flash("Non sei autorizzato a eliminare questo post", "error")
    except Exception as e:
        g.db.rollback()
        flash(f"Errore durante l'eliminazione: {str(e)}", "error")
    
    return redirect(url_for("index"))

@app.route("/add_comment/<int:post_id>", methods=["POST"])
def add_comment(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    content = request.form.get("content", "").strip()
    if not content:
        flash("Il commento non può essere vuoto", "error")
        return redirect(url_for("index"))
    
    try:
        cur = g.db.cursor()
        cur.execute("""
            INSERT INTO comments (post_id, user_id, content)
            VALUES (?, ?, ?)
        """, (post_id, session['user_id'], content))
        g.db.commit()
    except Exception as e:
        g.db.rollback()
        flash(f"Errore nell'aggiunta del commento: {str(e)}", "error")
    
    return redirect(url_for("index"))

@app.route("/delete_comment/<int:comment_id>", methods=["POST"])
def delete_comment(comment_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    try:
        cur = g.db.cursor()
        # Verifica proprietà commento
        cur.execute("SELECT user_id FROM comments WHERE id = ?", (comment_id,))
        result = cur.fetchone()
        if result and result[0] == session['user_id']:
            cur.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
            g.db.commit()
            flash("Commento eliminato", "success")
        else:
            flash("Non sei autorizzato", "error")
    except Exception as e:
        g.db.rollback()
        flash(f"Errore: {str(e)}", "error")
    
    return redirect(url_for("index"))

@app.route("/", methods=["GET"])
def index():
    try:
        search_type = request.args.get("type", "posts")
        user_id = session.get("user_id")
        user_type = session.get("user_type")
        cur = g.db.cursor(dictionary=True)

        if search_type == "posts":
            return handle_post_search(cur, user_id)
        elif search_type == "users":
            return handle_user_search(cur, user_type)  # Passa l'user type
        else:
            return handle_default_view(cur, user_id, user_type)

    except Exception as e:
        flash(f"Errore durante il caricamento: {str(e)}", "error")
        return redirect(url_for("index"))

def handle_user_search(cur, current_user_type):
    q = request.args.get("q", "").strip().lower()
    search_field = request.args.get("search_user_field", "username")
    users_with_scores = []

    target_type = None
    if current_user_type == "Student":
        target_type = "Business"
    elif current_user_type == "Business":
        target_type = "Student"

    base_query = """
        SELECT DISTINCT u.*
        FROM users u
        {join_clause}
        WHERE LOWER({search_field}) LIKE ?
        {user_type_clause}
        ORDER BY u.id DESC
        LIMIT 50
    """

    if search_field == "username":
        query = base_query.format(
            join_clause="",
            search_field="u.Username",
            user_type_clause=f"AND u.user_type = '{target_type}'" if target_type else ""
        )
        params = [f"%{q}%"]
    else:  # tag search
        query = base_query.format(
            join_clause="JOIN user_tags ut ON u.id = ut.user_id JOIN tags t ON ut.tag_id = t.id",
            search_field="t.name",
            user_type_clause=f"AND u.user_type = '{target_type}'" if target_type else ""
        )
        params = [f"%{q}%"]

    cur.execute(query, params)
    users = cur.fetchall()

    # calcola gli score
    for user in users:
        cur.execute("SELECT t.name FROM user_tags ut JOIN tags t ON ut.tag_id = t.id WHERE ut.user_id = ?", (user['id'],))
        tags = [row['name'].lower() for row in cur.fetchall()]
        
        score = 0
        if q:
            if search_field == "username":
                score += 100 if q in user['Username'].lower() else 0
            score += sum(10 for tag in tags if q in tag)
        
        user['tags'] = tags
        users_with_scores.append((user, min(score, 100)))

    users_with_scores.sort(key=lambda x: x[1], reverse=True)
    return render_template("index.html", users_with_scores=users_with_scores, search_type="users")

def handle_post_search(cur, user_id):
    q = request.args.get("q", "").strip().lower()
    search_field = request.args.get("search_field", "content")
    posts = []

    # Costruzione query in base al campo di ricerca
    if search_field in ["content", "title"]:
        cur.execute(f"""
            SELECT p.*, u.Username, u.profile_pic, u.user_type
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE LOWER(p.{search_field}) LIKE ?
            ORDER BY p.creation_date DESC
            LIMIT 50
        """, (f"%{q}%",))
    else:  # ricerca per tag
        cur.execute("""
            SELECT DISTINCT p.*, u.Username, u.profile_pic, u.user_type
            FROM posts p
            JOIN users u ON p.user_id = u.id
            JOIN post_tags pt ON p.id = pt.post_id
            JOIN tags t ON pt.tag_id = t.id
            WHERE LOWER(t.name) LIKE ?
            ORDER BY p.creation_date DESC
            LIMIT 50
        """, (f"%{q}%",))

    posts = cur.fetchall()
    _add_post_metadata(cur, posts)
    return render_template("index.html", posts=posts, search_type="posts")


def handle_default_view(cur, user_id, user_type):
    posts = []
    users_with_scores = []

    # Caricamento post rilevanti
    if user_id:
        cur.execute("""
            SELECT t.name 
            FROM user_tags ut
            JOIN tags t ON ut.tag_id = t.id
            WHERE ut.user_id = ?
        """, (user_id,))
        user_tags = [row['name'] for row in cur.fetchall()]

        if user_tags:
            cur.execute(f"""
                SELECT DISTINCT p.*, u.Username, u.profile_pic, u.user_type
                FROM posts p
                JOIN users u ON p.user_id = u.id
                JOIN post_tags pt ON p.id = pt.post_id
                JOIN tags t ON pt.tag_id = t.id
                WHERE t.name IN ({','.join(['?']*len(user_tags))})
                ORDER BY p.creation_date DESC
                LIMIT 20
            """, user_tags)
        else:
            cur.execute("""
                SELECT p.*, u.Username, u.profile_pic, u.user_type
                FROM posts p
                JOIN users u ON p.user_id = u.id
                ORDER BY p.creation_date DESC
                LIMIT 20
            """)
        
        posts = cur.fetchall()
        _add_post_metadata(cur, posts)

    # Suggerimenti utenti
    if user_id and user_type:
        target_type = "Student" if user_type == "Business" else "Business"
        cur.execute(f"""
            SELECT *, COALESCE(Username, email) as display_name
            FROM users
            WHERE user_type = ?
            LIMIT 10
        """, (target_type,))
        
        for user in cur.fetchall():
            cur.execute("""
                SELECT t.name
                FROM user_tags ut
                JOIN tags t ON ut.tag_id = t.id
                WHERE ut.user_id = ?
            """, (user['id'],))
            user['tags'] = [row['name'] for row in cur.fetchall()]
            users_with_scores.append((user, 0))  # Punteggio non necessario per i suggerimenti

    return render_template("index.html",
                        posts=posts,
                        users_with_scores=users_with_scores,
                        search_type="posts")

def _add_post_metadata(cur, posts):
    # Aggiunge tag e commenti ai post
    for post in posts:
        # Carica tag
        cur.execute("""
            SELECT t.name
            FROM post_tags pt
            JOIN tags t ON pt.tag_id = t.id
            WHERE pt.post_id = ?
        """, (post['id'],))
        post['tags'] = [row['name'] for row in cur.fetchall()]

        # Carica commenti
        cur.execute("""
            SELECT c.*, u.Username, u.profile_pic, u.user_type
            FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.post_id = ?
            ORDER BY c.created_at
        """, (post['id'],))
        post['comments'] = cur.fetchall()

# Registrazione
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            username = request.form.get("username", "").strip()
            if not username:
                username = None
            if len(username) > 20:
                flash("Il nome deve essere di 20 caratteri o di meno", "error")
                return render_template("signup.html")
            email = request.form["email"]
            validate_email(email, check_deliverability=True)
            password = request.form["password"]
            user_type = request.form.get("user_type", "Student")
            hashed_password = generate_password_hash(password)
            conn = connct()
            if conn:
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO users (email, password, user_type, Username) VALUES (?, ?, ?, ?)",
                        (email, hashed_password, user_type, username)
                    )
                    conn.commit()
                    flash("Account creato con successo!", "success");
                    return redirect(url_for("login"))
                except mariadb.Error as e:
                    flash(f"Errore: {e}", "error")
                finally:
                    cur.close(); conn.close()
        except EmailNotValidError as e:
            flash(f"Email invalida: {e}", "error")
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
                if user and bcrypt.checkpw(password.encode("utf-8"), user[1].encode("utf-8")):
                    session.permanent = bool(remember)
                    session['user_id'] = user[0]
                    session['user_type'] = user[2]
                    return redirect(url_for("profile"))
                else:
                    flash("Email o password sbagliati", "error")
            finally:
                cur.close(); conn.close()
    return render_template("login.html")

# Serve per le immagini caricate
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# @before_request/@teardown_request gestiscono la connessione DB in g.db
@app.before_request
def before_request():
    # apre connessione e la mette in g.db
    g.db = connct()
    if not g.db:
        flash("Connessione al database fallita", "error")
        return redirect(url_for("login"))

@app.teardown_request
def teardown_request(exception):
    db = getattr(g, "db", None)
    if db:
        db.close()

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user_type = session.get("user_type", "Student")
    cur = g.db.cursor()
    error_occurred = False  # Flag per tracciare gli errori

    if request.method == "POST":
        try:
            # Inizializza le variabili
            bio = request.form.get("bio", "")
            file = request.files.get("profile_pic")
            username_input = request.form.get('username', '').strip() or None
            update_success = False
            if len(bio) > 1500:
                flash("La bio non può essere più lunga di 1500 caratteri", "error")
                error_occurred = True
            if username_input and len(username_input) > 20:
                flash("L'username deve essere più corto di 20 caratteri", "error")
                error_occurred = True
            # Gestione immagine profilo
            pic_filename = None
            if file and allowed_file(file.filename):
                pic_filename = secure_filename(f"user_{user_id}.png")
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], pic_filename)
                img = Image.open(file).convert("RGB")
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                img.save(filepath)

            # Aggiornamento dati base
            if pic_filename:
                cur.execute("UPDATE users SET bio=?, profile_pic=?, Username=? WHERE id=?",
                        (bio, pic_filename, username_input, user_id))
            else:
                cur.execute("UPDATE users SET bio=?, Username=? WHERE id=?",
                        (bio, username_input, user_id))

            # Gestione tipologia utente
            if user_type == "Student":
                cv = request.files.get("cv_file")
                if cv and cv.filename.lower().endswith(".pdf"):
                    cv_filename = secure_filename(f"cv_{user_id}.pdf")
                    cv.save(os.path.join(app.config["UPLOAD_FOLDER"], cv_filename))
                    cur.execute("UPDATE users SET cv_file=? WHERE id=?", (cv_filename, user_id))
                
                tags = request.form.get("tags", "")
                tag_list = [t.strip() for t in tags.split(",") if t.strip()][:3]
                cur.execute("DELETE FROM user_tags WHERE user_id=?", (user_id,))
                for t in tag_list:
                    tid = get_or_create_tag(t)
                    cur.execute("INSERT INTO user_tags (user_id, tag_id) VALUES (?,?)", (user_id, tid))

            elif user_type == "Business":
                address = request.form.get("address", "")
                phone = request.form.get("phone", "")
                cur.execute("UPDATE users SET address=?, phone=? WHERE id=?", (address, phone, user_id))
                
                tags = request.form.get("tags", "")
                tag_list = [t.strip() for t in tags.split(",") if t.strip()][:3]
                cur.execute("DELETE FROM user_tags WHERE user_id=?", (user_id,))
                for t in tag_list:
                    tid = get_or_create_tag(t)
                    cur.execute("INSERT INTO user_tags (user_id, tag_id) VALUES (?,?)", (user_id, tid))

            # Gestione email/password
            new_email = request.form.get("email", "").strip()
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")

            if new_email or new_password:
                cur.execute("SELECT password, email FROM users WHERE id = ?", (user_id,))
                result = cur.fetchone()
                
                if not result:
                    flash("Errore durante il recupero dei dati utente", "error")
                    error_occurred = True
                else:
                    current_pass_hash, current_email = result
                    
                    if not current_password:
                        flash("Password attuale richiesta per modifiche sensibili", "error")
                        error_occurred = True
                    elif not bcrypt.checkpw(current_password.encode('utf-8'), current_pass_hash.encode('utf-8')):
                        flash("Password attuale non corretta", "error")
                        error_occurred = True
                    else:
                        # Aggiornamento email
                        if new_email:
                            try:
                                validate_email(new_email, check_deliverability=True)
                                if new_email == current_email:
                                    flash("Email identica a quella esistente", "info")
                                else:
                                    cur.execute("SELECT id FROM users WHERE email = ?", (new_email,))
                                    if cur.fetchone():
                                        flash("Email già registrata", "error")
                                        error_occurred = True
                                    else:
                                        cur.execute("UPDATE users SET email = ? WHERE id = ?", 
                                            (new_email, user_id))
                                        flash("Email aggiornata con successo", "success")
                            except EmailNotValidError as e:
                                flash(f"Email non valida: {str(e)}", "error")
                                error_occurred = True
                        
                        # Aggiornamento password
                        if new_password:
                            if len(new_password) < 8:
                                flash("La password deve contenere almeno 8 caratteri", "error")
                                error_occurred = True
                            else:
                                new_hash = generate_password_hash(new_password)
                                cur.execute("UPDATE users SET password = ? WHERE id = ?", 
                                    (new_hash, user_id))
                                flash("Password aggiornata con successo", "success")

            # Commit finale solo se nessun errore
            if not error_occurred:
                g.db.commit()
                flash("Profilo aggiornato con successo", "success")
            else:
                g.db.rollback()

        except Exception as e:
            g.db.rollback()
            flash(f"Errore durante l'aggiornamento: {str(e)}", "error")
            error_occurred = True

        return redirect(url_for("profile"))

    # GET: Caricamento dati
    cur.execute("SELECT email, user_type, profile_pic, bio, cv_file, address, phone, Username FROM users WHERE id=?", (user_id,))
    user_data = cur.fetchone()
    email, user_type, profile_pic, bio, cv_file, address, phone, username = user_data

    cur.execute("SELECT t.name FROM tags t JOIN user_tags ut ON ut.tag_id = t.id WHERE ut.user_id = ?", (user_id,))
    user_tags = [row[0] for row in cur.fetchall()]

    return render_template(
        "profile.html",
        username=username,
        email=email,
        user_type=user_type,
        profile_pic=profile_pic,
        bio=bio,
        cv_file=cv_file,
        address=address,
        phone=phone,
        user_tags=user_tags
    )

@app.route("/user/<int:user_id>")
def view_user(user_id):
    # Assicuriamoci che l’utente sia loggato
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Connessione già presente in g.db (vedi before_request)
    cur = g.db.cursor()

    # Carichiamo i dati di base dell’utente
    cur.execute("""
        SELECT id, email, user_type, profile_pic, bio, cv_file, address, phone, Username
        FROM users
        WHERE id = ?
    """, (user_id,))
    row = cur.fetchone()
    if not row:
        flash("Utente non trovato", "error")
        return redirect(url_for("index"))

    user = {
        "id": row[0],
        "email": row[1],
        "user_type": row[2],
        "profile_pic": row[3],
        "bio": row[4],
        "cv_file": row[5],
        "address": row[6],
        "phone": row[7],
        "Username": row[8]
    }

    # Recuperiamo i tag associati a questo utente
    cur.execute("""
        SELECT t.name
        FROM tags t
        JOIN user_tags ut ON ut.tag_id = t.id
        WHERE ut.user_id = ?
    """, (user_id,))
    tags = [r[0] for r in cur.fetchall()]

    return render_template(
        "user_profile.html",
        user=user,
        tags=tags
    )


@app.route("/view_database")
def view_database():
    # Se non sei Admin, rimandi al profilo
    if session.get("user_type") != "Admin":
        return redirect(url_for("profile"))

    db = connct()
    if not db:
        flash("Connessione al database fallita", "error")
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

@app.route("/forgot", methods=["GET", "POST"])
def forgot():

    if "user_id" in session:
        flash("Sei già registrato, non è necessario cambiare password", "error")
        return redirect(url_for("index"))

    if request.method == "GET" and request.args.get("reset"):
        for key in ("code_sent", "code", "forgot_email", "sent_time"):
            session.pop(key, None)
        flash("Inserisci di nuovo la tua email", "error")
        return redirect(url_for("forgot"))

    # Stato della procedura: se il codice è già stato inviato
    code_sent = session.get("code_sent", False)
    # Email corrente (dal form o da sessione, se già inviata)
    email = request.form.get("email") or session.get("forgot_email")

    if request.method == "POST":
        # --- 1) Reinvia codice se richiesto
        if request.args.get("resend") and code_sent:
            now = time.time()
            if now - session.get("sent_time", 0) < 60:
                flash("Devi attendere qualche secondo prima di reinviare il codice", "error")
                return redirect(url_for("forgot"))
            # Reinvia
            code = email_sender(email)
            session['sent_time'] = now
            flash("Codice reinviato con successo", "success")
            return redirect(url_for("forgot"))

        # --- 2) Prima fase: invio email con codice
        if not code_sent:
            try:
                validate_email(email, check_deliverability=True)
                db = connct()
                cur = db.cursor()
                cur.execute("SELECT email FROM users WHERE email = ?", (email,))
                row = cur.fetchone()
                cur.close()
                db.close()
                if not row:
                    raise EmailNotValidError("Email non trovata nel database")
                code = email_sender(email)
                session['code'] = code
                session['code_sent'] = True
                session['forgot_email'] = email
                session['sent_time'] = time.time()
                flash("Codice di verifica inviato all'indirizzo indicato", "success")
                return redirect(url_for("forgot"))
            except EmailNotValidError as e:
                flash(f"Email invalida: {e}", "error")

        # --- 3) Seconda fase: verifica del codice inserito
        else:
            user_code = request.form.get("code", "")
            if user_code == session.get("code"):
                # Codice corretto: reindirizza al reset della password
                session.pop("code_sent", None)
                session['cambia_password'] = True
                return redirect(url_for("reset_password"))
            else:
                flash("Codice errato. Riprova o cambia email.", "error")

    return render_template("forgot.html", code_sent=code_sent, email=email)


@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if "user_id" in session:
        flash("Sei già registrato, non è necessario resettare password", "error")
        return redirect(url_for("index"))
    if session.get("cambia_password", False):
        flash("uwu", "error")
    else:
        flash("owo", "success")
    return render_template("reset_password.html");

@app.route("/send_request/<int:receiver_id>", methods=["POST"])
def send_request(receiver_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    sender_id = session["user_id"]
    request_type = request.form.get("type", "contact_request")
    message = request.form.get("message", "")

    try:
        cur = g.db.cursor()
        cur.execute("""
            INSERT INTO notifications (receiver_id, sender_id, type, message)
            VALUES (?, ?, ?, ?)
        """, (receiver_id, sender_id, request_type, message))
        g.db.commit()
        flash("Richiesta inviata con successo", "success")
    except Exception as e:
        g.db.rollback()
        flash(f"Errore: {str(e)}", "error")
    
    return redirect(url_for("view_user", user_id=receiver_id))
@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    cur = g.db.cursor(dictionary=True)
    cur.execute("""
        SELECT n.*,
            u.Username as sender_name,
            u.profile_pic as sender_pic,
            u.user_type as user_type
        FROM notifications n
        JOIN users u ON n.sender_id = u.id
        WHERE n.receiver_id = ?
        ORDER BY n.created_at DESC
    """, (session['user_id'],))
    notifications = cur.fetchall()
    
    return render_template("notifications.html", notifications=notifications)

@app.route("/handle_notification/<int:notification_id>", methods=["POST"])
def handle_notification(notification_id):
    action = request.form.get("action")
    if action not in ["accept", "reject"]:
        return redirect(url_for("notifications"))

    try:
        cur = g.db.cursor(dictionary=True)

        cur.execute("""
            SELECT n.*, u.email as sender_email
            FROM notifications n
            JOIN users u ON n.sender_id = u.id
            WHERE n.id = ?
        """, (notification_id,))
        notification = cur.fetchone()

        if not notification:
            flash("Notifica non trovata", "error")
            return redirect(url_for("notifications"))

        new_status = "accepted" if action == "accept" else "rejected"
        cur.execute("""
            UPDATE notifications
            SET status = ?
            WHERE id = ?
        """, (new_status, notification_id))

        if action == "accept":
            if notification['type'] == 'contact_request':
                cur.execute("""
                    INSERT INTO connections (user1_id, user2_id)
                    VALUES (?, ?)
                """, (notification['receiver_id'], notification['sender_id']))

                send_notification_email(
                    receiver_email=notification['sender_email'],
                    message="La tua richiesta di contatto è stata accettata!"
                )

        g.db.commit()
        flash(f"Richiesta {new_status} con successo", "success")

    except Exception as e:
        g.db.rollback()
        flash(f"Errore: {str(e)}", "error")
    
    return redirect(url_for("notifications"))

def send_notification_email(receiver_email: str, message: str):
    msg = EmailMessage()
    msg["Subject"] = "Aggiornamento richiesta - Iu-ventus"
    msg["From"] = configurazioni['smtp_user']
    msg["To"] = receiver_email

    html = f"""<!DOCTYPE html>
    <html>
    <body>
        <p>La tua richiesta ha ricevuto un aggiornamento:</p>
        <p><strong>{message}</strong></p>
    </body>
    </html>"""
    
    msg.add_alternative(html, subtype="html")
    
    try:
        with smtplib.SMTP(configurazioni['smtp_server'], configurazioni['smtp_port']) as server:
            server.starttls()
            server.login(configurazioni['smtp_user'], configurazioni['smtp_password'])
            server.send_message(msg)
    except Exception as e:
        print(f"Errore invio email: {str(e)}")

@app.before_request
def check_notifications():
    if "user_id" in session:
        cur = g.db.cursor(dictionary=True)
        cur.execute("""
            SELECT COUNT(*) as count
            FROM notifications
            WHERE receiver_id = ?
            AND status='unread'
        """, (session['user_id'],))
        result = cur.fetchone()
        g.unread_count = result['count'] if result else 0

@app.route("/info")
def info():
    return render_template("info.html")

if __name__ == "__main__":
    app.run(debug=True)
