"""Seed an initial admin user in Firestore."""
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.core.auth import hash_password
from backend.app.core.database import get_firestore


def seed_admin(email: str, password: str, full_name: str = "Admin"):
    db = get_firestore()

    # Check if admin already exists
    existing = list(db.collection("users").where("email", "==", email).limit(1).stream())
    if existing:
        print(f"User {email} already exists.")
        return

    user_doc = {
        "full_name": full_name,
        "email": email,
        "password_hash": hash_password(password),
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "system",
    }
    _, ref = db.collection("users").add(user_doc)
    print(f"Admin user created: {email} (ID: {ref.id})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python seed_admin.py <email> <password> [full_name]")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else "Admin"
    seed_admin(email, password, name)
