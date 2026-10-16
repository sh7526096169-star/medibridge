
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import re
import sqlite3
from functools import wraps
from pathlib import Path
from datetime import datetime
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_from_directory, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "medibridge.db"
UPLOAD_DIR = BASE / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=[])
app.secret_key = os.environ.get("MEDIBRIDGE_SECRET", os.urandom(32).hex())
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
RECORD_TYPES = {
    "Past condition", "Current symptom", "Current medicine",
    "Stopped medicine", "Allergy", "Other"
}
MEDICINE_TYPES = {"Current medicine", "Stopped medicine"}


# ---------------- DATABASE ----------------

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mobile TEXT UNIQUE NOT NULL,
            pin_hash TEXT NOT NULL,
            name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            address TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            record_type TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        # Add optional medicine dates to existing databases.
        columns = {
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(medical_records)"
            ).fetchall()
        }

        if "start_date" not in columns:
            con.execute(
                "ALTER TABLE medical_records ADD COLUMN start_date TEXT"
            )

        if "stop_date" not in columns:
            con.execute(
                "ALTER TABLE medical_records ADD COLUMN stop_date TEXT"
            )


init_db()


# ---------------- COMMON HELPERS ----------------

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped


def current_user():
    if "user_id" not in session:
        return None

    with db() as con:
        return con.execute(
            "SELECT * FROM users WHERE id=?",
            (session["user_id"],)
        ).fetchone()


def valid_optional_date(value):
    if not value:
        return True
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} · MediBridge</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:#f2f7f8;color:#173b4d}
header{background:#087f8c;color:white;padding:17px 5%;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
header a{color:white;text-decoration:none;margin-left:12px}
main{max-width:1100px;margin:28px auto;padding:0 18px}
.card{background:white;border-radius:16px;padding:22px;margin-bottom:18px;box-shadow:0 5px 22px #1233}
.narrow{max-width:470px;margin:45px auto}
h1,h2{margin-top:0}
input,textarea,select{width:100%;padding:12px;margin:7px 0 14px;border:1px solid #ccdadd;border-radius:8px;font:inherit}
button,.btn{display:inline-block;border:0;background:#087f8c;color:white;padding:11px 16px;border-radius:8px;cursor:pointer;text-decoration:none;font:inherit}
.secondary{background:#e5f4f4;color:#075e67}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}
.muted{color:#607782;line-height:1.6}
.notice{padding:12px;border-radius:8px;background:#fff4d8;margin:12px 0}
.success{background:#e0f6ef;padding:10px;border-radius:8px;margin-bottom:10px}
.record{border-bottom:1px solid #e3ecee;padding:12px 0;overflow-wrap:anywhere}
.chat{position:fixed;right:16px;bottom:16px;width:min(320px,calc(100vw - 32px));background:white;border:1px solid #d5e3e5;border-radius:14px;padding:15px;box-shadow:0 5px 25px #1233;z-index:5}
.chat summary{font-weight:bold;cursor:pointer;color:#087f8c}
.chat p{font-size:13px;line-height:1.5}
footer{text-align:center;color:#607782;padding:20px;font-size:12px}
@media(max-width:500px){header{align-items:flex-start}main{margin-top:15px}.card{padding:16px}}
@media print{header,.chat,footer,button,.btn{display:none!important}body{background:white}main{max-width:100%;margin:0;padding:0}.card{box-shadow:none;border:1px solid #ddd}}
</style>
</head>
<body>
<header>
<strong>✚ MediBridge</strong>
<nav>
{% if session.get('user_id') %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>
<a href="{{ url_for('logout') }}">Logout</a>
{% endif %}
</nav>
</header>
<main>
{% for message in get_flashed_messages() %}
<div class="success">{{ message }}</div>
{% endfor %}
{{ content|safe }}
</main>
{% if session.get('user_id') %}
<details class="chat">
<summary>✦ MediBridge Help Assistant</summary>
<p>I can help you navigate this demo and prepare questions for your doctor. I cannot diagnose conditions or recommend starting/stopping medicines.</p>
<form method="post" action="{{ url_for('assistant') }}">
<label for="question">How can I help?</label>
<input id="question" name="question" maxlength="500" placeholder="e.g. How do I prepare for a visit?" required>
<button type="submit">Ask assistant</button>
</form>
</details>
{% endif %}
<footer>Demo prototype · Use fictional data only · Not for emergencies or real clinical decisions</footer>
</body>
</html>
"""


def page(title, content, **context):
    return render_template_string(
        PAGE, title=title, content=content, **context
    )


# ---------------- LOGIN / REGISTER ----------------

@app.route("/", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    message = ""

    if request.method == "POST":
        action = request.form.get("action", "login")
        mobile = request.form.get("mobile", "").strip()
        pin = request.form.get("pin", "")

        if not re.fullmatch(r"[6-9]\d{9}", mobile):
            message = "Enter a valid 10-digit Indian mobile number."
        elif not re.fullmatch(r"\d{4,6}", pin):
            message = "PIN must contain 4 to 6 digits."
        else:
            with db() as con:
                user = con.execute(
                    "SELECT * FROM users WHERE mobile=?", (mobile,)
                ).fetchone()

                if action == "register":
                    if user:
                        message = "This mobile number is already registered. Please log in."
                    else:
                        cur = con.execute(
                            """INSERT INTO users (mobile,pin_hash,created_at)
                            VALUES (?,?,?)""",
                            (mobile, generate_password_hash(pin),
                             datetime.now().isoformat(timespec="seconds"))
                        )
                        session.clear()
                        session["user_id"] = cur.lastrowid
                        session.permanent = True
                        return redirect(url_for("profile"))

                elif user and check_password_hash(user["pin_hash"], pin):
                    session.clear()
                    session["user_id"] = user["id"]
                    session.permanent = True
                    return redirect(url_for("dashboard"))
                else:
                    message = "Login failed. Check your number and PIN."

    content = """
    <div class="card narrow">
    <h1>Welcome to MediBridge</h1>
    <p class="muted">Keep your healthcare information organised in one place.</p>
    {% if message %}<div class="notice">{{ message }}</div>{% endif %}
    <form method="post">
    <label>Mobile number</label>
    <input name="mobile" inputmode="numeric" pattern="[6-9][0-9]{9}" maxlength="10" placeholder="10-digit mobile number" required>
    <label>PIN (4–6 digits)</label>
    <input name="pin" type="password" inputmode="numeric" pattern="[0-9]{4,6}" minlength="4" maxlength="6" required>
    <button name="action" value="login">Login</button>
    <button class="secondary" name="action" value="register">Create account</button>
    </form>
    <p class="muted">Demo only: do not use a real PIN or sensitive medical information.</p>
    </div>
    """
    return page("Login", render_template_string(content, message=message))


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    with db() as con:
        records = con.execute(
            "SELECT * FROM medical_records WHERE user_id=? ORDER BY id DESC",
            (user["id"],)
        ).fetchall()
        uploads = con.execute(
            "SELECT * FROM uploads WHERE user_id=? ORDER BY id DESC",
            (user["id"],)
        ).fetchall()

    content = """
    <h1>Hello, {{ user['name'] or 'there' }} 👋</h1>
    <p class="muted">Your personal healthcare continuity dashboard.</p>
    <div class="grid">
      <section class="card"><h2>Personal profile</h2>
        <p>{{ user['name'] or 'Not completed' }}</p>
        <p>{{ user['mobile'] }}</p>
        <a class="btn" href="{{ url_for('profile') }}">Edit profile</a>
      </section>
      <section class="card"><h2>Medical history</h2>
        <p>{{ records|length }} record(s) saved</p>
        <a class="btn" href="{{ url_for('medical') }}">View / add records</a>
      </section>
      <section class="card"><h2>Reports</h2>
        <p>{{ uploads|length }} file(s) uploaded</p>
        <a class="btn" href="{{ url_for('files_page') }}">Manage files</a>
      </section>
      <section class="card"><h2>Doctor visit</h2>
        <p>Prepare a summary to discuss with your clinician.</p>
        <a class="btn" href="{{ url_for('summary') }}">Create summary</a>
      </section>
    </div>
    <section class="card"><h2>Recent medical records</h2>
    {% for r in records[:5] %}
      <div class="record"><strong>{{ r['record_type'] }}</strong>
      <p>{{ r['details'] }}</p>
      {% if r['record_type'] in ['Current medicine', 'Stopped medicine'] %}
      <p>Start date: {{ r['start_date'] or 'Not provided' }}</p>
      <p>Stop date: {{ r['stop_date'] or 'Not provided' }}</p>
      {% endif %}
      <small>{{ r['created_at'] }}</small></div>
    {% else %}<p class="muted">No records yet.</p>{% endfor %}
    </section>
    <div class="notice">This prototype is not production-ready and does not replace professional medical care.</div>
    """
    return page(
        "Dashboard",
        render_template_string(content, user=user, records=records, uploads=uploads)
    )


# ---------------- PROFILE ----------------

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()

    if request.method == "POST":
        name = request.form.get("name", "").strip()[:100]
        email = request.form.get("email", "").strip()[:150]
        address = request.form.get("address", "").strip()[:300]

        with db() as con:
            con.execute(
                "UPDATE users SET name=?,email=?,address=? WHERE id=?",
                (name, email, address, user["id"])
            )

        flash("Profile saved.")
        return redirect(url_for("dashboard"))

    content = """
    <section class="card">
    <h1>Personal profile</h1>
    <p class="muted">Aadhaar number is intentionally not collected in this demo.</p>
    <form method="post">
      <label>Full name</label><input name="name" maxlength="100" value="{{ user['name'] }}" required>
      <label>Mobile number (login ID)</label><input value="{{ user['mobile'] }}" disabled>
      <label>Email</label><input type="email" name="email" maxlength="150" value="{{ user['email'] }}">
      <label>Address</label><textarea name="address" maxlength="300" rows="3">{{ user['address'] }}</textarea>
      <button>Save profile</button>
    </form>
    </section>
    """
    return page("Profile", render_template_string(content, user=user))


# ---------------- MEDICAL HISTORY + OPTIONAL DATES ----------------

@app.route("/medical", methods=["GET", "POST"])
@login_required
def medical():
    uid = session["user_id"]

    if request.method == "POST":
        record_type = request.form.get("record_type", "").strip()
        details = request.form.get("details", "").strip()
        start_date = request.form.get("start_date", "").strip() or None
        stop_date = request.form.get("stop_date", "").strip() or None

        error = None

        if record_type not in RECORD_TYPES:
            error = "Please select a valid record type."
        elif not details or len(details) > 3000:
            error = "Enter details (maximum 3000 characters)."
        elif record_type not in MEDICINE_TYPES and (start_date or stop_date):
            error = "Dates are only available for medicine records."
        elif not valid_optional_date(start_date):
            error = "Please enter a valid start date."
        elif not valid_optional_date(stop_date):
            error = "Please enter a valid stop date."
        elif start_date and stop_date and stop_date < start_date:
            error = "Stop date cannot be earlier than start date."

        if error:
            flash(error)
        else:
            if record_type not in MEDICINE_TYPES:
                start_date = None
                stop_date = None

            with db() as con:
                con.execute(
                    """INSERT INTO medical_records
                    (user_id,record_type,details,created_at,start_date,stop_date)
                    VALUES (?,?,?,?,?,?)""",
                    (uid, record_type, details,
                     datetime.now().isoformat(timespec="seconds"),
                     start_date, stop_date)
                )
            flash("Medical record saved.")

        return redirect(url_for("medical"))

    with db() as con:
        records = con.execute(
            "SELECT * FROM medical_records WHERE user_id=? ORDER BY id DESC",
            (uid,)
        ).fetchall()

    content = """
    <section class="card">
    <h1>Medical history</h1>
    <p class="muted">Use fictional data for this demo. Medicine dates are optional.</p>
    <form method="post">
      <label>Record type</label>
      <select name="record_type" id="record_type" required>
        <option value="Past condition">Past condition</option>
        <option value="Current symptom">Current symptom</option>
        <option value="Current medicine">Current medicine</option>
        <option value="Stopped medicine">Stopped medicine</option>
        <option value="Allergy">Allergy</option>
        <option value="Other">Other</option>
      </select>

      <div id="medicine_dates" hidden>
        <label for="start_date">Medicine Start Date (optional)</label>
        <input type="date" id="start_date" name="start_date">
        <label for="stop_date">Medicine Stop Date (optional)</label>
        <input type="date" id="stop_date" name="stop_date">
        <p class="muted">Leave either or both dates blank if unknown.</p>
      </div>

      <label>Details</label>
      <textarea name="details" rows="4" maxlength="3000"
      placeholder="Medicine name or other relevant details" required></textarea>
      <button type="submit">Save record</button>
    </form>
    </section>

    <section class="card"><h2>Saved records</h2>
    {% for r in records %}
      <div class="record">
        <strong>{{ r['record_type'] }}</strong>
        <p>{{ r['details'] }}</p>
        {% if r['record_type'] in ['Current medicine', 'Stopped medicine'] %}
          <p><strong>Start date:</strong> {{ r['start_date'] or 'Not provided' }}</p>
          <p><strong>Stop date:</strong> {{ r['stop_date'] or 'Not provided' }}</p>
        {% endif %}
        <small>Record created: {{ r['created_at'] }}</small>
      </div>
    {% else %}<p class="muted">No records saved yet.</p>{% endfor %}
    </section>

    <script>
    const typeSelect = document.getElementById("record_type");
    const dateFields = document.getElementById("medicine_dates");

    function toggleMedicineDates() {
      dateFields.hidden = ![
        "Current medicine", "Stopped medicine"
      ].includes(typeSelect.value);
    }

    typeSelect.addEventListener("change", toggleMedicineDates);
    toggleMedicineDates();
    </script>
    """
    return page("Medical history", render_template_string(content, records=records))


# ---------------- REPORT UPLOADS + VIEW BUTTON ----------------

@app.route("/files", methods=["GET", "POST"])
@login_required
def files_page():
    uid = session["user_id"]

    if request.method == "POST":
        f = request.files.get("file")

        if not f or not f.filename:
            flash("Choose a file first.")
        else:
            filename = secure_filename(f.filename)
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

            if not filename or ext not in ALLOWED_EXTENSIONS:
                flash("Only PDF, PNG and JPG files are allowed.")
            else:
                stored = f"{os.urandom(16).hex()}.{ext}"
                f.save(UPLOAD_DIR / stored)

                with db() as con:
                    con.execute(
                        """INSERT INTO uploads
                        (user_id,filename,stored_name,created_at)
                        VALUES (?,?,?,?)""",
                        (uid, filename, stored,
                         datetime.now().isoformat(timespec="seconds"))
                    )
                flash("File uploaded. Use fictional or sample reports only.")

        return redirect(url_for("files_page"))

    with db() as con:
        files = con.execute(
            "SELECT * FROM uploads WHERE user_id=? ORDER BY id DESC",
            (uid,)
        ).fetchall()

    content = """
    <section class="card">
    <h1>Reports and prescriptions</h1>
    <p class="muted">Allowed formats: PDF, PNG, JPG. Maximum size: 5 MB. Use sample files only.</p>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg" required>
      <button>Upload file</button>
    </form>
    </section>

    <section class="card"><h2>Uploaded files</h2>
    {% for f in files %}
      <div class="record">
        <strong>{{ f['filename'] }}</strong>
        <p class="muted">Uploaded: {{ f['created_at'] }}</p>
        <a class="btn" href="{{ url_for('view_report', file_id=f['id']) }}"
           target="_blank" rel="noopener">View Report</a>
      </div>
    {% else %}
      <p class="muted">No files uploaded yet.</p>
    {% endfor %}
    </section>
    """
    return page("Files", render_template_string(content, files=files))


# ---------------- SECURE REPORT VIEWER ----------------

@app.route("/view-report/<int:file_id>")
@login_required
def view_report(file_id):
    uid = session["user_id"]

    # A user can only access a report linked to their own account.
    with db() as con:
        report = con.execute(
            "SELECT * FROM uploads WHERE id=? AND user_id=?",
            (file_id, uid)
        ).fetchone()

    if not report:
        abort(404)

    stored_name = report["stored_name"]
    file_path = UPLOAD_DIR / stored_name

    if not file_path.is_file():
        abort(404, description="Uploaded report file was not found.")

    ext = stored_name.rsplit(".", 1)[-1].lower()
    mime_types = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg"
    }

    return send_from_directory(
        str(UPLOAD_DIR),
        stored_name,
        mimetype=mime_types.get(ext, "application/octet-stream"),
        as_attachment=False,
        download_name=report["filename"]
    )


# ---------------- DOCTOR VISIT SUMMARY ----------------

@app.route("/summary")
@login_required
def summary():
    user = current_user()

    with db() as con:
        records = con.execute(
            "SELECT * FROM medical_records WHERE user_id=? ORDER BY id DESC",
            (user["id"],)
        ).fetchall()

    content = """
    <section class="card">
    <h1>Doctor-visit summary</h1>
    <p class="muted">Review this draft before sharing it with a clinician.</p>
    <label>Patient name</label><input id="patient" value="{{ user['name'] }}">
    <label>Mobile</label><input value="{{ user['mobile'] }}" disabled>
    <label>Email</label><input value="{{ user['email'] }}" disabled>
    <label>Address</label><textarea rows="2" disabled>{{ user['address'] }}</textarea>

    <label>Medical notes</label>
    <textarea id="notes" rows="14">{% for r in records %}{{ r['record_type'] }}: {{ r['details'] }}
{% if r['record_type'] in ['Current medicine', 'Stopped medicine'] %}Medicine start date: {{ r['start_date'] or 'Not provided' }}
Medicine stop date: {{ r['stop_date'] or 'Not provided' }}
{% endif %}Record created: {{ r['created_at'] }}

{% endfor %}</textarea>
    <button type="button" onclick="window.print()">Print / Save as PDF</button>
    </section>
    """
    return page("Doctor summary", render_template_string(content, user=user, records=records))


# ---------------- HELP ASSISTANT ----------------

@app.route("/assistant", methods=["POST"])
@login_required
def assistant():
    question = request.form.get("question", "").strip().lower()[:500]

    if not question:
        reply = "Type a question first."
    elif any(word in question for word in [
        "emergency", "can't breathe", "cannot breathe", "chest pain"
    ]):
        reply = (
            "If this may be an emergency, contact local emergency services "
            "immediately and tell a trusted person nearby. Do not wait for this demo."
        )
    elif any(word in question for word in [
        "stop medicine", "stop medication", "dose", "dosage",
        "diagnose", "diagnosis"
    ]):
        reply = (
            "I can't diagnose or recommend medicine changes. "
            "Please contact your doctor or pharmacist."
        )
    else:
        reply = (
            "Demo assistant: I can help organise records or prepare "
            "questions for your doctor, but I am not a real AI medical service."
        )

    content = """
    <h1>Assistant response</h1>
    <section class="card">
      <p>{{ reply }}</p>
      <a class="btn" href="{{ url_for('dashboard') }}">Back to dashboard</a>
    </section>
    """
    return page("Assistant", render_template_string(content, reply=reply))


# ---------------- LOGOUT / ERRORS ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.errorhandler(413)
def too_large(error):
    return "File too large. Maximum upload size is 5 MB.", 413


if __name__ == "__main__":
    app.run(debug=True)
