# ArcFace-only

ArcFace is the only supported backend. No legacy fallback exists.

## Steps (fresh setup)

1. Start service from `apps/karmavitta/face_service/` (`bench start` does this automatically)
2. Configure Face Attendance Settings → `face_service_url` + `face_service_api_key` (Recognition Backend = `arcface_service`)
3. Re-register every employee via mobile (sends `face_image` to ArcFace service)
4. Confirm diagnostics: `active_arcface_templates` > 0
5. Test A/B attendance isolation

Legacy templates (non-ArcFace) are **not** compatible and must be replaced by re-registration.

## Notes

- Do not attempt to convert legacy vectors to ArcFace — vector spaces are incompatible.
- If migrating from older installs, run `bench --site <site> migrate` to enforce `arcface_service`.
