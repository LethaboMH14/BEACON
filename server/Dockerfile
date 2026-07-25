# BEACON server — ADR-0004 (Azure Container Apps).
# Multi-stage: ortools/pandas are large, so wheels are built in a full image
# and only the installed site-packages + app code ship in the slim runtime
# image, keeping the final image as small as this stack allows.

FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app

COPY --from=builder /install /usr/local
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Migrations run at container start, not baked into the image — DATABASE_URL
# (Postgres in Azure, per ADR-0004) is only known at deploy time.
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
