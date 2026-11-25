import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from app import app


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


def test_persist_and_retry_order_with_postgresql(monkeypatch):
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
            admin.execute(sql.SQL("SET search_path TO {}").format(name))
            admin.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

            request_id = str(uuid4())
            order = {"request_id": request_id, "station": 1}
            with TestClient(app) as client:
                assert client.get("/api/health").status_code == 200
                created = client.post("/api/orders", json=order)
                assert created.status_code == 201
                assert created.json()["status"] == "pending"

                retrieved = client.get(f"/api/orders/{request_id}")
                assert retrieved.status_code == 200
                assert retrieved.json() == created.json()
                retry = client.post("/api/orders", json=order)
                assert retry.status_code == 200
                assert retry.json() == created.json()

                conflict = client.post("/api/orders", json={**order, "station": 2})
                assert conflict.status_code == 409
                assert client.get(f"/api/orders/{uuid4()}").status_code == 404

            assert admin.execute("SELECT count(*) FROM medirover_orders").fetchone() == (1,)


            waiting_id = str(uuid4())
            with TestClient(app) as client:
                assert client.post("/api/orders", json={"request_id": waiting_id, "station": 2}).status_code == 201
                assert client.post(f"/api/orders/{request_id}/complete", json={"station": 1}).status_code == 409
                assert client.post(f"/api/orders/{uuid4()}/start").status_code == 404

                with ThreadPoolExecutor(max_workers=2) as workers:
                    started = list(workers.map(
                        lambda order_id: client.post(f"/api/orders/{order_id}/start"),
                        (request_id, waiting_id),
                    ))
                assert sorted(result.status_code for result in started) == [200, 409]
                active_id, next_id = (
                    (request_id, waiting_id) if started[0].status_code == 200
                    else (waiting_id, request_id)
                )
                assert client.post(f"/api/orders/{active_id}/start").json()["status"] == "running"
                assert client.get(f"/api/orders/{next_id}").json()["status"] == "pending"
                active_station = 1 if active_id == request_id else 2
                wrong_station = 3 - active_station
                receipt_path = f"/api/orders/{active_id}/complete"
                assert client.post(receipt_path).status_code == 422
                assert client.post(receipt_path, json={"station": wrong_station}).status_code == 409
                assert client.post(f"/api/orders/{next_id}/complete", json={"station": wrong_station}).status_code == 409
                assert client.post(f"/api/orders/{uuid4()}/complete", json={"station": active_station}).status_code == 404
                assert client.get(f"/api/orders/{active_id}").json()["status"] == "running"
                assert client.post(receipt_path, json={"station": active_station}).json()["status"] == "completed"
                assert client.post(receipt_path, json={"station": active_station}).status_code == 200
                assert client.post(receipt_path, json={"station": wrong_station}).status_code == 409
                assert client.post(f"/api/orders/{active_id}/start").status_code == 409
                assert client.post(f"/api/orders/{next_id}/start").json()["status"] == "running"
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(name))
