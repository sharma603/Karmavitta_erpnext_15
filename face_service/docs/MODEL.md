# MODEL

| Item | Value |
|------|--------|
| Engine | InsightFace `FaceAnalysis` |
| Recognition | ArcFace embedding |
| Default pack | `buffalo_l` (configurable) |
| Runtime | ONNX Runtime |
| Dimension | 512 (pack-dependent — validate) |
| Normalization | L2 |
| Similarity | Cosine |

## Compatibility

Never compare FaceNet embeddings with ArcFace embeddings.

Each Face Biometric row stores `model_name`, `model_version`, `embedding_dimension`.

## Commercial licensing

Verify InsightFace model pack license before commercial distribution. Replace the pack if required.
