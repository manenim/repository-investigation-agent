FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DB_PATH=/data/investigations.sqlite3
WORKDIR /srv/trace
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home trace && mkdir /data && chown trace:trace /data
COPY app ./app
COPY evals/snapshot.json ./evals/snapshot.json
# Sample report is copied when generated; no environment or local database enters the image.
COPY evals/sample-report.* ./evals/
USER trace
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready',timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
