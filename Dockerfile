# AutoVerify NG — Dockerfile for Render deployment
#
# A Dockerfile is used (rather than Render's native Python buildpack)
# because Tesseract OCR is a SYSTEM binary, not a pip package — Docker
# lets us apt-get install it reliably during the build.

FROM python:3.12-slim

# System dependencies:
# - tesseract-ocr: real plate OCR (utils/ocr.py)
# - libgl1 / libglib2.0-0: required by opencv-python-headless at runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_APP=app.py

# Render sets $PORT at runtime — gunicorn binds to it.
# --timeout 120: the first request after a cold start loads TensorFlow/
# OpenCV, which can take longer than gunicorn's 30s default timeout.
#
# `flask db upgrade` applies any pending schema migrations (see
# migrations/) before the app starts — critical when DATABASE_URL points
# at a persistent database (e.g. Postgres on Render) rather than the
# ephemeral local SQLite fallback, since db.create_all() alone can never
# add a new column to a table that already exists. `flask seed-demo`
# then ensures the demo officer/admin/vehicle records exist (idempotent
# — safe on every deploy, won't duplicate on restart).
CMD flask db upgrade && flask seed-demo && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
