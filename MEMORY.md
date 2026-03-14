# Vantage GenAI AdCopy Agent - Project State

## Deployment
- **Live URL:** https://vantage-adcopy-agent-566761437172.asia-south1.run.app
- **Region:** asia-south1 (Mumbai)
- **API Docs:** https://vantage-adcopy-agent-566761437172.asia-south1.run.app/api/docs
- **GitHub:** https://github.com/StielChancellor/Vantage-GenAI-AdCopy-Agent

## Tech Stack
- **Backend:** Python 3.12 + FastAPI
- **Frontend:** React 19 + Vite
- **Database:** GCP Firestore (nam5, structured data + auth + audit)
- **Vector DB:** ChromaDB (embedded, RAG historical ads)
- **Auth:** Custom JWT (bcrypt + PyJWT), admin-created users
- **AI:** Google Gemini (google-generativeai SDK)
- **Hosting:** Google Cloud Run (serverless, scale-to-zero)
- **GCP Project:** vantage-genai-adcopy-agent (566761437172)

## Admin Credentials
- Email: admin@vantage.com
- Password: Admin123!

## Feature Checklist
- [x] Project structure & scaffolding
- [x] FastAPI backend with auth, admin, generate routers
- [x] CSV ingestion (historical ads + brand USPs)
- [x] RAG engine with ChromaDB (cold-start fallback)
- [x] Web scraper (1-level deep crawl)
- [x] Google Reviews (4-5 star filter, 30-day cache)
- [x] Ad generation (Gemini, multi-platform)
- [x] React frontend (Login, Dashboard, Admin)
- [x] Dockerfile & cloudbuild.yaml
- [x] Auth tests passing
- [x] GCP APIs enabled (Firestore, Cloud Run, Places)
- [x] Deployed to Cloud Run (asia-south1)
- [x] Admin user seeded

## Known Issues
- Gemini API free tier quota may be exhausted (429 errors) - needs billing enabled
- ChromaDB data is ephemeral in Cloud Run (/tmp) - persists only during instance lifetime
