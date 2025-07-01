from flask import Blueprint, render_template, request, redirect, url_for, session
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = client["user_db"]
users_collection = db["users"]
students_collection = db["students"]  # Collection for student data

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
        user_type = request.form.get("user_type", "faculty")  # Get user type from form
        student_id = request.form.get("student_id", "")  # For parent registration

        # Check if user exists
        if users_collection.find_one({"email": email}):
            message = "Email already registered."
        else:
            # Validate parent registration
            if user_type == "parent":
                if not student_id:
                    message = "Student ID is required for parent registration."
                else:
                    # Check if another parent is already linked to this student
                    existing_parent = users_collection.find_one({
                        "user_type": "parent",
                        "student_id": student_id
                    })
                    if existing_parent:
                        message = "A parent account is already linked to this student ID."
                    else:
                        # Create parent account
                        user_data = {
                            "username": username,
                            "email": email,
                            "password": password,
                            "user_type": user_type,
                            "student_id": student_id
                        }
                        users_collection.insert_one(user_data)
                        return redirect(url_for("auth.login"))
            else:
                # Create faculty account
                user_data = {
                    "username": username,
                    "email": email,
                    "password": password,
                    "user_type": user_type
                }
                users_collection.insert_one(user_data)
                return redirect(url_for("auth.login"))
    
    return render_template("register.html", message=message)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    message = ""
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        login_type = request.form.get("login_type", "faculty")
        student_id = request.form.get("student_id", "")

        user = users_collection.find_one({"email": email})
        
        if user and check_password_hash(user["password"], password):
            # Check if login type matches user type in database
            user_type = user.get("user_type", "faculty")  # Default to faculty for existing users
            
            if login_type == "parent":
                # For parent login, verify student_id
                if user_type != "parent":
                    message = "This account is not registered as a parent account."
                elif not student_id:
                    message = "Student ID is required for parent login."
                elif user.get("student_id") != student_id:
                    message = "Invalid student ID for this parent account."
                else:
                    session["user"] = user["username"]
                    session["user_type"] = "parent"
                    session["student_id"] = student_id
                    session["student_name"] = f"Student {student_id}"  # Better default name
                    # return redirect(url_for("chat.ai_chat"))  # Redirect to chat instead of rendering template
                    return render_template("index.html")
            else:
                # Faculty login
                if user_type == "parent":
                    message = "This account is registered as a parent account. Please use parent login."
                else:
                    session["user"] = user["username"]
                    session["user_type"] = "faculty"
                    # return redirect(url_for("chat.ai_chat"))  # Redirect to chat instead of rendering template
                    return render_template("index.html")
        else:
            message = "Invalid credentials."
    
    return render_template("login.html", message=message)

@auth_bp.route("/logout")
def logout():
    session.clear()  # Clear all session data
    return redirect(url_for("auth.login"))
