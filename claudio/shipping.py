"""発送平準化シミュレーター（Web UI）"""

import datetime as dt
import io
from collections import defaultdict

import pandas as pd
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from auth import require_login, render

router = APIRouter(prefix="/shipping")

# ============================================================
# デフォルトパラメータ
# ============================================================
DEFAULT_DAILY_CAP = {"熊本支社": 4000, "宮崎支社": 4000}
THROUGHPUT_PER_PERSON = 400
DEFAULT_MAX_STORAGE = 7
DEFAULT_START = "2025-12-01"
DEFAULT_END = "2026-01-31"

HOLIDAYS = {
    dt.date(2025, 11, 3), dt.date(2025, 11, 24),
    dt.date(2026, 1, 1), dt.date(2026, 1, 12),
}
LONG_BREAKS = {dt.date(2025, 12, 29) + dt.timedelta(d) for d in range(6)}
CLOSED = HOLIDAYS | LONG_BREAKS


def _is_business_day(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in CLOSED


def _business_days_desc(ideal: dt.date, max_storage: int):
    out = []
    for k in range(0, max_storage + 1):
        d = ideal - dt.timedelta(days=k)
        if _is_business_day(d):
            out.append((d, k))
    return out


def _generate_sample_inputs(daily_cap, start, end):
    lt_def = {"福岡県": 1, "熊本県": 1, "大阪府": 2, "東京都": 2, "北海道": 3}
    lt_rows = []
    for base in daily_cap:
        for pref, lt in lt_def.items():
            lt_rows.append({"発送拠点": base, "都道府県": pref, "リードタイム": lt})
    lt_master = pd.DataFrame(lt_rows)

    prefs = list(lt_def.keys())
    pref_share = [0.30, 0.20, 0.25, 0.15, 0.10]
    orders = []
    day = start
    while day <= end:
        base_qty = 3000
        if day.month == 1 and 6 <= day.day <= 9:
            base_qty += 2400 - (day.day - 6) * 500
        if day.month == 12 and 24 <= day.day <= 26:
            base_qty += 1400
        if day.weekday() == 6:
            base_qty = int(base_qty * 0.4)
        for base_office in daily_cap:
            office_qty = base_qty if base_office == "熊本支社" else int(base_qty * 0.7)
            for pref, share in zip(prefs, pref_share):
                qty = int(round(office_qty * share))
                if qty > 0:
                    orders.append({
                        "到着希望日": day, "発送拠点": base_office,
                        "都道府県": pref, "件数": qty,
                    })
        day += dt.timedelta(days=1)
    return pd.DataFrame(orders), lt_master


def _run_leveling(order_df, lt_master, daily_cap, max_storage):
    lt_lookup = {(r["発送拠点"], r["都道府県"]): r["リードタイム"]
                 for _, r in lt_master.iterrows()}

    df = order_df.copy()
    df["リードタイム"] = df.apply(
        lambda r: lt_lookup.get((r["発送拠点"], r["都道府県"])), axis=1)
    df["仮発送日"] = df.apply(
        lambda r: r["到着希望日"] - dt.timedelta(days=int(r["リードタイム"])), axis=1)

    load = defaultdict(int)
    ideal_load = defaultdict(int)
    detail_rows, unplaced_rows = [], []

    df = df.sort_values(["発送拠点", "仮発送日", "都道府県"]).reset_index(drop=True)
    for _, r in df.iterrows():
        base, pref = r["発送拠点"], r["都道府県"]
        ideal, lt, qty = r["仮発送日"], int(r["リードタイム"]), int(r["件数"])
        ideal_load[(base, ideal)] += qty
        cap = daily_cap[base]
        remaining = qty
        for ship_day, storage in _business_days_desc(ideal, max_storage):
            if remaining <= 0:
                break
            avail = cap - load[(base, ship_day)]
            if avail <= 0:
                continue
            take = min(avail, remaining)
            load[(base, ship_day)] += take
            remaining -= take
            detail_rows.append({
                "発送拠点": base, "都道府県": pref, "到着希望日": r["到着希望日"],
                "リードタイム": lt, "仮発送日": ideal,
                "確定発送日": ship_day, "保管日数": storage, "件数": take,
            })
        if remaining > 0:
            unplaced_rows.append({
                "発送拠点": base, "都道府県": pref, "到着希望日": r["到着希望日"],
                "仮発送日": ideal, "件数": remaining,
            })

    return pd.DataFrame(detail_rows), pd.DataFrame(unplaced_rows), load, ideal_load


# ============================================================
# Routes
# ============================================================

@router.get("/", name="shipping_index")
async def shipping_index(request: Request):
    from app import templates
    user = require_login(request)
    return render(request, templates, "shipping/index.html", {
        "default_cap_kumamoto": DEFAULT_DAILY_CAP["熊本支社"],
        "default_cap_miyazaki": DEFAULT_DAILY_CAP["宮崎支社"],
        "default_max_storage": DEFAULT_MAX_STORAGE,
        "default_start": DEFAULT_START,
        "default_end": DEFAULT_END,
    })


@router.post("/run", name="shipping_run")
async def shipping_run(request: Request):
    require_login(request)
    body = await request.json()

    cap_k = int(body.get("cap_kumamoto", DEFAULT_DAILY_CAP["熊本支社"]))
    cap_m = int(body.get("cap_miyazaki", DEFAULT_DAILY_CAP["宮崎支社"]))
    max_storage = int(body.get("max_storage", DEFAULT_MAX_STORAGE))
    start = dt.date.fromisoformat(body.get("start", DEFAULT_START))
    end = dt.date.fromisoformat(body.get("end", DEFAULT_END))

    daily_cap = {"熊本支社": cap_k, "宮崎支社": cap_m}
    order_df, lt_master = _generate_sample_inputs(daily_cap, start, end)
    detail, unplaced, load, ideal_load = _run_leveling(order_df, lt_master, daily_cap, max_storage)

    # Build summary
    total_placed = int(detail["件数"].sum()) if len(detail) else 0
    total_unplaced = int(unplaced["件数"].sum()) if len(unplaced) else 0
    total = total_placed + total_unplaced

    summary = {
        "total": total, "placed": total_placed, "unplaced": total_unplaced,
        "rate": round(total_placed / total * 100, 1) if total else 0,
    }

    # Per-office stats
    offices = {}
    for base, cap in daily_cap.items():
        before = max([q for (b, _), q in ideal_load.items() if b == base], default=0)
        after = max([q for (b, _), q in load.items() if b == base], default=0)
        d = detail[detail["発送拠点"] == base] if len(detail) else pd.DataFrame()
        avg_storage = round(float((d["保管日数"] * d["件数"]).sum() / d["件数"].sum()), 2) if len(d) else 0
        max_s = int(d["保管日数"].max()) if len(d) else 0
        offices[base] = {
            "cap": cap, "before_max": before, "after_max": after,
            "avg_storage": avg_storage, "max_storage": max_s,
        }
    summary["offices"] = offices

    # Daily schedule data for charts
    chart_data = {}
    for base in daily_cap:
        # After leveling
        after_items = sorted(
            [(d.isoformat(), q) for (b, d), q in load.items() if b == base],
            key=lambda x: x[0]
        )
        # Before leveling (ideal)
        before_items = sorted(
            [(d.isoformat(), q) for (b, d), q in ideal_load.items() if b == base],
            key=lambda x: x[0]
        )
        chart_data[base] = {
            "after": {"dates": [x[0] for x in after_items], "values": [x[1] for x in after_items]},
            "before": {"dates": [x[0] for x in before_items], "values": [x[1] for x in before_items]},
            "cap": daily_cap[base],
        }
    summary["chart_data"] = chart_data

    # Schedule table (top rows)
    schedule_rows = []
    for (b, d), q in sorted(load.items(), key=lambda x: (x[0][0], x[0][1])):
        needed = int(q / THROUGHPUT_PER_PERSON) + (1 if q % THROUGHPUT_PER_PERSON else 0)
        schedule_rows.append({
            "office": b, "date": d.isoformat(), "qty": q,
            "people": needed, "over": q > daily_cap[b],
        })
    summary["schedule"] = schedule_rows

    # Unplaced rows
    up_rows = []
    if len(unplaced):
        for _, r in unplaced.iterrows():
            up_rows.append({
                "office": r["発送拠点"], "pref": r["都道府県"],
                "arrival": r["到着希望日"].isoformat(), "ideal": r["仮発送日"].isoformat(),
                "qty": int(r["件数"]),
            })
    summary["unplaced_rows"] = up_rows

    return JSONResponse(summary)


@router.post("/download", name="shipping_download")
async def shipping_download(request: Request):
    """Run and return Excel file."""
    require_login(request)
    body = await request.json()

    cap_k = int(body.get("cap_kumamoto", DEFAULT_DAILY_CAP["熊本支社"]))
    cap_m = int(body.get("cap_miyazaki", DEFAULT_DAILY_CAP["宮崎支社"]))
    max_storage = int(body.get("max_storage", DEFAULT_MAX_STORAGE))
    start = dt.date.fromisoformat(body.get("start", DEFAULT_START))
    end = dt.date.fromisoformat(body.get("end", DEFAULT_END))

    daily_cap = {"熊本支社": cap_k, "宮崎支社": cap_m}
    order_df, lt_master = _generate_sample_inputs(daily_cap, start, end)
    detail, unplaced, load, ideal_load = _run_leveling(order_df, lt_master, daily_cap, max_storage)

    def to_date_str(df):
        out = df.copy()
        for c in out.columns:
            if out[c].map(lambda v: isinstance(v, dt.date)).any():
                out[c] = out[c].map(lambda v: v.isoformat() if isinstance(v, dt.date) else v)
        return out

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        to_date_str(detail).to_excel(xw, sheet_name="配置明細", index=False)
        if len(unplaced):
            to_date_str(unplaced).to_excel(xw, sheet_name="配置不可", index=False)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=shipping_result.xlsx"},
    )
