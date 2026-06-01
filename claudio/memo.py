from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database import get_db
from auth import require_login, render

router = APIRouter(prefix="/memo")


# --------------- List ---------------

@router.get("/", name="memo_list")
async def memo_list(request: Request, q: str = ""):
    from app import templates
    user = require_login(request)

    conn = get_db()
    try:
        if q:
            memos = conn.execute(
                """SELECT id, title, content, color, is_pinned,
                          datetime(created_at, '+9 hours') as created_at,
                          datetime(updated_at, '+9 hours') as updated_at
                   FROM memos WHERE user_id = ? AND (title LIKE ? OR content LIKE ?)
                   ORDER BY is_pinned DESC, updated_at DESC""",
                (user["id"], f"%{q}%", f"%{q}%"),
            ).fetchall()
        else:
            memos = conn.execute(
                """SELECT id, title, content, color, is_pinned,
                          datetime(created_at, '+9 hours') as created_at,
                          datetime(updated_at, '+9 hours') as updated_at
                   FROM memos WHERE user_id = ?
                   ORDER BY is_pinned DESC, updated_at DESC""",
                (user["id"],),
            ).fetchall()
    finally:
        conn.close()

    return render(request, templates, "memo/list.html", {
        "memos": [dict(m) for m in memos],
        "search": q,
    })


# --------------- Create ---------------

@router.post("/new", name="memo_create")
async def memo_create(request: Request):
    user = require_login(request)
    body = await request.json()
    title = (body.get("title") or "").strip()
    content = body.get("content", "")
    color = body.get("color", "#fff")

    if not title:
        return JSONResponse({"error": "タイトルは必須です"}, status_code=400)

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO memos (user_id, title, content, color) VALUES (?, ?, ?, ?)",
            (user["id"], title, content, color),
        )
        conn.commit()
        memo_id = cur.lastrowid
        row = conn.execute(
            """SELECT id, title, content, color, is_pinned,
                      datetime(created_at, '+9 hours') as created_at,
                      datetime(updated_at, '+9 hours') as updated_at
               FROM memos WHERE id = ?""",
            (memo_id,),
        ).fetchone()
    finally:
        conn.close()

    return JSONResponse({"status": "ok", "memo": dict(row)})


# --------------- Update ---------------

@router.post("/{memo_id}/edit", name="memo_update")
async def memo_update(request: Request, memo_id: int):
    user = require_login(request)
    body = await request.json()
    title = (body.get("title") or "").strip()
    content = body.get("content", "")
    color = body.get("color")

    if not title:
        return JSONResponse({"error": "タイトルは必須です"}, status_code=400)

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM memos WHERE id = ? AND user_id = ?",
            (memo_id, user["id"]),
        ).fetchone()
        if not existing:
            return JSONResponse({"error": "メモが見つかりません"}, status_code=404)

        if color:
            conn.execute(
                "UPDATE memos SET title=?, content=?, color=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
                (title, content, color, memo_id, user["id"]),
            )
        else:
            conn.execute(
                "UPDATE memos SET title=?, content=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
                (title, content, memo_id, user["id"]),
            )
        conn.commit()
        row = conn.execute(
            """SELECT id, title, content, color, is_pinned,
                      datetime(created_at, '+9 hours') as created_at,
                      datetime(updated_at, '+9 hours') as updated_at
               FROM memos WHERE id = ?""",
            (memo_id,),
        ).fetchone()
    finally:
        conn.close()

    return JSONResponse({"status": "ok", "memo": dict(row)})


# --------------- Delete ---------------

@router.post("/{memo_id}/delete", name="memo_delete")
async def memo_delete(request: Request, memo_id: int):
    user = require_login(request)

    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM memos WHERE id = ? AND user_id = ?",
            (memo_id, user["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"status": "ok"})


# --------------- Toggle Pin ---------------

@router.post("/{memo_id}/pin", name="memo_toggle_pin")
async def memo_toggle_pin(request: Request, memo_id: int):
    user = require_login(request)

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT is_pinned FROM memos WHERE id = ? AND user_id = ?",
            (memo_id, user["id"]),
        ).fetchone()
        if not row:
            return JSONResponse({"error": "メモが見つかりません"}, status_code=404)

        new_val = 0 if row["is_pinned"] else 1
        conn.execute(
            "UPDATE memos SET is_pinned=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
            (new_val, memo_id, user["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"status": "ok", "is_pinned": new_val})
