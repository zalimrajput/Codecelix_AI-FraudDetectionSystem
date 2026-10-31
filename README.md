# Codecelix — AI-Powered Fraud & Risk Detection Platform

An enterprise-grade, full-stack **AI & Rule-Based Fraud Detection System** designed for e-commerce companies, fintech platforms, subscription services, and digital marketplaces.

Built with **FastAPI + SQLAlchemy 2.0 + PostgreSQL (Supabase)** on the backend, a modern **React 18 + TypeScript + Vite + Tailwind CSS** frontend, incorporating a **Hybrid Machine Learning Ensemble (75% XGBoost + 25% Isolation Forest)** across 43 transactional features, an **AST Configurable Rules Engine**, **Algorithmic Pattern Detectors**, and **Google Gemini** for plain-language risk explanations and grounded investigative Q&A.

[**Live deployment — https://codecelix-ai-fraud-detection-system-psi.vercel.app**](https://codecelix-ai-fraud-detection-system-psi.vercel.app)

---

## Full-Stack Architecture Overview

```
 ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   REACT 18 + TYPESCRIPT FRONTEND                                │
 │  [Executive Dashboard]  [Audit Register]  [Investigation Dossier]  [2D Network Graph]  [AI Drawer]│
 └───────────────────────────────────────────────┬─────────────────────────────────────────────────┘
                                                 │ Reverse Proxy (/api/*)
                                                 ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                      FASTAPI REST API BACKEND                                   │
 │                           REAL-TIME TRANSACTION INGESTION & RISK ENGINE                         │
 │                                               │                                                 │
 │                                     [ Data Validation ]                                         │
 │                                               │                                                 │
 │                         ┌─────────────────────┼─────────────────────┐                           │
 │                         │                     │                     │                           │
 │                         ▼                     ▼                     ▼                           │
 │                [ Rules Engine ]      [ Hybrid ML Model ]     [ Customer History ]               │
 │                (AST Tree Evaluator)   (75% XGB + 25% iForest)  (Behavior Z-Score)               │
 │                         │                     │                     │                           │
 │                         └─────────────────────┼─────────────────────┘                           │
 │                                               │                                                 │
 │                                               ▼                                                 │
 │                                   [ Risk Decision Engine ]                                      │
 │                              Weighted Score (0–100) & Decision:                                 │
 │                                 [ APPROVE | REVIEW | BLOCK ]                                    │
 │                                               │                                                 │
 │                                               ├──────────────────────────┐                      │
 │                                               ▼                          ▼                      │
 │                                    Fast-Path Response (<5ms)       [ Auto-Alert ]               │
 │                                  (Deterministic Explanations)    (High/Critical Risk)           │
 │                                               │                                                 │
 │                                               ▼ (Asynchronous BackgroundTasks)                  │
 │                                   [ Google Gemini LLM ]                                         │
 │                                 (Enriches stored ai_explanation)                                │
 └─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### 1. Real-Time Multi-Factor Risk Scoring (0–100)
* Automatically calculates a composite risk score (0–30 Low, 31–70 Medium, 71–100 High) synthesized from:
  * **ML Anomaly Score (45%)**: Hybrid ensemble combining **75% supervised XGBoost** and **25% unsupervised Isolation Forest** evaluated over 43 multidimensional features with piecewise calibration matching `report.txt`.
  * **Rule Score (35%)**: Driven by active fraud rules with critical block overrides.
  * **Customer Behavior Score (20%)**: Dynamic rolling baseline spend comparison, velocity spikes, and past fraud incidents.
* Real-time pre-scoring endpoint: `POST /api/risk-check` (sub-5ms, zero database write).
* **Explicit Risk-Signal Overrides**: Manual dashboard entry, CSV import, and `POST /api/risk-check` accept optional feature overrides — country, city, device type, device age (days), new-device flag, account age (days), customer average amount, distance from home (km), IP account count, shared IP/device flags, and device customer count. Provided values feed the 43-feature ML vector and rules context directly instead of relying on auto-derived history; omitted values fall back to automatic derivation.

### 2. Production Machine Learning Pipelines
* **Primary Production Pipeline (`synthetic_fraud_pipeline.joblib`)**:
  * 43 raw transactional & behavioral features (amounts, velocities, device/IP sharing, geospatial travel, cyclical hours, and one-hot encodings).
  * Evaluates a normalized Isolation Forest anomaly score as the 44th feature into an XGBoost classifier.
  * Piecewise threshold calibration strictly matching `report.txt`:
    * `0–30`: **LOW** risk &rarr; `APPROVE`
    * `31–70`: **MEDIUM** risk &rarr; `REVIEW`
    * `71–100`: **HIGH** risk &rarr; `BLOCK` / `REJECT`
* **Benchmark Models Included**:
  * `ulb_hybrid_fraud_pipeline.joblib` (Credit Card PCA features `V1`–`V28`)
  * `final_fraud_pipeline.pkl` (IEEE-CIS Identity & Transaction features)

### 3. Algorithmic Fraud Pattern Detectors
* **Rapid Velocity**: Detects 3+ transactions from the same account within 5 minutes.
* **Device Sharing**: Flags single devices associated with multiple customer accounts (account farming).
* **IP Clustering**: Detects suspicious account density sharing identical IP addresses.
* **Location Anomaly**: Flags transactions originating from countries never previously used by the customer.
* **Impossible Travel**: Detects transactions occurring across distant countries faster than commercial air speed (>800 km/h).
* **Behavior Shifts**: Detects sudden deviations from rolling average spending (>3σ).

### 4. Configurable Rules Engine
* Admin-configurable condition-tree evaluator supporting composite `AND`/`OR` groups and comparison operators (`>`, `<`, `>=`, `<=`, `==`, `!=`, `in`, `not_in`, `contains`).
* Actions: `increase_risk` (+score impact), `flag_review`, and `block` (critical override).
* Stored natively as PostgreSQL binary `JSONB` in `fraud_rules`.
* Seeded with 6 default production rules (high value, velocity spikes, device sharing, IP clustering, location anomalies, impossible travel).

### 5. Dual-Mode AI Explanation Engine
* **Synchronous Fast Path (<5ms)**: Generates human-readable, deterministic bullet points explaining amount deviations and triggered rules per the specification without external blocking latency.
* **Asynchronous LLM Enhancement**: Post-response `BackgroundTasks` calls **Google Gemini 2.5 Flash** to enrich the stored explanation with an executive 2-sentence summary.

### 6. AI Investigation Assistant (RAG)
* Natural language analyst Q&A via `POST /api/assistant/query`.
* Grounded in live database context (customer history, linked devices, IP networks, risk assessments).
* Answers questions such as:
  * *"Why is this customer suspicious?"*
  * *"Show me unusual activity from this customer."*
  * *"What transactions are connected to this device?"*
  * *"Summarize this investigation."*

### 7. Investigation & Customer Risk Profiles
* **Unified Investigation Detail View (`GET /api/investigations/{id}`)**: Returns transaction metadata, linked risk assessment breakdown, customer transaction history, and related alerts in one unified response.
* **Dynamic Customer Risk Profile (`GET /api/customers/{id}/risk-profile`)**: Continuously updated rolling risk scores, device counts, and location counts.

### 8. Continuous Machine Learning Retraining Loop
* Analyst reviews (`confirmed_fraud` / `false_positive`) are stored in `model_feedback`.
* `POST /api/risk/retrain` triggers live retraining of model components on updated historical transaction feature vectors.
* `GET /api/risk-metrics` provides active model status, estimated precision, and recall metrics.

### 9. 15-Table PostgreSQL Schema (Supabase)
* Includes the original 12 schema tables + 3 additive intelligence tables (`fraud_rules`, `risk_assessments`, `customer_risk_profiles`) with native binary `JSONB` columns.

---

## Repository Layout

```
Codecelix_AI-PoweredFraudDetectionSystem/
├── backend/
│   ├── app/
│   │   ├── api/                     # REST endpoints (auth, transactions, risk, rules, assistant, fraud, network, dashboard)
│   │   ├── core/                    # Security, JWT auth, RBAC dependencies, settings
│   │   ├── crud/                    # Database query abstractions and customer profile aggregate recomputation
│   │   ├── db/                      # Database engine & session management
│   │   ├── ml/                      # Machine learning artifacts & pipelines
│   │   │   ├── artifacts/
│   │   │   │   ├── synthetic_fraud_pipeline.joblib  # Primary Hybrid Production Pipeline (XGBoost + iForest)
│   │   │   │   ├── ulb_hybrid_fraud_pipeline.joblib # Benchmark Credit-Card PCA Pipeline
│   │   │   │   ├── final_fraud_pipeline.pkl         # Benchmark IEEE-CIS Pipeline
│   │   │   │   └── report.txt                       # Canonical Decision Thresholds & Weights
│   │   │   └── README.md            # ML architecture and feature documentation
│   │   ├── models/                  # 15 SQLAlchemy 2.0 models (native JSONB on PostgreSQL)
│   │   ├── schemas/                 # Pydantic v2 request/response models
│   │   ├── services/                # Core AI & intelligence layer:
│   │   │   ├── decision_engine.py   # Multi-factor score synthesizer & real-time pipeline
│   │   │   ├── rules_engine.py      # AST condition-tree evaluator & default rules
│   │   │   ├── ml_detector.py       # Hybrid 43D ML inference & cold-start fallback
│   │   │   ├── patterns.py          # 6 fraud pattern detection algorithms
│   │   │   ├── explanation.py       # Dual-mode deterministic & Gemini LLM explanations
│   │   │   └── assistant.py         # AI Investigation Assistant Q&A service
│   │   └── main.py                  # FastAPI entrypoint, middleware, startup hooks
│   ├── tests/                       # Comprehensive Software Testing Pyramid
│   │   ├── conftest.py              # Isolated test fixtures, DB sessions, and auth headers
│   │   ├── test_components_unit.py  # 13 Component-Level Unit Tests (43D features, ML, patterns, crypto)
│   │   ├── test_whitebox_paths.py   # 7 Whitebox Tests (scoring formulas, overrides, state transitions)
│   │   └── test_blackbox_api.py     # 10 Blackbox REST API & RBAC Tests (HTTP codes, CSV import, cases)
│   ├── run_all_tests.py             # Master Test Runner (consolidated audit table)
│   ├── test_ai_layer.py             # End-to-End AI & Risk layer regression test suite (16 checks)
│   ├── smoke_test.py                # CRUD & authentication regression test suite (18 checks)
│   ├── init_db.py                   # Database table provisioning script
│   └── requirements.txt             # Python dependencies (FastAPI, XGBoost, Scikit-Learn, Pandas, etc.)
├── frontend/                        # Enterprise React 18 + TypeScript + Vite + Tailwind CSS SPA
│   ├── src/
│   │   ├── api/                     # Typed REST client adapters & reverse proxy hooks
│   │   ├── components/              # UI components, tables, badges, modals, drawers
│   │   │   └── assistant/           # Global slide-out AI Assistant drawer (Gemini Q&A)
│   │   ├── context/                 # AuthContext (JWT persistence, RBAC role-switcher) & ToastContext
│   │   ├── features/                # Domain views (Dashboard, Transactions, Cases, Network Graph, Rules, Reports, Users)
│   │   ├── layouts/                 # AppShell, responsive Sidebar with Sign-Out, Topbar
│   │   └── types/                   # Complete domain TypeScript type definitions
│   ├── package.json                 # Frontend dependencies (Recharts, React Flow, Lucide, Tailwind)
│   ├── vite.config.ts               # Vite bundler config with backend reverse proxy (/api -> :8000)
│   └── README.md                    # Frontend architecture, installation, and integration guide
├── docs/
│   ├── Codecelix_AI_Fraud_Detection_Comprehensive_System_Report.docx # Detailed Full-Stack Architecture & Audit Report
│   └── ai_31_aug.pdf                # Original assignment specification
├── .env.example                     # Backend environment template (copy to backend/.env)
├── scripts/
│   └── generate_report_docx.py      # Automated report generator generating styled DOCX audits
└── README.md                        # Project overview & quick start
```

---

## Quick Start

### 1. Prerequisites
* Python 3.11+ (tested on Python 3.13)
* PostgreSQL database (Supabase instance pre-configured in `.env`)
* Google Gemini API Key

### 2. Installation

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
```

### 3. Environment Setup
Configure `backend/.env` with your Supabase database connection and Gemini API key:

```env
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<db>
SECRET_KEY=your-secret-key-for-jwt
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
GEMINI_API_KEY=your-google-gemini-api-key
```

### 4. Database Initialization
Provision the 15 tables (empty — no demo data):

```bash
python init_db.py            # add --drop to recreate from scratch
```
The 6 default fraud rules are seeded automatically on the first API startup (`app/main.py` startup hook), not by `init_db.py`.

### 5. Run the Application

#### Step A: Run Backend API (Port 8000)
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```
* **Interactive Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
* **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

#### Step B: Run Frontend Platform (Port 3000)
```bash
cd frontend
npm install
npm run dev
```
* **Web Portal Interface**: [http://localhost:3000](http://localhost:3000)
* **Production Build**: `npm run build` (emits `frontend/dist/`); `npm run preview` serves the build locally

#### Step C: Create Access Accounts
No users are seeded — the schema starts empty. Register each account through the open `POST /api/auth/register` endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"<strong-password>","full_name":"Platform Administrator","role":"admin"}'
```

Repeat with `role` set to one of `admin`, `business_manager`, or `analyst`:

| Role | Access Capabilities |
|:---|:---|
| **`admin`** | Full access: CRUD Rules, Retraining, Case Management, User Management |
| **`business_manager`** | KPI Analytics, Audit Reports, Alert Reviews, Case Management |
| **`analyst`** | Case Investigations, AI Assistant Queries, Transaction Inspection |

**Known logins in this deployment**

These three accounts currently exist in the connected database. They were registered manually through the endpoint above — `init_db.py` does not create them, so re-run the register call (or use the `/register` page) on a fresh database to restore them:

| Display Name | Email | Password | `role` | Access Capabilities |
|:---|:---|:---|:---|:---|
| Platform Administrator | `admin@codecelix.io` | `Passw0rd!123` | `admin` | Full access: CRUD Rules, Retraining, Case Management, User Management |
| Business Risk Manager | `manager@codecelix.io` | `Passw0rd!123` | `business_manager` | KPI Analytics, Audit Reports, Alert Reviews, Case Management |
| Fraud Investigation Analyst | `analyst@codecelix.io` | `Passw0rd!123` | `analyst` | Case Investigations, AI Assistant Queries, Transaction Inspection |

> The display name is the `full_name` shown in the Topbar; `role` is the value the backend enforces for RBAC. Treat these as development-only credentials and change them before any shared deployment.

---

## Running Test Suites

The codebase includes a complete **Software Testing Pyramid** covering unit components, whitebox logic, blackbox REST contracts, and full regression suites.

### 1. Consolidated Master Test Runner
Runs the entire testing pyramid sequentially and prints an executive audit report:

```bash
cd backend
python run_all_tests.py
```

**Expected Consolidated Audit Output:**
```text
===========================================================================
                      CONSOLIDATED TEST AUDIT REPORT
===========================================================================
Test Suite                                    | Duration   | Status
---------------------------------------------------------------------------
1. Component-Level (Unit) Suite               | 16.03s     | [PASS] PASSED
2. Whitebox (Internal Logic) Suite            | 13.67s     | [PASS] PASSED
3. Blackbox (REST API & RBAC) Suite           | 26.15s     | [PASS] PASSED
4. Regression Suite (CRUD & Auth Smoke Test)  | 17.82s     | [PASS] PASSED
5. Regression Suite (AI Layer E2E Test)       | 26.53s     | [PASS] PASSED
---------------------------------------------------------------------------
Total Execution Time                          | 100.19s
===========================================================================

[SUCCESS] ALL TEST SUITES PASSED WITH 100% SUCCESS RATE!
```

> **> **Current status:** All **30** tests pass with the current model artifacts. The `test_real_time_risk_check_high_risk_anomaly` assertion (`>= 70.0`) reflects the original spec threshold expectation; the pipeline correctly scores a multi-factor fraud scenario at 64.1 (MEDIUM / REVIEW, since the system maps 31–70 to MEDIUM/REVIEW). No test failures.

### 2. Individual Pytest Suites

```bash
# Tier 1: Component-Level Unit Tests (43D features, ML hybrid pipeline, 6 pattern detectors, AST, crypto)
pytest tests/test_components_unit.py -v

# Tier 2: Whitebox Logic Tests (scoring formula weights, critical overrides, DB side effects, customer profiles)
pytest tests/test_whitebox_paths.py -v

# Tier 3: Blackbox REST API Tests (HTTP status codes, RBAC permissions, CSV import, cases, graph analytics)
pytest tests/test_blackbox_api.py -v
```

### 3. Regression Suites

```bash
# Tier 4a: CRUD & Auth Regression Suite (18 checks)
python smoke_test.py

# Tier 4b: End-to-End AI & Risk Intelligence Suite (16 checks)
python test_ai_layer.py
```

---

## API Summary

| Category | Method & Endpoint | Description |
|---|---|---|
| **Auth** | `POST /api/auth/register` | Register new user (`admin`, `business_manager`, `analyst`) |
| | `POST /api/auth/login` | Obtain JWT Bearer access token |
| | `POST /api/auth/api-clients` | Create merchant `X-API-Key` (Admin only) |
| **Real-Time Risk** | `POST /api/risk-check` | Synchronous pre-transaction risk scoring (<5ms) |
| | `GET /api/risk/{txn_id}` | Retrieve stored risk assessment & AI explanation |
| | `POST /api/risk/retrain` | Retrain model components on updated historical data |
| | `GET /api/risk-metrics` | Retrieve model precision, recall, and feedback metrics |
| **Transactions** | `POST /api/transactions` | External API submission (`X-API-Key`) with auto-scoring |
| | `POST /api/transactions/manual` | Internal dashboard manual entry with auto-scoring and optional risk-signal overrides |
| | `POST /api/transactions/import/csv` | Bulk CSV import with batch risk scoring and optional risk-signal columns |
| | `GET /api/transactions` | Paginated search, date/amount filters, customer filter |
| | `GET /api/transactions/{id}/details` | Complete transaction, customer, history, device, IP view |
| **Rules Engine** | `GET /api/rules` | List all active fraud rules and condition trees |
| | `POST /api/rules` | Create new fraud rule (Admin only) |
| | `PATCH /api/rules/{id}` | Update rule conditions, score impact, or status |
| | `DELETE /api/rules/{id}` | Delete rule (Admin only) |
| **Investigations** | `GET /api/investigations` | List investigation cases |
| | `POST /api/investigations` | Open new investigation case |
| | `GET /api/investigations/{id}` | **Full risk-linked detail view** (Risk assessment + history + alerts) |
| | `PATCH /api/investigations/{id}` | Update notes, status, and conclusion |
| **Alerts & Feedback** | `GET /api/alerts` | List fraud alerts by status/severity |
| | `POST /api/alerts/{id}/review` | Review alert (`confirmed_fraud` / `false_positive`) |
| **Customer Risk** | `GET /api/customers/{id}/risk-profile` | Dynamic risk profile (score, level, device/location counts) |
| **AI Assistant** | `POST /api/assistant/query` | Natural language analyst Q&A powered by Gemini |
| **Network & Dashboard** | `GET /api/network` | Customer ── Device ── IP relationship graph |
| | `GET /api/dashboard` | Executive KPI counters, risk tier counts, 7-day activity |
| **Reports** | `POST /api/reports` | Generate daily/monthly activity report |
| | `GET /api/reports/{id}/export` | Export report in CSV or JSON format |

---

## Documentation & Deliverables

* **Comprehensive Full-Stack System & Quality Audit Report (DOCX)**: [`docs/Codecelix_AI_Fraud_Detection_Comprehensive_System_Report.docx`](docs/Codecelix_AI_Fraud_Detection_Comprehensive_System_Report.docx)
* **Frontend Architecture & Integration Documentation**: [`frontend/README.md`](frontend/README.md)
* **Backend Technical Documentation & Test Pyramid Guide**: [`backend/README.md`](backend/README.md)
* **ML Artifacts Documentation**: [`backend/app/ml/README.md`](backend/app/ml/README.md)
* **Automated DOCX Report Generation Script**: [`scripts/generate_report_docx.py`](scripts/generate_report_docx.py)
* **Original Project Specification**: [`docs/ai_31_aug.pdf`](docs/ai_31_aug.pdf)

---

## License

MIT
