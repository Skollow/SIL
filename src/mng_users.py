"""
mng_users.py – Admin CLI tool for managing users.
This is only used if you re-enable authentication in the future.
Run from the command line: python mng_users.py
"""

import json
import os
import getpass
from werkzeug.security import generate_password_hash

USERS_FILE = "configs/users.json"


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_users(users):
    os.makedirs("configs", exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def add_user(username, password):
    users = load_users()
    for u in users:
        if u["username"] == username:
            print("User already exists.")
            return
    user_id = max((u["id"] for u in users), default=0) + 1
    users.append({
        "id": user_id,
        "username": username,
        "password": generate_password_hash(password)
    })
    save_users(users)
    print(f"User '{username}' created successfully.")


def list_users():
    users = load_users()
    if not users:
        print("No users found.")
        return
    for u in users:
        print(f"  ID: {u['id']}  Username: {u['username']}")


def delete_user(username):
    users = load_users()
    new_users = [u for u in users if u["username"] != username]
    if len(new_users) == len(users):
        print(f"User '{username}' not found.")
        return
    save_users(new_users)
    print(f"User '{username}' deleted.")


if __name__ == "__main__":
    print("=== User Management ===")
    print("1. Add user")
    print("2. List users")
    print("3. Delete user")
    choice = input("Choose (1/2/3): ").strip()

    if choice == "1":
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        add_user(username, password)
    elif choice == "2":
        list_users()
    elif choice == "3":
        username = input("Username to delete: ").strip()
        delete_user(username)
    else:
        print("Invalid choice.")
