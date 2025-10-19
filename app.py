from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, datetime

# --- App Setup ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# --- Database Helper ---
def get_db_connection():
    conn = sqlite3.connect("bank.db")
    conn.row_factory = sqlite3.Row
    return conn

# --- Database Setup ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        mobile TEXT,
        pin TEXT NOT NULL,
        balance REAL DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        amount REAL,
        date TEXT,
        target_email TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()

init_db()

# --- Helper: Record Transaction ---
def record_transaction(user_id, t_type, amount, target_email=None):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO transactions (user_id, type, amount, date, target_email) VALUES (?, ?, ?, ?, ?)",
        (user_id, t_type, round(amount, 2), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), target_email)
    )
    conn.commit()
    conn.close()

# --- Home ---
@app.route('/')
def home():
    if 'user' in session:
        return redirect('/dashboard')
    return render_template('index.html')

# --- Register ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        mobile = request.form.get('mobile', '').strip()
        pin = request.form.get('pin', '').strip()

        # Basic validation
        if not (name and email and pin):
            flash("❌ Please fill required fields.", "error")
            return redirect('/register')

        try:
            deposit = float(request.form.get('deposit', '0'))
            if deposit < 0:
                flash("❌ Initial deposit cannot be negative.", "error")
                return redirect('/register')
        except ValueError:
            flash("❌ Invalid deposit amount.", "error")
            return redirect('/register')

        hashed_pin = generate_password_hash(pin)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        if cur.fetchone():
            conn.close()
            flash("⚠️ This email already exists. Please login.", "warning")
            return redirect('/login')

        cur.execute(
            "INSERT INTO users (name, email, mobile, pin, balance) VALUES (?, ?, ?, ?, ?)",
            (name, email, mobile, hashed_pin, round(deposit, 2))
        )
        conn.commit()
        conn.close()
        flash("✅ Account created successfully! Please login.", "success")
        return redirect('/login')

    return render_template('register.html')

# --- Login (no OTP) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pin = request.form.get('pin', '').strip()

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user_row = cur.fetchone()
        conn.close()

        if user_row and check_password_hash(user_row['pin'], pin):
            # ensure clean session before set
            session.pop('user', None)
            session['user'] = dict(user_row)
            flash(f"Welcome back, {user_row['name']}!", "success")
            return redirect('/dashboard')
        else:
            flash("❌ Invalid Email or PIN.", "error")

    return render_template('login.html')

# --- Dashboard ---
@app.route('/dashboard')
def dashboard():
    if 'user' not in session or 'id' not in session['user']:
        flash("Session expired. Please login again.", "warning")
        return redirect('/login')

    user_id = session['user']['id']
    conn = get_db_connection()
    user_row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    transactions = conn.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,)).fetchall()
    conn.close()

    if user_row:
        session['user'] = dict(user_row)
    else:
        session.pop('user', None)
        flash("Your account no longer exists.", "error")
        return redirect('/login')

    return render_template('dashboard.html', user=session['user'], transactions=transactions)

# --- Deposit ---
@app.route('/deposit', methods=['POST'])
def deposit():
    if 'user' not in session:
        return redirect('/login')

    try:
        amount = float(request.form.get('amount', '0'))
        if amount <= 0:
            flash("❌ Deposit must be positive.", "error")
            return redirect('/dashboard')
    except ValueError:
        flash("❌ Invalid amount.", "error")
        return redirect('/dashboard')

    user_id = session['user']['id']
    conn = get_db_connection()
    conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (round(amount, 2), user_id))
    conn.commit()
    updated_user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    session['user'] = dict(updated_user)
    record_transaction(user_id, "Deposit", amount)
    flash(f"✅ ₹{amount:.2f} deposited successfully!", "success")
    return redirect('/dashboard')

# --- Withdraw ---
@app.route('/withdraw', methods=['POST'])
def withdraw():
    if 'user' not in session:
        return redirect('/login')

    try:
        amount = float(request.form.get('amount', '0'))
        if amount <= 0:
            flash("❌ Withdrawal must be positive.", "error")
            return redirect('/dashboard')
    except ValueError:
        flash("❌ Invalid amount.", "error")
        return redirect('/dashboard')

    user = session['user']
    if amount > user['balance']:
        flash(f"⚠️ Insufficient Balance! Available: ₹{user['balance']:.2f}", "warning")
        return redirect('/dashboard')

    user_id = user['id']
    conn = get_db_connection()
    conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (round(amount, 2), user_id))
    conn.commit()
    updated_user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    session['user'] = dict(updated_user)
    record_transaction(user_id, "Withdraw", amount)
    flash(f"✅ ₹{amount:.2f} withdrawn successfully!", "success")
    return redirect('/dashboard')

# --- Transfer ---
@app.route('/transfer', methods=['POST'])
def transfer():
    if 'user' not in session:
        return redirect('/login')

    sender = session['user']
    recipient_email = request.form.get('email', '').strip().lower()
    try:
        amount = float(request.form.get('amount', '0'))
        if amount <= 0:
            flash("❌ Amount must be positive.", "error")
            return redirect('/dashboard')
    except ValueError:
        flash("❌ Invalid amount.", "error")
        return redirect('/dashboard')

    if recipient_email == sender['email']:
        flash("⚠️ You cannot transfer to yourself.", "warning")
        return redirect('/dashboard')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (recipient_email,))
    recipient = cur.fetchone()

    if not recipient:
        conn.close()
        flash("❌ Recipient not found.", "error")
        return redirect('/dashboard')

    if sender['balance'] < amount:
        conn.close()
        flash("⚠️ Insufficient balance.", "warning")
        return redirect('/dashboard')

    cur.execute("UPDATE users SET balance = balance - ? WHERE id=?", (round(amount, 2), sender['id']))
    cur.execute("UPDATE users SET balance = balance + ? WHERE id=?", (round(amount, 2), recipient['id']))
    conn.commit()

    updated_sender = conn.execute("SELECT * FROM users WHERE id=?", (sender['id'],)).fetchone()
    conn.close()
    session['user'] = dict(updated_sender)

    record_transaction(sender['id'], "Transfer Sent", amount, recipient_email)
    record_transaction(recipient['id'], "Transfer Received", amount, sender['email'])
    flash(f"✅ ₹{amount:.2f} transferred to {recipient_email}!", "success")
    return redirect('/dashboard')

# --- Logout ---
@app.route('/logout')
def logout():
    session.pop('user', None)
    flash("Logged out successfully.", "info")
    return redirect('/')

if __name__ == "__main__":
    app.run(debug=True)
