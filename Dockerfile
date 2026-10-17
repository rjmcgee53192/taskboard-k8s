# Taskboard image. Python 3.12 slim, gunicorn serving the Flask app.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /srv/taskboard

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

# Run as a non-root user, as the Kubernetes securityContext also requires.
RUN useradd --create-home --uid 10001 taskboard \
    && chown -R taskboard:taskboard /srv/taskboard
USER taskboard

EXPOSE 8080

# One worker: tasks live in process memory, so a single worker keeps the
# demo consistent. (With multiple workers, each would have its own copy.)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", \
     "--access-logfile", "-", "--error-logfile", "-", "app:app"]
