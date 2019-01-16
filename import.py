import csv, os
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

engine = create_engine(os.getenv('DATABASE_URL'))
db = scoped_session(sessionmaker(bind=engine))

# create table for books if it does not exist yet
db.execute("""CREATE TABLE IF NOT EXISTS books 
            (
            id SERIAL PRIMARY KEY, 
            isbn VARCHAR(15) NOT NULL, 
            title VARCHAR(300) NOT NULL, 
            author VARCHAR(100) NOT NULL, 
            year INTEGER NOT NULL
            )
            """
        )

# write data from .csv to books table
with open('books.csv', 'r') as f:
    reader = csv.reader(f)
    
    # skip row headings
    next(reader)
    # write data to SQL table (the primitive way)
    for isbn, title, author, year in reader:
        db.execute("""INSERT INTO books (isbn, title, author, year) 
                    VALUES (:isbn, :title, :author, :year )""", 
                    {"isbn": isbn, "title": title, "author": author, "year": year})
    db.commit()


