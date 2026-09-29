# DEPLOYMENT

Service path:

```text
apps/karmavitta/face_service/
```

1. Create venv + install requirements inside that folder
2. Run on `127.0.0.1:8090`
3. On self-hosted ERPNext, install/migrate synchronizes the local URL and `.env` key.
   In ERPNext → Face Attendance Settings, click **Check ArcFace** to confirm it is ready.
   For a production bench using Supervisor, regenerate its config after installing the
   app (`bench setup supervisor`), then reload processes (`sudo supervisorctl reread`
   and `sudo supervisorctl update`).
4. On Frappe Cloud, choose **Built-in (same Frappe app)** to use in-process ArcFace.
   The app dependencies are installed from the root `pyproject.toml`; click
   **Check ArcFace** in Face Attendance Settings to load the model and verify readiness.
5. Optionally set an external service URL and API key to use the separate FastAPI mode.
6. Re-register all employee faces (ArcFace)
7. Reload mobile app

Systemd example:

```ini
[Service]
WorkingDirectory=/home/er-bijay-sharma/erpnext-development/frappe-bench-v15/apps/karmavitta/face_service
Environment=PYTHONPATH=/home/er-bijay-sharma/erpnext-development/frappe-bench-v15/apps/karmavitta
ExecStart=/home/er-bijay-sharma/erpnext-development/frappe-bench-v15/apps/karmavitta/face_service/.venv/bin/uvicorn face_service.app.main:app --host 127.0.0.1 --port 8090
Restart=always
```
