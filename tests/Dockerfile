# Build context: repository root
FROM python:3.12-slim
WORKDIR /repo
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY portal/backend/requirements.txt portal/backend/requirements.txt
COPY tests/requirements.txt tests/requirements.txt
RUN pip install --no-cache-dir -r tests/requirements.txt
COPY shared/ shared/
COPY portal/backend/ portal/backend/
COPY engine/ engine/
COPY tests/ tests/
CMD ["sh", "tests/run_all.sh"]
