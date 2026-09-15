#!/usr/bin/env bash
# Safe diagnostics — never prints embeddings.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python - <<'PY'
from app.config import settings
print("model_name", settings.model_name)
print("model_version", settings.model_version)
print("insightface_model_pack", settings.insightface_model_pack)
print("embedding_dimension", settings.embedding_dimension)
print("face_match_threshold", settings.face_match_threshold)
print("face_duplicate_threshold", settings.face_duplicate_threshold)
print("face_match_margin", settings.face_match_margin)
print("onnx_provider", settings.onnx_provider)
try:
    import onnxruntime as ort
    print("onnx_available_providers", ort.get_available_providers())
except Exception as e:
    print("onnxruntime_error", e)
try:
    from app.models.face_engine import get_face_engine
    eng = get_face_engine()
    eng.initialize_model()
    print(eng.diagnostics())
except Exception as e:
    print("engine_init_error", type(e).__name__, str(e)[:200])
PY
