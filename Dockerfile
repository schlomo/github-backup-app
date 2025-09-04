FROM python:3.13-alpine3.22 AS builder

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Create virtual environment and install dependencies
RUN --mount=type=cache,target=/root/.cache/uv uv venv

# Copy source code
COPY . .

# Install the package in development mode to include all files
RUN --mount=type=cache,target=/root/.cache/uv uv pip install .


FROM python:3.13-alpine3.22
ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache \
    ca-certificates \
    git \
    git-lfs \
    && addgroup -g 1000 appuser \
    && adduser -D -u 1000 -G appuser appuser

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

WORKDIR /data

USER appuser

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["github-backup"]
