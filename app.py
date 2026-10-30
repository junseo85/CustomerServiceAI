import json
import os
import secrets
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import ai
import db

load_dotenv()


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("DATABASE", "issues.db"),
        SEED_DEMO=os.environ.get("SEED_DEMO", "0") == "1",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)
    db.init_db(app.config["DATABASE"], app.config["SEED_DEMO"])

    def get_db():
        if "db" not in g:
            g.db = db.connect(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn:
            conn.close()

    @app.before_request
    def load_user():
        g.user = None
        if "user_id" in session:
            g.user = get_db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

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
                "STATUSES": db.STATUSES, "CATEGORIES": db.CATEGORIES, "SEVERITIES": db.SEVERITIES}

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if g.user is None:
                if request.path.startswith("/api/"):
                    return jsonify(error="login required"), 401
                return redirect(url_for("login"))
            return fn(*a, **kw)
        return wrapper

    def staff_required(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a, **kw):
            if g.user["role"] not in db.STAFF_ROLES:
                abort(403)
            return fn(*a, **kw)
        return wrapper

    def visible_issue(issue_id):
        issue = get_db().execute(
            "SELECT i.*, u.username AS reporter FROM issues i JOIN users u ON u.id=i.reporter_id WHERE i.id=?",
            (issue_id,)).fetchone()
        if issue is None or (g.user["role"] not in db.STAFF_ROLES and issue["reporter_id"] != g.user["id"]):
            abort(404)
        return issue

    # ---- auth ----
    @app.route("/login", methods=["GET", "POST"])
    def login():
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
        data = request.get_json(silent=True) or {}
        lang = data.get("language", g.user["language"])
        msgs = [{"role": m["role"], "content": str(m["content"])[:4000]}
                for m in data.get("messages", [])[-30:]
                if isinstance(m, dict) and m.get("role") in ("user", "assistant") and "content" in m]
        if lang not in ai.LANGUAGES or not msgs or msgs[-1]["role"] != "user":
            return jsonify(error="invalid request"), 400
        try:
            result = ai.chat(msgs, lang)
        except Exception as e:  # network/API/parse failures
            app.logger.exception("AI error: %s", e)
            return jsonify(error="AI service unavailable"), 502
        out = {"reply": result["reply"], "ready": result["ready"]}
        if result["ready"]:
            i = result["issue"]
            transcript = json.dumps(msgs + [{"role": "assistant", "content": result["reply"]}],
                                    ensure_ascii=False)
            cur = get_db().execute(
                "INSERT INTO issues (reporter_id,title,description,category,severity,original_language,transcript)"
                " VALUES (?,?,?,?,?,?,?)",
                (g.user["id"], i["title"], i["description"], i["category"], i["severity"], lang, transcript))
            get_db().commit()
            out["issue_id"] = cur.lastrowid
        return jsonify(out)

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
        rows = get_db().execute(
            q + " ORDER BY CASE i.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,"
                " i.created_at DESC", args).fetchall()
        return render_template("issues.html", issues=rows)

    @app.route("/issues/<int:issue_id>")
    @login_required
    def issue_detail(issue_id):
        issue = visible_issue(issue_id)
        comments = get_db().execute(
            "SELECT c.*, u.username FROM comments c JOIN users u ON u.id=c.author_id"
            " WHERE issue_id=? ORDER BY c.id", (issue_id,)).fetchall()
        return render_template("issue.html", issue=issue, comments=comments)

    @app.post("/issues/<int:issue_id>/status")
    @staff_required
    def set_status(issue_id):
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
