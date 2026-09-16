# Face Biometric — Model Selection

Documented before implementation (required).

## Selected model

| Item | Value |
|------|--------|
| **Model name** | ArcFace |
| **Model version** | `insightface-buffalo_l-1.0` |
| **Format** | ONNX (InsightFace buffalo_l) |
| **Input image size** | **112 × 112** (aligned face crop) |
| **Preprocessing** | InsightFace face detection + alignment → RGB float32 → normalized |
| **Embedding dimension** | **512** |
| **Template normalization** | **L2 normalize** embedding so \(\|v\|_2 = 1\) |
| **Similarity method** | **Cosine similarity** (equivalent to dot product after L2 norm) |
| **Duplicate / match decision** | Cosine similarity **≥ configurable threshold** (service thresholds) |
| **License** | InsightFace MIT, model pack may be non-commercial — verify before commercial deployment |
| **Service** | FastAPI `face_service` (InsightFace/ONNX Runtime), CPU or GPU |

## Why ArcFace

ArcFace (InsightFace) provides strong identity discrimination and is the **only** supported backend. Server-side verification and duplicate detection compare against **all** active ArcFace templates via the face service.

Legacy on-device embeddings are **not** supported.

## Threshold calibration (ArcFace)

Default values (service is authoritative):

| Setting | Default | Meaning |
|---------|---------|---------|
| `face_duplicate_threshold` | **0.45** | Reject registration if ArcFace cosine ≥ this vs any other employee |
| `face_match_threshold` | **0.40** | Accept attendance match if cosine ≥ this |
| `face_same_person_update_threshold` | **0.50** | Existing employee re-register without admin if cosine ≥ this vs own template |

Metric: **cosine similarity** in \([-1, 1]\) (after L2). Higher = more similar.

Calibrate by measuring:

- Same person, different lighting/pose → should stay **above** match threshold  
- Different people → should stay **below** duplicate threshold  
- Target low **FAR** (false accept) for registration uniqueness; balance **FRR** for attendance  

Store thresholds on **Face Attendance Settings** (Karmavritta settings). Never ship a magic `0.95` without testing.

## Privacy

- Embeddings are **never** logged or printed  
- Duplicate API responses **do not** name the matched employee  
- `biometric_template` is permlevel-restricted; employees cannot read raw templates  

## Liveness

Liveness is **modular** (`liveness_provider` setting). Default: `none` (quality + multi-pose only). Blink/head-turn alone are **not** treated as strong PAD.
