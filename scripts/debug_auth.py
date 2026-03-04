import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append('/app/backend')

from dotenv import load_dotenv
ROOT_DIR = Path('/app/backend')
env_path = ROOT_DIR / ".env"
if not env_path.exists():
    env_path = ROOT_DIR.parent / ".env"
load_dotenv(env_path)

from core.auth import SECRET_KEY
from core.db import get_db_context

print(f"SECRET_KEY starts with: {SECRET_KEY[:5]}... (len: {len(SECRET_KEY)})")
print(f"Is default key? {SECRET_KEY == 'promptsrc_secret_key_change_in_production_2024'}")

with get_db_context() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, username FROM users")
    users = cursor.fetchall()
    print(f"Total users in DB: {len(users)}")
    for user in users:
        print(f"User: {user['id']} | {user['email']} | {user['username']}")
