import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

import app as app_module
from app import app, base_event


def test_missing_database_configuration(monkeypatch):
    monkeypatch.delenv("MEDIROVER_DATABASE_DSN", raising=False)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 503


@pytest.mark.parametrize(
    "payload",
    [
        {"request_id": "not-a-uuid", "station": 1},
        {"request_id": str(uuid4()), "station": 3},
        {"request_id": str(uuid4()), "station": True},
        {"request_id": str(uuid4()), "station": 1, "status": "running"},
    ],
)
def test_invalid_orders(monkeypatch, payload):
    monkeypatch.delenv("MEDIROVER_DATABASE_DSN", raising=False)
    with TestClient(app) as client:
        assert client.post("/api/orders", json=payload).status_code == 422


class FakeBase:

    def __init__(self):
        self.lines = []
        self.refuse = None
        self.port = object()

    def command(self, line, trip):
        self.lines.append(line)
        if self.refuse:
            raise HTTPException(409, "The base refused: " + self.refuse)


def test_whole_trip_with_postgresql(monkeypatch):
    dsn = os.environ.get("MEDIROVER_TEST_DSN")
    if not dsn:
        pytest.skip("Set MEDIROVER_TEST_DSN to an isolated PostgreSQL test database")
    schema = "medirover_test_" + uuid4().hex
    name = sql.Identifier(schema)
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(name))
        try:
            monkeypatch.setenv(
                "MEDIROVER_DATABASE_DSN",
                make_conninfo(dsn, options=f"-c search_path={schema}"),
            )
            monkeypatch.delenv("MEDIROVER_UART_PORT", raising=False)
            admin.execute(sql.SQL("SET search_path TO {}").format(name))
            admin.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
            with TestClient(app) as client:
                base = FakeBase()
                monkeypatch.setattr(app_module, "base", base)
                status = lambda trip: client.get(f"/api/orders/{trip}").json()["status"]

                trip = str(uuid4())
                order = {"request_id": trip, "station": 1}
                created = client.post("/api/orders", json=order)
                assert created.status_code == 201 and created.json()["status"] == "pending"
                assert base.lines == [f"ORDER,{trip},1"]
                assert client.post("/api/orders", json=order).status_code == 200
                assert client.post("/api/orders", json={**order, "station": 2}).status_code == 409
                assert client.post("/api/orders", json={"request_id": str(uuid4()), "station": 2}).status_code == 409
                assert client.get(f"/api/orders/{uuid4()}").status_code == 404
                assert len(base.lines) == 1

                assert client.post(f"/api/orders/{trip}/resume").status_code == 409
                assert client.post(f"/api/orders/{trip}/packed").json()["status"] == "pending"
                assert base.lines[-1] == f"KLAR,{trip}"
                base_event("STARTED", UUID(trip), "1")
                assert status(trip) == "running"
                with pytest.raises(HTTPException):
                    base_event("ACK", UUID(trip), "2")
                base_event("ERR", UUID(trip), "LINE")
                assert client.get(f"/api/orders/{trip}").json()["last_error"] == "LINE"
                assert client.post(f"/api/orders/{trip}/resume").json()["last_error"] is None
                base_event("ACK", UUID(trip), "1")
                assert status(trip) == "delivered"
                assert client.post("/api/orders", json={"request_id": str(uuid4()), "station": 2}).status_code == 409
                base_event("HOME", UUID(trip), None)
                assert status(trip) == "completed"

                base.refuse = "NOT_HOME"
                refused = str(uuid4())
                assert client.post("/api/orders", json={"request_id": refused, "station": 2}).status_code == 409
                assert client.get(f"/api/orders/{refused}").json()["last_error"].endswith("NOT_HOME")
                assert status(refused) == "rejected"

                base.refuse = None
                stopped = str(uuid4())
                assert client.post("/api/orders", json={"request_id": stopped, "station": 2}).status_code == 201
                assert client.post(f"/api/orders/{stopped}/close").status_code == 409
                assert client.post(f"/api/orders/{stopped}/stop").json()["status"] == "stopped"
                base_event("ERR", UUID(stopped), "STOPPED")
                assert client.post(f"/api/orders/{stopped}/close").json()["status"] == "cancelled"
                assert base.lines[-2:] == [f"STOP,{stopped}", f"LUK,{stopped}"]

                with ThreadPoolExecutor(max_workers=2) as workers:
                    results = list(workers.map(
                        lambda station: client.post("/api/orders", json={"request_id": str(uuid4()), "station": station}),
                        (1, 2),
                    ))
                assert sorted(result.status_code for result in results) == [201, 409]
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(name))
