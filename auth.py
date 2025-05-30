from flask import Blueprint, render_template, request, redirect, url_for, session
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = client["user_db"]
users_collection = db["users"]

auth_bp = Blueprint("auth", __name__)
USER_DB = "users.json"

def load_users():
    if not os.path.exists(USER_DB):
        return []
    with open(USER_DB, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USER_DB, "w") as f:
        json.dump(users, f, indent=4)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    message = ""
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        # Check if user exists
        if users_collection.find_one({"email": email}):
            message = "Email already registered."
        else:
            users_collection.insert_one({
                "username": username,
                "email": email,
                "password": password
            })
            return redirect(url_for("auth.login"))
    return render_template("register.html", message=message)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    message = ""
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = users_collection.find_one({"email": email})
        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            # return redirect(url_for("ai_chat"))
            return render_template("index.html", user=user["username"])
        else:
            message = "Invalid credentials."
    return render_template("login.html", message=message)

@auth_bp.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("auth.login"))
