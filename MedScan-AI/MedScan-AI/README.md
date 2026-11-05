# MedScan AI - AI-Powered Medical Imaging Analysis Platform

A web platform (graduation project, Medical Informatics) where a user uploads a medical image and receives findings from a **pre-trained deep learning model**, a Grad-CAM explanation, and a PDF report.

> **Research and educational use only.** This AI-generated result is intended for research and educational assistance only. It is not a definitive medical diagnosis and must be reviewed by a qualified medical professional. MedScan AI is not a medical device.

## Status at a glance

| Imaging task | Status |
|---|---|
| Chest X-ray analysis | **Operational** - TorchXRayVision DenseNet-121 (`densenet121-res224-all`) |
| Bone fracture detection | **Not integrated** (no verified model) |
| Brain CT analysis | **Not integrated** (no verified model) |

Unsupported tasks cannot be selected, return HTTP 501 and never produce output. The system has no demo or random-prediction mode.

## Features
Landing page, upload with drag-and-drop/preview/validation/progress, analysis page, results page (scores vs. published thresholds, Grad-CAM toggle, model info, limitations, disclaimer), PDF report, dashboard (totals, history, categories, reports, model status), responsive layout, PostgreSQL storage with an audit history.

## Stack
Frontend: HTML5, CSS3, vanilla JS (no frameworks). Backend: Python, FastAPI, SQLAlchemy 2, PostgreSQL. AI: PyTorch, TorchXRayVision, OpenCV, own Grad-CAM. Reports: ReportLab. Tests: pytest, Playwright. MONAI was **not** used: it is not needed for 2D chest X-rays, and CT support is not implemented.

## Architecture
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Installation
Requires Python 3.12 and PostgreSQL 14+ (tested with 16).

```bash
python -m venv .venv && source .venv/bin/activate
# Installing PyTorch - the plain `pip install torch` pulls several GB of CUDA libraries.
# On a CPU-only machine prefer:  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
# (During development the CPU build came from conda-forge because download.pytorch.org was unreachable.)
pip install -r backend/requirements.txt
cp .env.example .env     # then edit: set your own database password
```

### Database
```bash
sudo -u postgres psql -c "CREATE USER medscan WITH PASSWORD '<your password>';" -c "CREATE DATABASE medscan OWNER medscan;"
# set DATABASE_URL in .env. Tables are created automatically on start-up;
# database/schema.sql is the equivalent reference schema:  psql -d medscan -f database/schema.sql
```
If `DATABASE_URL` is unset the app falls back to a local SQLite file (development only).

### AI model setup
Nothing to install manually. On the first analysis the library downloads the weights (`densenet121-res224-all`, a GitHub release asset) into `storage/model_cache/`; the machine therefore needs access to `github.com` once. To pre-fetch: `python -c "from backend.models.ai_models.registry import get_model; get_model('chest_xray')"`. Image data is never sent to any external service.

## Running
```bash
uvicorn backend.main:app --port 8000
```
Open http://localhost:8000 (the backend serves the frontend). Interactive API docs: http://localhost:8000/docs.
To serve the frontend separately, add `<script>window.MEDSCAN_API_BASE="http://localhost:8000"</script>` before `main.js` and list that origin in `ALLOWED_ORIGINS`.
Docker files (`Dockerfile`, `docker-compose.yml`) are included but **were not run** during development.

## API
| Method & path | Purpose |
|---|---|
| `GET /api/health` | DB status, per-task model status, limits |
| `GET /api/categories` | Imaging tasks, accepted formats, blockers |
| `POST /api/upload` | multipart `category`, `file` -> `image_id` (201) |
| `POST /api/analyze` | `{ "image_id" }` -> completed analysis, or an error |
| `GET /api/analysis/{id}` | Analysis result (findings, model card, warnings) |
| `GET /api/analysis/{id}/heatmap` | Grad-CAM PNG |
| `GET /api/analyses?limit&offset&category` | History |
| `GET /api/stats` | Dashboard statistics |
| `GET /api/report/{id}` | PDF report (completed analyses only) |
| `GET /api/images/{id}/file` | Sanitised stored image |

Error codes: 413 too large, 415 wrong type, 422 invalid image/input, 404 unknown id, 409 report for incomplete analysis, 501 task not integrated.

## Testing
```bash
python -m pytest                      # SQLite, ~20 s on CPU after the model is cached
TEST_POSTGRES_URL=postgresql+psycopg2://user:pw@localhost/medscan_test python -m pytest   # also runs on PostgreSQL
# (also create an empty database named <name>_orm for the ORM tests)
python -m tests.evaluate_model        # downloads a public dataset sample and writes docs/evaluation_results.json
```
Browser tests need Chromium for the installed Playwright version (`playwright install chromium`) and are skipped otherwise.

**Last recorded run (development sandbox, PostgreSQL 16): 52 passed.** Covered: endpoints, upload/validation/security cases, database relationships, real-model inference (including "outputs depend on the image"), PDF content, error handling, and an end-to-end browser run.

### Model evaluation (actual results)
Data: `ieee8023/covid-chestxray-dataset`, frontal PA / AP-erect X-rays, positive = pneumonia findings, negative = "No Finding". Sample **n = 40** (30 positive, 10 negative); the task and decision rule were fixed before running. The dataset is not in the weights' documented training sets (based on documentation; not independently verified). Labels are the model's published thresholds.

| Label | Accuracy | Precision | Recall | F1 | AUC (95% bootstrap CI) |
|---|---|---|---|---|---|
| Pneumonia | 0.625 | 0.941 | 0.533 | 0.681 | 0.74 (0.58-0.89) |
| Lung Opacity | 0.800 | 0.958 | 0.767 | 0.852 | 0.85 (0.73-0.95) |

These numbers come from a tiny, imbalanced, selection-biased sample with a proxy task. They are a sanity check, **not a clinical validation**. Full output: `docs/evaluation_results.json`. Per-image dataset licences vary; images are cached locally (git-ignored) and are not redistributed.

## Known limitations
- Chest X-ray only. No fracture or brain CT model; CT would additionally need DICOM/NIfTI and windowing.
- PNG/JPEG only; no DICOM.
- Scores are uncalibrated; the model has no "normal" class; "no flag" does not mean normal. Operating thresholds are sensitive, so many labels can be flagged on a single image.
- The system cannot verify an upload is a frontal chest radiograph; other grayscale images still get scores (a warning is shown).
- Grad-CAM shows where the network looked, not a verified lesion; it is computed on the centre-cropped 224x224 view.
- `Fracture` among the 18 chest labels means findings visible on chest films, not limb fracture detection.
- No authentication, authorisation, rate limiting, HTTPS or retention policy; inference is synchronous (single worker, CPU).
- Docker files untested. Web fonts load from Google Fonts when online (system fallback otherwise).
- `tests/data/sample_cxr.png` is a sample from the TorchXRayVision repository, likely part of the model's training data; it is used for smoke/regression tests only.

## Future improvements
Verify and integrate fracture and brain CT models (licence, weights, external validation); DICOM support; calibration and external validation with clinicians; out-of-distribution/view detection; authentication and roles; background job queue; GPU support; Alembic migrations; multi-label localisation.
