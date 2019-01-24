import functools
import requests
import os

from flask import Flask, abort, flash, jsonify, session, redirect, render_template, request, url_for
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

# Check for environment variables
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

if not os.getenv("GOODREADS_API_KEY"):
    raise RuntimeError("GOODREADS_API_KEY is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# prepare tables
db.execute("""CREATE TABLE IF NOT EXISTS
              users
              (
                id SERIAL PRIMARY KEY,
                username VARCHAR(15) NOT NULL,
                password VARCHAR(100) NOT NULL
              ) """)

db.execute("""CREATE TABLE IF NOT EXISTS
              reviews
              (
                id SERIAL PRIMARY KEY,
                book_isbn VARCHAR(15) NOT NULL REFERENCES books(isbn),
                author_id INT NOT NULL REFERENCES users(id),
                text VARCHAR(1000) NOT NULL,
                rating INT NOT NULL,
                UNIQUE (book_isbn, author_id)
              ) """)

db.execute("""CREATE TABLE IF NOT EXISTS
              books
              (
                id SERIAL PRIMARY KEY,
                isbn VARCHAR(15) UNIQUE NOT NULL,
                title VARCHAR(300),
                author VARCHAR(100),
                year INT
              ) """)

db.commit()

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
    if request.method == "POST":
        q = request.form["q"]
        books = db.execute("""SELECT isbn, title, author
                            FROM books
                            WHERE isbn ILIKE :q
                            OR author ILIKE :q
                            OR title ILIKE :q""",
                            {"q": f"%{q}%"}).fetchall()
        if books:
            return render_template('search.html', books=books)

        flash('Could not find books matching your query')

    return render_template('search.html')


@app.route("/books/<isbn>", methods=["GET", "POST"])
@login_required
def book(isbn):
    if request.method == 'POST':

        review_rating = request.form['review-rating']
        review_text = request.form['review-text']

        db.execute("""INSERT INTO reviews (rating, text, book_isbn, author_id)
                    VALUES (:rating, :text, :book_isbn, :author_id)
                    ON CONFLICT DO NOTHING
                    """,
                    {"rating": review_rating,
                    "text": review_text,
                    "book_isbn": isbn,
                    "author_id": session["user_id"]}
                   )
        db.commit()

    # get book info from our DB
    book = db.execute("""SELECT isbn, title, author, year
                         FROM books WHERE isbn = :isbn""",
                         {"isbn": isbn}).fetchone()

    reviews = db.execute("""SELECT users.username, reviews.rating, reviews.text
                        FROM reviews
                        INNER JOIN users ON reviews.author_id = users.id
                        WHERE reviews.book_isbn = :isbn""",
                        {"isbn": isbn}).fetchall()

    # get additional book info from GoodReads API
    res = requests.get('https://www.goodreads.com/book/review_counts.json',
                       params={
                           "key": os.getenv('GOODREADS_API_KEY'), 
                           "isbns": isbn
                           }
                       )
    gr_data = res.json()['books'][0]

    # check if this user already reviewed the book
    # user can leave only 1 review
    already_reviewed = db.execute("""SELECT reviews.text FROM reviews
        WHERE reviews.author_id = :user_id AND reviews.book_isbn = :isbn""",
        {"user_id": session["user_id"], "isbn": isbn}
        ).fetchall()

    return render_template('book.html',
                           book=book,
                           gr_data=gr_data,
                           already_reviewed=already_reviewed,
                           reviews=reviews
                           )

# return JSONified book data on GET request
@app.route('/api/<isbn>')
def api(isbn):

    # prepare keys & fetch values for data
    keys = ['title', 'author', 'year', 'isbn', 'review_count', 'average_score']
    values = db.execute("""SELECT
            books.title, books.author, books.year, books.isbn,
            COUNT(reviews.rating), AVG(reviews.rating)
            FROM books
            LEFT JOIN reviews ON books.isbn = reviews.book_isbn
            WHERE books.isbn=:isbn
            GROUP BY books.title, books.author, books.year, books.isbn""",
            {"isbn": isbn}).fetchone()

    # if isbn is in our DB, build container, JSONify & return in
    if values:
        book_data = dict(zip(keys, values))
        return jsonify(book_data)

    # if isbn is not in our DB, return 404
    abort(404)


# almost as in Flask documentation
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
        elif db.execute('SELECT * FROM users WHERE username = :username',
                        {'username': username}).fetchone() is not None:
            error = f"User {username} is already registered."

        if error is None:
            db.execute(
                'INSERT INTO users (username, password) VALUES (:username, :password_hash)',
                {'username': username,
                    'password_hash': generate_password_hash(password)
                 }
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
        user = db.execute("SELECT * FROM users WHERE username = :username", 
                          {"username": username}).fetchone()

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


# as in Flask documentation
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.')
    return redirect(url_for('search'))
