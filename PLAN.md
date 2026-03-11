# SBA v3.0 — Product Transformation Plan

## PHASE 1: Architecture Overview

### System Architecture
- **Framework**: FastAPI + Jinja2 SSR templates + vanilla JS (3,372 LOC) + CSS (6,288 LOC)
- **Database**: SQLite with WAL mode, 30+ tables, comprehensive indexing
- **ML Pipeline**: XGBoost prop predictions, Poisson models, cross-validation
- **API Layer**: 22 route modules, SSE/WebSocket streaming, REST API with OpenAPI docs
- **CLI**: Typer-based CLI for data sync, model training, edge scanning
- **Infra**: Docker, service worker (PWA), rate limiting, API key auth

### System Component Map
```
CLI (Typer) ─────────────────────────────┐
                                          │
Web (FastAPI) ── Views (Jinja2 SSR)       │
  ├── API Routes (22 modules)             │
  ├── SSE/WebSocket (live streaming)      │
  ├── Middleware (rate limit, auth, CORS)  │
  └── Static (JS app, CSS)               │
                                          │
Services ─────────────────────────────────┤
  ├── EdgeFinder (EV detection)           │
  ├── MLPipeline (training/prediction)    │
  ├── Webhook (delivery + retry)          │
  └── Arbitrage detection                 │
                                          │
Data Layer ───────────────────────────────┤
  ├── Repository (CRUD + audit)           │
  ├── API Clients (Odds API, BallDontLie) │
  ├── Schema + Migrations                 │
  └── SQLite (WAL, SAVEPOINT atomics)     │
                                          │
Models ───────────────────────────────────┘
  ├── Statistical (EV, Kelly, Poisson, Arb)
  ├── ML (XGBoost, features, pipeline)
  └── Domain (dataclasses)
```

### Strengths
1. Rich feature set — 30+ pages covering EV, props, arb, CLV, portfolio, simulator
2. Solid data model with comprehensive schema and indexing
3. Good middleware stack (rate limiting, security headers, CORS, API key auth)
4. ML pipeline with XGBoost, cross-validation, feature importance
5. SSE + WebSocket for real-time updates
6. PWA support with service worker
7. Audit logging, input sanitization, constants extraction (v2.9)
8. 874 passing tests

### Weaknesses & Technical Debt
1. **Broken API endpoints**: `/api/arbitrage`, `/api/middles`, `/api/low-holds` reference non-existent `EdgeFinder(api_key=...)` constructor and `.fetch_odds()` method — these will crash at runtime
2. **Version mismatch**: pyproject.toml says "2.8.0" but `__init__.py` says "2.9.0"
3. **Monolithic JS**: Single 3,372-line `app.js` file handles all UI logic
4. **No data export**: No CSV/PDF export for bet history, analytics
5. **No background task scheduler**: Odds refresh, model retraining require manual CLI invocation
6. **No data backup/restore**: SQLite file with no backup strategy
7. **No pagination on several endpoints**: Some endpoints fetch unbounded results
8. **Inline HTML in JS**: Dashboard widgets construct HTML via template literals — fragile, no XSS protection
9. **No unit tests for several route modules**: Many route files lack dedicated tests
10. **No integration test for the full app lifecycle**: No end-to-end test that exercises the full flow
11. **Edge finder instantiates on every request**: No singleton/caching for EdgeFinder service
12. **Stale `EdgeFinder` usage in edges.py**: Routes 91-209 use old API (`finder.fetch_odds()`, `EdgeFinder(api_key=...)`)

## PHASE 2: Product Understanding

### Product Purpose
Professional sports betting analytics platform for finding +EV betting opportunities using mathematical models (Kelly criterion, Poisson, consensus probabilities) and ML (XGBoost) predictions across 20+ sportsbooks.

### Target Users
1. **Serious recreational bettors** — seeking data-driven edge over bookmakers
2. **Professional/sharp bettors** — CLV tracking, account limit management, bankroll optimization
3. **Prop bettors** — ML-powered player prop predictions

### Core Value Proposition
- Automated +EV detection with Kelly sizing
- Player prop predictions with XGBoost
- Multi-book odds comparison and arbitrage detection
- CLV tracking to measure betting skill
- Responsible gambling safeguards

### Friction Points
1. Requires CLI for data sync and model training (no auto-sync from UI)
2. No onboarding flow — new users see empty dashboard
3. Broken arbitrage/middles/low-hold endpoints
4. No historical performance benchmarks to validate model quality
5. No data import from popular bet trackers (Action Network, SharpApp)

## PHASE 5: Implementation Priorities

### P0 — Critical Fixes (Must ship)
1. Fix broken arbitrage/middles/low-holds endpoints in edges.py
2. Fix version mismatch between pyproject.toml and __init__.py
3. Fix XSS vulnerability in JS template literals (innerHTML with unescaped data)

### P1 — High-Impact Quality (Should ship)
4. Add data export API (CSV download for bet history)
5. Add auto-refresh capability from dashboard (trigger odds sync from UI)
6. Add health check endpoint improvements (DB connectivity, API key status)
7. Add proper error boundaries in frontend JS
8. Add comprehensive API error responses with consistent schema

### P2 — Premium Differentiators
9. Add expected vs actual model tracking (model calibration dashboard)
10. Add odds movement alerts (configurable threshold-based notifications)
11. Add bet grading with CLV analysis
12. Add session-based P/L tracking

### P3 — Infrastructure
13. Add structured JSON logging option
14. Add database backup/export endpoint
15. Add API versioning prefix
16. Add OpenTelemetry-compatible request tracing

## PHASE 10: Implementation Plan

### Batch 1: Critical Fixes
1. **Fix broken edge routes** — Update `/api/arbitrage`, `/api/middles`, `/api/low-holds` to use correct EdgeFinder API
2. **Fix version sync** — Align pyproject.toml with __init__.py at 3.0.0
3. **Fix XSS in template literals** — Add text escaping utility to app.js, use it in all innerHTML assignments

### Batch 2: API Quality
4. **Data export endpoint** — `GET /api/bets/export?format=csv` with proper Content-Disposition headers
5. **Enhanced health endpoint** — Return DB size, table counts, API key configured status, uptime
6. **Odds sync trigger** — `POST /api/data/sync` endpoint to trigger odds refresh from dashboard

### Batch 3: Frontend Hardening
7. **JS error boundaries** — Wrap all async fetch calls with consistent error handling
8. **Loading skeleton states** — Replace "Loading..." spinners with skeleton UI patterns
9. **Empty state improvements** — Better guidance when no data exists

### Batch 4: New Tests
10. **Fix and test all broken endpoints** — Ensure 100% of API routes are exercised
11. **Add integration smoke test** — Exercise full app startup and key endpoints
