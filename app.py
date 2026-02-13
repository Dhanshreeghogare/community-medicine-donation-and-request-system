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
app.secret_key ="cmrds_secret_key_2026"

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
    "_id": str(user["_id"]),   # ⭐ IMPORTANT
    "username": user["username"],
    "email": user["email"],
    "user_type": user_type,
    "profile_image": user.get("profile_image")
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

    user_id = session["user"].get("_id")
    
    user = donor_collection.find_one({"_id": ObjectId(user_id)})
    
    # Convert ObjectId to string for JSON serialization
    if user and "_id" in user:
        user["_id"] = str(user["_id"])
    
    # IMPORTANT: Ensure profile_image is in the user object
    if "profile_image" not in user:
        user["profile_image"] = None
    
    return render_template("donor_dashboard.html", user=user)




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
    
    
PROFILE_FOLDER = "static/profile_images"
os.makedirs(PROFILE_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/upload_profile", methods=["POST"])
def upload_profile():

    if "user" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    file = request.files.get("profileImage")

    if not file or file.filename == "":
        return jsonify({"success": False, "message": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Invalid image type. Allowed: png, jpg, jpeg, gif"}), 400

    try:
        # Get user_id from session
        user_id = session["user"]["_id"]
        
        # Get old profile image to delete later
        old_user = donor_collection.find_one({"_id": ObjectId(user_id)})
        old_image = old_user.get("profile_image") if old_user else None
        
        # Generate unique filename
        ext = file.filename.rsplit(".", 1)[1].lower()
        unique_name = f"{user_id}_{uuid.uuid4().hex}.{ext}"

        # Save new file
        path = os.path.join(PROFILE_FOLDER, unique_name)
        file.save(path)

        # Update database with new image
        donor_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"profile_image": unique_name}}
        )

        # Delete old image file if it exists and is not the default
        if old_image and old_image != "default.png":
            old_path = os.path.join(PROFILE_FOLDER, old_image)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                    print(f"✅ Deleted old profile image: {old_image}")
                except Exception as e:
                    print(f"⚠ Could not delete old image: {e}")

        # Update session with new profile image
        session["user"]["profile_image"] = unique_name
        session.modified = True

        print(f"✅ Profile image uploaded successfully: {unique_name}")

        return jsonify({
            "success": True, 
            "filename": unique_name,
            "filepath": f"/static/profile_images/{unique_name}"
        })
        
    except Exception as e:
        print(f"❌ Error uploading profile image: {str(e)}")
        return jsonify({"success": False, "message": "Server error during upload"}), 500


# ========== NEW ROUTE TO DELETE PROFILE IMAGE ==========
@app.route("/delete_profile_image", methods=["POST"])
def delete_profile_image():
    """Delete user's profile image and reset to default"""
    
    if "user" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    try:
        user_id = session["user"]["_id"]
        
        # Get current profile image filename
        user = donor_collection.find_one({"_id": ObjectId(user_id)})
        old_image = user.get("profile_image") if user else None
        
        # Delete the image file if it exists and is not default
        if old_image and old_image != "default.png":
            old_path = os.path.join(PROFILE_FOLDER, old_image)
            if os.path.exists(old_path):
                os.remove(old_path)
                print(f"✅ Deleted profile image: {old_image}")
        
        # Update database - remove profile_image field
        donor_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$unset": {"profile_image": ""}}
        )
        
        # Update session
        session["user"]["profile_image"] = None
        session.modified = True
        
        return jsonify({
            "success": True,
            "message": "Profile image deleted successfully",
            "default_image": "https://cdn-icons-png.flaticon.com/512/847/847969.png"
        })
        
    except Exception as e:
        print(f"❌ Error deleting profile image: {str(e)}")
        return jsonify({"success": False, "message": "Server error during deletion"}), 500



@app.route("/receiver/dashboard")
def receiver_dashboard():
    """Receiver dashboard - view and request available medicines"""
    
    if not session.get("user") or session["user"]["user_type"] != "receiver":
        return redirect("/login")

    user_id = session["user"].get("_id")
    
    # Get fresh user data from database
    user = receiver_collection.find_one({"_id": ObjectId(user_id)})
    
    # Convert ObjectId to string for JSON serialization
    if user and "_id" in user:
        user["_id"] = str(user["_id"])
    
    # Ensure profile_image is in the user object
    if "profile_image" not in user:
        user["profile_image"] = None
    
    return render_template("receiver_dashboard.html", user=user)


# ========== RECEIVER DASHBOARD BACKEND ROUTES ==========

# ---------------------------------------------------------------------
# GET AVAILABLE MEDICINES FOR RECEIVER (FROM DONORS)
# ---------------------------------------------------------------------
@app.route("/get_available_medicines", methods=["GET"])
def get_available_medicines():
    """Get all available medicines donated by donors for receivers to browse"""
    
    if not session.get("user") or session["user"]["user_type"] != "receiver":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        # Get all medicines with status 'available'
        available_medicines = donated_medicine.find({"status": "available"}).sort("created_at", -1)
        
        medicines = []
        for medicine in available_medicines:
            # Calculate days until expiry
            expiry_date = medicine.get("expiryDate")
            days_until_expiry = None
            expiry_status = "safe"
            
            if expiry_date:
                try:
                    expiry = datetime.strptime(expiry_date, "%Y-%m-%d")
                    today = datetime.now()
                    days_until_expiry = (expiry - today).days
                    
                    if days_until_expiry < 0:
                        expiry_status = "expired"
                    elif days_until_expiry <= 30:
                        expiry_status = "expiring_soon"
                    elif days_until_expiry <= 90:
                        expiry_status = "moderate"
                    else:
                        expiry_status = "safe"
                except:
                    expiry_status = "unknown"
            
            medicines.append({
                "id": str(medicine.get("_id")),
                "medicine_name": medicine.get("medicineName", "Unknown"),
                "manufacturer": medicine.get("manufacturer", "Unknown"),
                "quantity": medicine.get("quantity", 0),
                "expiry_date": expiry_date,
                "days_until_expiry": days_until_expiry,
                "expiry_status": expiry_status,
                "category": medicine.get("category", "other"),
                "condition": medicine.get("condition", "good"),
                "description": medicine.get("description", ""),
                "image": medicine.get("image", ""),
                "donor_username": medicine.get("username", "Anonymous"),
                "donor_email": medicine.get("email", ""),
                "created_at": medicine.get("created_at").isoformat() if medicine.get("created_at") else None
            })
        
        return jsonify({
            "success": True,
            "medicines": medicines
        })
        
    except Exception as e:
        print(f"❌ Error fetching available medicines: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# REQUEST MEDICINE (RECEIVER REQUESTS DONATED MEDICINE)
# ---------------------------------------------------------------------
@app.route("/request_medicine", methods=["POST"])
def request_medicine():
    """Receiver requests a medicine donation from a donor"""
    
    if not session.get("user") or session["user"]["user_type"] != "receiver":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        # Get form data
        medicine_name = request.form.get("medicine_name")
        dosage = request.form.get("dosage")
        quantity = request.form.get("quantity")
        urgency = request.form.get("urgency")
        location = request.form.get("location")
        condition = request.form.get("condition", "any")
        notes = request.form.get("notes", "")
        
        # Get prescription file
        prescription_file = request.files.get("prescription")
        prescription_filename = None
        
        # Validate required fields
        if not medicine_name or not dosage or not quantity or not urgency or not location:
            return jsonify({
                "success": False, 
                "message": "Required fields missing"
            }), 400
        
        # Validate quantity
        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError
        except:
            return jsonify({
                "success": False,
                "message": "Invalid quantity"
            }), 400
        
        # Handle prescription upload
        PRESCRIPTION_FOLDER = "static/prescriptions"
        os.makedirs(PRESCRIPTION_FOLDER, exist_ok=True)
        
        if prescription_file and prescription_file.filename != "":
            # Validate file type
            allowed_extensions = {"png", "jpg", "jpeg", "pdf"}
            ext = prescription_file.filename.rsplit(".", 1)[1].lower() if "." in prescription_file.filename else ""
            
            if ext not in allowed_extensions:
                return jsonify({
                    "success": False,
                    "message": "Invalid file type. Allowed: PNG, JPG, JPEG, PDF"
                }), 400
            
            # Generate unique filename
            prescription_filename = f"prescription_{uuid.uuid4().hex}.{ext}"
            filepath = os.path.join(PRESCRIPTION_FOLDER, prescription_filename)
            prescription_file.save(filepath)
        
        # Get receiver info from session
        receiver = session["user"]
        
        # Create medicine request document in requests_medicine collection
        requests_medicine = db["requests_medicine"]
        
        request_data = {
            "medicine_name": medicine_name,
            "dosage": dosage,
            "quantity": quantity,
            "urgency": urgency,
            "preferred_location": location,
            "condition_preference": condition,
            "additional_notes": notes,
            "prescription": prescription_filename,
            "receiver_id": receiver["_id"],
            "receiver_username": receiver["username"],
            "receiver_email": receiver["email"],
            "status": "pending",  # pending, approved, rejected, completed, cancelled
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = requests_medicine.insert_one(request_data)
        
        print(f"✅ Medicine request submitted successfully. Request ID: {result.inserted_id}")
        
        return jsonify({
            "success": True,
            "message": "Medicine request submitted successfully!",
            "request_id": str(result.inserted_id)
        })
        
    except Exception as e:
        print(f"❌ Error submitting medicine request: {str(e)}")
        return jsonify({"success": False, "message": "Server error during request submission"}), 500


# ---------------------------------------------------------------------
# GET RECEIVER STATISTICS
# ---------------------------------------------------------------------
@app.route("/get_receiver_stats", methods=["GET"])
def get_receiver_stats():
    """Get receiver dashboard statistics"""
    
    if not session.get("user") or session["user"]["user_type"] != "receiver":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    user = session["user"]
    email = user["email"]
    
    try:
        requests_medicine = db["requests_medicine"]
        
        # Get all requests by this receiver
        all_requests = list(requests_medicine.find({"receiver_email": email}))
        
        # Calculate statistics
        total_requests = len(all_requests)
        
        # Pending requests
        pending = len([r for r in all_requests if r.get("status") == "pending"])
        
        # Approved requests (ready for pickup)
        approved = len([r for r in all_requests if r.get("status") == "approved"])
        
        # Completed requests (medicines received)
        completed = len([r for r in all_requests if r.get("status") == "completed"])
        
        # Cancelled requests
        cancelled = len([r for r in all_requests if r.get("status") == "cancelled"])
        
        # Total medicines received (sum of quantities for completed requests)
        medicines_received = sum([r.get("quantity", 0) for r in all_requests if r.get("status") == "completed"])
        
        # Upcoming pickups (approved requests)
        upcoming_pickups = approved
        
        return jsonify({
            "success": True,
            "stats": {
                "total_requests": total_requests,
                "pending": pending,
                "approved": approved,
                "completed": completed,
                "cancelled": cancelled,
                "medicines_received": medicines_received,
                "upcoming_pickups": upcoming_pickups
            }
        })
        
    except Exception as e:
        print(f"❌ Error fetching receiver stats: {str(e)}")
        return jsonify({
            "success": True, 
            "stats": {
                "total_requests": 0,
                "pending": 0,
                "approved": 0,
                "completed": 0,
                "cancelled": 0,
                "medicines_received": 0,
                "upcoming_pickups": 0
            }
        })


# ---------------------------------------------------------------------
# GET RECEIVER REQUESTS HISTORY
# ---------------------------------------------------------------------
@app.route("/get_receiver_requests", methods=["GET"])
def get_receiver_requests():
    """Get all medicine requests made by the receiver from requests_medicine collection"""
    
    if not session.get("user") or session["user"]["user_type"] != "receiver":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    user = session["user"]
    email = user["email"]
    
    try:
        requests_medicine = db["requests_medicine"]
        
        # Get all requests by this receiver, sorted by created_at (newest first)
        all_requests = requests_medicine.find(
            {"receiver_email": email}
        ).sort("created_at", -1)
        
        requests = []
        for req in all_requests:
            # Calculate time ago
            created_at = req.get("created_at")
            time_ago = "Recently"
            
            if created_at:
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
            
            requests.append({
                "id": str(req.get("_id")),
                "medicine_name": req.get("medicine_name", "Unknown"),
                "dosage": req.get("dosage", ""),
                "quantity": req.get("quantity", 0),
                "urgency": req.get("urgency", "normal"),
                "preferred_location": req.get("preferred_location", ""),
                "status": req.get("status", "pending"),
                "donor_username": req.get("donor_username", "Pending"),
                "donor_email": req.get("donor_email"),
                "prescription": req.get("prescription"),
                "additional_notes": req.get("additional_notes", ""),
                "created_at": created_at.isoformat() if created_at else None,
                "time_ago": time_ago
            })
        
        return jsonify({
            "success": True,
            "requests": requests
        })
        
    except Exception as e:
        print(f"❌ Error fetching receiver requests: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# CANCEL REQUEST (RECEIVER CANCEL PENDING REQUEST)
# ---------------------------------------------------------------------
@app.route("/cancel_request", methods=["POST"])
def cancel_request():
    """Cancel a pending medicine request from requests_medicine collection"""
    
    if not session.get("user") or session["user"]["user_type"] != "receiver":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    data = request.get_json()
    
    if not data or not data.get("request_id"):
        return jsonify({"success": False, "message": "Request ID required"}), 400
    
    request_id = data.get("request_id")
    
    try:
        requests_medicine = db["requests_medicine"]
        
        # Find the request
        medicine_request = requests_medicine.find_one({"_id": ObjectId(request_id)})
        
        if not medicine_request:
            return jsonify({"success": False, "message": "Request not found"}), 404
        
        # Check if user owns this request
        if medicine_request.get("receiver_email") != session["user"]["email"]:
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        
        # Check if request can be cancelled (only pending requests)
        if medicine_request.get("status") != "pending":
            return jsonify({
                "success": False, 
                "message": f"Cannot cancel request with status: {medicine_request.get('status')}"
            }), 400
        
        # Update request status to cancelled
        requests_medicine.update_one(
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "status": "cancelled", 
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        print(f"✅ Request cancelled successfully. Request ID: {request_id}")
        
        return jsonify({
            "success": True,
            "message": "Request cancelled successfully"
        })
        
    except Exception as e:
        print(f"❌ Error cancelling request: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# RECEIVER PROFILE IMAGE UPLOAD (SAME AS DONOR)
# ---------------------------------------------------------------------
@app.route("/receiver/upload_profile", methods=["POST"])
def receiver_upload_profile():
    """Upload profile image for receiver"""
    
    if "user" not in session or session["user"]["user_type"] != "receiver":
        return jsonify({"success": False, "message": "Not logged in"}), 401

    file = request.files.get("profileImage")

    if not file or file.filename == "":
        return jsonify({"success": False, "message": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Invalid image type. Allowed: png, jpg, jpeg, gif"}), 400

    try:
        user_id = session["user"]["_id"]
        
        # Get old profile image to delete
        old_user = receiver_collection.find_one({"_id": ObjectId(user_id)})
        old_image = old_user.get("profile_image") if old_user else None
        
        # Generate unique filename
        ext = file.filename.rsplit(".", 1)[1].lower()
        unique_name = f"{user_id}_{uuid.uuid4().hex}.{ext}"

        # Save new file
        path = os.path.join(PROFILE_FOLDER, unique_name)
        file.save(path)

        # Update database with new image
        receiver_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"profile_image": unique_name}}
        )

        # Delete old image file if it exists
        if old_image and old_image != "default.png":
            old_path = os.path.join(PROFILE_FOLDER, old_image)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                    print(f"✅ Deleted old profile image: {old_image}")
                except Exception as e:
                    print(f"⚠ Could not delete old image: {e}")

        # Update session
        session["user"]["profile_image"] = unique_name
        session.modified = True

        print(f"✅ Receiver profile image uploaded successfully: {unique_name}")

        return jsonify({
            "success": True, 
            "filename": unique_name,
            "filepath": f"/static/profile_images/{unique_name}"
        })
        
    except Exception as e:
        print(f"❌ Error uploading profile image: {str(e)}")
        return jsonify({"success": False, "message": "Server error during upload"}), 500


# ---------------------------------------------------------------------
# RECEIVER DELETE PROFILE IMAGE
# ---------------------------------------------------------------------
@app.route("/receiver/delete_profile_image", methods=["POST"])
def receiver_delete_profile_image():
    """Delete receiver's profile image and reset to default"""
    
    if "user" not in session or session["user"]["user_type"] != "receiver":
        return jsonify({"success": False, "message": "Not logged in"}), 401

    try:
        user_id = session["user"]["_id"]
        
        # Get current profile image filename
        user = receiver_collection.find_one({"_id": ObjectId(user_id)})
        old_image = user.get("profile_image") if user else None
        
        # Delete the image file if it exists
        if old_image and old_image != "default.png":
            old_path = os.path.join(PROFILE_FOLDER, old_image)
            if os.path.exists(old_path):
                os.remove(old_path)
                print(f"✅ Deleted receiver profile image: {old_image}")
        
        # Update database - remove profile_image field
        receiver_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$unset": {"profile_image": ""}}
        )
        
        # Update session
        session["user"]["profile_image"] = None
        session.modified = True
        
        return jsonify({
            "success": True,
            "message": "Profile image deleted successfully",
            "default_image": "https://cdn-icons-png.flaticon.com/512/847/847969.png"
        })
        
    except Exception as e:
        print(f"❌ Error deleting receiver profile image: {str(e)}")
        return jsonify({"success": False, "message": "Server error during deletion"}), 500


# ---------------------------------------------------------------------
# CREATE REQUESTS_MEDICINE COLLECTION IF NOT EXISTS
# ---------------------------------------------------------------------
# This ensures the collection exists when the app starts
try:
    # Create requests_medicine collection if it doesn't exist
    if "requests_medicine" not in db.list_collection_names():
        db.create_collection("requests_medicine")
        print("✅ Created requests_medicine collection")
    else:
        print("✅ requests_medicine collection already exists")
    
    # Create prescriptions folder if it doesn't exist
    PRESCRIPTION_FOLDER = "static/prescriptions"
    os.makedirs(PRESCRIPTION_FOLDER, exist_ok=True)
    print("✅ Prescriptions folder ready")
    
except Exception as e:
    print(f"⚠ Error setting up collections: {e}")


# ========== ADMIN DASHBOARD BACKEND ROUTES ==========

# ---------------------------------------------------------------------
# ADMIN DASHBOARD ROUTE
# ---------------------------------------------------------------------
@app.route("/admin/dashboard")
def admin_dashboard():
    """Admin dashboard - user management, requests, donations overview"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return redirect("/login")

    user_id = session["user"].get("_id")
    
    # Get fresh user data from database
    user = admin_collection.find_one({"_id": ObjectId(user_id)})
    
    # Convert ObjectId to string for JSON serialization
    if user and "_id" in user:
        user["_id"] = str(user["_id"])
    
    # Ensure profile_image is in the user object
    if "profile_image" not in user:
        user["profile_image"] = None
    
    return render_template("admin_dashboard.html", user=user)


# ---------------------------------------------------------------------
# GET ADMIN DASHBOARD STATISTICS
# ---------------------------------------------------------------------
@app.route("/get_admin_stats", methods=["GET"])
def get_admin_stats():
    """Get admin dashboard statistics"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        # Count total users
        total_donors = donor_collection.count_documents({})
        total_receivers = receiver_collection.count_documents({})
        total_admins = admin_collection.count_documents({})
        total_users = total_donors + total_receivers + total_admins
        
        # Count active users (users with activity in last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # This is a simplified version - you may need to track last_login in your user collections
        active_donors = donor_collection.count_documents({})  # Replace with actual active logic
        active_receivers = receiver_collection.count_documents({})
        active_users = active_donors + active_receivers
        
        # Count pending medicine requests
        requests_medicine = db["requests_medicine"]
        pending_requests = requests_medicine.count_documents({"status": "pending"})
        
        # Count completed transactions
        completed_donations = donated_medicine.count_documents({"status": "completed"})
        completed_requests = requests_medicine.count_documents({"status": "completed"})
        completed_total = completed_donations + completed_requests
        
        # Count pending verifications
        # This assumes you have a verification field in user collections
        pending_verifications = 0
        pending_verifications += donor_collection.count_documents({"verified": {"$ne": True}})
        pending_verifications += receiver_collection.count_documents({"verified": {"$ne": True}})
        
        # Count today's registrations
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_donors = donor_collection.count_documents({"created_at": {"$gte": today_start}})
        today_receivers = receiver_collection.count_documents({"created_at": {"$gte": today_start}})
        today_registrations = today_donors + today_receivers
        
        # Count donors and receivers separately for role management
        total_donors_count = donor_collection.count_documents({})
        total_receivers_count = receiver_collection.count_documents({})
        
        # Count suspended/blocked users
        suspended_donors = donor_collection.count_documents({"status": "suspended"})
        suspended_receivers = receiver_collection.count_documents({"status": "suspended"})
        suspended_total = suspended_donors + suspended_receivers
        
        # Count blocked users
        blocked_donors = donor_collection.count_documents({"status": "blocked"})
        blocked_receivers = receiver_collection.count_documents({"status": "blocked"})
        blocked_total = blocked_donors + blocked_receivers
        
        return jsonify({
            "success": True,
            "stats": {
                "total_users": total_users,
                "active_users": active_users,
                "pending_requests": pending_requests,
                "completed_total": completed_total,
                "total_donors": total_donors_count,
                "total_receivers": total_receivers_count,
                "total_admins": total_admins,
                "pending_verifications": pending_verifications,
                "today_registrations": today_registrations,
                "suspended_users": suspended_total,
                "blocked_users": blocked_total
            }
        })
        
    except Exception as e:
        print(f"❌ Error fetching admin stats: {str(e)}")
        return jsonify({
            "success": True,
            "stats": {
                "total_users": 0,
                "active_users": 0,
                "pending_requests": 0,
                "completed_total": 0,
                "total_donors": 0,
                "total_receivers": 0,
                "total_admins": 1,
                "pending_verifications": 0,
                "today_registrations": 0,
                "suspended_users": 0,
                "blocked_users": 0
            }
        })


# ---------------------------------------------------------------------
# GET ALL USERS (FOR USER MANAGEMENT)
# ---------------------------------------------------------------------
@app.route("/get_all_users", methods=["GET"])
def get_all_users():
    """Get all users (donors, receivers, admins) for admin dashboard"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        # Get all donors
        donors = donor_collection.find({})
        donor_list = []
        for donor in donors:
            donor_list.append({
                "id": str(donor.get("_id")),
                "username": donor.get("username", "Unknown"),
                "email": donor.get("email", ""),
                "user_type": "donor",
                "status": donor.get("status", "active"),
                "verified": donor.get("verified", False),
                "profile_image": donor.get("profile_image"),
                "created_at": donor.get("created_at").isoformat() if donor.get("created_at") else None,
                "last_active": donor.get("last_active", None),
                "donations_count": donated_medicine.count_documents({"email": donor.get("email")})
            })
        
        # Get all receivers
        receivers = receiver_collection.find({})
        receiver_list = []
        for receiver in receivers:
            requests_medicine = db["requests_medicine"]
            receiver_list.append({
                "id": str(receiver.get("_id")),
                "username": receiver.get("username", "Unknown"),
                "email": receiver.get("email", ""),
                "user_type": "receiver",
                "status": receiver.get("status", "active"),
                "verified": receiver.get("verified", False),
                "profile_image": receiver.get("profile_image"),
                "created_at": receiver.get("created_at").isoformat() if receiver.get("created_at") else None,
                "last_active": receiver.get("last_active", None),
                "requests_count": requests_medicine.count_documents({"receiver_email": receiver.get("email")})
            })
        
        # Get all admins
        admins = admin_collection.find({})
        admin_list = []
        for admin in admins:
            admin_list.append({
                "id": str(admin.get("_id")),
                "username": admin.get("username", "Unknown"),
                "email": admin.get("email", ""),
                "user_type": "admin",
                "status": "active",
                "verified": True,
                "profile_image": admin.get("profile_image"),
                "created_at": admin.get("created_at").isoformat() if admin.get("created_at") else None,
                "last_active": admin.get("last_active", None)
            })
        
        # Combine all users
        all_users = donor_list + receiver_list + admin_list
        
        # Sort by created_at (newest first)
        all_users.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return jsonify({
            "success": True,
            "users": all_users,
            "counts": {
                "total": len(all_users),
                "donors": len(donor_list),
                "receivers": len(receiver_list),
                "admins": len(admin_list)
            }
        })
        
    except Exception as e:
        print(f"❌ Error fetching users: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# GET ALL MEDICINE DONATIONS (FROM DONORS)
# ---------------------------------------------------------------------
@app.route("/get_all_donations_admin", methods=["GET"])
def get_all_donations_admin():
    """Get all medicine donations for admin view"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        # Get all donations
        all_donations = donated_medicine.find({}).sort("created_at", -1)
        
        donations = []
        for donation in all_donations:
            # Calculate time ago
            created_at = donation.get("created_at")
            time_ago = "Recently"
            
            if created_at:
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
                "medicine_name": donation.get("medicineName", "Unknown"),
                "manufacturer": donation.get("manufacturer", ""),
                "quantity": donation.get("quantity", 0),
                "expiry_date": donation.get("expiryDate", "N/A"),
                "category": donation.get("category", "other"),
                "condition": donation.get("condition", "good"),
                "status": donation.get("status", "available"),
                "donor_username": donation.get("username", "Anonymous"),
                "donor_email": donation.get("email", ""),
                "image": donation.get("image", ""),
                "created_at": created_at.isoformat() if created_at else None,
                "time_ago": time_ago
            })
        
        # Count by status
        available_count = len([d for d in donations if d["status"] == "available"])
        claimed_count = len([d for d in donations if d["status"] in ["pending", "approved"]])
        completed_count = len([d for d in donations if d["status"] == "completed"])
        expired_count = len([d for d in donations if d["status"] == "expired"])
        
        return jsonify({
            "success": True,
            "donations": donations,
            "counts": {
                "total": len(donations),
                "available": available_count,
                "claimed": claimed_count,
                "completed": completed_count,
                "expired": expired_count
            }
        })
        
    except Exception as e:
        print(f"❌ Error fetching donations: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# GET ALL MEDICINE REQUESTS (FROM RECEIVERS)
# ---------------------------------------------------------------------
@app.route("/get_all_requests_admin", methods=["GET"])
def get_all_requests_admin():
    """Get all medicine requests for admin view"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        requests_medicine = db["requests_medicine"]
        
        # Get all requests
        all_requests = requests_medicine.find({}).sort("created_at", -1)
        
        requests = []
        for req in all_requests:
            # Calculate time ago
            created_at = req.get("created_at")
            time_ago = "Recently"
            
            if created_at:
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
            
            # Get urgency color
            urgency_color = "normal"
            if req.get("urgency") == "immediate":
                urgency_color = "danger"
            elif req.get("urgency") == "urgent":
                urgency_color = "warning"
            elif req.get("urgency") == "low":
                urgency_color = "success"
            
            requests.append({
                "id": str(req.get("_id")),
                "medicine_name": req.get("medicine_name", "Unknown"),
                "dosage": req.get("dosage", ""),
                "quantity": req.get("quantity", 0),
                "urgency": req.get("urgency", "normal"),
                "urgency_color": urgency_color,
                "preferred_location": req.get("preferred_location", ""),
                "status": req.get("status", "pending"),
                "receiver_username": req.get("receiver_username", "Unknown"),
                "receiver_email": req.get("receiver_email", ""),
                "receiver_id": req.get("receiver_id", ""),
                "prescription": req.get("prescription"),
                "additional_notes": req.get("additional_notes", ""),
                "donor_username": req.get("donor_username"),
                "donor_email": req.get("donor_email"),
                "created_at": created_at.isoformat() if created_at else None,
                "time_ago": time_ago
            })
        
        # Count by status
        pending_count = len([r for r in requests if r["status"] == "pending"])
        approved_count = len([r for r in requests if r["status"] == "approved"])
        completed_count = len([r for r in requests if r["status"] == "completed"])
        cancelled_count = len([r for r in requests if r["status"] == "cancelled"])
        
        return jsonify({
            "success": True,
            "requests": requests,
            "counts": {
                "total": len(requests),
                "pending": pending_count,
                "approved": approved_count,
                "completed": completed_count,
                "cancelled": cancelled_count
            }
        })
        
    except Exception as e:
        print(f"❌ Error fetching requests: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# GET RECENT PLATFORM ACTIVITY
# ---------------------------------------------------------------------
@app.route("/get_recent_activity_admin", methods=["GET"])
def get_recent_activity_admin():
    """Get recent platform activity for admin dashboard"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        activities = []
        
        # Get recent donations (last 5)
        recent_donations = donated_medicine.find({}).sort("created_at", -1).limit(5)
        for donation in recent_donations:
            created_at = donation.get("created_at")
            time_ago = "Recently"
            
            if created_at:
                time_diff = datetime.utcnow() - created_at
                if time_diff < timedelta(hours=1):
                    minutes = int(time_diff.total_seconds() / 60)
                    time_ago = f"{minutes} min ago"
                elif time_diff < timedelta(days=1):
                    hours = int(time_diff.total_seconds() / 3600)
                    time_ago = f"{hours} hour{'s' if hours > 1 else ''} ago"
                else:
                    days = time_diff.days
                    time_ago = f"{days} day{'s' if days > 1 else ''} ago"
            
            activities.append({
                "type": "donation",
                "icon": "fa-donate",
                "icon_color": "orange",
                "title": "New Medicine Donation",
                "description": f"{donation.get('username', 'Someone')} donated {donation.get('quantity')} units of {donation.get('medicineName')}",
                "time_ago": time_ago,
                "created_at": created_at.isoformat() if created_at else None
            })
        
        # Get recent requests (last 5)
        requests_medicine = db["requests_medicine"]
        recent_requests = requests_medicine.find({}).sort("created_at", -1).limit(5)
        for req in recent_requests:
            created_at = req.get("created_at")
            time_ago = "Recently"
            
            if created_at:
                time_diff = datetime.utcnow() - created_at
                if time_diff < timedelta(hours=1):
                    minutes = int(time_diff.total_seconds() / 60)
                    time_ago = f"{minutes} min ago"
                elif time_diff < timedelta(days=1):
                    hours = int(time_diff.total_seconds() / 3600)
                    time_ago = f"{hours} hour{'s' if hours > 1 else ''} ago"
                else:
                    days = time_diff.days
                    time_ago = f"{days} day{'s' if days > 1 else ''} ago"
            
            activities.append({
                "type": "request",
                "icon": "fa-prescription",
                "icon_color": "blue",
                "title": "New Medicine Request",
                "description": f"{req.get('receiver_username', 'Someone')} requested {req.get('quantity')} units of {req.get('medicine_name')}",
                "time_ago": time_ago,
                "created_at": created_at.isoformat() if created_at else None
            })
        
        # Get recent user registrations (last 5)
        recent_donors = donor_collection.find({}).sort("created_at", -1).limit(3)
        for donor in recent_donors:
            created_at = donor.get("created_at")
            if created_at:
                time_diff = datetime.utcnow() - created_at
                if time_diff < timedelta(hours=24):
                    time_ago = "Today"
                else:
                    days = time_diff.days
                    time_ago = f"{days} day{'s' if days > 1 else ''} ago"
            else:
                time_ago = "Recently"
            
            activities.append({
                "type": "registration",
                "icon": "fa-user-plus",
                "icon_color": "green",
                "title": "New Donor Registration",
                "description": f"{donor.get('username')} joined as a donor",
                "time_ago": time_ago,
                "created_at": created_at.isoformat() if created_at else None
            })
        
        recent_receivers = receiver_collection.find({}).sort("created_at", -1).limit(3)
        for receiver in recent_receivers:
            created_at = receiver.get("created_at")
            if created_at:
                time_diff = datetime.utcnow() - created_at
                if time_diff < timedelta(hours=24):
                    time_ago = "Today"
                else:
                    days = time_diff.days
                    time_ago = f"{days} day{'s' if days > 1 else ''} ago"
            else:
                time_ago = "Recently"
            
            activities.append({
                "type": "registration",
                "icon": "fa-user-plus",
                "icon_color": "teal",
                "title": "New Receiver Registration",
                "description": f"{receiver.get('username')} joined as a receiver",
                "time_ago": time_ago,
                "created_at": created_at.isoformat() if created_at else None
            })
        
        # Sort all activities by created_at (newest first)
        activities.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        # Return only the 10 most recent activities
        activities = activities[:10]
        
        return jsonify({
            "success": True,
            "activities": activities
        })
        
    except Exception as e:
        print(f"❌ Error fetching recent activity: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# UPDATE USER STATUS (ACTIVE/SUSPENDED/BLOCKED)
# ---------------------------------------------------------------------
@app.route("/update_user_status", methods=["POST"])
def update_user_status():
    """Update user status (active, suspended, blocked)"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    data = request.get_json()
    
    if not data:
        return jsonify({"success": False, "message": "Invalid request"}), 400
    
    user_id = data.get("user_id")
    user_type = data.get("user_type")
    new_status = data.get("status")
    
    if not user_id or not user_type or not new_status:
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    
    try:
        # Select the appropriate collection
        if user_type == "donor":
            collection = donor_collection
        elif user_type == "receiver":
            collection = receiver_collection
        elif user_type == "admin":
            collection = admin_collection
        else:
            return jsonify({"success": False, "message": "Invalid user type"}), 400
        
        # Update user status
        result = collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"status": new_status, "updated_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            print(f"✅ User {user_id} status updated to {new_status}")
            return jsonify({
                "success": True,
                "message": f"User status updated to {new_status}"
            })
        else:
            return jsonify({
                "success": False,
                "message": "User not found or status unchanged"
            }), 404
        
    except Exception as e:
        print(f"❌ Error updating user status: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# VERIFY USER
# ---------------------------------------------------------------------
@app.route("/verify_user", methods=["POST"])
def verify_user():
    """Verify a user (donor or receiver)"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    data = request.get_json()
    
    if not data:
        return jsonify({"success": False, "message": "Invalid request"}), 400
    
    user_id = data.get("user_id")
    user_type = data.get("user_type")
    
    if not user_id or not user_type:
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    
    try:
        # Select the appropriate collection
        if user_type == "donor":
            collection = donor_collection
        elif user_type == "receiver":
            collection = receiver_collection
        else:
            return jsonify({"success": False, "message": "Only donors and receivers can be verified"}), 400
        
        # Update user verification status
        result = collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"verified": True, "verified_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            print(f"✅ User {user_id} verified successfully")
            return jsonify({
                "success": True,
                "message": "User verified successfully"
            })
        else:
            return jsonify({
                "success": False,
                "message": "User not found or already verified"
            }), 404
        
    except Exception as e:
        print(f"❌ Error verifying user: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# VERIFY PRESCRIPTION
# ---------------------------------------------------------------------
@app.route("/verify_prescription", methods=["POST"])
def verify_prescription():
    """Verify a prescription for a medicine request"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    data = request.get_json()
    
    if not data:
        return jsonify({"success": False, "message": "Invalid request"}), 400
    
    request_id = data.get("request_id")
    
    if not request_id:
        return jsonify({"success": False, "message": "Request ID required"}), 400
    
    try:
        requests_medicine = db["requests_medicine"]
        
        # Update request status
        result = requests_medicine.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"prescription_verified": True, "prescription_verified_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            print(f"✅ Prescription for request {request_id} verified")
            return jsonify({
                "success": True,
                "message": "Prescription verified successfully"
            })
        else:
            return jsonify({
                "success": False,
                "message": "Request not found"
            }), 404
        
    except Exception as e:
        print(f"❌ Error verifying prescription: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# APPROVE/REJECT MEDICINE REQUEST
# ---------------------------------------------------------------------
@app.route("/update_request_status", methods=["POST"])
def update_request_status():
    """Update medicine request status (approve/reject)"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    data = request.get_json()
    
    if not data:
        return jsonify({"success": False, "message": "Invalid request"}), 400
    
    request_id = data.get("request_id")
    new_status = data.get("status")  # approved, rejected, completed
    
    if not request_id or not new_status:
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    
    try:
        requests_medicine = db["requests_medicine"]
        
        # Update request status
        result = requests_medicine.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": new_status, "updated_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            print(f"✅ Request {request_id} status updated to {new_status}")
            return jsonify({
                "success": True,
                "message": f"Request {new_status} successfully"
            })
        else:
            return jsonify({
                "success": False,
                "message": "Request not found"
            }), 404
        
    except Exception as e:
        print(f"❌ Error updating request status: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# ADMIN PROFILE IMAGE UPLOAD (SAME AS DONOR/RECEIVER)
# ---------------------------------------------------------------------
@app.route("/admin/upload_profile", methods=["POST"])
def admin_upload_profile():
    """Upload profile image for admin"""
    
    if "user" not in session or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Not logged in"}), 401

    file = request.files.get("profileImage")

    if not file or file.filename == "":
        return jsonify({"success": False, "message": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "Invalid image type. Allowed: png, jpg, jpeg, gif"}), 400

    try:
        user_id = session["user"]["_id"]
        
        # Get old profile image to delete
        old_user = admin_collection.find_one({"_id": ObjectId(user_id)})
        old_image = old_user.get("profile_image") if old_user else None
        
        # Generate unique filename
        ext = file.filename.rsplit(".", 1)[1].lower()
        unique_name = f"{user_id}_{uuid.uuid4().hex}.{ext}"

        # Save new file
        path = os.path.join(PROFILE_FOLDER, unique_name)
        file.save(path)

        # Update database with new image
        admin_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"profile_image": unique_name}}
        )

        # Delete old image file if it exists
        if old_image and old_image != "default.png":
            old_path = os.path.join(PROFILE_FOLDER, old_image)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                    print(f"✅ Deleted old admin profile image: {old_image}")
                except Exception as e:
                    print(f"⚠ Could not delete old admin image: {e}")

        # Update session
        session["user"]["profile_image"] = unique_name
        session.modified = True

        print(f"✅ Admin profile image uploaded successfully: {unique_name}")

        return jsonify({
            "success": True, 
            "filename": unique_name,
            "filepath": f"/static/profile_images/{unique_name}"
        })
        
    except Exception as e:
        print(f"❌ Error uploading admin profile image: {str(e)}")
        return jsonify({"success": False, "message": "Server error during upload"}), 500


# ---------------------------------------------------------------------
# ADMIN DELETE PROFILE IMAGE
# ---------------------------------------------------------------------
@app.route("/admin/delete_profile_image", methods=["POST"])
def admin_delete_profile_image():
    """Delete admin's profile image and reset to default"""
    
    if "user" not in session or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Not logged in"}), 401

    try:
        user_id = session["user"]["_id"]
        
        # Get current profile image filename
        user = admin_collection.find_one({"_id": ObjectId(user_id)})
        old_image = user.get("profile_image") if user else None
        
        # Delete the image file if it exists
        if old_image and old_image != "default.png":
            old_path = os.path.join(PROFILE_FOLDER, old_image)
            if os.path.exists(old_path):
                os.remove(old_path)
                print(f"✅ Deleted admin profile image: {old_image}")
        
        # Update database - remove profile_image field
        admin_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$unset": {"profile_image": ""}}
        )
        
        # Update session
        session["user"]["profile_image"] = None
        session.modified = True
        
        return jsonify({
            "success": True,
            "message": "Profile image deleted successfully",
            "default_image": "https://cdn-icons-png.flaticon.com/512/847/847969.png"
        })
        
    except Exception as e:
        print(f"❌ Error deleting admin profile image: {str(e)}")
        return jsonify({"success": False, "message": "Server error during deletion"}), 500


# ---------------------------------------------------------------------
# GET USER DETAILS BY ID
# ---------------------------------------------------------------------
@app.route("/get_user_details", methods=["GET"])
def get_user_details():
    """Get detailed information about a specific user"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    user_id = request.args.get("user_id")
    user_type = request.args.get("user_type")
    
    if not user_id or not user_type:
        return jsonify({"success": False, "message": "Missing parameters"}), 400
    
    try:
        # Select the appropriate collection
        if user_type == "donor":
            collection = donor_collection
        elif user_type == "receiver":
            collection = receiver_collection
        elif user_type == "admin":
            collection = admin_collection
        else:
            return jsonify({"success": False, "message": "Invalid user type"}), 400
        
        user = collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        # Get user activity
        user_details = {
            "id": str(user.get("_id")),
            "username": user.get("username"),
            "email": user.get("email"),
            "user_type": user_type,
            "status": user.get("status", "active"),
            "verified": user.get("verified", False),
            "profile_image": user.get("profile_image"),
            "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
            "last_active": user.get("last_active"),
            "phone": user.get("phone"),
            "address": user.get("address"),
            "city": user.get("city"),
            "state": user.get("state"),
            "pincode": user.get("pincode")
        }
        
        # Get user-specific statistics
        if user_type == "donor":
            user_details["donations_count"] = donated_medicine.count_documents({"email": user.get("email")})
            user_details["total_donated_quantity"] = sum([d.get("quantity", 0) for d in donated_medicine.find({"email": user.get("email")})])
        elif user_type == "receiver":
            requests_medicine = db["requests_medicine"]
            user_details["requests_count"] = requests_medicine.count_documents({"receiver_email": user.get("email")})
            user_details["fulfilled_requests"] = requests_medicine.count_documents({"receiver_email": user.get("email"), "status": "completed"})
        
        return jsonify({
            "success": True,
            "user": user_details
        })
        
    except Exception as e:
        print(f"❌ Error fetching user details: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500


# ---------------------------------------------------------------------
# GENERATE REPORTS
# ---------------------------------------------------------------------
@app.route("/generate_report", methods=["POST"])
def generate_report():
    """Generate various reports for admin"""
    
    if not session.get("user") or session["user"]["user_type"] != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    data = request.get_json()
    report_type = data.get("report_type")  # users, donations, requests, verification
    date_range = data.get("date_range", "all")  # today, week, month, year, all
    
    try:
        # This is a placeholder for actual report generation
        # You can implement PDF/Excel generation here
        
        print(f"📊 Generating {report_type} report for {date_range} date range")
        
        return jsonify({
            "success": True,
            "message": f"{report_type.capitalize()} report generated successfully",
            "report_url": f"/static/reports/{report_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        })
        
    except Exception as e:
        print(f"❌ Error generating report: {str(e)}")
        return jsonify({"success": False, "message": "Server error"}), 500

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
