# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS api
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/data/huggingface HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 ANONYMIZED_TELEMETRY=False
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10001 --create-home app \
    && mkdir -p /data/chroma /data/huggingface \
    && chown -R app:app /data
COPY main.py tck_indeksleme.py docker_setup.py ./
COPY ceza_kanunu_duzeltilmis_2/tck_rag.json ./datasets/tck_rag.json
COPY eklenebilir_hukuk/tck_gerekceleri_rag.json eklenebilir_hukuk/cmk_rag.json eklenebilir_hukuk/cgtik_rag.json eklenebilir_hukuk/genelhukumler_rag.json ./datasets/
COPY hukuk_sozlugu/ceza_hukuku_ontolojisi.json ./ontology.json
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS gateway-build
WORKDIR /src
COPY dotnet-gateway/Gateway.csproj ./
RUN dotnet restore Gateway.csproj
COPY dotnet-gateway/ ./
RUN dotnet publish Gateway.csproj -c Release --no-restore -o /out /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS gateway
WORKDIR /app
COPY --from=gateway-build /out ./
ENV ASPNETCORE_HTTP_PORTS=8080
USER $APP_UID
EXPOSE 8080
ENTRYPOINT ["dotnet", "Gateway.dll"]

FROM node:24-alpine AS web-build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_API_URL=/api/chat
RUN npm run build

FROM nginx:stable-alpine AS web
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-build /src/dist /usr/share/nginx/html
EXPOSE 80
