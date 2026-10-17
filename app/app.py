"""Taskboard: a tiny tasks API with a minimal web page.

This is a learning project. Data is kept in memory, so it does not
survive a restart. That is on purpose: the point of this project is the
Kubernetes packaging (probes, limits, HPA, manifests), not the storage.
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_from_directory

# ---------------------------------------------------------------------------
# Structured (JSON) logging
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_logger():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("taskboard")
    logger.handlers = [handler]
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger


log = get_logger()

# ---------------------------------------------------------------------------
# App and in-memory store
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder="static", static_url_path="")

_store_lock = threading.Lock()
_tasks = {}
_next_id = 1
_started_at = time.time()

# Simple counters for /metrics (Prometheus text exposition format)
_metrics_lock = threading.Lock()
_requests_total = 0
_requests_by_route = {}


@app.before_request
def _count_request():
    global _requests_total
    with _metrics_lock:
        _requests_total += 1
        key = f"{request.method} {request.path}"
        _requests_by_route[key] = _requests_by_route.get(key, 0) + 1


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Health endpoints (used by the Kubernetes probes)
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz():
    """Liveness: is the process alive?"""
    return jsonify({"status": "ok"}), 200


@app.get("/readyz")
def readyz():
    """Readiness: is the app ready to take traffic?"""
    return jsonify({"status": "ready", "uptime_seconds": round(time.time() - _started_at, 1)}), 200


# ---------------------------------------------------------------------------
# Prometheus metrics endpoint (scraped via prometheus.io annotations)
# ---------------------------------------------------------------------------


@app.get("/metrics")
def metrics():
    with _metrics_lock:
        lines = [
            "# HELP taskboard_http_requests_total Total HTTP requests handled.",
            "# TYPE taskboard_http_requests_total counter",
            f"taskboard_http_requests_total {_requests_total}",
            "# HELP taskboard_tasks_current Current number of stored tasks.",
            "# TYPE taskboard_tasks_current gauge",
            f"taskboard_tasks_current {len(_tasks)}",
            "# HELP taskboard_uptime_seconds Seconds since process start.",
            "# TYPE taskboard_uptime_seconds gauge",
            f"taskboard_uptime_seconds {round(time.time() - _started_at, 1)}",
        ]
    return "\n".join(lines) + "\n", 200, {"Content-Type": "text/plain; version=0.0.4"}


# ---------------------------------------------------------------------------
# Tasks API
# ---------------------------------------------------------------------------


def _validate_task_body(body):
    if not isinstance(body, dict):
        return "request body must be JSON"
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        return "field 'title' is required and must be a non-empty string"
    if len(title) > 200:
        return "field 'title' must be 200 characters or fewer"
    return None


@app.get("/api/tasks")
def list_tasks():
    with _store_lock:
        items = sorted(_tasks.values(), key=lambda t: t["id"])
    return jsonify(items), 200


@app.post("/api/tasks")
def create_task():
    body = request.get_json(silent=True)
    error = _validate_task_body(body)
    if error:
        log.warning(f"rejected task creation: {error}")
        return jsonify({"error": error}), 400
    global _next_id
    with _store_lock:
        task = {
            "id": _next_id,
            "title": body["title"].strip(),
            "done": bool(body.get("done", False)),
            "created_at": _now_iso(),
        }
        _tasks[_next_id] = task
        _next_id += 1
    log.info(f"created task id={task['id']}")
    return jsonify(task), 201


@app.patch("/api/tasks/<int:task_id>")
def update_task(task_id):
    body = request.get_json(silent=True) or {}
    with _store_lock:
        task = _tasks.get(task_id)
        if task is None:
            return jsonify({"error": "task not found"}), 404
        if "title" in body:
            if not isinstance(body["title"], str) or not body["title"].strip():
                return jsonify({"error": "field 'title' must be a non-empty string"}), 400
            task["title"] = body["title"].strip()
        if "done" in body:
            task["done"] = bool(body["done"])
    log.info(f"updated task id={task_id}")
    return jsonify(task), 200


@app.delete("/api/tasks/<int:task_id>")
def delete_task(task_id):
    with _store_lock:
        if task_id not in _tasks:
            return jsonify({"error": "task not found"}), 404
        del _tasks[task_id]
    log.info(f"deleted task id={task_id}")
    return "", 204


# ---------------------------------------------------------------------------
# Minimal frontend
# ---------------------------------------------------------------------------


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.after_request
def _log_request(response):
    log.info(f"{request.method} {request.path} -> {response.status_code}")
    return response


def main():
    port = int(os.environ.get("PORT", "8080"))
    log.info(f"starting taskboard on port {port}")
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
