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
        cur.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,))
        post_owner = cur.fetchone()
        if post_owner and post_owner[0] != session['user_id']:
            cur.execute("SELECT Username FROM users WHERE id = ?", (session['user_id'],))
            username = cur.fetchone()[0] or "Someone"
            cur.execute("""
                INSERT INTO notifications (receiver_id, sender_id, type, message)
                VALUES (?, ?, 'comment', ?)
            """, (post_owner[0], session['user_id'], f"💬 {username} commented on your post"))
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
            return handle_user_search(cur, user_type)
        else:
            return handle_default_view(cur, user_id, user_type)

    except Exception as e:
        flash(f"Errore durante il caricamento: {str(e)}", "error")
        return redirect(url_for("index"))

def handle_post_search(cur, user_id):
    post_q = request.args.get("post_q", "").strip().lower()
    post_search_field = request.args.get("post_search_field", "content")
    posts = []

    # Costruzione query in base al campo di ricerca
    if post_search_field in ["content", "title"]:
        cur.execute(f"""
            SELECT p.*, u.Username, u.profile_pic, u.user_type
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE LOWER(p.{post_search_field}) LIKE ?
            ORDER BY p.creation_date DESC
            LIMIT 50
        """, (f"%{post_q}%",))
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
        """, (f"%{post_q}%",))

    posts = cur.fetchall()
    _add_post_metadata(cur, posts)
    return render_template("index.html", posts=posts, search_type="posts")

def handle_user_search(cur, current_user_type):
    user_q = request.args.get("user_q", "").strip().lower()
    user_search_field = request.args.get("user_search_field", "username")
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

    if user_search_field == "username":
        query = base_query.format(
            join_clause="",
            search_field="u.Username",
            user_type_clause=f"AND u.user_type = '{target_type}'" if target_type else ""
        )
        params = [f"%{user_q}%"]
    else:  # Ricerca per tag
        query = base_query.format(
            join_clause="JOIN user_tags ut ON u.id = ut.user_id JOIN tags t ON ut.tag_id = t.id",
            search_field="t.name",
            user_type_clause=f"AND u.user_type = '{target_type}'" if target_type else ""
        )
        params = [f"%{user_q}%"]

    cur.execute(query, params)
    users = cur.fetchall()

    # Calcola gli score
    for user in users:
        cur.execute("SELECT t.name FROM user_tags ut JOIN tags t ON ut.tag_id = t.id WHERE ut.user_id = ?", (user['id'],))
        tags = [row['name'].lower() for row in cur.fetchall()]
        
        score = 0
        if user_q:
            if user_search_field == "username":
                score += 100 if user_q in user['Username'].lower() else 0
            score += sum(10 for tag in tags if user_q in tag)
        
        user['tags'] = tags
        users_with_scores.append((user, min(score, 100)))

    users_with_scores.sort(key=lambda x: x[1], reverse=True)
    return render_template("index.html", users_with_scores=users_with_scores, search_type="users")

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

    return render_template("index.html", posts=posts, users_with_scores=users_with_scores, search_type="posts")

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

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        username = request.form.get("username", "").strip() or None
        user_type = request.form.get("user_type", "Student")

        error = False

        # Validazione email
        try:
            validate_email(email, check_deliverability=True)
        except EmailNotValidError as e:
            flash(f"Email non valida: {str(e)}", "error")
            error = True

        # Validazione username
        if username and len(username) > 20:
            flash("L'username non può superare 20 caratteri", "error")
            error = True

        # Validazione password
        if len(password) < 8:
            flash("La password deve contenere almeno 8 caratteri", "error")
            error = True

        # Validazione user_type
        if user_type not in ("Student", "Business"):
            flash("Tipo utente non valido", "error")
            error = True

        if error:
            return render_template("signup.html")

        # Controllo email esistente
        try:
            with connct() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM users WHERE email = ?", (email,))
                    if cur.fetchone():
                        flash("Email già registrata", "error")
                        return render_template("signup.html")
                    
                    # Inserimento utente
                    hashed_password = generate_password_hash(password)
                    cur.execute(
                        """INSERT INTO users
                        (email, password, user_type, Username)
                        VALUES (?, ?, ?, ?)""",
                        (email, hashed_password, user_type, username)
                    )
                    conn.commit()

                    # Ottieni l'ID del nuovo utente e inizializza la sessione
                    new_user_id = cur.lastrowid
                    session['user_id'] = new_user_id
                    session['user_type'] = user_type

                    # Invia codice di verifica via email
                    verification_code = email_sender(email, "Iu-ventus | Verifica il tuo account")
                    cur.execute(
                        """UPDATE users
                        SET verification_code = ?, verification_code_expiry = ?
                        WHERE id = ?""",
                        (
                            verification_code,
                            datetime.now() + timedelta(minutes=30),
                            new_user_id
                        )
                    )
                    conn.commit()
                    
                    flash("Registrazione completata! Verifica la tua email.", "success")
                    return redirect(url_for("verify_account"))

        except mariadb.Error as e:
            flash(f"Errore di database: {str(e)}", "error")
            app.logger.error(f"Signup error: {str(e)}")
        
        except Exception as e:
            flash("Errore imprevisto durante la registrazione", "error")
            app.logger.error(f"Unexpected signup error: {str(e)}")

    return render_template("signup.html")

@app.route("/verify", methods=["GET", "POST"])
def verify_account():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        cur = g.db.cursor()
        cur.execute("""
            SELECT verification_code, verification_code_expiry, user_type
            FROM users
            WHERE id = ?
        """, (session['user_id'],))
        user = cur.fetchone()

        if user and code == user[0] and datetime.now() < user[1]:
            cur.execute("""
                UPDATE users
                SET verified = TRUE,
                    verification_code = NULL,
                    verification_code_expiry = NULL
                WHERE id = ?
            """, (session['user_id'],))
            g.db.commit()
            if user[2] == "Student":
                cur.execute("""
                INSERT INTO notifications (receiver_id, sender_id, type, message)
                VALUES (?, ?, 'system', ?)
            """, (session['user_id'], session['user_id'], "Benvenuto su Iu-ventus! Inizia a connetterti con le aziende"))
                g.db.commit()
            elif user[2] == "Business":
                return redirect(url_for("request_business_verification"))
            return redirect(url_for("profile"))
        else:
            flash("Codice non valido o scaduto", "error")
    
    return render_template("verify.html")

@app.route("/resend_code")
def resend_code():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        cur = g.db.cursor()
        # Get user email
        cur.execute("SELECT email, user_type FROM users WHERE id = ?", (session['user_id'],))
        user = cur.fetchone()
        
        if user:
            # Generate new verification code
            new_code = email_sender(user[0], "Iu-ventus | Nuovo codice di verifica")
            cur.execute("""
                UPDATE users
                SET verification_code = ?,
                    verification_code_expiry = ?
                WHERE id = ?
            """, (
                new_code,
                datetime.now() + timedelta(minutes=30),
                session['user_id']
            ))
            g.db.commit()
            flash("Nuovo codice inviato con successo!", "success")
        return redirect(url_for("verify_account"))
    except Exception as e:
        g.db.rollback()
        flash(f"Errore: {str(e)}", "error")
        return redirect(url_for("verify_account"))

@app.route("/request_business_verification", methods=["GET", "POST"])
def request_business_verification():
    if "user_id" not in session or session.get("user_type") != "Business":
        return redirect(url_for("index"))

    if request.method == "POST":
        details = request.form.get("details", "").strip()
        if not details:
            flash("Inserisci i dettagli della tua azienda", "error")
            return redirect(url_for("request_business_verification"))

        try:
            cur = g.db.cursor()
            cur.execute("""
                INSERT INTO verification_requests (user_id, details)
                VALUES (?, ?)
            """, (session['user_id'], details))
            g.db.commit()
            flash("Richiesta inviata. Attendi la verifica dell'amministratore.", "success")
        except Exception as e:
            g.db.rollback()
            flash(f"Errore: {str(e)}", "error")
    
    return render_template("business_verification.html")

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_BASE_DURATION = 30  # in secondi

@app.route("/login", methods=["GET", "POST"])
def login():
    now = datetime.now()

    # Inizializza valori di sessione
    if 'login_attempts' not in session:
        session['login_attempts'] = 0
    if 'lockout_multiplier' not in session:
        session['lockout_multiplier'] = 1

    # Controlla se siamo in lockout
    if 'lockout_until' in session:
        lockout_until = datetime.fromisoformat(session['lockout_until'])
        if now < lockout_until:
            remaining = int((lockout_until - now).total_seconds())
            flash(f"Hai superato il numero massimo di tentativi. Riprova tra {remaining} secondi.", "error")
            return render_template("login.html")
        else:
            # Expiry del lockout: azzera i tentativi, conserva multiplier
            session.pop('lockout_until', None)
            session['login_attempts'] = 0

    if request.method == "POST":
        # Dopo expiry, login_attempts è 0 e non entra qui finché non supera di nuovo MAX_LOGIN_ATTEMPTS
        if session['login_attempts'] >= MAX_LOGIN_ATTEMPTS:
            # Imposta nuovo lockout
            lock_duration = LOCKOUT_BASE_DURATION * session['lockout_multiplier']
            session['lockout_until'] = (now + timedelta(seconds=lock_duration)).isoformat()
            session['lockout_multiplier'] += 1
            flash(f"Hai superato il numero massimo di tentativi. Sessione bloccata per {lock_duration} secondi.", "error")
            return render_template("login.html")

        email = request.form.get("email")
        password = request.form.get("password")
        remember = request.form.get("remember")

        conn = connct()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, password, user_type, profile_pic, bio FROM users WHERE email = ?", (email,)
                )
                user = cur.fetchone()

                if user and bcrypt.checkpw(password.encode("utf-8"), user[1].encode("utf-8")):
                    # Login riuscito: reset completo dello stato
                    session.pop('login_attempts', None)
                    session.pop('lockout_until', None)
                    session.pop('lockout_multiplier', None)
                    session.permanent = bool(remember)
                    session['user_id'] = user[0]
                    session['user_type'] = user[2]
                    return redirect(url_for("profile"))
                else:
                    # Fallito: incrementa tentativi
                    session['login_attempts'] += 1
                    remaining = MAX_LOGIN_ATTEMPTS - session['login_attempts']
                    flash(f"Email o password sbagliati. Tentativi rimasti: {remaining}", "error")
            finally:
                cur.close()
                conn.close()

    return render_template("login.html")

@app.route("/admin/verifications")
def admin_verifications():
    if session.get("user_type") != "Admin":
        return redirect(url_for("index"))

    cur = g.db.cursor(dictionary=True)
    cur.execute("""
        SELECT vr.*, u.email, u.Username
        FROM verification_requests vr
        JOIN users u ON vr.user_id = u.id
        WHERE vr.status = 'pending'
    """)
    requests = cur.fetchall()
    
    return render_template("admin_verifications.html", requests=requests)

@app.route("/handle_verification/<int:request_id>", methods=["POST"])
def handle_verification(request_id):
    if session.get("user_type") != "Admin":
        return redirect(url_for("index"))

    action = request.form.get("action")

    try:
        cur = g.db.cursor()
        
        if action == "approve":
            cur.execute("SELECT user_id FROM verification_requests WHERE id = ?", (request_id,))
            result = cur.fetchone()
            if result:
                user_id = result[0]
                cur.execute("UPDATE users SET business_verified = TRUE WHERE id = ?", (user_id,))
                cur.execute("""
                    INSERT INTO notifications (receiver_id, sender_id, type, message)
                    VALUES (?, ?, 'business_verified', ?)
                """, (user_id, session['user_id'], "La verifica del tuo account è stata approvata! Ora sei un azienda ufficiale"))
        status = "approved" if action == "approve" else "rejected"
        
        cur.execute("UPDATE verification_requests SET status = ? WHERE id = ?", (status, request_id))
        g.db.commit()
        flash("Richiesta: %s" % status, "success")

    except Exception as e:
        g.db.rollback()
        flash(f"Errore: {str(e)}", "error")

    return redirect(url_for("admin_verifications"))

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
            linkedin = request.form.get("linkedin", "").strip()
            github = request.form.get("github", "").strip()
            website = request.form.get("website", "").strip()
            youtube = request.form.get("youtube", "").strip()
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
                cur.execute("""
                    UPDATE users
                    SET bio=?, profile_pic=?, Username=?,
                    linkedin=?, github=?, website=?, youtube=?
                    WHERE id=?
                """, (bio, pic_filename, username_input, linkedin, github, website, youtube, user_id))
            else:
                cur.execute("""
                    UPDATE users
                    SET bio=?, Username=?,
                        linkedin=?, github=?, website=?, youtube=?
                    WHERE id=?
                """, (bio, username_input, linkedin, github, website, youtube, user_id))

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
    cur.execute("""
        SELECT email, user_type, profile_pic, bio, cv_file,
        address, phone, Username, linkedin, github, website, youtube
        FROM users
        WHERE id=?
    """, (user_id,))
    user_data = cur.fetchone()
    (email, user_type, profile_pic, bio, cv_file, address, phone, username, linkedin, github, website, youtube) = user_data

    cur.execute("SELECT t.name FROM tags t JOIN user_tags ut ON ut.tag_id = t.id WHERE ut.user_id = ?", (user_id,))
    user_tags = [row[0] for row in cur.fetchall()]

    return render_template(
        "profile.html",
        username=username or "",
        email=email,
        user_type=user_type,
        profile_pic=profile_pic,
        bio=bio,
        cv_file=cv_file,
        address=address,
        phone=phone,
        user_tags=user_tags,
        linkedin=linkedin,
        github=github,
        website=website,
        youtube=youtube,
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
        SELECT id, email, user_type, profile_pic, bio, cv_file, address, phone, Username, linkedin, github, website, youtube, verified, business_verified
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
        tags=tags,
        linkedin=row[9],  # Adjust index based on your select order
        github=row[10],
        website=row[11],
        youtube=row[12],
        verified=row[13],
        business_verified=row[14]
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
        flash("Sei già loggato", "error")
        return redirect(url_for("index"))
    
    if not session.get("cambia_password"):
        flash("Richiesta non valida", "error")
        return redirect(url_for("forgot"))

    email = session.get("forgot_email")
    if not email:
        flash("Sessione scaduta", "error")
        return redirect(url_for("forgot"))

    if request.method == "POST":
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not password or len(password) < 8:
            flash("La password deve avere almeno 8 caratteri", "error")
            return redirect(url_for("reset_password"))
        
        if password != confirm_password:
            flash("Le password non coincidono", "error")
            return redirect(url_for("reset_password"))

        try:
            cur = g.db.cursor()
            # Trova l'utente per email
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
            user = cur.fetchone()
            if not user:
                flash("Utente non trovato", "error")
                return redirect(url_for("forgot"))
            
            # Aggiorna la password
            hashed_pw = generate_password_hash(password)
            cur.execute("UPDATE users SET password = ? WHERE email = ?", (hashed_pw, email))
            g.db.commit()

            # Pulisci la sessione
            session.pop("cambia_password", None)
            session.pop("forgot_email", None)
            
            flash("Password reimpostata con successo! Accedi con la nuova password", "success")
            return redirect(url_for("login"))

        except Exception as e:
            g.db.rollback()
            flash(f"Errore durante l'aggiornamento: {str(e)}", "error")

    return render_template("reset_password.html")

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
        LEFT JOIN users u ON n.sender_id = u.id
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
                    La tua richiesta ha ricevuto un aggiornamento:
                </p>
                <div style="margin:30px 0; padding:20px; background-color:#e0e7ff; border-left:6px solid #1e40af; border-radius:4px;">
                    <strong style="font-size:16px; color:#1e3a8a;">{message}</strong>
                </div>
                <p style="font-size:14px; color:#555555;">
                    Se non ti aspettavi questa email, puoi ignorarla tranquillamente.
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

@app.route("/delete_account", methods=["POST"])
def delete_account():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    password = request.form.get("password", "")
    
    try:
        cur = g.db.cursor()
        # Get user data and password hash
        cur.execute("SELECT password, profile_pic, cv_file FROM users WHERE id = ?", (user_id,))
        user_data = cur.fetchone()
        if not user_data:
            flash("Utente non trovato", "error")
            return redirect(url_for("profile"))
        
        stored_hash, profile_pic, cv_file = user_data
        
        # Verify password
        if not bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            flash("Password non corretta", "error")
            return redirect(url_for("profile"))

        # Delete media files
        def safe_delete(filename):
            if filename:
                path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(path):
                    os.remove(path)
        
        safe_delete(profile_pic)
        safe_delete(cv_file)

        # Delete post images
        cur.execute("SELECT image FROM posts WHERE user_id = ?", (user_id,))
        for row in cur.fetchall():
            safe_delete(row[0])

        # Delete all user-related data from DB
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        g.db.commit()

        # Logout and clear session
        session.clear()
        flash("Account eliminato con successo", "success")
        return redirect(url_for("login"))

    except Exception as e:
        g.db.rollback()
        flash(f"Errore durante l'eliminazione: {str(e)}", "error")
        return redirect(url_for("profile"))

# main.py
@app.route("/admin_delete_user/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if session.get("user_type") != "Admin":
        flash("Non autorizzato", "error")
        return redirect(url_for("index"))
    
    reason = request.form.get("reason", "")
    send_email = request.form.get("send_email") == "on"

    try:
        cur = g.db.cursor()
        
        # Recupera i dati dell'utente
        cur.execute("SELECT email, profile_pic, cv_file FROM users WHERE id = ?", (user_id,))
        user_data = cur.fetchone()
        if not user_data:
            flash("Utente non trovato", "error")
            return redirect(url_for("view_database"))
        
        email, profile_pic, cv_file = user_data

        # Invia email di notifica
        if send_email and email:
            msg = EmailMessage()
            msg["Subject"] = "Account eliminato - Iu-ventus"
            msg["From"] = configurazioni['smtp_user']
            msg["To"] = email

            html = f"""<!DOCTYPE html>
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #1f2937; padding: 30px; border-radius: 10px;">
                    <h2 style="color: #ef4444; font-size: 24px;">Il tuo account è stato eliminato</h2>
                    <p style="color: #e5e7eb; font-size: 16px; margin-top: 20px;">
                        Motivo fornito dall'amministratore:<br>
                        <em style="color: #94a3b8;">{reason or 'Nessun motivo specificato'}</em>
                    </p>
                    <p style="color: #e5e7eb; margin-top: 30px;">
                        Per ulteriori informazioni, contatta il supporto.
                    </p>
                </div>
            </body>
            </html>"""
            msg.add_alternative(html, subtype="html")

            try:
                with smtplib.SMTP(configurazioni['smtp_server'], configurazioni['smtp_port']) as server:
                    server.starttls()
                    server.login(configurazioni['smtp_user'], configurazioni['smtp_password'])
                    server.send_message(msg)
            except Exception as e:
                app.logger.error(f"Errore invio email: {str(e)}")

        # Elimina file media
        def safe_delete(filename):
            if filename:
                path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(path):
                    os.remove(path)
        
        safe_delete(profile_pic)
        safe_delete(cv_file)

        # Elimina post correlati
        cur.execute("DELETE FROM posts WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        g.db.commit()
        
        flash("Account eliminato con successo", "success")
    except Exception as e:
        g.db.rollback()
        flash(f"Errore durante l'eliminazione: {str(e)}", "error")
    
    return redirect(url_for("view_database"))

@app.route("/messages")
def messages():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    cur = g.db.cursor(dictionary=True)
    # Tutte le connessioni dell'utente
    cur.execute("""
        SELECT c.id, u.id as other_user_id, u.Username, u.profile_pic, u.user_type
        FROM connections c
        JOIN users u ON (c.user1_id = u.id OR c.user2_id = u.id) AND u.id != %s
        WHERE c.user1_id = %s OR c.user2_id = %s
    """, (session['user_id'], session['user_id'], session['user_id']))
    
    connections = cur.fetchall()
    return render_template("messages.html", connections=connections)

@app.route("/messages/<int:connection_id>", methods=["GET", "POST"])
def view_messages(connection_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    cur = g.db.cursor(dictionary=True)
    # Verifica che l'user sia nella connessione
    cur.execute("""
        SELECT DISTINCT * FROM connections
        WHERE id = %s AND (user1_id = %s OR user2_id = %s)
    """, (connection_id, session['user_id'], session['user_id']))
    
    if not cur.fetchone():
        flash("Unauthorized", "error")
        return redirect(url_for("messages"))
    
    # Query per i messaggi
    cur.execute("""
        SELECT m.*, u.Username, u.profile_pic
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE connection_id = %s
        ORDER BY sent_at
    """, (connection_id,))
    messages = cur.fetchall()
    
    # Invio dei messaggi
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            try:
                cur.execute("""
                    INSERT INTO messages (connection_id, sender_id, content)
                    VALUES (%s, %s, %s)
                """, (connection_id, session['user_id'], content))
                g.db.commit()
            except Exception as e:
                g.db.rollback()
                flash(f"Error sending message: {str(e)}", "error")
    
    return render_template("chat.html", messages=messages, connection_id=connection_id)

if __name__ == "__main__":
    app.run(debug=True)
