FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv のインストール（Python も uv が管理）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 依存関係を先にインストール（キャッシュ効率化）
COPY pyproject.toml uv.lock* ./
RUN uv sync --python 3.12 --no-dev --extra server --no-install-project

# アプリケーションコードをコピー
COPY server/ server/

EXPOSE 8000

CMD ["uv", "run", "--no-dev", "python", "-m", "uvicorn", \
     "server.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
