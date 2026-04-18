import sys
sys.path.append('.')
from backend.memory_db import init_memory_db
try:
    init_memory_db()
    print("MIGRATION SUCCESSFUL")
except Exception as e:
    print(f"MIGRATION FAILED: {e}")
