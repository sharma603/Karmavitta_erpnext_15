# DEPLOYMENT

Service path:

```text
apps/karmavitta/face_service/
```

1. Create venv + install requirements inside that folder
2. Run on `127.0.0.1:8090`
3. In ERPNext → Face Attendance Settings:
   - Recognition Backend = `arcface_service`
   - Face Service URL = `http://127.0.0.1:8090`
   - Face Service API Key = same as `.env`
4. Re-register all employee faces (ArcFace)
5. Reload mobile app

Systemd example:

```ini
[Service]
WorkingDirectory=/home/er-bijay-sharma/erpnext-development/frappe-bench-v15/apps/karmavitta/face_service
ExecStart=/home/er-bijay-sharma/erpnext-development/frappe-bench-v15/apps/karmavitta/face_service/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090
Restart=always
```
