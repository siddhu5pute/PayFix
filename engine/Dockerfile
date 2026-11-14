# Build context: repository root (so the shared contract can be copied in)
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/shared:/app
COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ /app/shared/
COPY engine/engine_app/ /app/engine_app/
EXPOSE 8100
CMD ["uvicorn", "engine_app.main:app", "--host", "0.0.0.0", "--port", "8100"]
