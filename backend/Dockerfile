FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /bin/

WORKDIR /app

# Install system dependencies required by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency metadata first for Docker layer caching
COPY pyproject.toml uv.lock ./

# Install locked runtime dependencies without the development group
RUN uv sync --locked --no-dev

# Copy application code
COPY . .

# Ensure the venv Python is used
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 5000

# Run Flask dev server, accessible from outside the container
CMD ["flask", "run", "--host", "0.0.0.0", "--port", "5000"]
