# Dropbox Clone

A file synchronization system with versioning, built with Django REST Framework and MinIO object storage. Clients watch a local folder and sync changes bidirectionally with the server.

## Architecture

```
┌─────────────┐         ┌─────────────────┐         ┌─────────┐
│   Client    │◄──────► │  Django Server   │◄──────► │  MinIO  │
│  (watchdog) │  HTTP   │  (REST API)      │  S3 API │ (blobs) │
└─────────────┘         └────────┬────────-┘         └─────────┘
                                 │
                                 ▼
                          ┌────────────┐
                          │ PostgreSQL │
                          │ (metadata) │
                          └────────────┘
```

- **Server**: Django + DRF API handling file metadata, versioning, and sync coordination
- **Storage**: MinIO (S3-compatible) for file blobs, PostgreSQL for metadata
- **Clients**: Python daemons using `watchdog` to monitor local folders and poll for remote changes

## Features

- File upload, download, rename, and delete
- Version history (retains last 5 versions per file)
- Optimistic concurrency control (conflict detection via version headers)
- Soft delete with trash (auto-expires after 5 days)
- Restore deleted files from trash
- Hash-based upload skipping (no re-upload if content unchanged)
- New client initialization (downloads all server files on first run)
- OpenAPI/Swagger documentation

## Prerequisites

- Docker & Docker Compose
- Python 3.11+

## Getting Started

### Start the server

```bash
docker-compose up --build
```

This starts:
- PostgreSQL on port `5433`
- MinIO on port `9000` (console on `9001`)
- Django server on port `8000`

### Run migrations

```bash
docker-compose exec server python manage.py migrate
```

### Start a client

```bash
cd client
pip install -r ../requirements.txt
python daemon.py
```

The client will watch the configured `synced_folder/` directory and sync changes with the server.

To run a second client (simulating another device):

```bash
cd client2
python daemon.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/files/` | List all files |
| POST | `/api/files/` | Upload a file |
| GET | `/api/files/<id>/` | Get file metadata |
| PATCH | `/api/files/<id>/` | Rename/update a file |
| DELETE | `/api/files/<id>/` | Soft delete a file |
| GET | `/api/files/<id>/download/` | Download file content |
| GET | `/api/files/<id>/download/?version=N` | Download specific version |
| GET | `/api/files/<id>/history/` | Get version history |
| POST | `/api/files/<id>/restore/` | Restore from trash |
| GET | `/api/sync/changes?since=<timestamp>` | Get changes since timestamp |

API documentation is available at `/api/docs/` when the server is running.

You can also import and test the API collection in Hoppscotch: [Open in Hoppscotch](https://hopp.sh/r/EpWjanJFptE9)

## Configuration

### Server

Environment variables (set in `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | `dropbox_clone` | Database name |
| `POSTGRES_USER` | `latifahz` | Database user |
| `POSTGRES_PASSWORD` | `password` | Database password |
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `MINIO_ENDPOINT` | `http://127.0.0.1:9000` | MinIO endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `dropbox-clone` | MinIO bucket name |

### Client

Edit `client/constants.py`:

```python
SERVER_URL = 'http://127.0.0.1:8000/api'
WATCHED_FOLDER = '/path/to/your/synced_folder'
```

## Project Structure

```
├── docker-compose.yml          # Infrastructure (Postgres, MinIO, Django)
├── Dockerfile                  # Server container
├── requirements.txt            # Python dependencies
├── dropboxClone/               # Django project
│   ├── dropboxClone/           # Project settings & URLs
│   └── sync_app/              # Main app
│       ├── models.py          # File & FileVersion models
│       ├── views.py           # API endpoints
│       ├── services.py        # Business logic
│       ├── storage.py         # MinIO operations
│       ├── serializers.py     # DRF serializers
│       └── urls.py            # URL routing
├── client/                     # Sync client 1
│   ├── daemon.py              # Watchdog daemon + polling loop
│   ├── client_services.py     # Upload/download/sync logic
│   └── constants.py           # Client configuration
└── client2/                    # Sync client 2 (second device)
```

## How Sync Works

1. **Local → Server**: The client watches the local folder with `watchdog`. On file create/modify/delete/rename, it pushes the change to the server API.
2. **Server → Local**: Every 10 seconds, the client polls `/api/sync/changes` for any changes made by other clients and applies them locally.
3. **Conflict handling**: Uploads include the client's known version number. If it doesn't match the server's current version, the upload is rejected with a 409 Conflict.
