# INSTALL (inside karmavitta app)

```bash
cd frappe-bench-v15/apps/karmavitta/face_service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # OR requirements-gpu.txt
cp .env.example .env
```

Set a strong `FACE_SERVICE_API_KEY`.

```bash
bash scripts/run.sh
# or
uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Calibrate thresholds after collecting same-person / different-person scores:

```env
FACE_MATCH_THRESHOLD=0.40
FACE_DUPLICATE_THRESHOLD=0.45
FACE_MATCH_MARGIN=0.05
```
