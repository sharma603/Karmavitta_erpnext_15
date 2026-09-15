# API

All endpoints except `/health` require header:

```http
X-API-Key: <FACE_SERVICE_API_KEY>
```

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/diagnostics` | Model / thresholds (no embeddings) |
| POST | `/face/quality` | Quality only |
| POST | `/face/embedding` | Generate ArcFace embedding |
| POST | `/face/register` | Embed + duplicate check vs templates_json |
| POST | `/face/verify` | Embed + 1:N identify |
| POST | `/face/match-embedding` | 1:N from precomputed ArcFace vector |

## verify multipart

- `image`: file
- `templates_json`: JSON list of `{employee, embedding, model_name, model_version, embedding_dimension, company, enabled}`
- `company`: optional tenant filter

## Success

```json
{
  "success": true,
  "matched": true,
  "employee": "HR-EMP-00002",
  "score": 0.52,
  "margin": 0.18,
  "code": "OK"
}
```

## Failure codes

`NO_FACE`, `MULTIPLE_FACES`, `FACE_TOO_SMALL`, `LOW_QUALITY`, `INVALID_IMAGE`, `NO_MATCH`, `LOW_CONFIDENCE`, `DUPLICATE_FACE`, `UNAUTHORIZED`, `RATE_LIMITED`, `MODEL_ERROR`
