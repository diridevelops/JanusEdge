# Getting Started

## Before You Start

The codebase, containers, and frontend UI are all named Janus Edge. The commands and URLs in this guide use that current implementation directly.

## Prerequisites

You need the following installed locally.

To simply run the application:

- Docker with the Compose plugin

To develop:

- Python 3.11 or newer
- Node.js 20 or newer

## Development Modes

There are two supported local workflows in the repository today.

### Option 1: Full Docker Compose

This starts MongoDB, MinIO, the Flask backend, and the Vite frontend in containers.

```bash
cp .env.example .env
docker compose up --build
```

To run it in the background:

```bash
docker compose up -d --build
```

### Option 2: Mixed Local App plus Docker Services

This is useful when you want MongoDB and MinIO in Docker, but you want to run Flask and Vite directly on your machine.

Start only the stateful services first:

```bash
docker compose up mongo minio -d
```

Then run the backend locally:

```bash
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask run --port 5000
```

Then run the frontend locally in a second shell:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

This mixed mode uses:

- MongoDB at `mongodb://localhost:27017/janusedge`
- MinIO at `localhost:9000`
- Flask at `http://localhost:5000`
- Vite at `http://localhost:5173`

## Environment Files

The repository ships three example environment files:

- Root `.env.example`: used by Docker Compose
- `backend/.env.example`: used for local backend development
- `frontend/.env.example`: used for local frontend development

The backend validates several secrets at startup. If `SECRET_KEY`, `JWT_SECRET_KEY`, `MINIO_ACCESS_KEY`, or `MINIO_SECRET_KEY` are empty, the Flask app will not boot.

## Exposed Services

When the stack is running with the repository defaults, these endpoints are available:

| Service | URL | Notes |
| --- | --- | --- |
| Frontend | `http://localhost:5173` | Vite development server |
| Backend API | `http://localhost:5000` | Flask API |
| MongoDB | `localhost:27017` | Exposed from the `mongo` container |
| MinIO API | `http://localhost:9000` | S3-compatible object storage endpoint |
| MinIO Console | `http://localhost:9001` | Browser UI for MinIO |

When the frontend runs locally, it sends `/api` requests through the Vite proxy to `VITE_API_PROXY_TARGET`, which defaults to `http://localhost:5000` in local frontend development.

## Common Commands

Start everything with Compose:

```bash
docker compose up -d
```

Start only MongoDB and MinIO:

```bash
docker compose up mongo minio -d
```

Stop running containers without removing them:

```bash
docker compose stop
```

Stop and remove containers:

```bash
docker compose down
```

Follow logs for a service:

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f mongo
docker compose logs -f minio
```

Remove containers and local Docker volumes:

```bash
docker compose down -v
```

This last command removes the `mongo-data` and `minio-data` volumes and will erase local database and object-storage state.

## Recommended First Checks

After startup:

1. Open `http://localhost:5173` and confirm the frontend loads.
2. Open `http://localhost:5000/api/auth/health` and confirm it returns `{"status": "ok"}`.
3. Open `http://localhost:9001` and confirm the MinIO console is reachable.

## Where To Go Next

- For an introduction to Janus Edge's features, read [Usage Guide](./usage.md).
- For system structure, read [Architecture Overview](./architecture/architecture.md).
- For backend-specific details, read [Backend Architecture](./architecture/backend.md).
- For frontend-specific details, read [Frontend Architecture](./architecture/frontend.md).
- For environment variables, read [Configuration](./configuration.md).