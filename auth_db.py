import bcrypt
import sqlite3
from contextlib import contextmanager


DB_FILE = "users.sqlite"
MIN_PASSWORD_BYTES = 12
MAX_PASSWORD_BYTES = 72
BCRYPT_ROUNDS = 12


def _password_bytes(password: str):
    password_bytes = password.encode("utf-8")
    if len(password_bytes) < MIN_PASSWORD_BYTES:
        return None, f"Password must be at least {MIN_PASSWORD_BYTES} bytes long."
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        return None, f"Password must be at most {MAX_PASSWORD_BYTES} bytes long."
    return password_bytes, None


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _database():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with _database() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_verified BOOLEAN NOT NULL DEFAULT 1
            )
            """
        )

        # Email verification and password reset were removed. Drop any
        # leftover one-time token tables from earlier versions.
        conn.execute("DROP TABLE IF EXISTS verification_tokens")
        conn.execute("DROP TABLE IF EXISTS password_reset_tokens")


def get_user_by_email(email: str):
    email = email.strip().lower()
    with _database() as conn:
        user = conn.execute(
            "SELECT id, email, password_hash, is_verified FROM users WHERE email = ?", (email,)
        ).fetchone()
    if user:
        return {"id": user[0], "email": user[1], "password_hash": user[2], "is_verified": bool(user[3])}
    return None


def create_user(email: str, password: str):
    email = email.strip().lower()
    password_bytes, error = _password_bytes(password)
    if error:
        return False, error

    if get_user_by_email(email):
        return False, "Email already exists"

    password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")
    try:
        with _database() as conn:
            conn.execute(
                "INSERT INTO users (email, password_hash, is_verified) VALUES (?, ?, 1)",
                (email, password_hash),
            )
        return True, "User created successfully"
    except sqlite3.IntegrityError:
        return False, "Email already exists"


def verify_password(plain_password: str, hashed_password: str):
    password_bytes, error = _password_bytes(plain_password)
    if error:
        return False
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


init_db()
