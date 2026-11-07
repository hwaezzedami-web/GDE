# Image du backend : API (uvicorn) et service de collecte partagent le même code.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data SQL_INIT_DIR=/app/db/init

WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY backend/app /app/app
COPY db /app/db
COPY data /app/data

RUN useradd --system --uid 10001 --home /app gsm && mkdir -p /app/logs && chown -R gsm /app/logs
USER gsm

EXPOSE 8000
# Par défaut : API. Le service de collecte surcharge la commande (voir docker-compose.yml).
CMD ["sh", "-c", "python -m app.cli init-db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --workers ${API_WORKERS:-2}"]
