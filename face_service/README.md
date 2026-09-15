# Karmavritta Face Recognition Service (inside Karmavitta app)

This FastAPI ArcFace / InsightFace service lives **inside the ERPNext Karmavitta app**:

```text
frappe-bench-v15/apps/karmavitta/face_service/
```

It is still a separate Python process (own venv) so heavy ML packages do **not** pollute the Frappe bench environment. ERPNext calls it over HTTP.

## Auto-start with bench

`bench start` launches this service via the bench `Procfile` process named `face_service`.
(The karmavitta app auto-adds that Procfile line on `install-app` / `migrate`.)

First start automatically:

1. Creates `face_service/.venv` and installs `requirements.txt` (one-time, several minutes)
2. Copies `.env.example` → `.env` if `.env` is missing
3. Starts Uvicorn on `127.0.0.1:8090`

Health check: `curl http://127.0.0.1:8090/health`

Then in Desk → **Face Attendance Settings**:

- Recognition Backend = `arcface_service`
- Face Service URL = `http://127.0.0.1:8090`
- Face Service API Key = value from `face_service/.env` (`FACE_SERVICE_API_KEY`)

## `.env` configuration (per server — REQUIRED)

`.env` is **gitignored and never pushed**. On every new server:

```bash
cd apps/karmavitta/face_service
cp .env.example .env
nano .env     # set FACE_SERVICE_API_KEY to a long random secret
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `FACE_SERVICE_API_KEY` | `change-me-face-service-key` | **Must change.** Must exactly match Desk → Face Service API Key |
| `FACE_SERVICE_PORT` | `8090` | Change only on port clash |
| `MODEL_NAME` / `MODEL_VERSION` | `ArcFace` / `insightface-buffalo_l-1.0` | Keep |
| `INSIGHTFACE_MODEL_PACK` | `buffalo_l` | Auto-downloaded on first run |
| `EMBEDDING_DIMENSION` | `512` | Keep |
| `FACE_MATCH_THRESHOLD` | `0.40` | Accept verification at/above this (ArcFace cosine scale) |
| `FACE_DUPLICATE_THRESHOLD` | `0.45` | Block registration at/above this vs anyone else |
| `FACE_MATCH_MARGIN` | `0.05` | Safety margin |
| `CTX_ID` | `-1` | `-1` = CPU, `0` = GPU 0 (needs `requirements-gpu.txt` + CUDA) |
| `ONNX_PROVIDER` | `CPUExecutionProvider` | `CUDAExecutionProvider` for GPU |
| `MAX_IMAGE_BYTES` | `5242880` | Reject images over 5 MB |
| `RATE_LIMIT_PER_MINUTE` | `120` | Per-IP cap |

Restart the service after editing `.env` (restart `bench start`).

## Manual start

```bash
cd apps/karmavitta/face_service
bash scripts/bench_start.sh          # same as bench start (no reload)
# or for local reload during development:
bash scripts/run.sh
```

Then re-register employee faces (ArcFace). FaceNet templates are not compatible.

## Docs

- [INSTALL.md](docs/INSTALL.md)
- [API.md](docs/API.md)
- [SECURITY.md](docs/SECURITY.md)
- [MODEL.md](docs/MODEL.md)
- [DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [MIGRATION.md](docs/MIGRATION.md)

## License warning (commercial)

InsightFace library is typically MIT. Pretrained packs (e.g. `buffalo_l`) may be non-commercial — verify before shipping.
