import hashlib
import secrets
import base64
import sqlite3
import time
import uuid

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64url(salt)}${_b64url(digest)}"

def create_user(db_path, email, password):
    user_id = f"u_{uuid.uuid4().hex[:10]}"
    now = time.time()
    pwd_hash = _hash_password(password)
    
    conn = sqlite3.connect(db_path)
    try:
        # Check if user exists
        exists = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if exists:
            print(f"User {email} already exists.")
            return
            
        conn.execute(
            "INSERT INTO users (id, email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, pwd_hash, now, now)
        )
        conn.commit()
        print(f"User {email} created successfully.")
    except Exception as e:
        print(f"Error creating user: {e}")
    finally:
        conn.close()

def update_password(db_path, email, password):
    pwd_hash = _hash_password(password)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE email = ?", (pwd_hash, email))
        conn.commit()
        print(f"Password updated for {email}.")
    except Exception as e:
        print(f"Error updating password: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    db_path = ".cache/chatbot/app.sqlite"
    create_user(db_path, "test@example.com", "password123")
    update_password(db_path, "test@example.com", "password123")
    create_user(db_path, "admin@unipro.ai", "password123")
    update_password(db_path, "admin@unipro.ai", "password123")
