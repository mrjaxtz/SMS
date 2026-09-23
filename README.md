# Student Management System — Web Version (Flask)

A real, browser-based rebuild of the desktop app: three portals (Admin,
Teacher, Student), each with their own login, all sharing one live
database — reachable by anyone with the link, no Claude account, no
desktop install.

## What's included in this MVP
- Portal select (Teacher/Student) + separate Admin login (`/admin-login`)
- **Admin:** dashboard stats, teacher management, student enrollment +
  search + delete, class management, course management
- **Teacher:** view assigned classes, view students per class, mark
  attendance, enter marks + view marks history
- **Student:** profile, marks/results, attendance %

**Not yet in the web version** (still only in the desktop app — ask if
you want these ported over next): class scheduling/timetable, reports
page, remarks, notifications, student add/remove-from-class by teacher,
marks editing/deleting, public directory export.

## Files
| File/folder | Purpose |
|---|---|
| `app.py` | The Flask application — all routes/logic |
| `database.py` | SQLite schema + connection helper |
| `templates/` | HTML pages (Jinja2), dark "Aurora" theme |
| `static/style.css` | All styling |
| `requirements.txt` | Python dependencies for deployment |
| `Procfile` | Tells the host how to start the app |
| `.gitignore` | Keeps the local database file out of Git |

## Run it locally first (optional but recommended)
```
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000` in your browser. Admin login is at
`http://127.0.0.1:5000/admin-login` (default `admin` / `admin123`).

## Deploy it for real — Render (free tier)

Render deploys from a GitHub repository (there's no drag-and-drop zip
upload), so step 1 is getting this code onto GitHub.

### Step 1: Put the code on GitHub
1. Go to [github.com](https://github.com) and create a free account if
   you don't have one.
2. Click the **+** in the top right → **New repository**. Name it
   `student-management-system`, keep it **Public**, don't add a README
   (we already have one) → **Create repository**.
3. On the new repo's page, click **uploading an existing file**.
4. Drag this entire project folder's contents in (all the `.py` files,
   `requirements.txt`, `Procfile`, `.gitignore`, and the `templates/`
   and `static/` folders — most browsers let you drag whole folders in
   at once and GitHub preserves the folder structure).
5. Scroll down, click **Commit changes**.

### Step 2: Create the Render Web Service
1. Go to [render.com](https://render.com) → sign up (free) → you can
   sign up with your GitHub account, which makes the next step easier.
2. In the Render dashboard: **New** → **Web Service**.
3. Connect your GitHub account if prompted, then select the
   `student-management-system` repo.
4. Fill in:
   - **Language:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
5. Click **Create Web Service**. Render will build and deploy — takes
   a couple of minutes. When it's done you'll get a live URL like
   `https://student-management-system-xxxx.onrender.com`.

That URL is what you share. Anyone can open it, pick Teacher or
Student, and log in — no account, no install. Admin logs in
separately at `<your-url>/admin-login`.

### Important: the free tier's database is not permanent
Render's free web services use temporary storage — every time the
app redeploys (new code push, or the service restarts after being
idle), `school.db` resets to just the default admin account. This is
fine for demoing and testing, but **not safe for real, permanent
records**. When you're ready to rely on this for real, the fix is to
switch to a hosted database (e.g. Render's free PostgreSQL tier) —
say the word and I'll adapt `database.py` and `app.py` for that.

### Also set a real secret key
Render lets you add environment variables in the service's
**Environment** tab. Add one called `SECRET_KEY` with any long random
string as the value — this keeps login sessions secure. The app
falls back to a default dev key if you skip this, which is fine for
testing but not for real use.
