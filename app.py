from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medicine_system.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# User Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    user_type = db.Column(db.String(20), default='unassigned')  # unassigned, donor, receiver, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'

# Medicine Donation Model
class MedicineDonation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    medicine_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    expiry_date = db.Column(db.String(50), nullable=False)
    donor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='available')  # available, claimed, expired
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    donor = db.relationship('User', backref=db.backref('donations', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create admin user on startup
def create_admin_user():
    with app.app_context():
        if not User.query.filter_by(user_type='admin').first():
            admin_user = User(
                username='admin',
                email='admin@aarogyamitra.com',
                password_hash=generate_password_hash('admin123'),
                user_type='admin'
            )
            db.session.add(admin_user)
            db.session.commit()
            print("✅ Admin user created: username='admin', password='admin123'")

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username']
        password = request.form['password']
        
        # Check if input is email or username
        user = None
        if '@' in username_or_email:
            user = User.query.filter_by(email=username_or_email).first()
        else:
            user = User.query.filter_by(username=username_or_email).first()
        
        # If not found with one method, try the other
        if not user:
            user = User.query.filter(
                (User.username == username_or_email) | (User.email == username_or_email)
            ).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            
            # Store user info in session
            session['username'] = user.username
            session['user_id'] = user.id
            session['user_type'] = user.user_type
            
            flash(f'Welcome back, {user.username}!', 'success')
            
            # Redirect based on user type
            if user.user_type == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.user_type in ['donor', 'receiver']:
                return redirect(url_for('dashboard'))
            else:
                # New user or unassigned role - go to role selection
                return redirect(url_for('role_selection'))
        else:
            flash('Invalid username/email or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form.get('confirm', '')
        user_type = request.form.get('user_type', 'unassigned')
        
        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('register'))
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('register'))
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            user_type=user_type
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('registration.html')

@app.route('/role-selection')
@login_required
def role_selection():
    """Show role selection page after login"""
    return render_template('role_selection.html', username=current_user.username)

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - redirects based on user type"""
    if current_user.user_type == 'donor':
        return redirect(url_for('donor_dashboard'))
    elif current_user.user_type == 'receiver':
        return redirect(url_for('receiver_dashboard'))
    elif current_user.user_type == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        # If no role assigned, go to role selection
        return redirect(url_for('role_selection'))

@app.route('/dashboard/donor')
@login_required
def donor_dashboard():
    """Donor-specific dashboard"""
    # Update user role in database if needed
    if current_user.user_type != 'donor':
        current_user.user_type = 'donor'
        db.session.commit()
        session['user_type'] = 'donor'
    
    user_donations = MedicineDonation.query.filter_by(donor_id=current_user.id).all()
    
    # Calculate statistics
    total_donations = len(user_donations)
    available_donations = len([d for d in user_donations if d.status == 'available'])
    claimed_donations = len([d for d in user_donations if d.status == 'claimed'])
    
    return render_template('donor_dashboard.html', 
                         donations=user_donations,
                         username=current_user.username,
                         total_donations=total_donations,
                         available_donations=available_donations,
                         claimed_donations=claimed_donations)

@app.route('/dashboard/receiver')
@login_required
def receiver_dashboard():
    """Receiver-specific dashboard"""
    # Update user role in database if needed
    if current_user.user_type != 'receiver':
        current_user.user_type = 'receiver'
        db.session.commit()
        session['user_type'] = 'receiver'
    
    available_medicines = MedicineDonation.query.filter_by(status='available').all()
    
    return render_template('receiver_dashboard.html',
                         available_medicines=available_medicines,
                         username=current_user.username)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin dashboard - only accessible by admin users"""
    if current_user.user_type != 'admin':
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard'))
    
    # Admin statistics
    total_users = User.query.count()
    total_donors = User.query.filter_by(user_type='donor').count()
    total_receivers = User.query.filter_by(user_type='receiver').count()
    total_medicines = MedicineDonation.query.count()
    available_medicines = MedicineDonation.query.filter_by(status='available').count()
    
    return render_template('admin_dashboard.html',
                         username=current_user.username,
                         total_users=total_users,
                         total_donors=total_donors,
                         total_receivers=total_receivers,
                         total_medicines=total_medicines,
                         available_medicines=available_medicines)

@app.route('/donate', methods=['GET', 'POST'])
@login_required
def donate_medicine():
    """Donate medicine page"""
    if request.method == 'POST':
        medicine_name = request.form['medicine_name']
        quantity = request.form['quantity']
        expiry_date = request.form['expiry_date']
        
        new_donation = MedicineDonation(
            medicine_name=medicine_name,
            quantity=quantity,
            expiry_date=expiry_date,
            donor_id=current_user.id
        )
        
        db.session.add(new_donation)
        db.session.commit()
        
        flash('Medicine donated successfully!', 'success')
        return redirect(url_for('donor_dashboard'))
    
    return render_template('donate.html')

@app.route('/claim/<int:medicine_id>')
@login_required
def claim_medicine(medicine_id):
    """Claim a medicine (for receivers)"""
    if current_user.user_type != 'receiver':
        flash('This feature is only available for medicine receivers.', 'error')
        return redirect(url_for('dashboard'))
    
    medicine = MedicineDonation.query.get_or_404(medicine_id)
    
    if medicine.status == 'available':
        medicine.status = 'claimed'
        db.session.commit()
        flash(f'You have successfully claimed {medicine.medicine_name}!', 'success')
    else:
        flash('This medicine is not available anymore.', 'error')
    
    return redirect(url_for('receiver_dashboard'))

@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    username = current_user.username
    logout_user()
    session.clear()
    flash(f'Goodbye, {username}! You have been logged out.', 'info')
    return redirect(url_for('index'))

# API endpoints
@app.route('/api/medicines')
def get_medicines():
    """API to get available medicines"""
    medicines = MedicineDonation.query.filter_by(status='available').all()
    medicine_list = []
    for med in medicines:
        medicine_list.append({
            'id': med.id,
            'name': med.medicine_name,
            'quantity': med.quantity,
            'expiry_date': med.expiry_date,
            'donor': med.donor.username
        })
    return {'medicines': medicine_list}

@app.route('/api/user/stats')
@login_required
def user_stats():
    """API to get user statistics"""
    if current_user.user_type == 'donor':
        donations = MedicineDonation.query.filter_by(donor_id=current_user.id).all()
        return {
            'total_donations': len(donations),
            'available_donations': len([d for d in donations if d.status == 'available']),
            'claimed_donations': len([d for d in donations if d.status == 'claimed'])
        }
    elif current_user.user_type == 'receiver':
        available_medicines = MedicineDonation.query.filter_by(status='available').count()
        return {
            'available_medicines': available_medicines
        }
    return {}

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin_user()
    app.run(debug=True)