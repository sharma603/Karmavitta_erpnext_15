# Implementation Report — ArcFace Backend Face Recognition

## 1. Existing architecture found

- Mobile: React Native + camera-kit + on-device FaceNet-512 TFLite → embedding
- ERPNext Karmavritta: stores Face Biometric, cosine 1:N, Face Attendance Log → Employee Checkin
- No separate ML service previously; no Device Registration DocType

## 2. Root cause(s) of wrong-employee bug

1. Client could influence identity (later fixed to ignore client employee)
2. FaceNet match threshold too low historically (~0.55)
3. FaceNet templates for different people can be relatively close (~0.67 observed)
4. Authoritative recognition needed on backend with stronger ArcFace + image pipeline

## 3. Files changed

### Face service (inside karmavitta app)
- `frappe-bench-v15/apps/karmavitta/face_service/**`

### Karmavitta
- `karmavitta/services/face_service_client.py` (new)
- `karmavitta/api/biometric.py` — `face_image` ArcFace register/verify
- `karmavitta/api/mobile.py` — ArcFace checkin path
- `karmavitta/api/diagnostics.py` (new)
- `karmavitta/face_attendance/utils.py` — recognition_backend in mobile config
- `face_attendance_settings.json` — ArcFace service fields
- `patches/v1_1/prepare_arcface_migration.py`
- `docs/face_service/README.md`

### Mobile app
- `src/services/faceApi.ts` — send `face_image` when ArcFace backend
- `src/services/karmavittaApi.ts` — face_image payloads + config types

## 4. New files created

Full FastAPI service tree under `karmavritta-face-service/` with docs + matching tests.

## 5. Database / DocType changes

Face Attendance Settings additions:
- `recognition_backend` (`facenet_local` | `arcface_service`)
- `face_service_url`
- `face_service_api_key` (Password)
- `face_service_timeout_seconds`

Face Biometric unchanged (already has model metadata fields).

## 6. ML model configuration

- InsightFace pack: `buffalo_l` (configurable)
- ArcFace 512-D, L2, cosine
- ONNX Runtime CPU (or GPU via requirements-gpu.txt)
- **Commercial license of model pack must be verified before shipping**

Default starting thresholds (calibrate!):
- match 0.40, duplicate 0.45, margin 0.05

## 7. API changes

Face service: `/health`, `/face/quality`, `/face/embedding`, `/face/register`, `/face/verify`, `/diagnostics`

ERPNext:
- register/checkin accept `face_image` when `recognition_backend=arcface_service`
- client employee never trusted
- company-scoped template population sent to service

## 8. Security changes

- Face service API key
- Size / MIME / rate limits
- No embedding/image logging
- Duplicate responses never name the other employee
- Password field for service key in Desk

## 9. Migration steps

1. Install & run face service
2. Keep `facenet_local` until healthy
3. Switch to `arcface_service` + URL + key
4. Re-register all employees (FaceNet templates ignored, not converted)
5. Reload mobile app

## 10. Tests performed

- `tests/test_matching.py`: A→A, B→B, unknown NO_MATCH, duplicate, FaceNet skipped, company scope
- ERPNext migrate + clear-cache

Full InsightFace inference tests require model download on the deployment host.

## 11. Remaining risks

- Model pack commercial license
- Thresholds need site calibration
- Device activation DocType not yet added (API key + kiosk still primary)
- Concurrent large galleries may need FAISS later
- First InsightFace model download needs network

## 12. Deployment commands

```bash
# Face service (inside karmavitta app)
cd /home/er-bijay-sharma/erpnext-development/frappe-bench-v15/apps/karmavitta/face_service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set FACE_SERVICE_API_KEY
bash scripts/run.sh

# ERPNext
cd /home/er-bijay-sharma/erpnext-development/frappe-bench-v15
bench --site erp15.localhost migrate
bench --site erp15.localhost clear-cache
# Desk → Face Attendance Settings → Recognition Backend = arcface_service
```
