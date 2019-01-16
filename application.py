import functools, os

from flask import Flask, flash, g, session, redirect, render_template, request, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# wrapper for checking if user is logged in
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if session.get('user_id') is None:
            return redirect(url_for('login'))
        
        return view(**kwargs)
    
    return wrapped_view

@app.route("/")
@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    return render_template('search.html')


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        error = None

        if not username:
            error = 'Username required.'
        elif not password:
            error = 'Password required.'
        elif db.execute('SELECT * FROM users WHERE username = :username', {'username': username}).fetchone() is not None:
            error = f"User {username} is already registered."

        if error is None:
            db.execute(
                'INSERT INTO users (username, password) VALUES (:username, :password_hash)',
                        {'username': username, 'password_hash': generate_password_hash(password)}
                    )
            db.commit()
            flash(f'User {username} registered.')
            return redirect(url_for('login'))

        flash(error)
    
    return render_template('register.html')

# as in Flask documentation
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        error = None
        user = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchone()

        if user is None:
            error = 'Invalid username.'
        elif not check_password_hash(user['password'], password):
            error = 'Invalid password.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('search'))

        flash(error)

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('search'))
