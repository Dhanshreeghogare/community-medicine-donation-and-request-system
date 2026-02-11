from flask import Flask, render_template, request, jsonify, session, redirect
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import bcrypt

# ---------------------------------------------------------------------
# LOAD ENV VARIABLES
# ---------------------------------------------------------------------
load_dotenv()

app = Flask(__name__)
app.secret_key = "cmrds_secret_key_2026"

# ---------------------------------------------------------------------
# CONNECT TO MONGODB
# ---------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise Exception("⚠ ERROR: MONGO_URI is missing in .env file!")

client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsAllowInvalidCertificates=True
)

db = client["med_system"]

# Collections
donor_collection = db["donar"]
receiver_collection = db["receiver"]
admin_collection = db["admin"]

# ---------------------------------------------------------------------
# HOME
# ---------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")

# ---------------------------------------------------------------------
# REGISTRATION PAGE
# ---------------------------------------------------------------------
@app.route("/registration")
def registration_page():
    return render_template("registration.html")

# ---------------------------------------------------------------------
# LOGIN PAGE
# ---------------------------------------------------------------------
@app.route("/login")
def login_page():
    return render_template("login.html")

# ---------------------------------------------------------------------
# REGISTER USER
# ---------------------------------------------------------------------
@app.route("/registration", methods=["POST"])
def register_user():

    data = request.get_json()

    if not data:
        return jsonify({"success": False, "message": "Invalid JSON!"}), 400

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    user_type = data.get("user_type")

    if not username or not email or not password or not user_type:
        return jsonify({"success": False, "message": "All fields required!"}), 400

    # 🔥 Select collection based on user_type
    if user_type == "donor":
        collection = donor_collection
    elif user_type == "receiver":
        collection = receiver_collection
    elif user_type == "admin":
        collection = admin_collection
    else:
        return jsonify({"success": False, "message": "Invalid user type!"}), 400

    # Check if email already exists
    if collection.find_one({"email": email}):
        return jsonify({"success": False, "message": "Email already registered!"}), 409

    # Hash password
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    # Insert user
    collection.insert_one({
        "username": username,
        "email": email,
        "password": hashed_pw,
        "user_type": user_type
    })

    return jsonify({
        "success": True,
        "message": f"{user_type.capitalize()} registered successfully!"
    })


# ---------------------------------------------------------------------
# LOGIN USER
# ---------------------------------------------------------------------
@app.route("/login", methods=["POST"])
def login_user():

    data = request.get_json()

    if not data:
        return jsonify({"success": False, "message": "Invalid JSON!"}), 400

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"success": False, "message": "Email & password required!"}), 400

    user = None
    user_type = None

    # 🔥 Check in donor collection
    user = donor_collection.find_one({"email": email})
    if user:
        user_type = "donor"

    # 🔥 Check in receiver collection
    if not user:
        user = receiver_collection.find_one({"email": email})
        if user:
            user_type = "receiver"

    # 🔥 Check in admin collection
    if not user:
        user = admin_collection.find_one({"email": email})
        if user:
            user_type = "admin"

    if not user:
        return jsonify({"success": False, "message": "User not found!"}), 404

    # Check password
    if bcrypt.checkpw(password.encode("utf-8"), user["password"]):

        session["user"] = {
            "username": user["username"],
            "email": user["email"],
            "user_type": user_type
        }

        return jsonify({
            "success": True,
            "message": "Login successful!",
            "user_type": user_type
        })

    return jsonify({"success": False, "message": "Invalid password!"}), 401


# ---------------------------------------------------------------------
# DASHBOARDS
# ---------------------------------------------------------------------
@app.route("/donor/dashboard")
def donor_dashboard():
    if not session.get("user") or session["user"]["user_type"] != "donor":
        return redirect("/login")
    return render_template("donor_dashboard.html", user=session["user"])


@app.route("/receiver/dashboard")
def receiver_dashboard():
    if not session.get("user") or session["user"]["user_type"] != "receiver":
        return redirect("/login")
    return render_template("receiver_dashboard.html", user=session["user"])


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return redirect("/login")
    return render_template("admin_dashboard.html", user=session["user"])


# ---------------------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------------------------------------------------------------
# RUN SERVER
# ---------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
