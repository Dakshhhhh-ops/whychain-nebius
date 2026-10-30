# WhyChain as one container: the web app, the API and the data, for a Nebius AI Cloud Serverless Endpoint
# (image in Nebius Container Registry) or any Docker host.
#
#   docker build --platform linux/amd64 -t whychain .
#   docker run -p 8000:8000 whychain                                   # keyless: replays recorded investigations
#   docker run -p 8000:8000 -e NEBIUS_API_KEY -e WHYCHAIN_ACCESS_CODE whychain   # live, on Token Factory
#
# The Olist data (CC BY-NC-SA 4.0) is downloaded and rebuilt while the image builds; it is not in the repository.

# ---- the web app ----------------------------------------------------------------------------------------------
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- the API, the agents and the data ---------------------------------------------------------------------------
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 PORT=8000 WHYCHAIN_HARNESS=local USE_POSTGRES=false \
    WHYCHAIN_MAX_PARALLEL_RUNS=2 WHYCHAIN_RUN_TIMEOUT_S=900
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY whychain/ whychain/
COPY datagen/ datagen/
RUN pip install -e . && useradd --create-home --uid 1000 whychain

# the data: the real Olist marketplace (download + build, a few minutes) and the simulated distributor (seconds)
RUN python -m datagen.olist --no-postgres && python -m datagen.generate && rm -rf data/olist/raw

COPY scripts/ scripts/
COPY evals/ evals/
COPY runs/ runs/
COPY --from=web /web/dist frontend/dist
RUN chown -R whychain:whychain /app/runs /app/data
USER whychain

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)"
CMD ["python", "-m", "whychain.api"]
