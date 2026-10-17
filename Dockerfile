# --- build the console ---
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- API + agents ---
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY tbk ./tbk
RUN pip install --no-cache-dir -e .
COPY scripts ./scripts
COPY --from=web /web/dist ./web/dist
ENV PYTHONUNBUFFERED=1 FALKORDB_HOST=falkordb FALKORDB_PORT=6379
EXPOSE 8765
CMD ["sh", "scripts/entrypoint.sh"]
