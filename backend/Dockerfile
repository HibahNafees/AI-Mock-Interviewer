# Flask API for production (gunicorn). Multi-arch base: runs on Oracle's ARM VMs.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FLASK_APP=wsgi.py
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY wsgi.py docker-entrypoint.sh ./
RUN useradd --create-home --uid 10001 api && chmod +x docker-entrypoint.sh
USER api

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
# gthread workers: report generation runs in background threads, and a slow
# Fire call (plan, transcribe) shouldn't trip the worker timeout.
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--timeout", "120", "--access-logfile", "-"]
