"""Loopback prototype for Medirover test orders."""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from threading import Event, Thread
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field
from serial import Serial

from uart import read_receipts
from dashboard import register_dashboard, store_temperature

Station = Annotated[int, Field(strict=True, ge=1, le=2)]


@asynccontextmanager
async def lifespan(_app):
    device = os.environ.get("MEDIROVER_UART_PORT")
    if not device:
        yield
        return
    stop = Event()
    with Serial(device, baudrate=115200, timeout=0.2) as port:
        worker = Thread(
            target=read_receipts,
            args=(port, stop, accept_station_receipt, lambda value: store_temperature(connect, value)),
            name="medirover-uart",
            daemon=True,
        )
        worker.start()
        try:
            yield
        finally:
            stop.set()
            worker.join(timeout=4)


app = FastAPI(title="Medirover test-API", lifespan=lifespan)


class OrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    station: Station


class StationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station: Station


class Order(OrderInput):
    status: Literal["pending", "running", "completed"]
    created_at: datetime


def connect():
    dsn = os.environ.get("MEDIROVER_DATABASE_DSN")
    if not dsn:
        raise HTTPException(503, "Database is not configured")
    return psycopg.connect(dsn, connect_timeout=3, row_factory=dict_row)


register_dashboard(app, connect)


@app.get("/api/health")
def health():
    try:
        with connect() as connection:
            connection.execute("SELECT request_id FROM medirover_orders LIMIT 1")
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        raise HTTPException(503, "Database or order table unavailable") from None
    return {"database": "ok"}


@app.post("/api/orders", response_model=Order, status_code=201, responses={200: {"model": Order}})
def create_order(order: OrderInput, response: Response):
    try:
        with connect() as connection:
            saved = connection.execute(
                """
                INSERT INTO medirover_orders (request_id, station)
                VALUES (%s, %s)
                ON CONFLICT (request_id) DO NOTHING
                RETURNING request_id, station, status, created_at
                """,
                (order.request_id, order.station),
            ).fetchone()
            if saved is None:
                saved = connection.execute(
                    """
                    SELECT request_id, station, status, created_at
                    FROM medirover_orders WHERE request_id = %s
                    """,
                    (order.request_id,),
                ).fetchone()
                if saved is None or saved["station"] != order.station:
                    raise HTTPException(409, "Request ID already used for another order")
                response.status_code = 200
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        raise HTTPException(503, "Database or order table unavailable") from None
    return saved


@app.get("/api/orders/{request_id}", response_model=Order)
def get_order(request_id: UUID):
    try:
        with connect() as connection:
            saved = connection.execute(
                """
                SELECT request_id, station, status, created_at
                FROM medirover_orders WHERE request_id = %s
                """,
                (request_id,),
            ).fetchone()
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        raise HTTPException(503, "Database or order table unavailable") from None
    if saved is None:
        raise HTTPException(404, "Order not found")
    return saved


@app.post("/api/orders/{request_id}/start", response_model=Order)
def start_order(request_id: UUID):
    return change_order_status(request_id, "pending", "running")


@app.post("/api/orders/{request_id}/complete", response_model=Order)
def complete_order(request_id: UUID, receipt: StationReceipt):
    return accept_station_receipt(request_id, receipt.station)


def accept_station_receipt(request_id: UUID, station: int):
    return change_order_status(request_id, "running", "completed", station)


def change_order_status(request_id: UUID, expected: str, target: str, station: int | None = None):
    try:
        with connect() as connection:
            saved = connection.execute(
                """
                UPDATE medirover_orders SET status = %s
                WHERE request_id = %s AND status = %s AND station = COALESCE(%s, station)
                RETURNING request_id, station, status, created_at
                """,
                (target, request_id, expected, station),
            ).fetchone()
            if saved is None:
                saved = connection.execute(
                    """
                    SELECT request_id, station, status, created_at
                    FROM medirover_orders WHERE request_id = %s
                    """,
                    (request_id,),
                ).fetchone()
                if saved is None:
                    raise HTTPException(404, "Order not found")
                if station is not None and saved["station"] != station:
                    raise HTTPException(409, "Receipt is from the wrong station")
                if saved["status"] != target:
                    raise HTTPException(409, f"Cannot move from {saved['status']} to {target}")
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name != "medirover_one_running_order":
            raise
        raise HTTPException(409, "Another trip is already running") from None
    except (psycopg.OperationalError, psycopg.errors.UndefinedTable):
        raise HTTPException(503, "Database or order table unavailable") from None
    return saved
