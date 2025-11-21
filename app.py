from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import bcrypt

load_dotenv()

app = Flask(__name__)

app.secret_key = "5f7b2943252caf397093d02c1a1b4bc2058bef83abad91958867a3092e93f3d7"   # required for session


# ---------------------------------------------------------------------
# CONNECT MONGODB (FINAL & CORRECT)
# ---------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise Exception("⚠ ERROR: MONGO_URI is missing in .env file!")

client = MongoClient(MONGO_URI)

try:
    client.admin.command("ping")
    print("✓ Connected to MongoDB successfully!")
except Exception as e:
    print("MongoDB Connection Error:", e)

db = client["CMDRS"]
users = db["users"]


# ---------------------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


# ---------------------------------------------------------------------
# REGISTRATION PAGE (GET)
# ---------------------------------------------------------------------
@app.route("/registration")
def registration_page():
    return render_template("registration.html")


# ---------------------------------------------------------------------
# LOGIN PAGE (GET)
# ---------------------------------------------------------------------
@app.route("/login")
def login_page():
    return render_template("login.html")


# ---------------------------------------------------------------------
# REGISTER USER (POST)
# ---------------------------------------------------------------------
@app.route("/registration", methods=["POST"])
def register_user():

    data = request.get_json()

    if not data:
        return jsonify({"success": False, "message": "Invalid JSON received!"}), 400

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    user_type = data.get("user_type")

    # Validate fields
    if not username or not email or not password or not user_type:
        return jsonify({"success": False, "message": "All fields are required!"}), 400

    # Check if email already exists
    existing_user = users.find_one({"email": email})
    if existing_user:
        return jsonify({"success": False, "message": "Email already registered!"}), 409

    # Hash password
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    # Insert new user
    users.insert_one({
        "username": username,
        "email": email,
        "password": hashed_pw,
        "user_type": user_type
    })

    return jsonify({"success": True, "message": "User registered successfully!"}), 201


# ---------------------------------------------------------------------
# LOGIN USER (POST)
# ---------------------------------------------------------------------
# # @app.route("/login", methods=["POST"])
# # def login_user():


#     data = request.get_json()

#     if not data:
#         return jsonify({"success": False, "message": "Invalid JSON received!"}), 400

#     email = data.get("email")
#     password = data.get("password")

#     if not email or not password:
#         return jsonify({"success": False, "message": "Email & password required!"}), 400

#     user = users.find_one({"email": email})

#     if not user:
#         return jsonify({"success": False, "message": "User not found!"}), 404

#     # Check password
#     if bcrypt.checkpw(password.encode("utf-8"), user["password"]):
#         return jsonify({"success": True, "message": "Login Successful!"})
#     else:
#         return jsonify({"success": False, "message": "Invalid password!"}), 401

@app.route("/login", methods=["POST"])
def login_user():

    data = request.get_json()

    if not data:
        return jsonify({"success": False, "message": "Invalid JSON!"}), 400

    email = data.get("email")
    password = data.get("password")

    user = users.find_one({"email": email})

    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 404

    if bcrypt.checkpw(password.encode("utf-8"), user["password"]):

        # ⭐ Save user session
        session["user"] = {
            "username": user["username"],
            "email": user["email"],
            "user_type": user["user_type"]
        }

        return jsonify({"success": True, "message": "Login successful!"})
    else:
        return jsonify({"success": False, "message": "Invalid password!"}), 401



@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/donor/dashboard")
def donor_dashboard():
    if not session.get("user"):
        return redirect("/login")

    return render_template("donor_dashboard.html", user=session["user"])

# ---------------------------------------------------------------------
# RUN SERVER
# ---------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
