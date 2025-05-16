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

@app.route("/", methods=["GET"])
def index():
    q = request.args.get("q", "").strip().lower()
    user_id = session.get("user_id")
    user_type = session.get("user_type")

    cur = g.db.cursor(dictionary=True)

    # scegliamo quali colonne prendere in base al tipo
    if user_id:
        if user_type == "Student":
            cur.execute("SELECT id, email, user_type, address, phone FROM users WHERE user_type='Business'")
        elif user_type == "Business":
            cur.execute("SELECT id, email, user_type, cv_file FROM users WHERE user_type='Student'")
        elif user_type == "Admin":
            # admin vede TUTTI
            cur.execute("""
                SELECT id, email, user_type, address, phone, cv_file
                FROM users
            """)
        else:
            cur.execute("SELECT id, email, user_type FROM users")
    else:
        # guest
        cur.execute("SELECT id, email, user_type FROM users")

    users = cur.fetchall()
    users_with_scores = []

    for u in users:
        uid = u['id']
        # prendi i tag
        cur.execute(
            "SELECT t.name FROM tags t JOIN user_tags ut ON ut.tag_id = t.id WHERE ut.user_id = ?",
            (uid,)
        )
        tags = [r['name'] for r in cur.fetchall()]

        # calcola score
        score = 0
        if q:
            score = sum(1 for t in tags if q in t.lower())

        u['tags'] = tags
        users_with_scores.append((u, score))

    users_with_scores.sort(key=lambda x: x[1], reverse=True)
    return render_template("index.html", users_with_scores=users_with_scores)


# Registrazione
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
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
                        "INSERT INTO users (email, password, user_type) VALUES (?, ?, ?)",
                        (email, hashed_password, user_type)
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

    if request.method == "POST":
        # bio & profile pic
        bio = request.form.get("bio", "")
        file = request.files.get("profile_pic")
        if file and allowed_file(file.filename):
            pic_filename = secure_filename(f"user_{user_id}.png")
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], pic_filename)
            img = Image.open(file).convert("RGB")
            img.thumbnail((200, 200), Image.Resampling.LANCZOS)
            img.save(filepath)
            cur.execute("UPDATE users SET bio=?, profile_pic=? WHERE id=?", (bio, pic_filename, user_id))
        else:
            cur.execute("UPDATE users SET bio=? WHERE id=?", (bio, user_id))

        # — Studenti: carica CV + tags
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

        # — Azienda
        if user_type == "Business":
            address = request.form.get("address", "")
            phone   = request.form.get("phone", "")
            cur.execute("UPDATE users SET address=?, phone=? WHERE id=?", (address, phone, user_id))
            tags = request.form.get("tags", "")
            tag_list = [t.strip() for t in tags.split(",") if t.strip()][:3]
            cur.execute("DELETE FROM user_tags WHERE user_id=?", (user_id,))
            for t in tag_list:
                tid = get_or_create_tag(t)
                cur.execute("INSERT INTO user_tags (user_id, tag_id) VALUES (?,?)", (user_id, tid))

        g.db.commit()
        flash("Profilo aggiornato con successo", "success")
        return redirect(url_for("profile"))

    # GET: recupera dati esistenti
    cur.execute("SELECT email, user_type, profile_pic, bio, cv_file, address, phone FROM users WHERE id=?", (user_id,))
    email, user_type, profile_pic, bio, cv_file, address, phone = cur.fetchone()

    # recupera i tag selezionati
    cur.execute("""
        SELECT t.name FROM tags t
        JOIN user_tags ut ON ut.tag_id = t.id
        WHERE ut.user_id = ?
    """, (user_id,))
    user_tags = [row[0] for row in cur.fetchall()]

    # recupera tutti i tag con contatore per il form
    cur.execute("""
        SELECT t.name, COUNT(ut.user_id) as cnt
        FROM tags t
        LEFT JOIN user_tags ut ON ut.tag_id = t.id
        GROUP BY t.id
        ORDER BY cnt DESC
    """)
    all_tags = [{"name": row[0], "count": row[1]} for row in cur.fetchall()]

    return render_template(
        "profile.html",
        email=email,
        user_type=user_type,
        profile_pic=profile_pic,
        bio=bio,
        cv_file=cv_file,
        address=address,
        phone=phone,
        user_tags=user_tags,
        all_tags=all_tags
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
        SELECT id, email, user_type, profile_pic, bio, cv_file, address, phone
        FROM users
        WHERE id = ?
    """, (user_id,))
    row = cur.fetchone()
    if not row:
        flash("Utente non trovato", "error")
        return redirect(url_for("index"))

    user = {
        "id":       row[0],
        "email":    row[1],
        "user_type":row[2],
        "profile_pic": row[3],
        "bio":      row[4],
        "cv_file":  row[5],
        "address":  row[6],
        "phone":    row[7]
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


if __name__ == "__main__":
    app.run(debug=True)
