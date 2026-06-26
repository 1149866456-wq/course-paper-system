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
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "admin123")

# Render Disk 持久化存储路径
# Render Disk 挂载到 /data，数据库和上传文件都存这里
DATA_DIR = "/data" if os.path.exists("/data") else os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(DATA_DIR, "database.db")
app.config["UPLOAD_FOLDER"] = os.path.join(DATA_DIR, "uploads")

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "zip", "rar"}

# 初始数据
COURSES = [
    ("巫运辉 聚合物反应工程 截止时间6月28号", "2025-06-28"),
    ("巫运辉 高分子成型加工设备 截止时间6月29号", "2025-06-29"),
    ("项目化实践报告4 截止时间7月3号", "2025-07-03"),
    ("谢华理 高分子材料改性 截止时间6月30号", "2025-06-30"),
    ("杨树颖 高分子材料助剂 截止时间6月28号", "2025-06-28"),
]

STUDENTS = [
    ("陈广园",),
    ("陈欣婷",),
    ("陈昱杰",),
    ("成文熙",),
    ("崔廷帅",),
    ("范浩锋",),
    ("韩静莹",),
    ("何俊锋",),
    ("侯泓安",),
    ("黄俊铭",),
    ("李海怡",),
    ("李若萱",),
    ("梁浩云",),
    ("林土生",),
    ("刘滨濠",),
    ("刘璐",),
    ("卢明威",),
    ("莫凯钊",),
    ("潘晓婷",),
    ("谢昕瑶",),
    ("谢作琛",),
    ("杨进坚",),
    ("张绍飞",),
    ("钟翼烛",),
    ("邹润龙",),
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
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            filename TEXT NOT NULL,
            submit_time TEXT NOT NULL,
            UNIQUE(student_id, course_id)
        );
        """
    )

    # Insert initial data
    for name, deadline in COURSES:
        db.execute("INSERT INTO courses (name, deadline) VALUES (?, ?)", (name, deadline))

    for name_tuple in STUDENTS:
        db.execute("INSERT INTO students (name) VALUES (?)", name_tuple)

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
        "SELECT id FROM students WHERE name = ?",
        (name,),
    ).fetchone()

    if not student:
        flash("姓名不存在，请核对后重试", "error")
        return redirect(url_for("index"))

    student_id_db = student["id"]
    course_id_int = int(course_id)

    # Check if existing submission (for overwrite)
    existing = db.execute(
        "SELECT id, filename FROM submissions WHERE student_id = ? AND course_id = ?",
        (student_id_db, course_id_int),
    ).fetchone()

    # Save file
    course = db.execute("SELECT name FROM courses WHERE id = ?", (course_id_int,)).fetchone()
    course_name = course["name"]
    upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], f"course_{course_id_int}")
    os.makedirs(upload_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = secure_filename(file.filename)
    filename = f"{student_id_db}_{timestamp}_{safe_filename}"
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
    stats = []
    for course in courses:
        submitted = db.execute(
            "SELECT COUNT(*) as count FROM submissions WHERE course_id = ?",
            (course["id"],)
        ).fetchone()["count"]
        total = db.execute("SELECT COUNT(*) as count FROM students").fetchone()["count"]
        stats.append({
            "course": course,
            "submitted": submitted,
            "total": total,
            "pending": total - submitted
        })

    return render_template("admin.html", stats=stats)


@app.route("/admin/course/<int:course_id>")
@login_required
def admin_course(course_id):
    db = get_db()
    course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        flash("课程不存在", "error")
        return redirect(url_for("admin_dashboard"))

    submissions = db.execute(
        "SELECT s.*, st.name FROM submissions s JOIN students st ON s.student_id = st.id WHERE s.course_id = ? ORDER BY s.submit_time DESC",
        (course_id,)
    ).fetchall()

    all_students = {s["id"]: s for s in db.execute("SELECT * FROM students").fetchall()}
    submitted_ids = {sub["student_id"] for sub in submissions}
    unsubmitted = [all_students[sid] for sid in all_students if sid not in submitted_ids]

    return render_template("course.html", course=course, submissions=submissions, unsubmitted=unsubmitted)


@app.route("/admin/download/<int:course_id>")
@login_required
def admin_download(course_id):
    db = get_db()
    course = db.execute("SELECT name FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        flash("课程不存在", "error")
        return redirect(url_for("admin_dashboard"))

    submissions = db.execute(
        "SELECT * FROM submissions WHERE course_id = ?",
        (course_id,)
    ).fetchall()

    if not submissions:
        flash("该课程暂无提交记录", "error")
        return redirect(url_for("admin_course", course_id=course_id))

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in submissions:
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], f"course_{course_id}", sub["filename"])
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    zf.writestr(sub["filename"], f.read())

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{course['name']}_论文汇总.zip",
    )


@app.route("/admin/download-all")
@login_required
def admin_download_all():
    db = get_db()
    submissions = db.execute(
        "SELECT s.*, c.name as course_name FROM submissions s JOIN courses c ON s.course_id = c.id"
    ).fetchall()

    if not submissions:
        flash("暂无提交记录", "error")
        return redirect(url_for("admin_dashboard"))

    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in submissions:
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], f"course_{sub['course_id']}", sub["filename"])
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    zf.writestr(f"{sub['course_name']}/{sub['filename']}", f.read())

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name="全部论文汇总.zip",
    )


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", error="页面不存在"), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("error.html", error="服务器内部错误"), 500


# Initialize database on app startup (for production)
with app.app_context():
    if not os.path.exists(DATABASE):
        init_db()
        print("Database initialized!")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
