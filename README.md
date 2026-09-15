# Karmavitta — Face Attendance for ERPNext

Mobile face attendance system for ERPNext v15.

## Features

- **Face Attendance Settings** — mobile API key, geofence, match thresholds, kiosk mode
- **Face Biometric** — FaceNet / ArcFace embedding per employee (one face → one employee)
- **ArcFace Face Service** — InsightFace + ONNX Runtime under `face_service/` (optional authoritative backend)
- **Face Registration Audit** — registration / duplicate / update audit trail
- **Face Attendance Log** — IN/OUT logs with GPS, device, match score
- **Mobile APIs** — config, register face, check-in, offline sync

## ArcFace backend (inside this app)

Starts automatically with **`bench start`** (Procfile process `face_service`).

Manual run:

```bash
cd apps/karmavitta/face_service
bash scripts/run.sh
# or for bench-style (no reload):
bash scripts/bench_start.sh
```

Then set Face Attendance Settings → Recognition Backend = `arcface_service`,  
URL = `http://127.0.0.1:8090`, API key = `face_service/.env` → `FACE_SERVICE_API_KEY`.

See `face_service/README.md` and `docs/face_service/README.md`.

## Install

```bash
bench get-app /path/to/karmavitta   # or git URL
bench --site SITE install-app karmavitta
bench --site SITE migrate
bench build --app karmavitta
bench --site SITE clear-cache
```

## Desk Setup

1. Open **Face Attendance → Face Attendance Settings**
2. Copy **Mobile API Key**
3. Add allowed office locations (or use Assets → Location)
4. Register faces from the mobile app (creates **Face Biometric**)

## Mobile App API

Base URL: `https://YOUR-SITE/api/method/`

| Method | Endpoint | Auth |
|--------|----------|------|
| GET config | `karmavitta.api.mobile.get_config` | API Key |
| Register face | `karmavitta.api.biometric.register_face` | User login |
| Face status | `karmavitta.api.biometric.get_face_registration_status` | User login |
| Active templates | `karmavitta.api.biometric.list_active_face_templates` | API Key |
| My profile | `karmavitta.api.mobile.get_my_profile` | User login |
| Face status (mobile) | `karmavitta.api.mobile.get_face_status` | User login |
| Check-in | `karmavitta.api.mobile.checkin` | API Key + User/Kiosk |
| Today logs | `karmavitta.api.mobile.get_today_logs` | User login |
| Offline sync | `karmavitta.api.mobile.sync_offline_logs` | API Key |
| Kiosk employees | `karmavitta.api.mobile.list_employees_for_kiosk` | API Key |

### Example: get config

```bash
curl "https://erp15.localhost:8000/api/method/karmavitta.api.mobile.get_config?api_key=YOUR_KEY"
```

### Example: check-in

```bash
curl -X POST "https://erp15.localhost:8000/api/method/karmavitta.api.mobile.checkin" \
  -H "Authorization: token API_KEY:API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "MOBILE_API_KEY",
    "face_match_score": 0.92,
    "latitude": 25.2854,
    "longitude": 51.5310,
    "device_id": "android-001",
    "device_name": "Reception Tablet"
  }'
```

## Mobile App Flow

1. App loads config using Mobile API Key
2. Employee / admin logs in with ERPNext credentials
3. Register face → creates **Face Biometric** (server blocks duplicate faces)
4. Daily: capture face on device → compare locally → send score + GPS to `checkin`
5. Server validates score, geofence, and saves **Face Attendance Log**

## Notes

- Identity = FaceNet embedding on device + **Face Biometric** on server
- Duplicate faces are rejected server-side (`FACE_ALREADY_REGISTERED`)
- Enable **Sync to Employee Checkin** and **Sync to HR Attendance** in Face Attendance Settings
- Link Employee to User (`user_id`) so mobile login maps to employee
- Legacy **Employee Face Profile** is still supported as a fallback only
