# Deployment

## What The Repository Clearly Supports Today

Based on the checked-in files, the repository clearly supports two runtime modes today:

1. local development with Docker Compose
2. mixed local development with MongoDB and MinIO in Docker and Flask and Vite running directly on the host

The repository also includes backend and frontend Dockerfiles, but both are development-oriented rather than production-hardened.

## Current Docker Compose Topology

`docker-compose.yml` defines these services:

- `mongo`
- `minio`
- `backend`
- `frontend`

Characteristics of the current Compose setup:

- MongoDB and MinIO have persistent named volumes
- the backend waits for healthy MongoDB and MinIO containers
- the frontend depends on the backend container
- the backend runs the Flask development server
- the frontend runs the Vite development server
- source folders are bind-mounted into the backend and frontend containers for live development

This is a strong signal that the checked-in Compose file is intended for local development, not a locked-down production deployment.

## Current Dockerfiles

### Backend Dockerfile

The backend image:

- starts from `python:3.12-slim`
- installs `gcc`
- creates a virtual environment inside the image
- installs `requirements.txt`
- runs `flask run --host 0.0.0.0 --port 5000`

### Frontend Dockerfile

The frontend image:

- starts from `node:20-slim`
- installs dependencies with `npm install`
- runs `npm run dev -- --host 0.0.0.0`

Again, this is development behavior, not a production static asset build plus web server.

## What Is Not Fully Defined Yet

These pieces are not currently defined in checked-in deployment files:

- reverse proxy configuration
- HTTPS termination setup
- container image publishing workflow
- CI or CD deployment pipeline
- Kubernetes, Nomad, ECS, or similar manifests
- secret-management integration
- production health-check and observability stack

Treat all of those as TODO items.

## Practical Supported Approach Today

### Recommended local stack

For contributors and maintainers, the supported path is:

```bash
cp .env.example .env
docker compose up -d --build
```

### Mixed local stack

For app development with faster iteration on the host:

```bash
docker compose up mongo minio -d
```

Then run Flask and Vite locally.

## If You Need To Deploy Beyond Local Development

The repository contains enough pieces to support a manual deployment plan, but not enough to call it fully documented or officially packaged.

A minimal manual path would be:

1. provision MongoDB and MinIO separately
2. run the backend behind Gunicorn
3. build the frontend with `npm run build`
4. serve the built frontend behind a reverse proxy
5. route `/api` traffic to the backend

That path is consistent with the codebase, but the concrete reverse-proxy and infrastructure setup is still TODO.