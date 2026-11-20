# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS api
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/data/huggingface HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 ANONYMIZED_TELEMETRY=False
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10001 --create-home app \
    && mkdir -p /data/chroma /data/huggingface \
    && chown -R app:app /data
COPY backend/main.py backend/prompts.py backend/retrieval.py backend/penalties.py backend/tck_indeksleme.py backend/docker_setup.py ./
COPY data/rag/tck_rag.json data/rag/tck_gerekceleri_rag.json data/rag/cmk_rag.json data/rag/cgtik_rag.json data/rag/genelhukumler_rag.json ./datasets/
COPY data/ontoloji/ceza_hukuku_ontolojisi.json ./ontology.json
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]

FROM node:24-alpine AS web-build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_API_URL=/api/v1/analyze
RUN npm run build

FROM nginx:stable-alpine AS web
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-build /src/dist /usr/share/nginx/html
EXPOSE 80
