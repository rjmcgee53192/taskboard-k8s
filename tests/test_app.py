"""Unit tests for the taskboard API."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import app as taskboard  # noqa: E402


def make_client():
    taskboard._tasks.clear()
    taskboard._next_id = 1
    return taskboard.app.test_client()


def test_healthz():
    client = make_client()
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"


def test_readyz():
    client = make_client()
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ready"


def test_metrics_exposes_taskboard_metrics():
    client = make_client()
    res = client.get("/metrics")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "taskboard_http_requests_total" in body
    assert "taskboard_tasks_current" in body


def test_create_and_list_tasks():
    client = make_client()
    res = client.post("/api/tasks", json={"title": "buy milk"})
    assert res.status_code == 201
    created = res.get_json()
    assert created["id"] == 1
    assert created["title"] == "buy milk"
    assert created["done"] is False

    res = client.get("/api/tasks")
    assert res.status_code == 200
    items = res.get_json()
    assert len(items) == 1
    assert items[0]["title"] == "buy milk"


def test_create_task_requires_title():
    client = make_client()
    res = client.post("/api/tasks", json={})
    assert res.status_code == 400
    res = client.post("/api/tasks", json={"title": "   "})
    assert res.status_code == 400


def test_update_task_done_flag():
    client = make_client()
    client.post("/api/tasks", json={"title": "write tests"})
    res = client.patch("/api/tasks/1", json={"done": True})
    assert res.status_code == 200
    assert res.get_json()["done"] is True


def test_update_missing_task_returns_404():
    client = make_client()
    res = client.patch("/api/tasks/999", json={"done": True})
    assert res.status_code == 404


def test_delete_task():
    client = make_client()
    client.post("/api/tasks", json={"title": "temp"})
    res = client.delete("/api/tasks/1")
    assert res.status_code == 204
    res = client.get("/api/tasks")
    assert res.get_json() == []


def test_delete_missing_task_returns_404():
    client = make_client()
    res = client.delete("/api/tasks/999")
    assert res.status_code == 404
