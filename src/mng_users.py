import json
import os
from werkzeug.security import generate_password_hash

USERS_FILE = "configs/users.json"


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def add_user(username, password):

    users = load_users()

    # בדיקה אם המשתמש כבר קיים
    for u in users:
        if u["username"] == username:
            print("User already exists")
            return

    user_id = max([u["id"] for u in users], default=0) + 1

    password_hash = generate_password_hash(password)

    users.append({
        "id": user_id,
        "username": username,
        "password": password_hash
    })

    save_users(users)

    print("User created successfully")


if __name__ == "__main__":

    username = input("Username: ")
    password = input("Password: ")

    add_user(username, password)