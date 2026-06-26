import os
import sqlite3
import zipfile
from datetime import datetime
from functools import wraps
from io import BytesIO

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "admin123")

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "zip", "rar"}

# 初始数据
COURSES = [
    ("巫运辉_星期二早34节", "2025-06-28"),
    ("巫运辉_星期一下午56节", "2025-06-29"),
    ("项目化实践报告4", "2025-07-03"),
    ("谢华理_星期三早12节", "2025-06-30"),
    ("杨树颖_星期二早12节", "2025-06-28"),
]

STUDENTS = [
    ("陈广园", "20210101"),
    ("陈欣婷", "20210102"),
    ("陈昱杰", "20210103"),
    ("成文熙", "20210104"),
    ("崔廷帅", "20210105"),
    ("范浩锋", "20210106"),
    ("韩静莹", "20210107"),
    ("何俊锋", "20210108"),
    ("侯泓安", "20210109"),
    ("黄俊铭", "20210110"),
    ("李海怡", "20210111"),
    ("李若萱", "20210112"),
    ("梁浩云", "20210113"),
    ("林土生", "20210114"),
    ("刘滨濠", "20210115"),
    ("刘璐", "20210116"),
    ("卢明威", "20210117"),
    ("莫凯钊", "20210118"),
    ("潘晓婷", "20210119"),
    ("谢昕瑶", "20210120"),
    ("谢作琛", "20210121"),
    ("杨进坚", "20210122"),
    ("张绍飞", "20210123"),
    ("钟翼烛", "20210124"),
    ("邹润龙", "20210125"),
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        DROP TABLE IF EXISTS submissions;
        DROP TABLE IF EXISTS students;
        DROP TABLE IF EXISTS courses;

        CREATE TABLE courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            deadline TEXT NOT NULL
        );

        CREATE TABLE students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            student_id TEXT NOT NULL UNIQUE
        );

        CREATE TABLE submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            filename TEXT NOT NULL,
            submit_time TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (course_id) REFERENCES courses(id),
            UNIQUE(student_id, course_id)
        );
    """
    )

    # Insert initial data
    for name, deadline in COURSES:
        db.execute("INSERT INTO courses (name, deadline) VALUES (?, ?)", (name, deadline))

    for name, sid in STUDENTS:
        db.execute("INSERT INTO students (name, student_id) VALUES (?, ?)", (name, sid))

    db.commit()
    db.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ==================== 同学端 ====================

@app.route("/")
def index():
    db = get_db()
    courses = db.execute("SELECT * FROM courses").fetchall()
    
    # Get submitted courses for the given name (if provided)
    name = request.args.get("name", "").strip()
    submitted_courses = set()
    if name:
        student = db.execute("SELECT id FROM students WHERE name = ?", (name,)).fetchone()
        if student:
            submissions = db.execute(
                "SELECT course_id FROM submissions WHERE student_id = ?",
                (student["id"],)
            ).fetchall()
            submitted_courses = {sub["course_id"] for sub in submissions}
    
    return render_template("upload.html", courses=courses, submitted_courses=submitted_courses, name=name)


@app.route("/submit", methods=["POST"])
def submit():
    name = request.form.get("name", "").strip()
    course_id = request.form.get("course_id", "").strip()
    file = request.files.get("file")

    # Validation
    if not all([name, course_id, file]):
        flash("请填写姓名、选择课程并上传文件", "error")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("仅支持 PDF, Word, ZIP, RAR 格式", "error")
        return redirect(url_for("index"))

    db = get_db()

    # Verify student exists by name only
    student = db.execute(
        "SELECT id, student_id FROM students WHERE name = ?",
        (name,),
    ).fetchone()

    if not student:
        flash("姓名不存在，请核对后重试", "error")
        return redirect(url_for("index"))

    student_id_db = student["id"]
    student_id_original = student["student_id"]
    course_id_int = int(course_id)

    # Check if existing submission (for overwrite)
    existing = db.execute(
        "SELECT id, filename FROM submissions WHERE student_id = ? AND course_id = ?",
        (student_id_db, course_id_int),
    ).fetchone()

    # Save file
    course = db.execute("SELECT name FROM courses WHERE id = ?", (course_id_int,)).fetchone()
    course_name = course["name"]
    upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], course_name)
    os.makedirs(upload_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = secure_filename(file.filename)
    filename = f"{student_id_original}_{timestamp}_{safe_filename}"
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)

    # Save to database (title is auto-generated from filename)
    submit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = os.path.splitext(safe_filename)[0]

    if existing:
        # Delete old file
        old_filename = existing["filename"]
        old_filepath = os.path.join(upload_dir, old_filename)
        if os.path.exists(old_filepath):
            os.remove(old_filepath)
        # Update existing record
        db.execute(
            "UPDATE submissions SET title = ?, filename = ?, submit_time = ? WHERE id = ?",
            (title, filename, submit_time, existing["id"]),
        )
        flash("论文已更新覆盖！", "success")
    else:
        # Insert new record
        db.execute(
            "INSERT INTO submissions (student_id, course_id, title, filename, submit_time) VALUES (?, ?, ?, ?, ?)",
            (student_id_db, course_id_int, title, filename, submit_time),
        )
        flash("论文提交成功！", "success")

    db.commit()
    return redirect(url_for("index"))


# ==================== 管理后台 ====================


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == app.config["ADMIN_PASSWORD"]:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            flash("密码错误", "error")

    return render_template("login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    db = get_db()
    courses = db.execute("SELECT * FROM courses").fetchall()
    students = db.execute("SELECT * FROM students").fetchall()
    total_students = len(students)

    # Build stats for each course
    course_stats = []
    for course in courses:
        submissions = db.execute(
            "SELECT s.*, st.name, st.student_id FROM submissions s JOIN students st ON s.student_id = st.id WHERE s.course_id = ? ORDER BY s.submit_time DESC",
            (course["id"],),
        ).fetchall()

        submitted_count = len(submissions)
        submitted_ids = {sub["student_id"] for sub in submissions}

        unsubmitted = [
            {"name": s["name"], "student_id": s["student_id"]}
            for s in students
            if s["id"] not in submitted_ids
        ]

        course_stats.append(
            {
                "course": course,
                "submitted_count": submitted_count,
                "total": total_students,
                "submissions": submissions,
                "unsubmitted": unsubmitted,
            }
        )

    return render_template("dashboard.html", course_stats=course_stats)


@app.route("/admin/download/<int:course_id>")
@login_required
def download_course(course_id):
    db = get_db()
    course = db.execute("SELECT name FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        flash("课程不存在", "error")
        return redirect(url_for("admin_dashboard"))

    course_name = course["name"]
    upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], course_name)

    if not os.path.exists(upload_dir):
        flash("该课程暂无提交文件", "error")
        return redirect(url_for("admin_dashboard"))

    # Create zip in memory
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(upload_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.join(course_name, file)
                zf.write(file_path, arcname)

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{course_name}_论文汇总.zip",
    )


# ==================== 初始化 ====================

# Initialize database on app startup (for production)
with app.app_context():
    if not os.path.exists(DATABASE):
        init_db()
        print("Database initialized!")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
