FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY stepbound_be ./stepbound_be
COPY migrations ./migrations
COPY wsgi.py .

RUN useradd --system --uid 10001 stepbound
USER stepbound

ENV FLASK_APP=wsgi.py
EXPOSE 8000
# Migrations first, so a new image brings its tables with it: right for a
# single instance. With several, set MIGRATE_ON_START=0 and run
# `flask db upgrade` once, as its own step, before rolling them out.
ENV MIGRATE_ON_START=1
CMD ["sh", "-c", "if [ \"$MIGRATE_ON_START\" = 1 ]; then flask db upgrade; fi && exec gunicorn --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --access-logfile - wsgi:app"]
