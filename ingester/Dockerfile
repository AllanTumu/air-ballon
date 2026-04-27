FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as non-root
RUN useradd -m -u 1001 ingester
USER ingester

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import socket,os,sys;\
import psycopg;\
psycopg.connect(os.environ['DB_DSN'], connect_timeout=5).close();\
sys.exit(0)" || exit 1

CMD ["python", "main.py"]
