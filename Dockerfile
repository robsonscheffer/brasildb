FROM ghcr.io/astral-sh/uv:0.9.24-python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy BRASILDB_DATA=/data

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY brasildb ./brasildb
COPY sql ./sql
COPY catalog.yaml ./
RUN uv sync --frozen --no-dev

VOLUME ["/data"]
ENTRYPOINT ["uv", "run", "--no-sync", "brasildb"]
