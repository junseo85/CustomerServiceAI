import base64
import json
import os
import secrets
import uuid
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import ai
import db

load_dotenv()


# extension -> (mime, magic-byte prefixes); content is verified, never trusting client headers
ALLOWED_UPLOADS = {
    "png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    "jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "gif": ("image/gif", (b"GIF87a", b"GIF89a")),
    "webp": ("image/webp", (b"RIFF",)),
    "pdf": ("application/pdf", (b"%PDF",)),
    "txt": ("text/plain", None),
    "log": ("text/plain", None),
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_REPORT = 5


def create_app(config=None):
    app = Flask(__name__)
    # Keep deployment settings overridable so tests can use isolated databases and uploads.
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("DATABASE", "issues.db"),
        SEED_DEMO=os.environ.get("SEED_DEMO", "0") == "1",
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR", "uploads"),
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES + 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)
    db.init_db(app.config["DATABASE"], app.config["SEED_DEMO"])
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    def get_db():
        if "db" not in g:
            g.db = db.connect(app.config["DATABASE"])
        return g.db

    # A request-scoped connection is reused by its controllers and always closed afterward.
    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn:
            conn.close()

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify(error="File too large (max 10 MB)"), 413

    # Load the signed-in user once so route guards and templates share the same identity.
    @app.before_request
    def load_user():
        g.user = None
        if "user_id" in session:
            g.user = get_db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

    # Require a session-bound token on every state-changing form or API request.
    @app.before_request
    def csrf_protect():
        if request.method == "POST":
            token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not token or token != session.get("csrf"):
                abort(400, "Bad CSRF token")

    @app.context_processor
    def inject():
        session.setdefault("csrf", secrets.token_hex(16))
        return {"csrf_token": session["csrf"], "languages": ai.LANGUAGES, "STAFF_ROLES": db.STAFF_ROLES,
                "STATUSES": db.STATUSES, "CATEGORIES": db.CATEGORIES, "SEVERITIES": db.SEVERITIES,
                "ai_status": ai.status()}

    def login_required(fn):
        # API callers receive a status response; browser navigation goes to the login page.
        @wraps(fn)
        def wrapper(*a, **kw):
            if g.user is None:
                if request.path.startswith("/api/"):
                    return jsonify(error="login required"), 401
                return redirect(url_for("login"))
            return fn(*a, **kw)
        return wrapper

    def staff_required(fn):
        # Compose authentication with the separate staff-role authorization check.
        @wraps(fn)
        @login_required
        def wrapper(*a, **kw):
            if g.user["role"] not in db.STAFF_ROLES:
                abort(403)
            return fn(*a, **kw)
        return wrapper

    def visible_issue(issue_id):
        # Resolve an issue only for staff or its reporter; hide inaccessible IDs as not found.
        issue = get_db().execute(
            "SELECT i.*, u.username AS reporter FROM issues i JOIN users u ON u.id=i.reporter_id WHERE i.id=?",
            (issue_id,)).fetchone()
        if issue is None or (g.user["role"] not in db.STAFF_ROLES and issue["reporter_id"] != g.user["id"]):
            abort(404)
        return issue

    # ---- auth ----
    @app.route("/login", methods=["GET", "POST"])
    def login():
        # Verify the password hash, then rotate session state to prevent session fixation.
        if request.method == "POST":
            u = get_db().execute("SELECT * FROM users WHERE username=?",
                                 (request.form.get("username", ""),)).fetchone()
            if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
                session.clear()
                session["user_id"] = u["id"]
                session["csrf"] = secrets.token_hex(16)
                return redirect(url_for("chat_page"))
            flash("Invalid username or password")
        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        # Public registration creates employee accounts only; staff roles are not self-assignable.
        if request.method == "POST":
            name, pw = request.form.get("username", "").strip(), request.form.get("password", "")
            lang = request.form.get("language", "en")
            if not name or len(pw) < 8 or lang not in ai.LANGUAGES:
                flash("Username required, password must be 8+ characters")
            else:
                try:
                    get_db().execute(
                        "INSERT INTO users (username, password_hash, role, language) VALUES (?,?,?,?)",
                        (name, generate_password_hash(pw), "employee", lang))
                    get_db().commit()
                    return redirect(url_for("login"))
                except Exception:
                    flash("Username already taken")
        return render_template("register.html")

    @app.post("/logout")
    def logout():
        # Logout is a CSRF-protected POST and clears both identity and CSRF state.
        session.clear()
        return redirect(url_for("login"))

    # ---- chat ----
    @app.route("/")
    @login_required
    def chat_page():
        return render_template("chat.html")

    @app.post("/api/chat")
    @login_required
    def api_chat():
        # Each turn resubmits the bounded conversation; only this user's pending uploads are eligible.
        data = request.get_json(silent=True) or {}
        lang = data.get("language", g.user["language"])
        msgs = [{"role": m["role"], "content": str(m["content"])[:4000]}
                for m in data.get("messages", [])[-30:]
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and "content" in m]
        if lang not in ai.LANGUAGES or not msgs or msgs[-1]["role"] != "user":
            return jsonify(error="invalid request"), 400
        ids = [int(x) for x in data.get("attachment_ids", []) if str(x).isdigit()][:MAX_FILES_PER_REPORT]
        files = []
        if ids:
            files = get_db().execute(
                f"SELECT * FROM attachments WHERE issue_id IS NULL AND uploader_id=? AND id IN ({','.join('?' * len(ids))})",
                [g.user["id"], *ids]).fetchall()
        new_ids = {int(x) for x in data.get("new_attachment_ids", []) if str(x).isdigit()}
        images = []
        for f in files:
            if f["id"] in new_ids and f["mime"].startswith("image/") and f["size"] <= 5 * 1024 * 1024:
                with open(os.path.join(app.config["UPLOAD_DIR"], f["stored_name"]), "rb") as fh:
                    images.append(f"data:{f['mime']};base64,{base64.b64encode(fh.read()).decode()}")
        if new_ids and files:
            names = ", ".join(f["filename"] for f in files if f["id"] in new_ids)
            msgs[-1]["content"] += f"\n[User attached: {names}]"
        try:
            result = ai.chat(msgs, lang, images)
        except Exception as e:  # network/API/parse failures
            app.logger.exception("AI error: %s", e)
            return jsonify(error="AI service unavailable"), 502
        out = {"reply": result["reply"], "ready": result["ready"]}
        if result["ready"]:
            # File the completed report and link its selected uploads in the same DB transaction.
            i = result["issue"]
            transcript = json.dumps(msgs + [{"role": "assistant", "content": result["reply"]}],
                                    ensure_ascii=False)
            cur = get_db().execute(
                "INSERT INTO issues (reporter_id,title,description,category,severity,original_language,transcript)"
                " VALUES (?,?,?,?,?,?,?)",
                (g.user["id"], i["title"], i["description"], i["category"], i["severity"], lang, transcript))
            if files:
                get_db().execute(
                    f"UPDATE attachments SET issue_id=? WHERE id IN ({','.join('?' * len(files))})",
                    [cur.lastrowid, *[f["id"] for f in files]])
            get_db().commit()
            out["issue_id"] = cur.lastrowid
        return jsonify(out)

    def attachment_json(a):
        return {"id": a["id"], "filename": a["filename"], "mime": a["mime"], "size": a["size"],
                "url": url_for("attachment_file", att_id=a["id"])}

    @app.post("/api/attachments")
    @login_required
    def api_upload():
        # Validate extension and file signature before storing under an opaque server-generated name.
        f = request.files.get("file")
        if f is None or not f.filename:
            return jsonify(error="No file provided"), 400
        name = os.path.basename(f.filename.replace("\\", "/"))[:120] or "file"
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ALLOWED_UPLOADS:
            return jsonify(error="Unsupported file type. Allowed: images, PDF, TXT, LOG"), 400
        data = f.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            return jsonify(error="File too large (max 10 MB)"), 413
        if not data:
            return jsonify(error="File is empty"), 400
        mime, magics = ALLOWED_UPLOADS[ext]
        if magics and not data.startswith(magics):
            return jsonify(error="File content does not match its extension"), 400
        if ext == "webp" and data[8:12] != b"WEBP":
            return jsonify(error="File content does not match its extension"), 400
        if not magics:
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                return jsonify(error="File content does not match its extension"), 400
        pending = get_db().execute(
            "SELECT COUNT(*) FROM attachments WHERE issue_id IS NULL AND uploader_id=?",
            (g.user["id"],)).fetchone()[0]
        if pending >= MAX_FILES_PER_REPORT:
            return jsonify(error=f"Max {MAX_FILES_PER_REPORT} attachments per report"), 400
        stored = f"{uuid.uuid4().hex}.{ext}"
        with open(os.path.join(app.config["UPLOAD_DIR"], stored), "wb") as out:
            out.write(data)
        cur = get_db().execute(
            "INSERT INTO attachments (uploader_id, filename, stored_name, mime, size) VALUES (?,?,?,?,?)",
            (g.user["id"], name, stored, mime, len(data)))
        get_db().commit()
        a = get_db().execute("SELECT * FROM attachments WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(attachment_json(a)), 201

    @app.post("/api/attachments/<int:att_id>/delete")
    @login_required
    def api_delete_attachment(att_id):
        # Users may remove only their own uploads that have not yet been attached to a report.
        a = get_db().execute(
            "SELECT * FROM attachments WHERE id=? AND uploader_id=? AND issue_id IS NULL",
            (att_id, g.user["id"])).fetchone()
        if a is None:
            return jsonify(error="not found"), 404
        get_db().execute("DELETE FROM attachments WHERE id=?", (att_id,))
        get_db().commit()
        try:
            os.remove(os.path.join(app.config["UPLOAD_DIR"], a["stored_name"]))
        except OSError:
            pass
        return jsonify(ok=True)

    @app.route("/attachments/<int:att_id>")
    @login_required
    def attachment_file(att_id):
        # Pending files are private to their uploader; filed files use the parent issue's access rule.
        a = get_db().execute("SELECT * FROM attachments WHERE id=?", (att_id,)).fetchone()
        if a is None:
            abort(404)
        if a["issue_id"] is None:
            if a["uploader_id"] != g.user["id"]:
                abort(404)
        else:
            visible_issue(a["issue_id"])
        is_image = a["mime"].startswith("image/")
        resp = send_from_directory(app.config["UPLOAD_DIR"], a["stored_name"], mimetype=a["mime"],
                                   as_attachment=not is_image and a["mime"] != "application/pdf",
                                   download_name=a["filename"])
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
        return resp

    @app.get("/api/ai-status")
    @login_required
    def api_ai_status():
        return jsonify(ai.status())

    @app.post("/api/translate")
    @login_required
    def api_translate():
        data = request.get_json(silent=True) or {}
        text, lang = str(data.get("text", ""))[:8000], data.get("language")
        if lang not in ai.LANGUAGES:
            return jsonify(error="unsupported language"), 400
        try:
            return jsonify(text=ai.translate(text, lang))
        except Exception as e:
            app.logger.exception("Translate error: %s", e)
            return jsonify(error="AI service unavailable"), 502

    # ---- dashboard ----
    @app.route("/issues")
    @login_required
    def issues():
        # Employees are scoped to their reports; staff can browse all issues with allowlisted filters.
        q = "SELECT i.*, u.username AS reporter FROM issues i JOIN users u ON u.id=i.reporter_id WHERE 1=1"
        args = []
        if g.user["role"] not in db.STAFF_ROLES:
            q += " AND i.reporter_id=?"
            args.append(g.user["id"])
        for col, allowed in (("status", db.STATUSES), ("category", db.CATEGORIES), ("severity", db.SEVERITIES)):
            v = request.args.get(col)
            if v in allowed:
                q += f" AND i.{col}=?"
                args.append(v)
        q = q.replace("i.*,", "i.*, (SELECT COUNT(*) FROM attachments a WHERE a.issue_id=i.id) AS att_count,", 1)
        rows = get_db().execute(
            q + " ORDER BY CASE i.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,"
                " i.created_at DESC", args).fetchall()
        return render_template("issues.html", issues=rows)

    @app.route("/issues/<int:issue_id>")
    @login_required
    def issue_detail(issue_id):
        # The shared visibility guard protects the issue and all data rendered from it.
        issue = visible_issue(issue_id)
        comments = get_db().execute(
            "SELECT c.*, u.username FROM comments c JOIN users u ON u.id=c.author_id"
            " WHERE issue_id=? ORDER BY c.id", (issue_id,)).fetchall()
        attachments = get_db().execute(
            "SELECT * FROM attachments WHERE issue_id=? ORDER BY id", (issue_id,)).fetchall()
        return render_template("issue.html", issue=issue, comments=comments, attachments=attachments)

    @app.post("/issues/<int:issue_id>/status")
    @staff_required
    def set_status(issue_id):
        # Status changes are staff-only and accept only the application's defined states.
        visible_issue(issue_id)
        status = request.form.get("status")
        if status not in db.STATUSES:
            abort(400)
        get_db().execute("UPDATE issues SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (status, issue_id))
        get_db().commit()
        return redirect(url_for("issue_detail", issue_id=issue_id))

    @app.post("/issues/<int:issue_id>/comments")
    @login_required
    def add_comment(issue_id):
        # Both staff and the report owner may comment, but only on an issue they can view.
        visible_issue(issue_id)
        body = request.form.get("body", "").strip()[:4000]
        if body:
            get_db().execute("INSERT INTO comments (issue_id, author_id, body) VALUES (?,?,?)",
                             (issue_id, g.user["id"], body))
            get_db().commit()
        return redirect(url_for("issue_detail", issue_id=issue_id))

    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
