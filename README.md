# Houle: ocean buoy monitoring platform

Houle collects, stores and displays measurements from a fleet of simulated ocean buoys. Everything runs on Kubernetes (Minikube) and can be started locally.


| Component  | Tech                        | Role                                                         |
| ---------- | --------------------------- | ------------------------------------------------------------ |
| Simulator  | Python, `requests`          | Simulates 3 buoys (waves, battery with solar charge, GPS drift) and posts a measurement every 5 s |
| Backend    | FastAPI, SQLAlchemy, psycopg | Validates, stores and serves measurements; computes fleet state and alerts |
| Database   | PostgreSQL 16 + PVC         | Persistent storage of the measurement history                |
| Dashboard  | Vue 3 + TypeScript          | Fleet overview, stats and active alerts, auto-refreshed every 5 s |

Inside the cluster, components reach each other through Kubernetes Services (`backend:8000`, `postgres:5432`), never through Pod IPs.

## Repository layout

```
.
├── backend/        # FastAPI app (main.py, requirements.txt, Dockerfile)
├── simulator/      # Buoy simulator (simulator.py, requirements.txt, Dockerfile)
├── frontend/       # Vue dashboard (App.vue)
├── k8s/            # Kubernetes manifests (namespace, postgres, backend, simulator)
└── docker-compose.yml   # Used only to build and tag both images
```

## Prerequisites

- Docker
- [Minikube](https://minikube.sigs.k8s.io/) and `kubectl`
- Node.js 18+ (for the dashboard)
- A Docker Hub account, or use `minikube image load` (see below)

## Run it

### 1. Start the cluster

```bash
minikube start --driver=docker
```

### 2. Build and push the images

```bash
docker compose build
docker compose push
```

This produces `mayess03/houle-backend:0.1.2` and `mayess03/houle-simulator:0.1.2`. Replace `mayess03` with your own Docker Hub username in `docker-compose.yml` and in the manifests if you use your own registry.

No registry? Load the images straight into Minikube instead of pushing:

```bash
minikube image load mayess03/houle-backend:0.1.2
minikube image load mayess03/houle-simulator:0.1.2
```

### 3. Deploy

Apply the manifests in this order (the namespace must exist first, and the backend needs the database):

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/simulator.yaml
```

Wait until everything is running:

```bash
kubectl get pods -n houle -w
```

You should see `postgres`, `backend` and `simulator` all `Running` (the backend is `1/1 Ready` once `/readyz` confirms the database connection).

### 4. Expose the backend locally

```bash
kubectl port-forward -n houle service/backend 8000:8000
```

Leave this running. The API is now available at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`.

### 5. Start the dashboard

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the URL printed by the dev server. The dashboard calls `/api/stats`, `/api/buoys` and `/api/alerts`, which the dev server proxies to `http://localhost:8000`, so the port-forward from step 4 must be active. If it is not, the dashboard shows "Backend inaccessible".

## Quick checks

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
curl http://localhost:8000/buoys
curl http://localhost:8000/alerts
curl http://localhost:8000/stats
curl "http://localhost:8000/buoys/buoy-001/history?limit=10"
kubectl logs -n houle deploy/simulator --tail=20
```

## API

| Endpoint                           | Description                                              |
| ---------------------------------- | -------------------------------------------------------- |
| `POST /measurements`               | Ingest one measurement (validated, deduplicated)         |
| `GET /buoys`                       | Latest state of every buoy (status, last seen, alerts)   |
| `GET /buoys/{buoy_id}/history`     | Measurement history, newest first (`limit` 1 to 1000)    |
| `GET /alerts`                      | Active alerts: silent, low battery, high waves           |
| `GET /stats`                       | Fleet counters                                           |
| `GET /healthz`                     | Liveness probe                                           |
| `GET /readyz`                      | Readiness probe (checks the database connection)         |


## Configuration

Backend environment variables (set in `k8s/backend.yaml`):

| Variable               | Default | Meaning                                  |
| ---------------------- | ------- | ---------------------------------------- |
| `DATABASE_URL`         | (required) | SQLAlchemy URL of PostgreSQL          |
| `LOW_BATTERY_THRESHOLD` | `20`   | Battery percentage below which an alert is raised |
| `HIGH_WAVE_THRESHOLD`  | `4.0`   | Wave height in meters above which an alert is raised |
| `BUOY_SILENCE_SECONDS` | `30`    | Seconds without data before a buoy is `silent` |

Simulator: `API_URL` (default `http://backend:8000`) and `INTERVAL_SECONDS` (default `5`).

In the simulator, `buoy-003` starts at 11% battery so the low battery alert is visible right away.

## Cleanup

```bash
kubectl delete namespace houle   # removes every resource, including the database volume
minikube stop
```

## Known limitations and next steps

Not implemented in this version:

- **Kubernetes operator and CRDs**: buoys are simulated by one Deployment running three simulated buoys, not one Pod per `Buoy` custom resource.
- **Weather systems**: wave height follows a sine wave plus noise, not moving weather systems affecting neighbouring buoys.
- **Forecasting**: no forecast endpoint yet. A rolling average over recent measurements is the planned first step.
- **Monitoring**: no Prometheus or Grafana. Fleet indicators (silent buoys, low batteries) are only available through `/stats` and `/alerts`.
- **Local buffering on the buoy**: measurements missed during an outage are not replayed after reconnection.
