from contextlib import contextmanager
from datetime import datetime, timezone
import math
import os
from pathlib import Path
from typing import Literal

import psycopg
from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

STATIC = Path(__file__).with_name("static")
STATISTICS_SQL = """
SELECT station,
       count(*) AS orders,
       count(*) FILTER (WHERE status = 'pending') AS pending,
       count(*) FILTER (WHERE status = 'running') AS running,
       count(*) FILTER (WHERE status = 'completed') AS completed
FROM medirover_orders
GROUP BY station
HAVING count(*) FILTER (WHERE status = 'completed') >= %s
ORDER BY station
"""


@contextmanager
def database(connect):
    try:
        with connect() as connection:
            yield connection
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        raise HTTPException(503, "Database or dashboard tables unavailable") from None


def store_temperature(connect, value, humidity_percent=None):
    if isinstance(value, bool) or not math.isfinite(value) or not -100 <= value <= 150:
        raise ValueError("Invalid temperature")
    if humidity_percent is not None and (
        isinstance(humidity_percent, bool) or not 0 <= humidity_percent <= 100
    ):
        raise ValueError("Invalid relative humidity")
    with database(connect) as connection:
        connection.execute(
            "INSERT INTO medirover_temperatures (temperature_c, humidity_percent) VALUES (%s, %s)",
            (value, humidity_percent),
        )


def register_dashboard(app, connect):
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def website():
        notice = ""
        if os.environ.get("MEDIROVER_DEMO") == "1":
            notice = '<aside class="notice">Demotilstand. Ture og målinger kan være testdata.</aside>'
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8").replace("<!--environment-->", notice), headers={"Cache-Control": "no-cache"})

    @app.get("/api/orders")
    def history(
        station: int | None = Query(None, ge=1, le=2),
        status: Literal["pending", "running", "delivered", "completed", "stopped", "cancelled", "rejected"] | None = None,
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1000000),
    ):
        conditions = "WHERE (%s::smallint IS NULL OR station = %s) AND (%s::text IS NULL OR status = %s)"
        parameters = (station, station, status, status)
        with database(connect) as connection:
            total = connection.execute(
                "SELECT count(*) AS total FROM medirover_orders " + conditions,
                parameters,
            ).fetchone()["total"]
            items = connection.execute(
                "SELECT request_id, station, status, last_error, created_at FROM medirover_orders "
                + conditions + " ORDER BY created_at DESC, request_id DESC LIMIT %s OFFSET %s",
                (*parameters, limit, offset),
            ).fetchall()
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/statistics")
    def statistics(min_completed: int = Query(0, ge=0, le=100000)):
        with database(connect) as connection:
            rows = connection.execute(STATISTICS_SQL, (min_completed,)).fetchall()
        return {"stations": rows, "min_completed": min_completed}

    @app.get("/api/temperature")
    def temperature():
        with database(connect) as connection:
            row = connection.execute(
                "SELECT temperature_c, humidity_percent, measured_at FROM medirover_temperatures "
                "ORDER BY measured_at DESC, id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return {
                "temperature_c": None,
                "humidity_percent": None,
                "measured_at": None,
                "state": "missing",
                "age_seconds": None,
            }
        age = max(0, int((datetime.now(timezone.utc) - row["measured_at"]).total_seconds()))
        humidity = row["humidity_percent"]
        return {
            "temperature_c": float(row["temperature_c"]),
            "humidity_percent": float(humidity) if humidity is not None else None,
            "measured_at": row["measured_at"],
            "state": "fresh" if age <= 120 else "stale",
            "age_seconds": age,
        }
