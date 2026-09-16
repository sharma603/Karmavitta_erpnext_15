# Karmavritta ↔ ArcFace Face Service

Face ML service code lives **inside this app**:

```text
apps/karmavitta/face_service/
```

## ERPNext settings

Face Attendance Settings:

- `recognition_backend`: `arcface_service` (only)
- `face_service_url`
- `face_service_api_key`
- `face_service_timeout_seconds`

## APIs

- `karmavitta.api.biometric.register_face` — requires `face_image` (ArcFace)
- `karmavitta.api.mobile.checkin` — accepts `face_image`; ignores client employee
- `karmavitta.api.diagnostics.face_recognition_diagnostics`

## Client

`karmavitta/services/face_service_client.py` — HTTP multipart to the local FastAPI service.
