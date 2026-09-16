# Karmavitta — Face Attendance for ERPNext v15

Mobile face + QR attendance system for ERPNext. Employees mark attendance from an
Android app (face recognition or QID scan); the server verifies identity, applies
GPS/geofence and timing rules, and syncs to HRMS (`Employee Checkin` / `Attendance`).

## Features

- **Face Attendance Settings** — single page for mobile API key, rules, geofence,
  biometric thresholds, HRMS sync, kiosk mode, face-service connection
- **Face Biometric** — one face embedding per employee, server-side duplicate blocking
- **ArcFace Face Service** — InsightFace/ONNX FastAPI service under `face_service/`
  (recommended backend; auto-starts with `bench start`)
- **Face Attendance Log** — every IN/OUT with GPS, device info, match score
- **Face Attendance Location** — allowed office sites with GPS + radius
- **Face Registration Audit** — registration / duplicate / update trail
- **Mobile APIs** — config, face register/status, check-in, offline sync, kiosk list

## Requirements

| Item | Version / Notes |
|------|-----------------|
| Frappe / ERPNext | v15 |
| HRMS | Optional — needed only for `Employee Checkin` / `Attendance` sync |
| Python (bench env) | 3.11 / 3.12 (whatever your bench uses) |
| Python (face service) | 3.10+ in its own `face_service/.venv` (auto-created) |
| Mobile app | Android (React Native app in separate repo) |
| Camera device | Any Android phone/tablet for kiosk or personal use |

---

## 1. Install the app

```bash
cd ~/frappe-bench
bench get-app https://github.com/sharma603/Karmavitta_erpnext_15.git
bench --site YOUR-SITE install-app karmavitta
bench --site YOUR-SITE migrate
bench build --app karmavitta
bench --site YOUR-SITE clear-cache
```

What the installer does automatically (`karmavitta/install.py`):

- Creates **Face Attendance Settings** (enabled, kiosk mode ON, HR sync ON)
- Creates the **Face Attendance** workspace with links (Settings, Face Biometric, Logs)
- Adds `face_service` to the bench **Procfile** (if missing) so it auto-runs
- On migrate: raises geofence default to 500 m if it was below 300 m

Requires the `erpnext` app (`required_apps = ["erpnext"]`).

---

## 2. Face service setup (ArcFace backend)

The face service is a separate FastAPI process (own venv, so heavy ML packages never
touch your bench env). It lives inside this app at `face_service/`.

### 2.1 Auto-run (default)

`bench start` launches it via the Procfile entry (added automatically on install):

```text
face_service: bash apps/karmavitta/face_service/scripts/bench_start.sh
```

On **first run** the script automatically:

1. Creates `face_service/.venv` and installs `requirements.txt` (takes several minutes)
2. Copies `.env.example` → `.env` if `.env` is missing
3. Starts Uvicorn on `127.0.0.1:8090`

Check it: `curl http://127.0.0.1:8090/health` → `{"status":"ok"}` (or similar).

### 2.2 Configure `.env` (REQUIRED on every new server)

`.env` is **gitignored and never pushed** — you must set it per server:

```bash
cd apps/karmavitta/face_service
cp .env.example .env
nano .env
```

| Variable | Default | What to do |
|----------|---------|------------|
| `FACE_SERVICE_API_KEY` | `change-me-face-service-key` | **Must change** — long random secret; paste the same value into Desk settings |
| `FACE_SERVICE_PORT` | `8090` | Change only if port clashes |
| `MODEL_NAME` | `ArcFace` | Leave as is |
| `INSIGHTFACE_MODEL_PACK` | `buffalo_l` | Leave as is (downloads on first run) |
| `EMBEDDING_DIMENSION` | `512` | Leave as is |
| `FACE_MATCH_THRESHOLD` | `0.40` | Accept check-in when similarity ≥ this (ArcFace cosine) |
| `FACE_DUPLICATE_THRESHOLD` | `0.45` | Block new registration when similarity vs anyone ≥ this |
| `FACE_MATCH_MARGIN` | `0.05` | Safety margin |
| `CTX_ID` | `-1` | `-1` = CPU; `0` = GPU 0 (needs `requirements-gpu.txt` + CUDA) |
| `ONNX_PROVIDER` | `CPUExecutionProvider` | `CUDAExecutionProvider` for GPU |
| `MAX_IMAGE_BYTES` | `5242880` | Reject images larger than 5 MB |
| `RATE_LIMIT_PER_MINUTE` | `120` | Per-IP request cap |

Restart after editing: stop `bench start` (Ctrl+C) and start again.

### 2.3 Manual run (without bench)

```bash
cd apps/karmavitta/face_service
bash scripts/run.sh            # dev mode with auto-reload
# production-style (same as bench):
bash scripts/bench_start.sh
```

### 2.4 GPU (optional)

```bash
pip install -r requirements-gpu.txt
```

```env
CTX_ID=0
ONNX_PROVIDER=CUDAExecutionProvider
```

### 2.5 Backend

Only **ArcFace** (`arcface_service`) is supported. `Face Service URL` and `API Key` must be configured; on-device embeddings are not supported.

More docs: `face_service/README.md` + `face_service/docs/` (INSTALL, API, SECURITY,
MODEL, DEPLOYMENT).

---

## 3. Desk configuration (Face Attendance Settings)

Open **Face Attendance → Face Attendance Settings**. Every group explained:

### General
| Field | Meaning |
|-------|---------|
| Enable Face Attendance | Master switch |
| Default Company | Used for kiosk check-ins and reports |
| Mobile API Key | Auto-generated, read-only. **Copy this into the mobile app** |

### Mobile App Rules
| Field | Default | Meaning |
|-------|---------|---------|
| Minimum Face Match Score | `0.40` | Reject ArcFace matches below this |
| Check-in Photo Required | off | If on, every check-in uploads a photo (slower) |
| Allow Offline Sync | on | Phones queue logs offline and upload later |
| Max Check-ins Per Day | `20` | Abuse guard |
| Require GPS Location | on | Reject check-ins with no coordinates |
| Default Geofence Radius | `500` m | Used when a location has no own radius |
| Strict Geofence | off | **Recommended off** — GPS is recorded but a wrong pin won't block a known site. On = phone must be inside radius |
| Log Type Mode | `Auto` | Auto = 1st log IN, 2nd OUT…; or force IN / OUT / Ask User |
| Min Minutes Before Check-out | `10` | `0` = allow immediate check-out |

### Allowed Locations (Geofence)
Add one row per office/site: name + latitude + longitude (+ optional radius).
Used by GPS validation and the mobile location picker.

### Integration (HRMS)
| Field | Meaning |
|-------|---------|
| Sync to Employee Checkin | Creates HRMS `Employee Checkin` per log (needs HRMS app) |
| Sync to HR Attendance | Creates/updates daily `Attendance` = Present from IN/OUT |
| Kiosk Mode Enabled | Shared tablet can check anyone in with API key only (no login) |

### Face Biometric
| Field | Default | Meaning |
|-------|---------|---------|
| Biometric Model Name/Version/Dimension | ArcFace / insightface-buffalo_l-1.0 / 512 | ArcFace InsightFace model |
| Similarity Metric | cosine | L2-normalized cosine similarity |
| Face Duplicate Threshold | `0.45` | Block registration if ArcFace similarity vs ANY other employee ≥ this |
| Face Match Threshold | `0.40` | Accept verification if similarity ≥ this |
| Same-Person Update Threshold | `0.50` | Employee can update own face without admin if new capture vs own template ≥ this |
| Liveness Provider | `none` | `none` / `quality_multipose` / `external` (blink alone is not strong anti-spoof) |

### ArcFace Face Service
| Field | Meaning |
|-------|---------|
| Recognition Backend | `arcface_service` (only option) |
| Face Service URL | e.g. `http://127.0.0.1:8090` |
| Face Service API Key | Same secret as `face_service/.env` → `FACE_SERVICE_API_KEY` |
| Face Service Timeout | `30` seconds |

---

## 4. Employee setup

1. **Link login to employee** — open each **Employee** and set `user_id` to their
   ERPNext User. Without this, mobile login can't map to an employee.
2. **Register face** — admin logs into the mobile app → Employees → pick employee →
   **Register Face** → person looks straight at camera → capture. Server checks
   duplicates and creates the **Face Biometric** record.
3. Verify in Desk → **Face Biometric** list. Re-registration by the same employee
   needs approval unless similarity passes the same-person threshold
   (`request/approve_face_reregistration`).

---

## 5. Mobile app setup

1. Install the Android app (separate repo/APK).
2. First screen → **Configure / ERPNext Connection**:
   - **Site URL** — e.g. `http://192.168.1.10:8000` (phone must reach this over Wi-Fi/LAN)
   - **Mobile API Key** — paste from Face Attendance Settings
3. **Test & Save Connection**, then login with ERPNext username + password.
4. Daily use: pick location → **Face Attendance** (auto face capture + verify) or
   **Mark Attendance / QID scan** → result screen shows IN/OUT + time.
5. Works offline if allowed — logs upload later via `sync_offline_logs`.

---

## 6. How attendance works (request flow)

```text
Phone captures face image + GPS + location + device info
  → POST karmavitta.api.mobile.checkin (API key + session, or kiosk API key) with face_image
      → ERPNext validates: key, session, location, GPS/geofence, timing rules
      → ERPNext → face_service :8090 verify (ArcFace compare vs saved templates)
      → score ≥ threshold? accept : reject
      → creates Face Attendance Log (IN/OUT per Log Type Mode)
      → syncs Employee Checkin + HR Attendance (if enabled + HRMS installed)
  → phone shows AttendanceResult (IN/OUT, employee, time)
```

Registration flow: capture face_image → POST to face_service → duplicate scan vs all ArcFace templates
(`FACE_ALREADY_REGISTERED` if match vs someone else) → save Face Biometric +
Registration Audit entry.

---

## 7. Mobile API reference

Base URL: `https://YOUR-SITE/api/method/`

| Purpose | Endpoint | Auth |
|---------|----------|------|
| GET config | `karmavitta.api.mobile.get_config` | API Key |
| My profile | `karmavitta.api.mobile.get_my_profile` | User login |
| Face status (mobile) | `karmavitta.api.mobile.get_face_status` | User login |
| Register face (mobile) | `karmavitta.api.mobile.register_face` | User login |
| Active face profiles | `karmavitta.api.mobile.list_active_face_profiles` | API Key |
| Check-in | `karmavitta.api.mobile.checkin` | API Key + User/Kiosk |
| Today logs | `karmavitta.api.mobile.get_today_logs` | User login |
| Offline sync | `karmavitta.api.mobile.sync_offline_logs` | API Key |
| Kiosk employees | `karmavitta.api.mobile.list_employees_for_kiosk` | API Key |
| Register face (core) | `karmavitta.api.biometric.register_face` | User login |
| Verify face (core) | `karmavitta.api.biometric.verify_face` | API Key |
| Registration status | `karmavitta.api.biometric.get_face_registration_status` | User login |
| Biometric config | `karmavitta.api.biometric.get_biometric_config` | API Key |
| Active templates | `karmavitta.api.biometric.list_active_face_templates` | API Key |

### Example: get config

```bash
curl "https://YOUR-SITE/api/method/karmavitta.api.mobile.get_config?api_key=YOUR_MOBILE_KEY"
```

### Example: check-in

```bash
curl -X POST "https://YOUR-SITE/api/method/karmavitta.api.mobile.checkin" \
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

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `bench start` shows no `face_service` | Re-run `bench --site SITE migrate` (auto-adds Procfile entry), then restart bench |
| Face service `401 / key mismatch` | `.env` `FACE_SERVICE_API_KEY` ≠ Desk → Face Service API Key. Make them identical, restart service |
| `Cannot connect to 127.0.0.1:8090` | Service not running — check `bench start` log tab; first run installs venv (slow) |
| Mobile "Cannot reach ERPNext" | Phone and server must share network; Site URL must be LAN IP (`http://192.168.x.x:8000`), not `localhost` |
| "Session expired" in app | Login again; check Site URL didn't change |
| Duplicate-face false block | Raise Desk → Face Duplicate Threshold toward `0.45`; ArcFace `.env` duplicate threshold `0.45` is authoritative |
| Wrong-person match | Raise Face Match Threshold (`0.40`–`0.50`); never go below `0.35` |
| No Employee Checkin created | Install HRMS app + enable both sync flags |
| `.env` lost after fresh clone | Expected — `.env` is gitignored. Copy from `.env.example` and set the key |

## License

MIT. Note: InsightFace library is typically MIT, but pretrained packs (e.g.
`buffalo_l`) may be non-commercial — verify before commercial deployment.
