# MedScan AI - Technical Architecture

## 1. Components

```
Browser (HTML/CSS/vanilla JS)
   |  HTTP/JSON + multipart          (same origin: FastAPI also serves /frontend)
FastAPI app  (backend/main.py)
   |-- api/upload.py, analysis.py, reports.py   request validation, HTTP errors
   |-- services/image_processing.py             validate + sanitise + store image
   |-- services/inference.py                    orchestration, persistence, audit log
   |-- services/report_generator.py             PDF (ReportLab)
   |-- models/ai_models/registry.py             category -> model; honest status
   |       |-- chest_xray.py                    TorchXRayVision DenseNet-121 + Grad-CAM
   |       `-- UnavailableModel                 bone_fracture, brain_ct (never returns results)
   `-- models/database_models.py (SQLAlchemy)  ->  PostgreSQL
Filesystem (storage/): uploads/ (sanitised PNG), outputs/ (Grad-CAM), reports/ (PDF), model_cache/ (weights)
```

## 2. Request flow

1. `GET /api/categories` - the upload page renders tasks; only `operational` ones are selectable.
2. `POST /api/upload` (multipart: `category`, `file`) - size cap -> magic-byte sniff (PNG/JPEG) -> full decode -> pixel/size limits -> colour-image rejection -> re-encode as grayscale PNG under a server-generated UUID. A `medical_images` row stores UUID, SHA-256, dimensions, format. No filename, no metadata.
3. `POST /api/analyze` `{image_id}` - creates `analysis_results` (pending) + history events, loads the model (lazy, cached, guarded by a lock), preprocesses (grayscale, scale to [-1024,1024], centre-crop, resize 224), runs DenseNet-121, computes Grad-CAM for the label with the highest score/threshold ratio, writes findings JSON and the overlay. Any failure -> status `failed` with the message and an HTTP error; **no placeholder result is ever stored**.
4. `GET /api/analysis/{id}`, `/heatmap`, `GET /api/analyses`, `GET /api/stats` - results, listing, dashboard data.
5. `GET /api/report/{id}` - builds the PDF on demand for completed analyses and records a `reports` row.

## 3. Database (PostgreSQL via SQLAlchemy)

`medical_images 1--* analysis_results 1--* reports`, `analysis_results 1--* analysis_history`. All foreign keys `ON DELETE CASCADE`. Findings/model info are JSON columns. See `database/schema.sql`. There is no users table because authentication is not implemented.

## 4. AI module contract

Each task implements `ImagingModel.analyze(path) -> InferenceOutput` and exposes a `ModelCard` (source, licence, reference, limitations, status, blocker). To add a task: implement the class, register it in `registry.py`, set `status="operational"` only after the weights are verified and evaluated. The API distinguishes: real inference (`result_type: "model_inference"`), and not-integrated tasks (HTTP 501, no result row). There is no demo/random mode.

### Chest X-ray model facts
- Library `torchxrayvision` (Apache-2.0 per package metadata); weights `densenet121-res224-all` downloaded from the project's GitHub release on first use.
- 18 multi-label outputs; no "normal" class. Per-label operating thresholds ship with the weights; a label is "flagged" when `score >= threshold`.
- Scores are raw sigmoid outputs and are **not calibrated probabilities**.
- Grad-CAM (own implementation) is taken on the last DenseNet feature map with respect to the label logit.

## 5. Security and privacy measures
Content-based file validation, size caps, decompression-bomb limit, re-encoding (strips EXIF/appended payloads), server-generated filenames (no path traversal), parameterised ORM queries, strict request schemas, restricted CORS, `nosniff`/`X-Frame-Options` headers, secrets only via environment variables, no external calls with image data (only the one-time weight download). Not implemented: authentication/authorisation, rate limiting, HTTPS termination, encryption at rest, retention policy - all required before any real-world deployment.
