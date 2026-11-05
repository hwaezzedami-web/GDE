# Contexte de construction : racine du projet (voir docker-compose.yml)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_DIR=/srv/db

WORKDIR /srv/backend

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY db /srv/db

RUN useradd --system --uid 10001 --home /srv gsm && mkdir -p /srv/logs && chown gsm /srv/logs
USER gsm

EXPOSE 8000
# init-db est idempotent : rejoué à chaque démarrage.
CMD ["sh", "-c", "python -m app.cli init-db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
