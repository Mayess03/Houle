# Houle

Houle is an ocean buoy monitoring demo. A Python simulator sends buoy measurements to a FastAPI backend, which stores them in PostgreSQL and calculates fleet status and alerts. A Vue dashboard displays the latest fleet statistics and active alerts.

## Project structure

```text
backend/     FastAPI API and PostgreSQL persistence
frontend/    Vue 3 + TypeScript dashboard (Vite)
simulator/   Python buoy measurement simulator
k8s/         Kubernetes manifests for the namespace, database, API, and simulator
docker-compose.yml
```

## Requirements

- Python 3.12 or later
- Node.js and npm
- Docker (for a local PostgreSQL database), or a reachable PostgreSQL instance

## Run locally

Start a PostgreSQL database. For a disposable local development database:

```sh
docker run --name houle-postgres -e POSTGRES_USER=houle -e POSTGRES_PASSWORD=YOUR_LOCAL_PASSWORD -e POSTGRES_DB=houle -p 5432:5432 -d postgres:16-alpine
```

The credentials above are for local development only. Do not reuse them in a shared or production environment.

### Start the backend

In a terminal, create and activate a virtual environment, install the backend dependencies, and set the database URL:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://houle:YOUR_LOCAL_PASSWORD@localhost:5432/houle"
uvicorn main:app --reload
```

The API listens on `http://localhost:8000`. It creates the measurements table at startup. Interactive API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

For Bash, use `python3 -m venv .venv`, `source .venv/bin/activate`, and `export DATABASE_URL="postgresql+psycopg://houle:YOUR_LOCAL_PASSWORD@localhost:5432/houle"` in place of the Windows-specific setup commands.

### Start the simulator

In another terminal:

```powershell
cd simulator
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:API_URL = "http://localhost:8000"
py simulator.py
```

The simulator sends measurements for three sample buoys every five seconds by default. `API_URL` defaults to `http://backend:8000`, which is suitable for service-to-service traffic in a container network; set it to `http://localhost:8000` when running the simulator directly on your machine.

### Start the dashboard

In a third terminal:

```sh
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (usually `http://localhost:5173`). The Vite development server proxies `/api` requests to the backend at `http://localhost:8000`.

To create a production frontend bundle, run `npm run build` from `frontend/`. The generated files are written to `frontend/dist/`.

## API

All API routes are served from the backend root (for example, `http://localhost:8000/stats`):

| Method | Route | Description |
| --- | --- | --- |
| `GET` | `/healthz` | Liveness check |
| `GET` | `/readyz` | Readiness check, including database connectivity |
| `POST` | `/measurements` | Store a buoy measurement |
| `GET` | `/stats` | Fleet totals and alert counts |
| `GET` | `/buoys` | Latest status and measurement for each buoy |
| `GET` | `/buoys/{buoy_id}/history?limit=100` | Measurement history; `limit` must be between 1 and 1000 |
| `GET` | `/alerts` | Current silent-buoy, low-battery, and high-wave alerts |

Example measurement payload:

```json
{
  "measurement_id": "unique-measurement-id",
  "buoy_id": "buoy-001",
  "measured_at": "2026-10-30T09:00:00Z",
  "wave_height": 1.25,
  "battery_level": 90.0,
  "latitude": 36.85,
  "longitude": 10.5
}
```

`measured_at` must include a timezone. The API rejects values outside the supported ranges for wave height, battery level, and geographic coordinates.

## Configuration

The backend reads these environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | Required | SQLAlchemy PostgreSQL connection URL, such as `postgresql+psycopg://user:YOUR_PASSWORD@host:5432/database` |
| `API_HOST` | `0.0.0.0` | Host used when running `main.py` directly |
| `API_PORT` | `8000` | Port used when running `main.py` directly |
| `LOW_BATTERY_THRESHOLD` | `20` | Battery percentage below which a warning is raised |
| `HIGH_WAVE_THRESHOLD` | `4.0` | Wave height in meters above which a warning is raised |
| `BUOY_SILENCE_SECONDS` | `30` | Time without a received measurement before a buoy is marked silent |

The simulator accepts `API_URL` (default `http://backend:8000`) and `INTERVAL_SECONDS` (default `5`).

## Containers and Kubernetes

`docker-compose.yml` currently builds the backend and simulator images only. It does not configure a database, expose the API port, or run the frontend, so use the local steps above or complete the Compose configuration before relying on it as a full-stack launcher.

The `k8s/` directory contains manifests for the `houle` namespace, PostgreSQL, the backend, and the simulator. Apply them in dependency order:

```sh
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/simulator.yaml
```

The manifests reference the published backend and simulator images. They do not include a frontend deployment. For local dashboard development against the Kubernetes backend, forward the API service port:

```sh
kubectl -n houle port-forward service/backend 8000:8000
```

Then start the frontend with `npm run dev`. Review and replace the database credentials and Kubernetes Secret values before using these manifests in any shared or production cluster. Keep real credentials out of source control.