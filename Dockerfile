# CyberShield SatCom 3D - one container: the backend serves the API, the WebSocket and the built dashboard.
# Build:  docker build -t cybershield .
# Run:    docker compose up -d      (see docker-compose.yml and docs/CLOUD_DEPLOY.md)

# ---- 1. build the dashboard (React + Vite)
FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. the backend (FastAPI) + the built dashboard
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements-cloud.txt ./
RUN pip install --no-cache-dir -r requirements-cloud.txt
COPY backend/ ./
COPY --from=frontend /src/frontend/dist /app/frontend/dist
ENV FRONTEND_DIST=/app/frontend/dist
RUN useradd --create-home cybershield && mkdir -p /app/database /app/exports && chown -R cybershield /app
USER cybershield
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
