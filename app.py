"""
app.py
Student Management System — web version (Flask).

Run locally:   python app.py
Deploy:        see README.md (Render/Railway instructions)
"""

import os
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, session, flash

from database import init_db, get_connection
from auth import login_required, current_user, verify_login, start_session, create_user, delete_user

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-this-in-production")

# Create the database tables now, at import time. This must NOT be inside
# `if __name__ == "__main__":` below — gunicorn (used in production on
# Render/Railway) imports this file and calls the `app` object directly,
# it never runs that block, so init_db() would never fire and every
# database query would fail with "no such table".
init_db()


# ---------------- Portal select & login ----------------

ROLE_META = {
    "admin": {"icon": "🛡️", "title": "Admin Portal", "accent": "#7c5cff"},
    "teacher": {"icon": "👩‍🏫", "title": "Teacher Portal", "accent": "#2dd4bf"},
    "student": {"icon": "🧑‍🎓", "title": "Student Portal", "accent": "#fbbf24"},
}


@app.route("/")
def portal_select():
    if "user_id" in session:
        return redirect(url_for(f"{session['role']}_dashboard"))
    return render_template("portal_select.html", roles={k: v for k, v in ROLE_META.items() if k != "admin"})


@app.route("/admin-login")
def admin_login_page():
    return render_template("login.html", role="admin", meta=ROLE_META["admin"])


@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    if role not in ROLE_META:
        return redirect(url_for("portal_select"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = verify_login(username, password)
        if not user:
            flash("Invalid username or password.", "error")
            return render_template("login.html", role=role, meta=ROLE_META[role])
        if user["role"] != role:
            flash(f"This account is not registered as {ROLE_META[role]['title']}.", "error")
            return render_template("login.html", role=role, meta=ROLE_META[role])
        start_session(user)
        return redirect(url_for(f"{role}_dashboard"))
    return render_template("login.html", role=role, meta=ROLE_META[role])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("portal_select"))


# ==================== ADMIN ====================

@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    conn = get_connection()
    counts = {}
    for label, table in [("Teachers", "teachers"), ("Students", "students"),
                          ("Classes", "classes"), ("Courses", "courses")]:
        counts[label] = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
    conn.close()
    return render_template("admin/dashboard.html", counts=counts)


@app.route("/admin/teachers", methods=["GET", "POST"])
@login_required("admin")
def admin_teachers():
    conn = get_connection()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            user_id = create_user(
                request.form["username"].strip(), request.form["password"], "teacher",
                request.form["full_name"].strip(), request.form.get("email", "").strip()
            )
            if user_id is None:
                flash("That username is already taken.", "error")
            else:
                conn.execute("INSERT INTO teachers (user_id, subject, phone) VALUES (?,?,?)",
                             (user_id, request.form.get("subject", "").strip(), request.form.get("phone", "").strip()))
                conn.commit()
                flash("Teacher added.", "success")
        elif action == "delete":
            delete_user(request.form["user_id"])
            flash("Teacher deleted.", "success")
        conn.close()
        return redirect(url_for("admin_teachers"))

    teachers = conn.execute("""
        SELECT t.id, u.id as user_id, u.full_name, u.username, t.subject, t.phone, u.email
        FROM teachers t JOIN users u ON t.user_id = u.id ORDER BY u.full_name
    """).fetchall()
    conn.close()
    return render_template("admin/teachers.html", teachers=teachers)


@app.route("/admin/students", methods=["GET", "POST"])
@login_required("admin")
def admin_students():
    conn = get_connection()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            user_id = create_user(
                request.form["username"].strip(), request.form["password"], "student",
                request.form["full_name"].strip(), request.form.get("email", "").strip()
            )
            if user_id is None:
                flash("That username is already taken.", "error")
            else:
                try:
                    class_id = request.form.get("class_id") or None
                    conn.execute("INSERT INTO students (user_id, roll_no, class_id, phone, dob) VALUES (?,?,?,?,?)",
                                 (user_id, request.form.get("roll_no", "").strip() or None, class_id,
                                  request.form.get("phone", "").strip(), request.form.get("dob", "").strip()))
                    conn.commit()
                    flash("Student enrolled.", "success")
                except Exception:
                    delete_user(user_id)  # roll back the orphaned login account
                    flash("That roll number already exists.", "error")
        elif action == "delete":
            delete_user(request.form["user_id"])
            flash("Student deleted.", "success")
        conn.close()
        return redirect(url_for("admin_students"))

    search = request.args.get("q", "").strip()
    query = """
        SELECT s.id, u.id as user_id, u.full_name, u.username, s.roll_no,
               COALESCE(c.class_name || ' ' || COALESCE(c.section,''), 'Unassigned') as class_name, s.phone
        FROM students s JOIN users u ON s.user_id = u.id
        LEFT JOIN classes c ON s.class_id = c.id
    """
    params = ()
    if search:
        query += " WHERE u.full_name LIKE ? OR s.roll_no LIKE ?"
        params = (f"%{search}%", f"%{search}%")
    query += " ORDER BY u.full_name"
    students = conn.execute(query, params).fetchall()
    classes = conn.execute("SELECT id, class_name, section FROM classes ORDER BY class_name").fetchall()
    conn.close()
    return render_template("admin/students.html", students=students, classes=classes, search=search)


@app.route("/admin/classes", methods=["GET", "POST"])
@login_required("admin")
def admin_classes():
    conn = get_connection()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            teacher_id = request.form.get("teacher_id") or None
            conn.execute("INSERT INTO classes (class_name, section, teacher_id) VALUES (?,?,?)",
                         (request.form["class_name"].strip(), request.form.get("section", "").strip(), teacher_id))
            conn.commit()
            flash("Class added.", "success")
        elif action == "delete":
            conn.execute("DELETE FROM classes WHERE id=?", (request.form["class_id"],))
            conn.commit()
            flash("Class deleted.", "success")
        conn.close()
        return redirect(url_for("admin_classes"))

    classes = conn.execute("""
        SELECT c.id, c.class_name, c.section, COALESCE(u.full_name, 'Unassigned') as teacher_name
        FROM classes c LEFT JOIN teachers t ON c.teacher_id = t.id LEFT JOIN users u ON t.user_id = u.id
        ORDER BY c.class_name
    """).fetchall()
    teachers = conn.execute("SELECT t.id, u.full_name FROM teachers t JOIN users u ON t.user_id=u.id").fetchall()
    conn.close()
    return render_template("admin/classes.html", classes=classes, teachers=teachers)


@app.route("/admin/courses", methods=["GET", "POST"])
@login_required("admin")
def admin_courses():
    conn = get_connection()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            try:
                conn.execute("INSERT INTO courses (course_name, course_code, class_id) VALUES (?,?,?)",
                             (request.form["course_name"].strip(), request.form["course_code"].strip(),
                              request.form.get("class_id") or None))
                conn.commit()
                flash("Course added.", "success")
            except Exception:
                flash("That course code already exists.", "error")
        elif action == "delete":
            conn.execute("DELETE FROM courses WHERE id=?", (request.form["course_id"],))
            conn.commit()
            flash("Course deleted.", "success")
        conn.close()
        return redirect(url_for("admin_courses"))

    courses = conn.execute("""
        SELECT co.id, co.course_name, co.course_code,
               COALESCE(c.class_name || ' ' || COALESCE(c.section,''), 'Unassigned') as class_name
        FROM courses co LEFT JOIN classes c ON co.class_id = c.id ORDER BY co.course_name
    """).fetchall()
    classes = conn.execute("SELECT id, class_name, section FROM classes ORDER BY class_name").fetchall()
    conn.close()
    return render_template("admin/courses.html", courses=courses, classes=classes)


# ==================== TEACHER ====================

def _teacher_id():
    conn = get_connection()
    row = conn.execute("SELECT id FROM teachers WHERE user_id=?", (session["user_id"],)).fetchone()
    conn.close()
    return row["id"] if row else None


@app.route("/teacher")
@login_required("teacher")
def teacher_dashboard():
    tid = _teacher_id()
    conn = get_connection()
    classes = conn.execute(
        "SELECT id, class_name, section FROM classes WHERE teacher_id=?", (tid,)
    ).fetchall() if tid else []
    conn.close()
    return render_template("teacher/dashboard.html", classes=classes)


@app.route("/teacher/students")
@login_required("teacher")
def teacher_students():
    tid = _teacher_id()
    conn = get_connection()
    classes = conn.execute("SELECT id, class_name, section FROM classes WHERE teacher_id=?", (tid,)).fetchall()
    class_id = request.args.get("class_id", type=int)
    students = []
    if class_id:
        students = conn.execute("""
            SELECT s.id, u.full_name, s.roll_no, s.phone FROM students s
            JOIN users u ON s.user_id=u.id WHERE s.class_id=?
        """, (class_id,)).fetchall()
    conn.close()
    return render_template("teacher/students.html", classes=classes, students=students, class_id=class_id)


@app.route("/teacher/attendance", methods=["GET", "POST"])
@login_required("teacher")
def teacher_attendance():
    tid = _teacher_id()
    conn = get_connection()
    classes = conn.execute("SELECT id, class_name, section FROM classes WHERE teacher_id=?", (tid,)).fetchall()
    class_id = request.args.get("class_id", type=int) or request.form.get("class_id", type=int)
    today = date.today().isoformat()

    if request.method == "POST":
        att_date = request.form.get("date", today)
        for key, value in request.form.items():
            if key.startswith("status_"):
                sid = key.replace("status_", "")
                conn.execute("""
                    INSERT INTO attendance (student_id, class_id, date, status) VALUES (?,?,?,?)
                    ON CONFLICT(student_id, date) DO UPDATE SET status=excluded.status
                """, (sid, class_id, att_date, value))
        conn.commit()
        flash("Attendance saved.", "success")
        conn.close()
        return redirect(url_for("teacher_attendance", class_id=class_id))

    students = []
    if class_id:
        students = conn.execute("""
            SELECT s.id, u.full_name FROM students s JOIN users u ON s.user_id=u.id WHERE s.class_id=?
        """, (class_id,)).fetchall()
    conn.close()
    return render_template("teacher/attendance.html", classes=classes, students=students,
                            class_id=class_id, today=today)


@app.route("/teacher/marks", methods=["GET", "POST"])
@login_required("teacher")
def teacher_marks():
    tid = _teacher_id()
    conn = get_connection()
    classes = conn.execute("SELECT id, class_name, section FROM classes WHERE teacher_id=?", (tid,)).fetchall()
    class_id = request.args.get("class_id", type=int) or request.form.get("class_id", type=int)

    if request.method == "POST":
        conn.execute("""
            INSERT INTO marks (student_id, course_id, exam_type, marks_obtained, max_marks)
            VALUES (?,?,?,?,?)
        """, (request.form["student_id"], request.form["course_id"], request.form["exam_type"],
              float(request.form["marks_obtained"]), float(request.form["max_marks"])))
        conn.commit()
        flash("Marks recorded.", "success")
        conn.close()
        return redirect(url_for("teacher_marks", class_id=class_id))

    students, courses, marks = [], [], []
    if class_id:
        students = conn.execute("""
            SELECT s.id, u.full_name FROM students s JOIN users u ON s.user_id=u.id WHERE s.class_id=?
        """, (class_id,)).fetchall()
        courses = conn.execute("SELECT id, course_name FROM courses WHERE class_id=?", (class_id,)).fetchall()
        marks = conn.execute("""
            SELECT m.id, u.full_name as student_name, co.course_name, m.exam_type,
                   m.marks_obtained, m.max_marks
            FROM marks m JOIN students s ON m.student_id=s.id JOIN users u ON s.user_id=u.id
            JOIN courses co ON m.course_id=co.id WHERE s.class_id=? ORDER BY m.date DESC
        """, (class_id,)).fetchall()
    conn.close()
    return render_template("teacher/marks.html", classes=classes, students=students,
                            courses=courses, marks=marks, class_id=class_id)


# ==================== STUDENT ====================

def _student_row():
    conn = get_connection()
    row = conn.execute("SELECT * FROM students WHERE user_id=?", (session["user_id"],)).fetchone()
    conn.close()
    return row


@app.route("/student")
@login_required("student")
def student_dashboard():
    srow = _student_row()
    conn = get_connection()
    class_row = None
    if srow and srow["class_id"]:
        class_row = conn.execute("SELECT class_name, section FROM classes WHERE id=?",
                                  (srow["class_id"],)).fetchone()
    conn.close()
    return render_template("student/dashboard.html", student=srow, class_row=class_row)


@app.route("/student/marks")
@login_required("student")
def student_marks():
    srow = _student_row()
    conn = get_connection()
    marks = conn.execute("""
        SELECT co.course_name, m.exam_type, m.marks_obtained, m.max_marks,
               ROUND(100.0*m.marks_obtained/m.max_marks,1) as pct
        FROM marks m JOIN courses co ON m.course_id=co.id
        WHERE m.student_id=? ORDER BY m.date DESC
    """, (srow["id"],)).fetchall()
    conn.close()
    return render_template("student/marks.html", marks=marks)


@app.route("/student/attendance")
@login_required("student")
def student_attendance():
    srow = _student_row()
    conn = get_connection()
    rows = conn.execute("SELECT date, status FROM attendance WHERE student_id=? ORDER BY date DESC",
                         (srow["id"],)).fetchall()
    summary = conn.execute("""
        SELECT ROUND(100.0*SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END)/COUNT(*),1) as pct
        FROM attendance WHERE student_id=?
    """, (srow["id"],)).fetchone()["pct"]
    conn.close()
    return render_template("student/attendance.html", rows=rows, summary=summary)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
