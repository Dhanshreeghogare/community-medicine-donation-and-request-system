from flask import Blueprint, request, jsonify
from database import get_db
import bcrypt

auth = Blueprint("auth", __name__)
db = get_db()


@auth.route("/register", methods=["POST"])
def register():
    data = request.json
    name = data["name"]
    email = data["email"]
    password = data["password"]

    # check if user exists
    if db.users.find_one({"email": email}):
        return jsonify({"msg": "Email already registered"})

    # hash password
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    db.users.insert_one({
        "name": name,
        "email": email,
        "password": hashed_pw
    })

    return jsonify({"msg": "User Registered Successfully"})


@auth.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data["email"]
    password = data["password"]

    user = db.users.find_one({"email": email})

    if not user:
        return jsonify({"msg": "User not found"})

    if not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
        return jsonify({"msg": "Incorrect Password"})

    return jsonify({"msg": "Login Successful", "name": user["name"]})
