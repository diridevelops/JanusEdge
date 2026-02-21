FROM python:3.12-slim

WORKDIR /app

# Install system dependencies required by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for Docker layer caching
COPY requirements.txt requirements-dev.txt* ./

# Create virtual environment and install dependencies
RUN python -m venv .venv \
    && .venv/bin/pip install --no-cache-dir --upgrade pip \
    && .venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure the venv Python is used
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 5000

# Run Flask dev server, accessible from outside the container
CMD ["flask", "run", "--host", "0.0.0.0", "--port", "5000"]
