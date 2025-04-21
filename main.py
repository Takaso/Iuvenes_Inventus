from flask import Flask, render_template, request, redirect, url_for, session;
import mariadb; import bcrypt;

app = Flask(__name__);
app.secret_key = "supersecretkey"; # Serve per le sessioni

# Qui ci connettiamo al database
def connct():
    try:
        return mariadb.connect(
            host="127.0.0.1",
            user="root",
            password="",
            database="user_auth"
        );
    except mariadb.Error as e:
        print(f"Database connection failed: {e}")
        return None;

# Questa funzione serve per generare una password sicura
def generate_password_hash(password: str) -> str:
    byte_ = password.encode("utf-8");
    return bcrypt.hashpw(byte_, bcrypt.gensalt()).decode("utf-8");

# La home
@app.route("/")
def index():
    return render_template("index.html");

# Questa è la pagina di register
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"];
        password = request.form["password"];
        user_type = request.form["user_type"];
        hashed_password = generate_password_hash(password);
        connection = connct();
        if connection: # Se si connette al database
            try:
                cursor = connection.cursor();
                cursor.execute(
                    "INSERT INTO users (email, password, user_type) VALUES (?, ?, ?)",
                    (email, hashed_password, user_type),
                ); connection.commit(); # Eseguiamo l'SQL di inserire nel DB i valori e confermiamo la connessione
                return redirect(url_for("login")); # Una volta fatto ti manda al login
            except mariadb.Error as e:
                return f"Error: {e}";
            finally:
                cursor.close(); connection.close();
    return render_template("signup.html");

# Pagina del login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]; password = request.form["password"]; # Prende i dati dal form
        connection = connct(); # Si connette al database
        if connection:
            try:
                cursor = connection.cursor();
                cursor.execute("SELECT id, password, user_type FROM users WHERE email = ?", (email,));
                result = cursor.fetchone();
                if result and bcrypt.checkpw(password.encode("utf-8"), result[1].encode("utf-8")):
                    session["user_id"] = result[0]; # Crea la sessione utente
                    session["user_type"] = result[2];
                    return redirect(url_for("profile"));
                else:
                    return "Invalid email or password";
            except mariadb.Error as e:
                return f"Error: {e}";
            finally:
                cursor.close(); connection.close();
    return render_template("login.html");

# Profile endpoint
@app.route("/profile")
def profile():
    if "user_id" not in session: # Se non sei registrato manda al login
        return redirect(url_for("login"));
    user_type = session.get("user_type", "Student"); # Sessione di default: Studente
    return render_template("profile.html", user_type=user_type);

# Logout endpoit
@app.route("/logout")
def logout():
    session.clear(); # Elimina la sessione
    return redirect(url_for("login"));

@app.route("/view_database")
def view_database():
    if session.get("user_type") != "Admin":
        return redirect(url_for("profile")); # Ti rimanda a /profile se non sei admin
    db = connct()
    if db:
        cursor = db.cursor(); # Accedi al database
        cursor.execute("SELECT id, email, user_type FROM users"); # Esegui comando SQL
        users = [{"id": row[0], "email": row[1], "user_type": row[2]} for row in cursor.fetchall()]; # Mette in lista i dati
        cursor.close(); # Chiude la sessione
        db.close();
        return render_template("view_database.html", users=users); # Passa l'argomento al file html
    else:
        return "Database connection failed"; 

if __name__ == "__main__":
    app.run(debug=True)
