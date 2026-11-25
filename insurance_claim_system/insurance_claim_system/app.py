import os
import uuid
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, send_from_directory, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from db import get_db, close_db, init_db
from rules import evaluate_claim

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXT = {"pdf", "png", "jpg", "jpeg"}
app.teardown_appcontext(close_db)


# ---------- helpers ----------
def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco

def log_history(db, claim_id, status, note):
    db.execute("INSERT INTO claim_history (claim_id,status,note) VALUES (?,?,?)",
               (claim_id, status, note))

def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# ---------- auth ----------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        full_name = request.form["full_name"].strip()
        password = request.form["password"]
        if not (username and full_name and password):
            flash("All fields are required.", "danger")
            return render_template("register.html")
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            flash("Username already taken.", "danger")
            return render_template("register.html")
        cur = db.execute(
            "INSERT INTO users (username,full_name,password_hash,role) VALUES (?,?,?,'customer')",
            (username, full_name, generate_password_hash(password)))
        # demo policy so the new user can file claims immediately
        today = date.today()
        db.execute(
            "INSERT INTO policies (policy_number,user_id,policy_type,coverage_amount,start_date,end_date) "
            "VALUES (?,?,?,?,?,?)",
            ("POL-" + uuid.uuid4().hex[:8].upper(), cur.lastrowid, "Health", 100000,
             (today - timedelta(days=30)).isoformat(), (today + timedelta(days=335)).isoformat()))
        db.commit()
        flash("Registered! A demo policy was created. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_db().execute("SELECT * FROM users WHERE username=?",
                                (request.form["username"].strip(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session.update(user_id=user["id"], role=user["role"], name=user["full_name"])
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- dashboard ----------
@app.route("/dashboard")
@login_required()
def dashboard():
    db = get_db()
    if session["role"] == "adjuster":
        stats = db.execute(
            "SELECT status, COUNT(*) c FROM claims GROUP BY status").fetchall()
        claims = db.execute(
            "SELECT c.*, u.full_name, p.policy_number FROM claims c "
            "JOIN users u ON u.id=c.user_id JOIN policies p ON p.id=c.policy_id "
            "ORDER BY (c.status='Under Review') DESC, c.created_at DESC").fetchall()
        return render_template("admin_dashboard.html", claims=claims,
                               stats={s["status"]: s["c"] for s in stats})
    claims = db.execute(
        "SELECT c.*, p.policy_number FROM claims c JOIN policies p ON p.id=c.policy_id "
        "WHERE c.user_id=? ORDER BY c.created_at DESC", (session["user_id"],)).fetchall()
    policies = db.execute("SELECT * FROM policies WHERE user_id=?", (session["user_id"],)).fetchall()
    return render_template("dashboard.html", claims=claims, policies=policies)


# ---------- customer: file a claim ----------
@app.route("/claims/new", methods=["GET", "POST"])
@login_required("customer")
def new_claim():
    db = get_db()
    policies = db.execute("SELECT * FROM policies WHERE user_id=?", (session["user_id"],)).fetchall()
    if request.method == "POST":
        policy = db.execute("SELECT * FROM policies WHERE id=? AND user_id=?",
                            (request.form["policy_id"], session["user_id"])).fetchone()
        if not policy:
            flash("Invalid policy.", "danger")
            return render_template("new_claim.html", policies=policies)
        try:
            amount = float(request.form["claim_amount"])
        except ValueError:
            flash("Enter a valid amount.", "danger")
            return render_template("new_claim.html", policies=policies)

        incident_date = request.form["incident_date"]
        description = request.form["description"].strip()

        filename = None
        f = request.files.get("document")
        if f and f.filename:
            if not allowed(f.filename):
                flash("Only PDF/PNG/JPG files allowed.", "danger")
                return render_template("new_claim.html", policies=policies)
            filename = uuid.uuid4().hex[:8] + "_" + secure_filename(f.filename)
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        already = db.execute(
            "SELECT COALESCE(SUM(approved_amount),0) s FROM claims WHERE policy_id=? AND status='Approved'",
            (policy["id"],)).fetchone()["s"]
        dup = db.execute(
            "SELECT 1 FROM claims WHERE policy_id=? AND incident_date=?",
            (policy["id"], incident_date)).fetchone() is not None

        status, approved, note, flag = evaluate_claim(policy, amount, incident_date, already, dup)
        claim_number = "CLM-" + uuid.uuid4().hex[:8].upper()
        cur = db.execute(
            "INSERT INTO claims (claim_number,policy_id,user_id,incident_date,description,"
            "claim_amount,approved_amount,status,flag_reason,document,adjuster_note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (claim_number, policy["id"], session["user_id"], incident_date, description,
             amount, approved, status, flag, filename, note))
        log_history(db, cur.lastrowid, "Submitted", "Claim submitted by customer.")
        log_history(db, cur.lastrowid, status, note)
        db.commit()
        flash(f"Claim {claim_number} submitted — status: {status}.", "success")
        return redirect(url_for("claim_detail", claim_id=cur.lastrowid))
    return render_template("new_claim.html", policies=policies)


# ---------- claim detail ----------
@app.route("/claims/<int:claim_id>")
@login_required()
def claim_detail(claim_id):
    db = get_db()
    claim = db.execute(
        "SELECT c.*, u.full_name, p.policy_number, p.policy_type, p.coverage_amount "
        "FROM claims c JOIN users u ON u.id=c.user_id JOIN policies p ON p.id=c.policy_id "
        "WHERE c.id=?", (claim_id,)).fetchone()
    if not claim or (session["role"] != "adjuster" and claim["user_id"] != session["user_id"]):
        abort(404)
    history = db.execute("SELECT * FROM claim_history WHERE claim_id=? ORDER BY id", (claim_id,)).fetchall()
    return render_template("claim_detail.html", claim=claim, history=history)

@app.route("/uploads/<path:filename>")
@login_required()
def uploaded_file(filename):
    db = get_db()
    c = db.execute("SELECT user_id FROM claims WHERE document=?", (filename,)).fetchone()
    if not c or (session["role"] != "adjuster" and c["user_id"] != session["user_id"]):
        abort(404)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ---------- adjuster: decide ----------
@app.route("/claims/<int:claim_id>/decide", methods=["POST"])
@login_required("adjuster")
def decide(claim_id):
    db = get_db()
    claim = db.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    if not claim:
        abort(404)
    decision = request.form["decision"]
    note = request.form.get("note", "").strip()
    if decision == "approve":
        try:
            approved = float(request.form.get("approved_amount") or claim["claim_amount"])
        except ValueError:
            flash("Invalid approved amount.", "danger")
            return redirect(url_for("claim_detail", claim_id=claim_id))
        approved = max(0, min(approved, claim["claim_amount"]))
        status = "Approved"
    elif decision == "reject":
        approved, status = 0, "Rejected"
    else:
        abort(400)
    db.execute("UPDATE claims SET status=?, approved_amount=?, adjuster_note=?, "
               "updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, approved, note, claim_id))
    log_history(db, claim_id, status, note or f"Decision by adjuster ({status}).")
    db.commit()
    flash(f"Claim marked {status}.", "success")
    return redirect(url_for("dashboard"))


# ---------- adjuster: create policy for a customer ----------
@app.route("/policies/new", methods=["GET", "POST"])
@login_required("adjuster")
def new_policy():
    db = get_db()
    customers = db.execute("SELECT id, full_name, username FROM users WHERE role='customer'").fetchall()
    if request.method == "POST":
        db.execute(
            "INSERT INTO policies (policy_number,user_id,policy_type,coverage_amount,start_date,end_date) "
            "VALUES (?,?,?,?,?,?)",
            ("POL-" + uuid.uuid4().hex[:8].upper(), request.form["user_id"],
             request.form["policy_type"], float(request.form["coverage_amount"]),
             request.form["start_date"], request.form["end_date"]))
        db.commit()
        flash("Policy created.", "success")
        return redirect(url_for("dashboard"))
    return render_template("new_policy.html", customers=customers)


if __name__ == "__main__":
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    init_db()
    app.run(debug=True)
