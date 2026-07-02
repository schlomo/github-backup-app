FROM python:3.14-alpine AS builder

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install locked dependencies into the project virtualenv. Using the lock file
# (instead of `uv pip install .`) guarantees the image ships the exact same
# dependency versions that were tested, preventing silent breakage when an
# upstream release changes behaviour (e.g. PyJWT 2.11 requiring a string `iss`).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source code and install the project itself. --no-editable builds and
# installs the package into the virtualenv (rather than linking back to /app,
# which does not exist in the final image stage).
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.14-alpine
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
