# Karmavritta Face Recognition Service (inside Karmavitta app)

This FastAPI ArcFace / InsightFace service lives **inside the ERPNext Karmavitta app**:

```text
frappe-bench-v15/apps/karmavitta/face_service/
```

It is still a separate Python process (own venv) so heavy ML packages do **not** pollute the Frappe bench environment. ERPNext calls it over HTTP.

## Auto-start with bench

`bench start` launches this service via the bench `Procfile` process named `face_service`.

First start may create `face_service/.venv` and install packages (one-time, can take several minutes).

Then in Desk → **Face Attendance Settings**:

- Recognition Backend = `arcface_service`
- Face Service URL = `http://127.0.0.1:8090`
- Face Service API Key = value from `face_service/.env` (`FACE_SERVICE_API_KEY`)

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
