FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && python -m playwright install --with-deps chromium
COPY jobflow ./jobflow
COPY web ./web
RUN mkdir -p /app/data
ENV JOBFLOW_DATA_DIR=/app/data DATABASE_URL=sqlite:////app/data/jobflow.db JOBFLOW_REQUIRE_AUTH=true
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn jobflow.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
