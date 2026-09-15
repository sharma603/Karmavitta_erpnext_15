# MIGRATION (FaceNet → ArcFace)

FaceNet-512 and ArcFace are **incompatible**. Do not convert vectors.

## Steps

1. Start service from `apps/karmavitta/face_service/`
2. Keep `recognition_backend=facenet_local` until `/health` is OK
3. Switch Face Attendance Settings → `arcface_service` + URL + API key
4. Existing FaceNet templates are **ignored** by ArcFace matching
5. Re-register every employee via mobile (sends `face_image`)
6. Confirm diagnostics: `active_arcface_templates` > 0
7. Test A/B attendance isolation

## Rollback

Set Recognition Backend back to `facenet_local`.
