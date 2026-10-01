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
# Migrations first: a new image brings its tables with it.
CMD ["sh", "-c", "flask db upgrade && exec gunicorn --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --access-logfile - wsgi:app"]
