# Janus Edge

Janus Edge is a self-hosted trade journaling and analytics application for futures traders. It imports execution-level CSV exports, reconstructs trades, stores media alongside journal entries, and surfaces analytics such as performance summaries and Monte Carlo simulations.

## Why It Exists

Janus Edge is built for traders who want a local-first workflow they can inspect, modify, and run on their own infrastructure. The stack is intentionally straightforward: a React frontend, a Flask API, MongoDB for persistence, and MinIO for media storage.

## Features

- Import execution CSV files from NinjaTrader and Quantower
- Reconstruct trades from execution data
- Journal trades with notes, tags, and media attachments
- Review charts and analytics dashboards
- Run what-if and Monte Carlo analysis workflows
- Store uploaded media in S3-compatible object storage

## Tech Stack

- Frontend: React 19, TypeScript, Vite, Tailwind CSS, Lightweight Charts
- Backend: Python 3.11+, Flask, PyMongo, pandas, yfinance
- Data services: MongoDB 8 and MinIO
- Auth: JWT via Flask-JWT-Extended

## Repository Layout

- `frontend/`: React single-page application
- `backend/`: Flask API and domain services
- `trade_examples/`: sample import files for manual testing

## Local Development With Docker

1. Copy the root environment template.

```bash
cp .env.example .env
```

2. Start the full stack.

```bash
docker compose up -d
```

3. Open the applications.

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:5000`
- MinIO console: `http://localhost:9001`

4. Stop the stack when finished.

```bash
docker compose down
```

The development defaults in `.env.example` are placeholders for local use only. Replace them before any shared or production deployment.

## Local Development Without Docker

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop or separately managed MongoDB and MinIO instances

### Backend

1. Copy the backend env template.

```bash
cp backend/.env.example backend/.env
```

2. Create and activate a virtual environment.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies and run the API.

```bash
pip install -r requirements.txt
flask run --port 5000
```

### Frontend

1. Copy the frontend env template.

```bash
cp frontend/.env.example frontend/.env.local
```

2. Install dependencies and start Vite.

```bash
cd frontend
npm install
npm run dev
```

By default, the frontend talks to `/api` and proxies API requests to `http://localhost:5000` during development.

## Production Installation

Janus Edge can be deployed as separate services behind HTTPS. The repository currently ships development-oriented Dockerfiles and Compose defaults, so production should provide hardened infrastructure and explicit environment values.

1. Provision MongoDB with authentication enabled and regular backups.
2. Provision MinIO or another S3-compatible object store with unique access credentials and a dedicated bucket.
3. Set strong values for `SECRET_KEY`, `JWT_SECRET_KEY`, `MINIO_ACCESS_KEY`, and `MINIO_SECRET_KEY`.
4. Restrict `CORS_ORIGINS` to your real frontend origin.
5. Run the backend with Gunicorn.

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:5000 run:app
```

6. Build the frontend and serve `frontend/dist` from a web server such as Nginx or Caddy.

```bash
cd frontend
npm ci
npm run build
```

7. Terminate TLS at the reverse proxy and route `/api` traffic to the Flask service.
8. Enable structured logging, dependency updates, and backup monitoring before exposing the deployment publicly.

## Configuration

The project uses checked-in example files for configuration contracts:

- `.env.example`: Docker Compose and containerized development
- `backend/.env.example`: local backend development
- `frontend/.env.example`: local frontend development

Do not commit copied `.env`, `.env.local`, or other machine-specific secret files.

## Security

- Sensitive values are expected from environment variables, not from tracked source files.
- Development example credentials such as `minioadmin` are placeholders only and must be replaced in any shared environment.
- Security issues should be reported privately using the process in `SECURITY.md`.

## Documentation

TBD

## Contributing And Support

The repository does not yet ship a full contribution guide. Until that is added, open an issue for bugs or feature requests, and use the private security process for vulnerabilities.

## License

No license file is committed yet. A recommended license choice is documented in `SUGGESTIONS.md` so you can make an explicit decision before publishing the repository.