# EDGEGUARD AI — Adaptive Edge Cyber-Resilience Platform

Research prototype for **“Design and Development of an Adaptive Edge Cyber-Resilience Mechanism for Real-Time Detection and Autonomous Containment of Unknown Attacks in Resource-Constrained IoT Networks.”**

EDGEGUARD AI is a FastAPI + React platform that runs a real, reproducible tabular intrusion-detection workflow: dataset ingestion and profiling, leakage-safe preprocessing, model training and held-out evaluation, withheld-attack-family experiments, simulated containment, host resource measurement, analytics and report export.

> **Scope statement:** network devices, containment actions and edge-device resource budgets are simulated. Host CPU, memory, latency and throughput are measured on the machine running the backend. No real network is scanned, throttled or blocked. Metrics are computed from the selected dataset and model; no detection, containment success or performance figure is seeded for display.

The original Streamlit REUG simulation is preserved unchanged and documented separately in [`docs/RESEARCH_SIMULATION.md`](docs/RESEARCH_SIMULATION.md).

---

## Contents

- [Implemented functionality](#implemented-functionality)
- [Modules](#modules)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Environment variables](#environment-variables)
- [Dataset management and Kaggle import](#dataset-management-and-kaggle-import)
- [End-to-end research workflow](#end-to-end-research-workflow)
- [Preprocessing guarantees](#preprocessing-guarantees)
- [Models and unknown-attack evaluation](#models-and-unknown-attack-evaluation)
- [Containment, resources and reports](#containment-resources-and-reports)
- [API overview](#api-overview)
- [Testing results](#testing-results)
- [Deployment](#deployment)
- [Repository layout](#repository-layout)
- [Known limitations and unfinished tasks](#known-limitations-and-unfinished-tasks)

---

## Implemented functionality

### Real functionality

- CSV and Parquet upload with size limits, content checks and safe storage.
- Optional Kaggle import using backend-only credentials, preset or custom dataset slug, streamed archive download, progress and explicit errors.
- Automatic profiling: rows, columns, dtypes, missing values, duplicates, file size, class distribution and likely target columns.
- Dataset version history, target-column selection, preview and deletion.
- Leakage-safe preprocessing: split first, fit imputers/encoders/scalers/selectors on train only, oversample train only, apply the saved transform to validation and test.
- Configurable missing-value handling, duplicate removal, infinite-value handling, encoding, scaling, variance filtering, top-k selection and class balancing.
- Before/after preprocessing statistics and persisted fitted pipeline.
- Training for Random Forest, XGBoost (when installed), Decision Tree, Logistic Regression, Isolation Forest, One-Class SVM and an MLP reconstruction autoencoder.
- Real held-out test metrics, confusion matrix, ROC and precision-recall curves, per-class performance, latency, throughput and artifact persistence.
- Saved-model prediction on uploaded CSV/Parquet.
- Withheld-attack-family holdout and leave-one-family-out (LOFO) unknown-attack studies with separate known/unknown metrics.
- Closed-loop simulated containment with verification, event history and release/recovery.
- Host resource measurement plus a clearly separated simulated edge-device budget.
- Cross-experiment analytics and CSV, JSON and PDF exports.
- Research documentation served from the backend and rendered in the UI.
- Background jobs with WebSocket progress and polling fallback.

### Deliberately simulated

- IoT device inventory and network topology.
- IP addresses, flows, containment actions and their enforcement.
- Edge-device CPU/memory constraints.
- The effect of containment on traffic. Verification re-scores real held-out records after applying a simulated traffic allowance and resource damping; it does **not** observe a real network.

---

## Modules

| # | Module | What it does |
|---|--------|--------------|
| 1 | **Command Center** | Aggregates real counts and latest jobs/experiments/threats from SQLite. Labels historical analysis as replay, not live capture. |
| 2 | **Dataset Management** | Upload, Kaggle import, profile, preview, select target, inspect versions, delete. |
| 3 | **Data Preprocessing** | Configure and run the leakage-safe pipeline; inspect before/after statistics and saved artifacts. |
| 4 | **ML Model Laboratory** | Choose a model and hyperparameters, train in a background job, inspect held-out metrics, load and predict. |
| 5 | **Unknown Attack Detection** | Hold out attack families, run LOFO, compare known vs unknown detection and threshold behaviour. |
| 6 | **Threat Intelligence** | Lists evaluated threat/benign records, anomaly scores and withheld-family status from experiment outputs. |
| 7 | **Autonomous Containment** | MONITOR → DETECT → ASSESS → CONTAIN → VERIFY → LEARN simulation, with release/recovery. |
| 8 | **Edge Resource Monitoring** | Measured host CPU/memory, preprocessing and inference latency, throughput, model size; editable simulated edge budget. |
| 9 | **Research Analytics** | Metric comparisons, curves, per-class results, resource figures and downloadable results. |
| 10 | **Experimental Reports** | Create and download reproducible CSV/JSON/PDF reports for an experiment. |
| 11 | **Research Documentation** | Abstract through references, generated from the backend's research documentation service. |

---

## Architecture

```text
React 18 + Vite + Tailwind (11 modules, Recharts)
        │  REST /api/*        WebSocket /ws/jobs/{job_id}
        ▼
FastAPI application (backend/main.py)
        │
        ├── routers: datasets · ml · operations · ws
        ├── services:
        │     datasets        upload, profile, versions, Kaggle
        │     preprocessing   leakage-safe pipeline + artifacts
        │     modeling        training, metrics, prediction
        │     unknown         family holdout / LOFO
        │     containment     simulated closed loop
        │     resources       host measurement + edge simulation
        │     analytics       comparisons and exports
        │     reports         CSV / JSON / PDF
        │     docs            research documentation
        ├── jobs: in-process thread pool, SQLite job state, WS + polling
        └── storage: SQLite metadata + data/edgeguard artifact directories
```

- **Frontend:** React 18, Vite 5, Tailwind CSS 3, Recharts, lucide-react, React Router.
- **Backend:** Python 3.12, FastAPI, Uvicorn, pandas, NumPy, scikit-learn, joblib, psutil, ReportLab.
- **Storage:** stdlib `sqlite3`; files on local disk. In production, SQLite and artifacts need a persistent volume.
- **Deployment:** FastAPI can serve `frontend/dist` for a single-origin deployment. Vercel serves the frontend; Render/Railway/Fly can host the API.

The SPA is mounted only when `frontend/dist` exists. Unknown non-API paths fall back to `index.html`, so client-side routes work after a refresh.

---

## Quick start

### Prerequisites

- Python 3.11+ (tested with 3.12.2)
- Node.js 18+ and npm (tested with Node 26.4.0 / npm 11.17.0)
- No GPU required

### 1. Backend

From the repository root:

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash
# source .venv/bin/activate          # macOS / Linux
# .\.venv\Scripts\Activate.ps1       # Windows PowerShell

pip install -r requirements-api.txt
uvicorn backend.main:app --reload --port 8000
```

- API: `http://localhost:8000/api/health`
- Swagger: `http://localhost:8000/api/docs`
- On first start the backend creates `data/edgeguard/` and the SQLite schema.

The app reads configuration from the process environment. `.env` is **not** auto-loaded. Either export variables in your shell or set them in the hosting provider:

```bash
cp .env.example .env
set -a; source .env; set +a          # Git Bash / Linux
```

### 2. Frontend development

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` and `/ws` to port 8000.

### 3. Single-server production build

```bash
cd frontend
npm install
npm run build
cd ..
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. FastAPI serves the built SPA and the API from one origin. If the backend is already running when you build, restart it so the new `dist` is detected.

### 4. Preserved legacy simulation (optional)

The original Streamlit project is separate and uses its own dependencies/state:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Its tests: `python -m pytest tests -q`.

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `EDGEGUARD_DATA_DIR` | `./data/edgeguard` | Root for datasets, artifacts, models, reports and SQLite. Use a persistent disk in production. |
| `EDGEGUARD_DB_PATH` | `<data dir>/edgeguard.sqlite3` | Optional explicit SQLite path. |
| `EDGEGUARD_MAX_UPLOAD_MB` | `512` | Maximum direct upload size. |
| `EDGEGUARD_MAX_KAGGLE_MB` | `2048` | Maximum Kaggle archive size. |
| `EDGEGUARD_SYNC_JOBS` | `0` | `1` runs jobs inline (tests/CLI). Keep `0` when serving. |
| `EDGEGUARD_CORS_ORIGINS` | localhost dev origins | Comma-separated browser origins allowed to call the API. Set your Vercel URL in production. |
| `KAGGLE_USERNAME` | unset | Kaggle account username. Backend only. |
| `KAGGLE_KEY` | unset | Kaggle API key. Backend only; never expose as `VITE_*`. |
| `KAGGLE_CONFIG_DIR` | `~/.kaggle` | Optional folder containing `kaggle.json`. |
| `VITE_API_BASE` | empty | Frontend build-time backend origin, e.g. `https://edgeguard-api.onrender.com`. Empty means same-origin. |

Optional: install `xgboost` in the backend environment to enable the XGBoost model. Without it, the API reports the model as unavailable instead of pretending to train it.

---

## Dataset management and Kaggle import

### Upload your own file

1. Open **Dataset Management**.
2. Upload a `.csv` or `.parquet` file.
3. The backend stores it safely, profiles it and records version 1.
4. Choose the **target column** from the detected candidates. Confirm the class distribution includes benign and attack rows.
5. Uploading a file with the same name creates a new version while preserving history.

Large CSV profiling reads in chunks and samples rows for preview/statistics where appropriate. Training and preprocessing use the stored file, with a configurable row cap (default 250,000) that is reported in the run statistics.

### Kaggle import

1. Sign in to Kaggle → **Settings → API → Create New Token**.
2. Accept the dataset's rules on its Kaggle page (required by Kaggle, not by this app).
3. Set `KAGGLE_USERNAME` and `KAGGLE_KEY` in the **backend** environment and restart the API.
4. Open **Dataset Management**. The Kaggle status panel shows whether credentials are configured.
5. Pick a preset or enter a dataset slug (`owner/dataset-name`) and start the import.
6. Progress is streamed through the job WebSocket (polling is the fallback). Errors identify authentication, missing dataset, archive or size problems.

Presets:

| Dataset | Slug |
|---------|------|
| Edge-IIoTset | `mohamedamineferrag/edgeiiotset-cyber-security-dataset-of-iot-iiot` |
| CICIoT2023 | `akashdogra/cic-iot-2023` |
| ToN_IoT | `arnobbhowmik/ton-iot-network-dataset` |

Notes:

- Kaggle credentials are only read by the backend. They are never returned by an API or embedded in the frontend.
- Archives are validated and extracted without trusting member paths. Supported CSV/Parquet members are imported and profiled; the import is capped by `EDGEGUARD_MAX_KAGGLE_MB`.
- The three datasets do **not** share a label column name or schema. Always inspect the profile and select the real label/target column. For multi-file datasets, import the file that contains the flow records you intend to study.
- If backend Kaggle access is unavailable, download the dataset manually from Kaggle and upload the extracted CSV/Parquet.
- You are responsible for each dataset's license and citation requirements.

---

## End-to-end research workflow

| Step | Where |
|------|-------|
| 1. Upload or import a dataset | Dataset Management |
| 2. Inspect rows, columns, dtypes, missing values, duplicates, classes, target candidates | Dataset Management |
| 3. Select the target and configure preprocessing | Dataset Management → Data Preprocessing |
| 4. Run leakage-safe preprocessing and inspect before/after statistics | Data Preprocessing |
| 5. Select a model and hyperparameters | ML Model Laboratory |
| 6. Train with live progress and save the artifact | ML Model Laboratory |
| 7. Evaluate on the untouched held-out test split | ML Model Laboratory / Research Analytics |
| 8. Withhold attack families and run holdout/LOFO evaluation | Unknown Attack Detection |
| 9. Inspect real metrics and curves | Research Analytics |
| 10. Inspect evaluated suspicious traffic and anomaly scores | Threat Intelligence |
| 11. Run simulated autonomous containment | Autonomous Containment |
| 12. Verify the containment outcome (SUCCESS / FAILED / INCONCLUSIVE) | Autonomous Containment |
| 13. Review measured host resources and simulated edge budget | Edge Resource Monitoring |
| 14. Generate CSV/JSON/PDF experimental artifacts | Experimental Reports / Research Analytics |

No button in these modules displays a canned success message: each action calls the backend and shows the returned job, metric, event or error.

---

## Preprocessing guarantees

The order is deliberate and enforced in `backend/services/preprocessing.py`:

1. Drop rows without a target label; derive benign/malicious and keep the original family label.
2. Remove exact duplicate rows when enabled.
3. Replace infinities with missing values when enabled.
4. Optionally drop rows with missing feature values (`drop_rows`); otherwise impute.
5. **Split train/validation/test before fitting any transform.**
6. Fit imputers, one-hot encoder, scaler, variance filter and top-k selector on the training split only.
7. Apply that fitted pipeline unchanged to validation and test.
8. Oversample the training split only when class balancing is enabled.
9. Persist the fitted pipeline and the split indices/artifact for training, prediction and containment verification.

Identifier-like columns and explicitly dropped columns are excluded. Before/after statistics report rows, features, class counts, missing values, duplicates and removed incomplete rows.

Feature selection clamps the requested top-k to the number of transformed columns available after variance filtering, so a valid configuration does not fail just because one-hot encoding changed the feature count.

---

## Models and unknown-attack evaluation

Available models:

- **Supervised:** Random Forest, XGBoost (optional), Decision Tree, Logistic Regression.
- **Anomaly / one-class:** Isolation Forest, One-Class SVM, autoencoder (scikit-learn MLP trained to reconstruct benign vectors; reconstruction error is the anomaly score).

Every reported metric is derived from predictions on the held-out test split and stored with the experiment:

- accuracy, precision, recall, F1
- false-positive and false-negative rates
- confusion matrix
- ROC curve and ROC AUC
- precision-recall curve and average precision
- per-class performance
- prediction latency and throughput
- model artifact size

**Unknown attacks.** The platform supports withholding selected attack families from training and testing on them, plus leave-one-attack-family-out evaluation. Reports separate known-attack performance from withheld-family performance and expose anomaly scores and configurable thresholds. This is an experimental simulation of novelty detection; a strong withheld-family score is not evidence of real zero-day detection. Family selection and row caps are recorded with the experiment.

---

## Containment, resources and reports

### Simulated containment

The event pipeline is MONITOR → DETECT → ASSESS → CONTAIN → VERIFY → LEARN:

- reads evaluated records from a completed experiment (or the latest available),
- assigns a simulated device/flow from the seeded inventory,
- scores severity, risk and confidence from the model output,
- selects an action: monitor, rate-limit, block IP, isolate device, quarantine device or terminate connection,
- records the event, action and rationale in SQLite,
- verifies by re-scoring held-out records after applying the simulated traffic allowance and resource damping,
- records SUCCESS, FAILED or INCONCLUSIVE; release/recovery is available per event.

Verification is a model-based re-evaluation of real held-out rows. It is not a packet capture, firewall rule or proof that a real device was contained.

### Resources

- **Measured:** host CPU/memory during preprocessing and inference, average prediction time, throughput, model file size.
- **Simulated:** edge-device CPU/memory budget and whether a workload fits it. The UI labels this separately and the budget is configurable.

### Reports and analytics

- Per-experiment metrics, curves, class results and resource figures.
- Model-to-model comparison for selected experiments.
- CSV and JSON exports (experiment detail and comparison).
- PDF report generated with ReportLab from stored results.
- Research documentation endpoint and page covering abstract, problem statement, objectives, literature review, gap, methodology, architecture, implementation, experimental method, results, conclusion, future scope and references.

---

## API overview

Base path: `/api`. Interactive schema: `/api/docs`.

| Area | Representative endpoints |
|------|--------------------------|
| Health / jobs | `GET /health`, `GET /jobs`, `GET /jobs/{id}`, `WS /ws/jobs/{id}` |
| Datasets | `GET/POST /datasets`, `POST /datasets/upload`, `GET /datasets/{id}/preview`, `PATCH /datasets/{id}/target`, `DELETE /datasets/{id}` |
| Kaggle | `GET /kaggle/status`, `GET /kaggle/presets`, `POST /kaggle/import` |
| Preprocessing | `GET/POST /preprocess/runs`, `GET /preprocess/runs/{id}`, `GET /preprocess/runs/{id}/families` |
| Modeling | `GET /models`, `GET/POST /experiments`, `GET/DELETE /experiments/{id}`, `POST /experiments/{id}/predict` |
| Unknown attacks | `POST /unknown/experiments` |
| Containment | `GET /containment/status`, `POST /containment/simulate`, `POST /containment/events/{id}/verify`, `POST /containment/events/{id}/release` |
| Resources | `GET /resources`, `PATCH /resources/edge-budget`, `POST /resources/benchmark` |
| Analytics / reports | `GET /analytics/overview`, `GET /analytics/compare`, `GET /analytics/export`, `GET/POST /reports`, `GET /reports/{id}/download` |
| Command center / docs | `GET /command-center`, `GET /threats`, `GET /documentation` |

Long-running work (preprocessing, training, unknown studies, containment, benchmarks, imports) returns `202` with a job ID. Job state is persisted in SQLite; progress is pushed over WebSocket and remains available by polling.

---

## Testing results

Verified on 2026-11-10 on Windows with Python 3.12.2 and Node 26.4.0.

| Check | Command | Result |
|-------|---------|--------|
| Backend platform tests | `python -m pytest backend/tests -q` | **12 passed** in 10.60 s (10 workflow/integration + 2 preprocessing unit tests) |
| Frontend tests | `cd frontend && npm test` | **6 passed** in 2 files |
| Frontend production build | `cd frontend && npm run build` | **success** in 4.58 s |
| Preserved legacy suite | `python -m pytest tests -q` | **78 passed** in 33.85 s |
| Python byte-compile | `python -m compileall -q backend` | exit 0 |
| Served SPA smoke test | Uvicorn + `curl` | `/api/health` 200, `/` 200, `/datasets` 200 (SPA fallback), `/api/docs` 200 |

The backend suite exercises upload/profiling/versioning, target validation, leakage-safe preprocessing, training, saved-artifact prediction, withheld-family holdout, containment/verification/release, resource budget/benchmark, and report/export/documentation generation.

The frontend suite covers formatting utilities and shared UI components. There is no browser end-to-end automation in the repository.

**Not validated in this environment:** importing the real Kaggle datasets (no Kaggle credentials were configured), public deployment, real network capture/containment, PostgreSQL, and accuracy on the named datasets. The automated ML checks use a synthetic fixture that verifies pipeline correctness, not research performance.

Known warnings: joblib's NumPy 2.5 pickle deprecation (4,139 warnings in the backend suite) and a Vite warning that the main JS chunk is 760.51 kB (208.90 kB gzip). Neither is a test failure.

---

## Deployment

### Frontend on Vercel

The root `vercel.json` builds `frontend/` and publishes `frontend/dist`:

```bash
npm install -g vercel
vercel --prod
```

Set `VITE_API_BASE` to the public backend origin **before building** (Vite variables are build-time). The rewrite sends client-side routes to `index.html`. Vercel does not host the Python API; deploy it separately below.

### Backend on Render

`render.yaml` defines a Python web service and a persistent disk:

- build: `pip install -r requirements-api.txt`
- start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- health check: `/api/health`
- data directory: `/var/data/edgeguard` on a 5 GB disk

Set `EDGEGUARD_CORS_ORIGINS` to the Vercel URL, and set `KAGGLE_USERNAME` / `KAGGLE_KEY` as secret environment variables. The `starter` plan is used because free instances may not support persistent disks; without a disk, SQLite and artifacts are lost on redeploy. For Railway/Fly/Docker, use the same build/start commands and mount a persistent volume at `EDGEGUARD_DATA_DIR`.

Requirements for any host:

- WebSocket support for `/ws/jobs/{id}` (polling still works without it).
- Request body limits above your configured upload size.
- A single backend instance while using SQLite and in-process jobs. Do not run multiple workers against the same SQLite state.
- HTTPS; add authentication before exposing the app publicly.

### Single-origin deployment

Build the frontend and run only FastAPI:

```bash
cd frontend && npm install && npm run build && cd ..
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

This avoids CORS and WebSocket cross-origin configuration. Put a reverse proxy in front for TLS and upload limits.

---

## Repository layout

```text
backend/
  main.py              FastAPI app, CORS, SPA mount, lifespan
  settings.py          paths, limits, CORS, research metadata
  db.py                SQLite schema and seeded simulated devices
  jobs.py              thread-pool job manager
  routers/             datasets, ml, operations, websocket
  services/            dataset, preprocessing, modeling, unknown,
                       containment, resources, analytics, reports, docs
  tests/               platform integration + unit tests
frontend/
  src/pages/           11 research modules
  src/components/      layout, UI primitives, charts
  src/api.js           typed-ish fetch/upload/WebSocket helpers
  src/hooks.js         data fetching and job progress
  dist/                production build (generated)
docs/
  RESEARCH_SIMULATION.md   legacy Streamlit documentation
app.py, src/, tests/   preserved original REUG simulation
results/               original experiment outputs (CRLF CSVs)
requirements.txt       legacy simulation dependencies
requirements-api.txt   platform backend dependencies
render.yaml            Render blueprint
vercel.json            Vercel frontend deployment
.env.example           backend environment reference
```

---

## Known limitations and unfinished tasks

- **Containment is simulated.** No firewall, iptables, SDN controller or device API is called. Verification models containment effect; it can return FAILED or INCONCLUSIVE.
- **No live capture.** Command Center and Threat Intelligence show dataset-derived/replayed analysis, not real-time network telemetry. UI labels state this.
- **SQLite only.** PostgreSQL support is not implemented. Concurrency is limited; jobs are in-process and do not resume after a restart.
- **No authentication or authorization.** Add auth, rate limiting and audit logging before any public or multi-user deployment.
- **Kaggle/import limits.** Downloads are not resumable; archives are capped by `EDGEGUARD_MAX_KAGGLE_MB`; only supported CSV/Parquet members are imported.
- **Sampling.** Preprocessing caps rows at 250,000 by default and anomaly models cap their training samples. Results on large datasets are therefore based on the recorded sample, not every row.
- **Dataset assumptions.** Benign-label detection is heuristic and can be overridden; target schemas differ across Edge-IIoTset, CICIoT2023 and ToN_IoT. Wrong target selection or label mapping invalidates results.
- **Unknown-attack evidence is experimental.** Withheld-family scores do not prove zero-day capability. No real zero-day dataset is included.
- **XGBoost is optional.** It is unavailable unless installed; the UI reports this rather than fabricating results.
- **Frontend tests are not browser E2E.** No Playwright/Cypress suite; responsive and interaction behavior was verified through build and component tests, not automated browsers.
- **Reports are functional, not publication-formatted.** PDF export is generated from stored metrics; it is not a typeset IEEE paper. Report scheduling is not implemented.
- **Deployment not exercised.** Vercel/Render configuration is provided, but no public deployment, TLS, proxy upload-limit or persistent-disk test was run here.
- **Bundle size warning.** The main frontend chunk exceeds Vite's 500 kB advisory; code splitting is a future optimization.
- **Legacy UI remains.** The original Streamlit app is intentionally separate and does not share the platform database.
- **No CI pipeline.** Tests are run manually; adding GitHub Actions is recommended.
- **Data licensing.** Dataset licenses and citations must be handled by the researcher.

---

For the research write-up, use the in-app **Research Documentation** module or `GET /api/documentation`. For the original simulation methodology and results, see [`docs/RESEARCH_SIMULATION.md`](docs/RESEARCH_SIMULATION.md).
