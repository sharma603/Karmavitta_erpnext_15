# Face Biometric — Model Selection

Documented before implementation (required).

## Selected model

| Item | Value |
|------|--------|
| **Model name** | FaceNet |
| **Model version** | `1.0` (`facenet_512.tflite`) |
| **Format** | TensorFlow Lite |
| **Input image size** | **160 × 160** RGB |
| **Preprocessing** | Resize face crop → RGB float32 → scale to **[-1, 1]** (`(pixel - 127.5) / 128.0`) |
| **Embedding dimension** | **512** |
| **Template normalization** | **L2 normalize** embedding so \(\|v\|_2 = 1\) |
| **Similarity method** | **Cosine similarity** (equivalent to dot product after L2 norm) |
| **Duplicate / match decision** | Cosine similarity **≥ configurable threshold** |
| **License** | Apache-2.0 compatible FaceNet TFLite packaging (on-device FaceNet assets) |
| **Android compatibility** | API 24+, TFLite Interpreter (CPU; GPU delegate optional later) |
| **Expected mobile performance** | ~100–350 ms per embedding on mid-range Android (CPU) |

## Why this model (not pose/bounds)

The previous mobile path stored camera **pose/bounds** vectors (~10 floats). Those are **not** biometric identity and cannot enforce “one face → one employee.”

FaceNet-512 produces a real 512-D identity embedding suitable for:

1. Server-side duplicate detection against **all** active templates  
2. On-device / server verification for attendance  

MobileFaceNet (112×112 → 192-D) remains a supported upgrade path via settings (`model_name` / `model_version` / `embedding_dimension`) without changing the DocType schema.

## Threshold calibration (do not hard-code forever)

Default starting values (must be tuned on your cameras and workforce):

| Setting | Default | Meaning |
|---------|---------|---------|
| `face_duplicate_threshold` | **0.72** | Reject registration if cosine ≥ this vs any other employee. Values ≤0.55 falsely block different people. |
| `face_match_threshold` | **0.58** | Accept attendance match if cosine ≥ this |
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
