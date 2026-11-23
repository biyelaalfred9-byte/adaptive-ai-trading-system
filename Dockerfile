FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 trader \
    && useradd --system --uid 10001 --gid trader --home-dir /app trader \
    && mkdir -p /data \
    && chown trader:trader /data

COPY pyproject.toml README.md ./
COPY trading_system ./trading_system
COPY configs/paper-trading.cloud.example.json ./configs/paper-trading.cloud.example.json

RUN pip install --no-cache-dir ".[crypto]" \
    && chown -R trader:trader /app

USER 10001:10001
VOLUME ["/data"]

CMD ["python", "-m", "trading_system.paper_trading_runner", "configs/paper-trading.cloud.example.json"]
