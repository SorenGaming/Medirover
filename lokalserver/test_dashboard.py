import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from fastapi.testclient import TestClient

from app import app, connect
from dashboard import store_temperature
from uart import accept_frame


@pytest.fixture
def client(monkeypatch):
    dsn = os.environ.get("MEDIROVER_TEST_DSN")
    if not dsn:
        pytest.skip("An isolated PostgreSQL test database is required")
    schema = "dashboard_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            admin.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            admin.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
            monkeypatch.setenv("MEDIROVER_DATABASE_DSN", make_conninfo(dsn, options=f"-c search_path={schema}"))
            monkeypatch.delenv("MEDIROVER_UART_PORT", raising=False)
            with TestClient(app) as instance:
                yield instance
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def seed(station, status):
    with connect() as connection:
        connection.execute(
            "INSERT INTO medirover_orders(request_id,station,status) VALUES (%s,%s,%s)",
            (uuid4(), station, status),
        )


def test_website_and_missing_database(monkeypatch):
    monkeypatch.delenv("MEDIROVER_DATABASE_DSN", raising=False)
    monkeypatch.delenv("MEDIROVER_UART_PORT", raising=False)
    with TestClient(app) as client:
        assert "Temperatur i boksen" in client.get("/").text
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/style.css").status_code == 200
        for endpoint in ("orders", "statistics", "temperature"):
            assert client.get("/api/" + endpoint).status_code == 503


def test_history_and_having_use_real_postgresql(client):
    seed(1, "completed"); seed(1, "completed"); seed(1, "pending")
    seed(2, "completed"); seed(2, "running")
    assert client.get("/api/orders").json()["total"] == 5
    page = client.get("/api/orders?station=1&status=completed&limit=1&offset=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert page["items"][0]["station"] == 1 and page["items"][0]["status"] == "completed"
    assert client.get("/api/orders?offset=100").json()["items"] == []
    stats = client.get("/api/statistics").json()["stations"]
    assert [(s["station"], s["completed"], s["orders"]) for s in stats] == [(1,2,3),(2,1,2)]
    assert client.get("/api/statistics?min_completed=2").json()["stations"] == [stats[0]]
    assert client.get("/api/statistics?min_completed=3").json()["stations"] == []


@pytest.mark.parametrize("query", ["orders?station=3", "orders?status=invalid", "orders?limit=0", "orders?offset=-1", "statistics?min_completed=-1", "statistics?min_completed=1%20OR%201=1"])
def test_invalid_filters(client, query):
    assert client.get("/api/" + query).status_code == 422


def test_temperature_missing_fresh_stale_and_uart(client):
    assert client.get("/api/temperature").json()["state"] == "missing"
    receipts = []
    save = lambda value: store_temperature(connect, value)
    for frame in (b"TEMP,rover,nan\n", b"TEMP,rover,999\n", b"TEMP,rover,21.7", b"TEMP,station,21.7\n"):
        accept_frame(frame, lambda *args: receipts.append(args), save)
    assert client.get("/api/temperature").json()["temperature_c"] is None
    accept_frame(b"TEMP,rover,21.75\n", lambda *args: receipts.append(args), save)
    reading = client.get("/api/temperature").json()
    assert reading["temperature_c"] == 21.75 and reading["state"] == "fresh"
    with connect() as connection:
        connection.execute("UPDATE medirover_temperatures SET measured_at = now() - interval '3 minutes'")
    assert client.get("/api/temperature").json()["state"] == "stale"
    request_id = uuid4()
    accept_frame(f"ACK,{request_id},1\n".encode(), lambda *args: receipts.append(args), save)
    assert receipts == [(request_id,1)]
    with pytest.raises(ValueError):
        store_temperature(connect, float("nan"))
    assert client.post("/api/temperature", json={"temperature_c":20}).status_code == 405


def test_schema_is_repeatable_without_erasing_data(client):
    seed(1, "completed")
    store_temperature(connect, 19.2)
    with connect() as connection:
        connection.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    assert client.get("/api/orders").json()["total"] == 1
    assert client.get("/api/temperature").json()["temperature_c"] == 19.2
