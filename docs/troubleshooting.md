# Troubleshooting

## Containers Do Not Start

Check the service state first:

```bash
docker compose ps
docker compose logs -f
```

If the backend container exits immediately, a common cause is missing or empty required secrets in `.env`.

The backend validates these values during startup:

- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

## A Port Is Already In Use

The repository defaults expect these host ports to be free:

- `5173` for the frontend
- `5000` for the backend
- `27017` for MongoDB
- `9000` and `9001` for MinIO

If a service fails to bind, stop the conflicting process or change the published port in `docker-compose.yml` or your local command line.

## Backend Cannot Connect To MongoDB

The correct MongoDB host depends on how you are running the backend.

### Backend running locally

Use:

```bash
MONGO_URI=mongodb://localhost:27017/janusedge
```

### Backend running inside Docker Compose

Use:

```bash
MONGO_URI=mongodb://mongo:27017/janusedge
```

If you mix these up, the backend will fail to connect even though MongoDB is healthy.

You can verify the MongoDB container separately with:

```bash
docker compose logs -f mongo
```

## Frontend Cannot Reach Backend

If the frontend loads but API calls fail:

1. confirm the backend is serving on port `5000`
2. confirm `VITE_API_PROXY_TARGET` points at the correct backend URL
3. restart the Vite dev server after changing frontend env files

For local frontend development, the expected default is:

```bash
VITE_API_PROXY_TARGET=http://localhost:5000
```

For the frontend container in Compose, the expected default is:

```bash
VITE_API_PROXY_TARGET=http://backend:5000
```

## Backend Cannot Connect To MinIO

As with MongoDB, the correct MinIO host depends on where Flask is running.

### Backend running locally

Use:

```bash
MINIO_ENDPOINT=localhost:9000
```

### Backend running inside Docker Compose

Use:

```bash
MINIO_ENDPOINT=minio:9000
```

If MinIO is unavailable during startup, the Flask app can still boot, but it logs a warning and media uploads will be unavailable.

Check MinIO logs with:

```bash
docker compose logs -f minio
```

## Bucket Or Media Upload Issues

The backend attempts to create the configured bucket automatically on startup.

If uploads still fail:

1. verify `MINIO_BUCKET` matches the intended bucket name
2. verify `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` are valid for the MinIO server you are using
3. confirm the backend can reach the MinIO endpoint you configured

The current media rules are:

- maximum file size `500 MB`
- maximum `20` attachments per trade
- allowed content types limited to common image and video formats

## Authentication Problems After Login

The frontend stores the JWT in `sessionStorage`.

If requests start returning `401`:

- the frontend clears the token automatically
- the app redirects back to `/login`

Common causes:

- the backend restarted with a different `JWT_SECRET_KEY`
- the token expired
- the request is hitting a different backend instance or environment than expected

## CSV Import Fails

The current import flow only supports CSV files recognized as NinjaTrader or Quantower exports.

Common import failures:

- the file is empty
- the file extension is not `.csv`
- the CSV format is not recognized
- the same file has already been imported for the same user, based on file hash

If the backend says the file has already been imported, delete the related import batch first or use a different file.

## Market Data Does Not Load On Trade Detail Pages

The trade detail page shows a market-data error when OHLC data cannot be fetched.

Common causes visible in the code:

- intraday data older than roughly two months is unavailable from the current source
- the imported symbol does not resolve to the correct Yahoo symbol
- no custom symbol mapping exists for that instrument

Check the symbol mappings in the Settings page if a trade symbol does not line up with Yahoo Finance naming.

## Resetting Local State

To stop the stack and remove local MongoDB and MinIO volumes:

```bash
docker compose down -v
```

This removes:

- `mongo-data`
- `minio-data`

Use this when local data becomes inconsistent or when you want a clean start. It is destructive.

## Local Build Or Dev Tool Problems

### Frontend

If the frontend dev server behaves strangely after dependency or env changes:

```bash
cd frontend
rm -rf node_modules
npm install
```

### Backend

If Python dependencies drift or the virtual environment is broken:

```bash
cd backend
rm -rf .venv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```