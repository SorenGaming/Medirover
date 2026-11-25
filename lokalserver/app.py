import os
from contextlib import asynccontextmanager
from datetime import datetime
from functools import partial
from threading import Event, Thread
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from dashboard import register_dashboard, store_temperature
from uart import Base

Station = Annotated[int, Field(strict=True, ge=1, le=2)]
Status = Literal["pending", "running", "delivered", "completed", "stopped", "cancelled", "rejected"]
ACTIVE = ("pending", "running", "delivered", "stopped")  # the rover is reserved
COLUMNS = "request_id, station, status, last_error, created_at"
CONTROLS = {  # button: (allowed statuses, command, new status)
    "packed": (("pending",), "KLAR", None),
    "stop": (ACTIVE, "STOP", "stopped"),
    "resume": (("running", "delivered"), "FORTSAET", None),
    "close": (("stopped",), "LUK", "cancelled"),
}
base = None


@asynccontextmanager
async def lifespan(_app):
    global base
    device = os.environ.get("MEDIROVER_UART_PORT")
    if not device:
        yield
        return
    stop = Event()
    base = Base(device, base_event, partial(store_temperature, connect))
    worker = Thread(target=base.run, args=(stop,), name="medirover-uart", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=4)
        base = None


app = FastAPI(title="Medirover", lifespan=lifespan)


class OrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    station: Station


class Order(OrderInput):
    status: Status
    last_error: str | None
    created_at: datetime


def connect():
    dsn = os.environ.get("MEDIROVER_DATABASE_DSN")
    if not dsn:
        raise HTTPException(503, "Database is not configured")
    return psycopg.connect(dsn, connect_timeout=3, row_factory=dict_row)


register_dashboard(app, connect)


def send(line, request_id):
    if base is None:
        raise HTTPException(503, "The base is not connected")
    base.command(line, request_id)


@app.get("/api/health")
def health():
    try:
        with connect() as connection:
            connection.execute("SELECT request_id FROM medirover_orders LIMIT 1")
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        raise HTTPException(503, "Database or order table unavailable") from None
    return {"database": "ok", "base": base is not None and base.port is not None}


@app.post("/api/orders", response_model=Order, status_code=201, responses={200: {"model": Order}})
def create_order(order: OrderInput, response: Response):
    try:
        with connect() as connection:
            saved = connection.execute(
                f"""
                INSERT INTO medirover_orders (request_id, station)
                VALUES (%s, %s)
                ON CONFLICT (request_id) DO NOTHING
                RETURNING {COLUMNS}
                """,
                (order.request_id, order.station),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "The rover already has an active trip") from None
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        raise HTTPException(503, "Database or order table unavailable") from None
    if saved is None:
        saved = get_order(order.request_id)
        if saved["station"] != order.station:
            raise HTTPException(409, "Request ID already used for another order")
        response.status_code = 200
        return saved
    try:
        send(f"ORDER,{order.request_id},{order.station}", order.request_id)
    except HTTPException as error:
        change_order_status(order.request_id, ("pending",), "rejected", error=str(error.detail)[:40])
        raise
    return saved


@app.get("/api/orders/{request_id}", response_model=Order)
def get_order(request_id: UUID):
    try:
        with connect() as connection:
            saved = connection.execute(
                f"SELECT {COLUMNS} FROM medirover_orders WHERE request_id = %s",
                (request_id,),
            ).fetchone()
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        raise HTTPException(503, "Database or order table unavailable") from None
    if saved is None:
        raise HTTPException(404, "Order not found")
    return saved


@app.post("/api/orders/{request_id}/{action}", response_model=Order)
def control_order(request_id: UUID, action: Literal["packed", "stop", "resume", "close"]):
    allowed, command, target = CONTROLS[action]
    if get_order(request_id)["status"] not in allowed:
        raise HTTPException(409, f"Cannot {action} this trip now")
    send(f"{command},{request_id}", request_id)
    return change_order_status(request_id, allowed, target)


def base_event(kind, request_id, value):
    if kind == "STARTED":
        change_order_status(request_id, ("pending",), "running")
    elif kind == "ACK":
        change_order_status(request_id, ("running",), "delivered", int(value or 0))
    elif kind == "HOME":
        change_order_status(request_id, ("running", "delivered"), "completed")
    elif kind == "ERR":
        change_order_status(request_id, ACTIVE, "stopped" if value == "STOPPED" else None, error=value)


def change_order_status(request_id, expected, target, station=None, error=None):
    try:
        with connect() as connection:
            saved = connection.execute(
                f"""
                UPDATE medirover_orders SET status = COALESCE(%s, status), last_error = %s
                WHERE request_id = %s AND status = ANY(%s) AND station = COALESCE(%s, station)
                RETURNING {COLUMNS}
                """,
                (target, error, request_id, list(expected), station),
            ).fetchone()
            if saved is None:
                saved = connection.execute(
                    f"SELECT {COLUMNS} FROM medirover_orders WHERE request_id = %s",
                    (request_id,),
                ).fetchone()
                if saved is None:
                    raise HTTPException(404, "Order not found")
                if station is not None and saved["station"] != station:
                    raise HTTPException(409, "Receipt is from the wrong station")
                raise HTTPException(409, f"Cannot move from {saved['status']} to {target}")
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        raise HTTPException(503, "Database or order table unavailable") from None
    return saved
