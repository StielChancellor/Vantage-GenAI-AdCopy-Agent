# Vantage GenAI AdCopy Agent - Project State

## Tech Stack
- **Backend:** Python 3.12 + FastAPI
- **Frontend:** React 19 + Vite
- **Database:** GCP Firestore (structured data, auth, audit logs)
- **Vector DB:** ChromaDB (embedded, for RAG historical ads)
- **Auth:** Custom JWT (bcrypt + PyJWT), admin-created users in Firestore
- **AI:** Google Gemini (via google-generativeai SDK)
- **Hosting:** Google Cloud Run (serverless)
- **GCP Project:** vantage-genai-adcopy-agent (566761437172)
- **GitHub:** StielChancellor/Vantage-GenAI-AdCopy-Agent

## Architecture
```
frontend/          React/Vite SPA
  src/pages/       Login, Dashboard, Admin
  src/components/  AdResults
  src/services/    api.js (axios)
  src/hooks/       useAuth.js (context)

backend/app/
  core/            config.py, auth.py, database.py
  models/          schemas.py (Pydantic)
  routers/         auth.py, admin.py, generate.py, health.py
  services/        csv_ingestion.py, scraper.py, reviews.py, rag_engine.py, ad_generator.py
```

## API Endpoints
- `GET  /health` - Health check
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/logout` - User logout
- `GET  /api/v1/auth/me` - Current user info
- `POST /api/v1/admin/users` - Create user (admin)
- `GET  /api/v1/admin/users` - List users (admin)
- `PUT  /api/v1/admin/users/{id}` - Update user (admin)
- `DEL  /api/v1/admin/users/{id}` - Delete user (admin)
- `POST /api/v1/admin/upload/historical-ads` - Upload historical CSV (admin)
- `POST /api/v1/admin/upload/brand-usp` - Upload brand USP CSV (admin)
- `GET  /api/v1/admin/audit-logs` - View audit logs (admin)
- `GET  /api/v1/admin/usage-stats` - View usage stats (admin)
- `POST /api/v1/generate` - Generate ad copy (authenticated)

## Firestore Collections
- `users` - {full_name, email, password_hash, role, created_at, created_by}
- `audit_logs` - {user_email, action, timestamp, session_id, tokens_consumed, inputs}
- `historical_ads` - {full_text, hotel_name, headlines[], descriptions[], ctr, cvr}
- `brand_usps` - {hotel_name, usps[], positive_keywords[], negative_keywords[], restricted_keywords[]}
- `review_cache` - {hotel_name, insights, review_count, overall_rating, cached_at}

## Feature Checklist
- [x] Project structure & scaffolding
- [x] FastAPI backend with auth, admin, generate routers
- [x] CSV ingestion service (historical ads + brand USPs)
- [x] RAG engine with ChromaDB (with cold-start fallback)
- [x] Web scraper (1-level deep crawl)
- [x] Google Reviews integration (4-5 star filter, caching)
- [x] Ad generation pipeline (Gemini, multi-platform)
- [x] React frontend (Login, Dashboard, Admin)
- [x] Dockerfile & cloudbuild.yaml
- [ ] Install backend deps & run auth tests
- [ ] Set up API keys (Gemini, Google Places)
- [ ] Enable GCP APIs (Firestore, Cloud Run)
- [ ] Initial commit & push to GitHub
- [ ] First deployment to Cloud Run
- [ ] Seed admin user

## API Keys Needed
1. **GEMINI_API_KEY** - From Google AI Studio (aistudio.google.com)
2. **GOOGLE_PLACES_API_KEY** - From Google Cloud Console (Places API)
3. **JWT_SECRET_KEY** - Generate a random secret for production

## Environment Setup
- Python 3.12: C:\Users\hi\AppData\Local\Programs\Python\Python312
- CLOUDSDK_PYTHON must point to above path for gcloud
- Node.js: v24.14.0
