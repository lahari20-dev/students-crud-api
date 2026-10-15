from contextlib import contextmanager
from datetime import date
from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field


DATABASE_PATH = Path(__file__).with_name("students.db")


@contextmanager
def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date_of_birth TEXT NOT NULL,
                email TEXT UNIQUE,
                phone TEXT,
                course TEXT
            )
            """
        )


def row_to_dict(row):
    return dict(row)


app = FastAPI(title="Student CRUD API")


# Create the database table when the app starts.
initialize_database()


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    email: str | None = None
    phone: str | None = None
    course: str | None = None


class StudentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: date | None = None
    email: str | None = None
    phone: str | None = None
    course: str | None = None


@app.get("/")
def home():
    return {"message": "Student CRUD API is running. Open /docs to try it."}


@app.post("/students", status_code=status.HTTP_201_CREATED)
def create_student(student: StudentCreate):
    values = student.model_dump()
    values["date_of_birth"] = values["date_of_birth"].isoformat()

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO students (name, date_of_birth, email, phone, course)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    values["name"],
                    values["date_of_birth"],
                    values["email"],
                    values["phone"],
                    values["course"],
                ),
            )

            row = connection.execute(
                "SELECT * FROM students WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

        return row_to_dict(row)

    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="That email is already in use")


@app.get("/students")
def list_students(
    name: str | None = Query(default=None, description="Search part of a name"),
    course: str | None = Query(default=None, description="Filter by course"),
):
    sql = "SELECT * FROM students WHERE 1 = 1"
    values = []

    if name:
        sql += " AND name LIKE ?"
        values.append(f"%{name}%")

    if course:
        sql += " AND course = ?"
        values.append(course)

    sql += " ORDER BY id"

    with get_connection() as connection:
        rows = connection.execute(sql, values).fetchall()

    return [row_to_dict(row) for row in rows]


@app.get("/students/{student_id}")
def get_student(student_id: int):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Student not found")

    return row_to_dict(row)


@app.put("/students/{student_id}")
def update_student(student_id: int, student: StudentUpdate):
    changes = student.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update",
        )

    if "name" in changes and changes["name"] is None:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    if "date_of_birth" in changes and changes["date_of_birth"] is None:
        raise HTTPException(
            status_code=400,
            detail="Date of birth cannot be empty",
        )

    if "date_of_birth" in changes:
        changes["date_of_birth"] = changes["date_of_birth"].isoformat()

    allowed_fields = {"name", "date_of_birth", "email", "phone", "course"}
    assignments = ", ".join(f"{field} = ?" for field in changes)
    values = list(changes.values()) + [student_id]

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                f"UPDATE students SET {assignments} WHERE id = ?",
                values,
            )

            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Student not found",
                )

            row = connection.execute(
                "SELECT * FROM students WHERE id = ?",
                (student_id,),
            ).fetchone()

        return row_to_dict(row)

    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="That email is already in use")


@app.delete("/students/{student_id}")
def delete_student(student_id: int):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM students WHERE id = ?",
            (student_id,),
        )

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Student not found")

    return {"message": "Student deleted successfully"}