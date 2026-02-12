from flask import Flask, render_template, request, jsonify, session, redirect
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import bcrypt
import uuid
from bson import ObjectId
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta



# ---------------------------------------------------------------------
# LOAD ENV VARIABLES
# ---------------------------------------------------------------------
load_dotenv()

app = Flask(__name__)
app.secret_key ="cmrds_secret_key_2026 "

UPLOAD_FOLDER = "static/medicine_images"
# PROFILE_UPLOAD_FOLDER = "static/profile_images"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# os.makedirs(PROFILE_UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
# app.config["PROFILE_UPLOAD_FOLDER"] = PROFILE_UPLOAD_FOLDER

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
donated_medicine = db["donated_medicine"]  

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
    user_type = data.get("user_type", "").lower()

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
        "user_type": user_type,
        
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



@app.route("/submit_donation", methods=["POST"])
def submit_donation():

    # 🔒 Ensure logged in donor
    user = session.get("user")
    if not user or user.get("user_type") != "donor":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    # -----------------------------
    # Get Form Data
    # -----------------------------
    medicine_name = request.form.get("medicineName")
    manufacturer = request.form.get("manufacturer")
    expiry_date = request.form.get("expiryDate")
    quantity = request.form.get("quantity")
    category = request.form.get("category")
    condition = request.form.get("condition")
    description = request.form.get("description")

    # -----------------------------
    # Basic Validation
    # -----------------------------
    if not medicine_name or not expiry_date or not quantity:
        return jsonify({
            "success": False,
            "message": "Required fields missing"
        }), 400

    # Quantity check
    try:
        quantity = int(quantity)
        if quantity <= 0:
            raise ValueError
    except:
        return jsonify({
            "success": False,
            "message": "Invalid quantity"
        }), 400

    # Expiry validation
    try:
        exp_date_obj = datetime.strptime(expiry_date, "%Y-%m-%d")
        if exp_date_obj.date() < datetime.utcnow().date():
            return jsonify({
                "success": False,
                "message": "Medicine already expired"
            }), 400
    except:
        return jsonify({
            "success": False,
            "message": "Invalid expiry format"
        }), 400

    # -----------------------------
    # Image Upload Handling
    # -----------------------------
    file = request.files.get("image")
    filename = None

    if file and file.filename != "":
        ext = file.filename.rsplit(".", 1)[-1]
        filename = f"{uuid.uuid4()}.{ext}"

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

    # -----------------------------
    # Store in MongoDB
    # -----------------------------
    donation_data = {
        "username": user["username"],
        "email": user["email"],
        "medicineName": medicine_name,
        "manufacturer": manufacturer,
        "expiryDate": expiry_date,
        "quantity": quantity,
        "category": category,
        "condition": condition,
        "description": description,
        "image": filename,
        "status": "available",
        "created_at": datetime.utcnow()
    }

    donated_medicine.insert_one(donation_data)

    return jsonify({
        "success": True,
        "message": "Medicine donated successfully!"
    })

# GET DONOR DASHBOARD STATS
# ---------------------------------------------------------------------
@app.route("/get_donor_stats", methods=["GET"])
def get_donor_stats():
    """Get donor dashboard statistics"""
    if not session.get("user") or session["user"]["user_type"] != "donor":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    user = session["user"]
    email = user["email"]
    
    # Get all donations by this donor
    all_donations = list(donated_medicine.find({"email": email}))
    
    # Calculate statistics
    total_donated = len(all_donations)
    
    # Successful donations (status: completed, collected, or delivered)
    successful = len([d for d in all_donations if d.get("status") in ["completed", "collected", "delivered"]])
    
    # Pending donations (status: available, pending, or approved)
    pending = len([d for d in all_donations if d.get("status") in ["available", "pending", "approved"]])
    
    # Lives impacted - calculate based on medicine quantity for successful donations
    lives_impacted = sum([d.get("quantity", 0) for d in all_donations if d.get("status") in ["completed", "collected", "delivered"]])
    
    # If no donations yet, set default values
    if total_donated == 0:
        total_donated = 0
        successful = 0
        pending = 0
        lives_impacted = 0
    
    return jsonify({
        "success": True,
        "stats": {
            "total_donated": total_donated,
            "successful": successful,
            "pending": pending,
            "lives_impacted": lives_impacted
        }
    })
    
# GET RECENT ACTIVITY
# ---------------------------------------------------------------------
@app.route("/get_recent_activity", methods=["GET"])
def get_recent_activity():
    """Get recent donation activity for the donor"""
    if not session.get("user") or session["user"]["user_type"] != "donor":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    user = session["user"]
    email = user["email"]
    
    # Get last 10 donations sorted by created_at (newest first)
    recent_donations = donated_medicine.find(
        {"email": email}
    ).sort("created_at", -1).limit(10)
    
    activities = []
    
    for donation in recent_donations:
        medicine_name = donation.get("medicineName", "Medicine")
        quantity = donation.get("quantity", 0)
        expiry_date = donation.get("expiryDate", "N/A")
        status = donation.get("status", "available")
        created_at = donation.get("created_at")
        
        # Handle case when created_at is None
        if not created_at:
            created_at = datetime.utcnow()
        
        # Calculate time ago
        time_diff = datetime.utcnow() - created_at
        
        if time_diff < timedelta(minutes=1):
            time_ago = "Just now"
        elif time_diff < timedelta(hours=1):
            minutes = int(time_diff.total_seconds() / 60)
            time_ago = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        elif time_diff < timedelta(days=1):
            hours = int(time_diff.total_seconds() / 3600)
            time_ago = f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif time_diff < timedelta(days=7):
            days = time_diff.days
            time_ago = f"{days} day{'s' if days > 1 else ''} ago"
        elif time_diff < timedelta(days=30):
            weeks = time_diff.days // 7
            time_ago = f"{weeks} week{'s' if weeks > 1 else ''} ago"
        else:
            time_ago = created_at.strftime("%b %d, %Y")
        
        # Simple activity object - just the essential data
        activities.append({
            "id": str(donation.get("_id")),
            "medicine_name": medicine_name,
            "quantity": quantity,
            "expiry_date": expiry_date,
            "status": status,
            "time_ago": time_ago
        })
    
    return jsonify({
        "success": True,
        "activities": activities
    })
    
    
# ---------------------------------------------------------------------
# GET ALL DONATIONS FOR DONOR
# ---------------------------------------------------------------------
@app.route("/get_all_donations", methods=["GET"])
def get_all_donations():
    """Get all donations for the donor (for history page)"""
    if not session.get("user") or session["user"]["user_type"] != "donor":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    user = session["user"]
    email = user["email"]
    
    # Get all donations by this donor
    all_donations = donated_medicine.find(
        {"email": email}
    ).sort("created_at", -1)
    
    donations = []
    
    for donation in all_donations:
        medicine_name = donation.get("medicineName", "Medicine")
        quantity = donation.get("quantity", 0)
        expiry_date = donation.get("expiryDate", "N/A")
        status = donation.get("status", "available")
        created_at = donation.get("created_at", datetime.utcnow())
        
        # Calculate time ago
        time_diff = datetime.utcnow() - created_at
        if time_diff < timedelta(minutes=1):
            time_ago = "Just now"
        elif time_diff < timedelta(hours=1):
            minutes = int(time_diff.total_seconds() / 60)
            time_ago = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        elif time_diff < timedelta(days=1):
            hours = int(time_diff.total_seconds() / 3600)
            time_ago = f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif time_diff < timedelta(days=7):
            days = time_diff.days
            time_ago = f"{days} day{'s' if days > 1 else ''} ago"
        else:
            time_ago = created_at.strftime("%b %d, %Y")
        
        donations.append({
            "id": str(donation.get("_id")),
            "medicine_name": medicine_name,
            "manufacturer": donation.get("manufacturer", ""),
            "quantity": quantity,
            "expiry_date": expiry_date,
            "category": donation.get("category", ""),
            "condition": donation.get("condition", ""),
            "description": donation.get("description", ""),
            "status": status,
            "image": donation.get("image", ""),
            "time_ago": time_ago,
            "created_at": created_at.isoformat() if created_at else None
        })
    
    return jsonify({
        "success": True,
        "donations": donations
    })

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
