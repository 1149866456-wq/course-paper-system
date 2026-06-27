import os
import uuid
from datetime import datetime
from functools import wraps
from io import BytesIO

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD", "admin123")

# Supabase configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# 本地开发时可以从 .env 文件读取
if not SUPABASE_URL or not SUPABASE_KEY:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
        SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
    except ImportError:
        pass

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set as environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "zip", "rar"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ==================== 同学端 ====================

@app.route("/")
def index():
    # Get all courses
    courses_response = supabase.table("courses").select("*").execute()
    courses = courses_response.data
    
    # Get submitted courses for the given name (if provided)
    name = request.args.get("name", "").strip()
    submitted_courses = set()
    
    if name:
        # Find student by name
        student_response = supabase.table("students").select("id").eq("name", name).execute()
        if student_response.data:
            student_id = student_response.data[0]["id"]
            # Get submissions for this student
            submissions_response = supabase.table("submissions").select("course_id").eq("student_id", student_id).execute()
            submitted_courses = {sub["course_id"] for sub in submissions_response.data}
    
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

    # Verify student exists by name only
    student_response = supabase.table("students").select("id, name").eq("name", name).execute()
    
    if not student_response.data:
        flash("姓名不存在，请核对后重试", "error")
        return redirect(url_for("index"))

    student = student_response.data[0]
    student_id_db = student["id"]
    student_id_original = str(student["id"]).zfill(8)  # 用 id 填充为8位数字
    course_id_int = int(course_id)

    # Check if existing submission (for overwrite)
    existing_response = supabase.table("submissions").select("id, filename").eq("student_id", student_id_db).eq("course_id", course_id_int).execute()
    existing = existing_response.data[0] if existing_response.data else None

    # Get course info
    course_response = supabase.table("courses").select("name").eq("id", course_id_int).execute()
    course = course_response.data[0] if course_response.data else None
    
    if not course:
        flash("课程不存在", "error")
        return redirect(url_for("index"))
    
    course_name = course["name"]
    # Use course_id as folder name to avoid Chinese characters in path
    course_folder = f"course_{course_id_int}"
    
    # Upload file to Supabase Storage
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = secure_filename(file.filename)
    filename = f"{student_id_original}_{timestamp}_{safe_filename}"
    file_path = f"{course_folder}/{filename}"
    
    # Read file content
    file_content = file.read()
    
    # Upload to Supabase Storage
    storage_response = supabase.storage.from_("papers").upload(file_path, file_content)
    
    if hasattr(storage_response, 'error') and storage_response.error:
        flash(f"文件上传失败: {storage_response.error}", "error")
        return redirect(url_for("index"))

    # Save to database (title is auto-generated from filename)
    submit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = os.path.splitext(safe_filename)[0]

    if existing:
        # Delete old file from storage
        old_filename = existing["filename"]
        old_file_path = f"{course_folder}/{old_filename}"
        supabase.storage.from_("papers").remove([old_file_path])
        
        # Update existing record
        supabase.table("submissions").update({
            "title": title,
            "filename": filename,
            "submit_time": submit_time
        }).eq("id", existing["id"]).execute()
        
        flash("论文已更新覆盖！", "success")
    else:
        # Insert new record
        supabase.table("submissions").insert({
            "student_id": student_id_db,
            "course_id": course_id_int,
            "title": title,
            "filename": filename,
            "submit_time": submit_time
        }).execute()
        
        flash("论文提交成功！", "success")

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
    # Get all courses with submission counts
    courses_response = supabase.table("courses").select("*").execute()
    courses = courses_response.data
    
    stats = []
    for course in courses:
        # Count submissions for this course
        submissions_response = supabase.table("submissions").select("id", count="exact").eq("course_id", course["id"]).execute()
        submitted_count = len(submissions_response.data) if submissions_response.data else 0
        
        # Get all students
        students_response = supabase.table("students").select("*").execute()
        all_students = students_response.data
        total_count = len(all_students)
        
        stats.append({
            "course": course,
            "submitted": submitted_count,
            "total": total_count,
            "pending": total_count - submitted_count
        })

    return render_template("admin.html", stats=stats)


@app.route("/admin/course/<int:course_id>")
@login_required
def admin_course(course_id):
    # Get course info
    course_response = supabase.table("courses").select("*").eq("id", course_id).execute()
    course = course_response.data[0] if course_response.data else None
    
    if not course:
        flash("课程不存在", "error")
        return redirect(url_for("admin_dashboard"))

    # Get submissions with student names
    submissions_response = supabase.table("submissions").select("*, students(name)").eq("course_id", course_id).execute()
    submissions = submissions_response.data

    # Get all students to find unsubmitted
    students_response = supabase.table("students").select("*").execute()
    all_students = {s["id"]: s for s in students_response.data}
    
    submitted_student_ids = {sub["student_id"] for sub in submissions}
    unsubmitted = [all_students[sid] for sid in all_students if sid not in submitted_student_ids]

    return render_template("course.html", course=course, submissions=submissions, unsubmitted=unsubmitted)


@app.route("/admin/download/<int:course_id>")
@login_required
def admin_download(course_id):
    # Get course name
    course_response = supabase.table("courses").select("name").eq("id", course_id).execute()
    course_name = course_response.data[0]["name"] if course_response.data else "unknown"
    
    # Get all submissions for this course
    submissions_response = supabase.table("submissions").select("*").eq("course_id", course_id).execute()
    submissions = submissions_response.data

    if not submissions:
        flash("该课程暂无提交记录", "error")
        return redirect(url_for("admin_course", course_id=course_id))

    # Create zip file in memory
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in submissions:
            # Download file from Supabase Storage
            file_path = f"course_{course_id}/{sub['filename']}"
            try:
                file_data = supabase.storage.from_("papers").download(file_path)
                zf.writestr(sub["filename"], file_data)
            except Exception as e:
                print(f"Error downloading {file_path}: {e}")
                continue

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{course_name}_论文汇总.zip",
    )


@app.route("/admin/download-all")
@login_required
def admin_download_all():
    # Get all submissions
    submissions_response = supabase.table("submissions").select("*, courses(name)").execute()
    submissions = submissions_response.data

    if not submissions:
        flash("暂无提交记录", "error")
        return redirect(url_for("admin_dashboard"))

    # Create zip file in memory
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in submissions:
            course_name = sub["courses"]["name"]
            file_path = f"course_{sub['course_id']}/{sub['filename']}"
            try:
                file_data = supabase.storage.from_("papers").download(file_path)
                zf.writestr(f"{course_name}/{sub['filename']}", file_data)
            except Exception as e:
                print(f"Error downloading {file_path}: {e}")
                continue

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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
