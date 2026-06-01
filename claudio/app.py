import logging
import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from starlette.middleware.sessions import SessionMiddleware
from jinja2 import Environment, FileSystemLoader

from config import SECRET_KEY, BASE_DIR, STATUS_COLORS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
from database import init_db, get_db, create_notification
from auth import router as auth_router, get_current_user, pop_flashes, render, _redirect_to_login, _upload_denied
from converter import router as converter_router


# --------------- Lifespan ---------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Claudio — initializing database")
    init_db()
    logger.info("Startup complete")
    yield
    logger.info("Shutting down")

# --------------- App ---------------

app = FastAPI(title="Claudio ツールプラットフォーム", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join(BASE_DIR, "static", "icons", "icon-96x96.png"))

# --------------- Jinja2 ---------------

_jinja_env = Environment(loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")), autoescape=True)


def _filesize(size):
    if size is None:
        return "-"
    for unit in ["B", "KB", "MB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


_jinja_env.filters["filesize"] = _filesize
from markupsafe import Markup
_jinja_env.filters["tojson"] = lambda v: Markup(json.dumps(v, ensure_ascii=False))


def _currency(value):
    """Format number as Japanese yen."""
    try:
        return f"¥{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def _status_color(status):
    """Return color for order status."""
    return STATUS_COLORS.get(status, "#95a5a6")


_jinja_env.filters["currency"] = _currency
_jinja_env.filters["status_color"] = _status_color


class _Templates:
    """Thin wrapper so render() can call templates.TemplateResponse-style."""

    def TemplateResponse(self, name: str, context: dict):
        from starlette.responses import HTMLResponse
        template = _jinja_env.get_template(name)
        html = template.render(**context)
        return HTMLResponse(html)


templates = _Templates()

# --------------- Exception handler for auth redirect ---------------


@app.exception_handler(_redirect_to_login)
async def _handle_login_redirect(request: Request, exc: _redirect_to_login):
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(_upload_denied)
async def _handle_upload_denied(request: Request, exc: _upload_denied):
    return RedirectResponse(url="/", status_code=303)


# --------------- Avatars ---------------

_avatars_dir = os.path.join(BASE_DIR, "avatars")
os.makedirs(_avatars_dir, exist_ok=True)


@app.get("/avatars/{filename}", name="avatar_file")
async def avatar_file(filename: str):
    # Prevent path traversal — only allow bare filenames
    if "/" in filename or "\\" in filename or ".." in filename:
        return HTMLResponse("Forbidden", status_code=403)
    path = os.path.join(_avatars_dir, filename)
    if not os.path.isfile(path):
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(path)


# --------------- Routers ---------------

app.include_router(auth_router)
app.include_router(converter_router)

# Lazy-import optional tool routers
try:
    from chatbot import router as chat_router
    app.include_router(chat_router)
    logger.info("Router loaded: chatbot")
except ImportError:
    logger.warning("chatbot not available — skipping")

try:
    from admin import router as admin_router, _AdminDenied
    app.include_router(admin_router)
    logger.info("Router loaded: admin")

    @app.exception_handler(_AdminDenied)
    async def _handle_admin_denied(request: Request, exc: _AdminDenied):
        return RedirectResponse(url="/", status_code=303)
except ImportError:
    logger.warning("admin not available — skipping")

try:
    from memo import router as memo_router
    app.include_router(memo_router)
    logger.info("Router loaded: memo")
except ImportError:
    logger.warning("memo not available — skipping")


# --------------- Notifications ---------------

@app.get("/api/notifications", name="notifications_list")
async def notifications_list(request: Request):
    from fastapi.responses import JSONResponse
    user = get_current_user(request)
    if not user:
        return JSONResponse({"notifications": []})

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, type, title, message, link, is_read,
                      datetime(created_at, '+9 hours') as created_at
               FROM notifications WHERE user_id = ?
               ORDER BY created_at DESC LIMIT 30""",
            (user["id"],),
        ).fetchall()
        unread = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
            (user["id"],),
        ).fetchone()[0]
    finally:
        conn.close()

    return JSONResponse({
        "notifications": [dict(r) for r in rows],
        "unread_count": unread,
    })


@app.post("/api/notifications/read", name="notifications_read")
async def notifications_read(request: Request):
    from fastapi.responses import JSONResponse
    user = get_current_user(request)
    if not user:
        return JSONResponse({"status": "error"}, status_code=401)

    body = await request.json()
    notif_id = body.get("id")

    conn = get_db()
    try:
        if notif_id:
            conn.execute(
                "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
                (notif_id, user["id"]),
            )
        else:
            conn.execute(
                "UPDATE notifications SET is_read = 1 WHERE user_id = ?",
                (user["id"],),
            )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"status": "ok"})


# --------------- Dashboard (Tool Hub) ---------------

TOOLS = [
    {
        "id": "converter",
        "name": "ファイル変換",
        "desc": "Word / PDF / Markdown / TXT を相互変換",
        "icon": "file-convert",
        "color": "#7ae99c",
        "url_name": "converter_upload",
    },
    {
        "id": "chatbot",
        "name": "社内問い合わせ",
        "desc": "社内規定・申請手続き・IT サポートなど AI がお答えします",
        "icon": "chat",
        "color": "#6366f1",
        "url_name": "chat_page",
    },
    {
        "id": "memo",
        "name": "メモ・備忘録",
        "desc": "個人メモの作成・管理",
        "icon": "memo",
        "color": "#fbbf24",
        "url_name": "memo_list",
    },
]


@app.get("/", name="dashboard")
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from datetime import datetime, timezone, timedelta
    now_jst = datetime.now(timezone(timedelta(hours=9)))

    is_admin = user["role"] in ("admin", "manager")

    conn = get_db()
    try:
        total_conversions = conn.execute(
            "SELECT COUNT(*) FROM conversions WHERE user_id=?", (user["id"],)
        ).fetchone()[0]
        recent_conversions = conn.execute(
            "SELECT * FROM conversions WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (user["id"],)
        ).fetchall()

        today_str = now_jst.strftime("%Y-%m-%d")

        # Admin-specific stats
        open_feedback = 0
        open_escalations = 0
        total_users = 0
        today_conversions = 0
        success_rate = 0
        weekly_data = []
        monthly_data = []
        yearly_data = []

        if is_admin:
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            today_conversions = conn.execute(
                "SELECT COUNT(*) FROM conversions WHERE date(created_at) = ?", (today_str,)
            ).fetchone()[0]
            open_feedback = conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE status='open'"
            ).fetchone()[0]
            open_escalations = conn.execute(
                "SELECT COUNT(*) FROM escalations WHERE status='open'"
            ).fetchone()[0]
            for i in range(6, -1, -1):
                day = (now_jst - timedelta(days=i)).strftime("%Y-%m-%d")
                day_label = (now_jst - timedelta(days=i)).strftime("%m/%d")
                count = conn.execute(
                    "SELECT COUNT(*) FROM conversions WHERE date(created_at) = ?", (day,)
                ).fetchone()[0]
                weekly_data.append({"label": day_label, "count": count})
            # Monthly: last 8 weeks grouped by week
            for i in range(7, -1, -1):
                week_end = now_jst - timedelta(weeks=i)
                week_start = week_end - timedelta(days=6)
                ws = week_start.strftime("%Y-%m-%d")
                we = week_end.strftime("%Y-%m-%d")
                count = conn.execute(
                    "SELECT COUNT(*) FROM conversions WHERE date(created_at) BETWEEN ? AND ?",
                    (ws, we),
                ).fetchone()[0]
                monthly_data.append({"label": week_end.strftime("%m/%d"), "count": count})
            # Yearly: last 12 months grouped by month
            for i in range(11, -1, -1):
                # Calculate year/month offset
                month_offset = now_jst.month - i
                year = now_jst.year + (month_offset - 1) // 12
                month = ((month_offset - 1) % 12) + 1
                month_str = f"{year}-{month:02d}"
                count = conn.execute(
                    "SELECT COUNT(*) FROM conversions WHERE strftime('%Y-%m', created_at) = ?",
                    (month_str,),
                ).fetchone()[0]
                yearly_data.append({"label": f"{month}月", "count": count})
        else:
            today_conversions = conn.execute(
                "SELECT COUNT(*) FROM conversions WHERE user_id=? AND date(created_at) = ?",
                (user["id"], today_str),
            ).fetchone()[0]
            success_rate = conn.execute(
                "SELECT ROUND(100.0 * SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1)) FROM conversions WHERE user_id=?",
                (user["id"],),
            ).fetchone()[0] or 0
    finally:
        conn.close()

    return render(request, templates, "dashboard.html", {
        "tools": TOOLS,
        "total_conversions": total_conversions,
        "recent_conversions": recent_conversions,
        "now": now_jst,
        "total_users": total_users,
        "today_conversions": today_conversions,
        "success_rate": int(success_rate),
        "weekly_data": weekly_data,
        "monthly_data": monthly_data,
        "yearly_data": yearly_data,
        "open_feedback": open_feedback,
        "open_escalations": open_escalations,
    })


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
