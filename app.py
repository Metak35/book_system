
import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

@app.route("/")
def index():
    search = request.args.get("search", "").strip()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            if search:
                cursor.execute(
                    "SELECT id, title, author, inventory_number, available "
                    "FROM books WHERE title ILIKE %s ORDER BY id",
                    (f"%{search}%",)
                )
            else:
                cursor.execute(
                    "SELECT id, title, author, inventory_number, available "
                    "FROM books ORDER BY id"
                )

            books = cursor.fetchall()
            
            cursor.execute("SELECT id, name FROM readers ORDER BY id")
            readers = cursor.fetchall()

            cursor.execute("""
                SELECT
                    loans.id,
                    books.title,
                    readers.name,
                    loans.issue_date,
                    loans.return_date
                FROM loans
                JOIN books ON loans.book_id = books.id
                JOIN readers ON loans.reader_id = readers.id
                ORDER BY loans.id DESC
            """)
            loans = cursor.fetchall()

    return render_template(
        "index.html",
        books=books,
        search=search,
        readers=readers,
        loans=loans
    )

@app.route("/add", methods=["POST"])
def add_book():
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    inventory_number = request.form.get("inventory_number", "").strip()

    if not title or not author or not inventory_number:
        return "Заполните все поля!", 400

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO books (title, author, inventory_number, available)
                VALUES (%s, %s, %s, TRUE)
                """,
                (title, author, inventory_number)
            )

    return redirect(url_for("index"))

@app.route("/add_reader", methods=["POST"])
def add_reader():
    name = request.form.get("name", "").strip()

    if not name:
        return "Введите имя читателя!", 400

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO readers (name) VALUES (%s)",
                (name,)
            )

        conn.commit()

    print("Читатель успешно добавлен:", name)

    return redirect(url_for("index"))

@app.route("/loans/add", methods=["POST"])
def issue_book():
    book_id = request.form.get("book_id", type=int)
    reader_id = request.form.get("reader_id", type=int)

    if not book_id or not reader_id:
        return "Выберите книгу и читателя!", 400

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT available FROM books WHERE id = %s FOR UPDATE",
                (book_id,)
            )
            book = cursor.fetchone()

            if not book:
                return "Книга не найдена!", 404

            if not book[0]:
                return "Книга уже выдана!", 400

            cursor.execute(
                "SELECT id FROM readers WHERE id = %s",
                (reader_id,)
            )

            if not cursor.fetchone():
                return "Читатель не найден!", 404

            cursor.execute(
                """
                INSERT INTO loans (book_id, reader_id, issue_date)
                VALUES (%s, %s, CURRENT_DATE)
                """,
                (book_id, reader_id)
            )

            cursor.execute(
                "UPDATE books SET available = FALSE WHERE id = %s",
                (book_id,)
            )

    return redirect(url_for("index"))

@app.route("/loans/return/<int:loan_id>", methods=["POST"])
def return_book(loan_id):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT book_id
                FROM loans
                WHERE id = %s AND return_date IS NULL
                FOR UPDATE
                """,
                (loan_id,)
            )

            loan = cursor.fetchone()

            if not loan:
                return "Выдача не найдена или книга уже возвращена!", 404

            book_id = loan[0]

            cursor.execute(
                """
                UPDATE loans
                SET return_date = CURRENT_DATE
                WHERE id = %s
                """,
                (loan_id,)
            )

            cursor.execute(
                """
                UPDATE books
                SET available = TRUE
                WHERE id = %s
                """,
                (book_id,)
            )

    return redirect(url_for("index"))

if __name__ == "__main__":

    app.run(debug=True, port=5000)
