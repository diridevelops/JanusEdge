# Configuration

## Configuration Sources

The repository currently uses three example environment files:

- `.env.example` for Docker Compose
- `backend/.env.example` for local backend development
- `frontend/.env.example` for local frontend development

The backend also has a testing-only value in code:

- `MONGO_URI_TEST`, used by `TestingConfig`

## Backend Variables

### Flask and backend runtime

| Variable | Example default | Used by | Notes |
| --- | --- | --- | --- |
| `FLASK_APP` | `run.py` | Compose and local backend env | Used by the Flask CLI |
| `FLASK_ENV` | `development` | Backend config selection | Chooses Development, Testing, or Production config |
| `FLASK_DEBUG` | `1` | Flask CLI runtime | Enables Flask debug behavior in local setups |
| `SECRET_KEY` | `dev-secret-change-in-production` | Flask app | Required at backend startup |
| `JWT_SECRET_KEY` | `dev-jwt-secret-change-in-production` | JWT signing | Required at backend startup |
| `CORS_ORIGINS` | `http://localhost:5173` | Flask-CORS | Comma-separated list split in code |

### MongoDB

| Variable | Example default | Used by | Notes |
| --- | --- | --- | --- |
| `MONGO_URI` | `mongodb://localhost:27017/janusedge` or `mongodb://mongo:27017/janusedge` | PyMongo | Host differs between local backend and Compose |
| `MONGO_URI_TEST` | `mongodb://localhost:27017/janusedge_test` | TestingConfig | Not present in example files, but read in code |

### MinIO

| Variable | Example default | Used by | Notes |
| --- | --- | --- | --- |
| `MINIO_ENDPOINT` | `localhost:9000` or `minio:9000` | MinIO client | Host differs between local backend and Compose |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO client | Required at backend startup |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO client | Required at backend startup |
| `MINIO_BUCKET` | `janusedge-media` | Storage initialization | Bucket is created automatically if missing |
| `MINIO_USE_SSL` | `false` | MinIO client | Parsed as a boolean in code |
| `MINIO_PUBLIC_URL` | `http://localhost:9000` | Media presigned URLs | Browser-facing MinIO origin used to generate presigned media URLs when the backend connects through an internal endpoint such as `minio:9000`. If the app is opened from another host, set this to that Docker host's browser-reachable address. |

## Docker Compose Variables

The root `.env.example` also includes MinIO service credentials for the container itself:

| Variable | Example default | Notes |
| --- | --- | --- |
| `MINIO_ROOT_USER` | `minioadmin` | Used by the MinIO container |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | Used by the MinIO container |

## Frontend Variables

| Variable | Example default | Used by | Notes |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | Axios client | Browser-facing base path |
| `VITE_API_PROXY_TARGET` | `http://localhost:5000` or `http://backend:5000` | Vite dev server | Used only by the dev proxy |
| `VITE_APP_NAME` | `Janus Edge` | Example files and Compose | Present in env files, but the current frontend source does not read it |

## Development Defaults By Workflow

### Full Docker Compose

The root `.env.example` is designed for container-to-container networking:

- `MONGO_URI=mongodb://mongo:27017/janusedge`
- `MINIO_ENDPOINT=minio:9000`
- `VITE_API_PROXY_TARGET=http://backend:5000`

### Mixed local app plus Docker services

The local backend and frontend example files are designed for host-to-container access:

- `MONGO_URI=mongodb://localhost:27017/janusedge`
- `MINIO_ENDPOINT=localhost:9000`
- `VITE_API_PROXY_TARGET=http://localhost:5000`

## Production Guidance

The repository does not yet contain a full production deployment contract, but the current code makes these requirements clear:

1. Replace all example secrets.
2. Set `CORS_ORIGINS` to your real frontend origin instead of `http://localhost:5173`.
3. Use real MongoDB and MinIO endpoints instead of local or Compose hostnames.
4. Decide whether MinIO traffic should use TLS and set `MINIO_USE_SSL` accordingly.
5. Set `MINIO_PUBLIC_URL` to a browser-reachable MinIO origin if the backend connects through an internal hostname such as `minio:9000`.
6. If you run Docker on one machine and open the app from another, set `MINIO_PUBLIC_URL` in the root `.env` to the Docker host address, for example `http://192.168.1.50:9000`, so trade-detail media does not point at `localhost`.
7. Do not rely on `VITE_APP_NAME` until the frontend reads it from `import.meta.env`.

## Startup Validation And Failure Mode

The backend calls `validate_config()` during app creation. If any required secret is empty, the backend raises a runtime error before serving requests.

This behavior applies even in local development, so copied env files must contain non-empty values.
