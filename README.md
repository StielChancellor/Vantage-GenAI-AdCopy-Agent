# Vantage GenAI Ad Copy Agent

App: 2.8.1 — last live: 2026-05-17
An enterprise-grade, AI-powered marketing platform for ad copy generation and CRM campaign management. Leverages Google Gemini AI with pre-processed performance insights to produce platform-optimized advertising copy and manage marketing calendars.

**Live Demo:** [vantage-adcopy-agent](https://vantage-adcopy-agent-566761437172.asia-south1.run.app)

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Environment Setup](#environment-setup)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [Seed Admin User](#seed-admin-user)
- [Deployment](#deployment)
  - [Docker (Local)](#docker-local)
  - [Google Cloud Run](#google-cloud-run)
- [API Reference](#api-reference)
- [Ad Generation Pipeline](#ad-generation-pipeline)
- [Supported Ad Platforms](#supported-ad-platforms)
- [Admin Panel](#admin-panel)
- [Cost Tracking](#cost-tracking)
- [CSV Upload Formats](#csv-upload-formats)
- [Configuration](#configuration)
- [Testing](#testing)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## Features

- **AI-Powered Ad Copy** - Generates optimized ad copy using Google Gemini with context-aware prompts
- **AI-Powered Insights** - Analyzes historical ad performance on CSV upload via Gemini, stores persistent insights in Firestore
- **Multi-Platform Output** - Produces copy for Google Search, FB Single Image, FB Carousel, FB Video, Performance Max, and YouTube simultaneously
- **CRM Marketing Calendar** - Create and manage open-agent-style CRM campaigns with a marketing calendar view
- **URL Autocomplete** - Bare domain entry (auto-prepends `https://`), tag-based multi-URL input with history suggestions
- **Google Places Autocomplete** - Search hotels by name, view ratings and review counts, add multiple Google listings
- **Facebook Ad Types** - Three distinct Facebook formats with platform-specific character limits: Single Image, Carousel, and Video
- **Carousel Card Flow** - Two modes: AI-suggested card visuals or manual card descriptions (2-10 cards)
- **Post-Generation Refinement** - Feedback loop to refine generated ad copy with accumulated token/time tracking
- **Web Scraping** - Crawls hotel reference URLs (1-level deep) to extract property details, amenities, and USPs
- **Google Reviews Integration** - Pulls 4-5 star reviews from Google Places API with AI-summarized insights
- **Brand Guardrails** - Enforces positive/negative/restricted keywords from uploaded brand USP sheets
- **Animated Landing Page** - Canvas-based landing with wave effects, particles, and mouse-following interactions
- **Sidebar Layout** - Persistent sidebar navigation with Ad Copy, CRM, and Admin sections
- **Light/Dark Theme** - System-wide day/night toggle available in navbar (pre-login) and sidebar (post-login)
- **Admin Dashboard** - User management, CSV uploads, audit logs, usage statistics, model selection, and CSV export
- **Cost Tracking** - Per-generation and per-refinement token usage and cost in INR with exportable reports
- **JWT Authentication** - Secure role-based access (admin/user) with session tracking
- **Scale-to-Zero Deployment** - Runs on Google Cloud Run with automatic scaling (0-5 instances)

---

## Architecture

```
                    +-------------------+
                    |   React Frontend  |
                    |   (Vite SPA)      |
                    +--------+----------+
                             |
                             | HTTPS / JWT
                             |
                    +--------v----------+
                    |  FastAPI Backend   |
                    |  (Uvicorn)        |
                    +--------+----------+
                             |
          +------------------+------------------+
          |                  |                  |
+---------v------+  +--------v-------+
|  Google Gemini |  |   Firestore    |
|  (AI Model)    |  |   (NoSQL DB)   |
+----------------+  +----------------+
          |
+---------v-----------+
|  Google Places API  |
|  (Reviews + Maps)   |
+---------------------+
```

**Data Flow:**
1. User submits hotel details, reference URLs, Google listings, and target platforms
2. Backend scrapes reference URLs and fetches Google Reviews from selected listings
3. Pre-processed ad performance insights are fetched from Firestore (generated on CSV upload)
4. Brand USPs and guardrails are loaded from Firestore
5. All context is assembled into a structured prompt for Gemini AI
6. Generated ad copy is parsed, logged with cost metrics, and returned to the frontend
7. User can optionally refine results via feedback — tokens and time accumulate across refinement cycles

---

## Tech Stack

| Layer        | Technology                                                  |
|------------- |-------------------------------------------------------------|
| **Frontend** | React 19, Vite 8, React Router 7, Axios, Lucide React       |
| **Backend**  | Python 3.12, FastAPI, Uvicorn, Pydantic                     |
| **AI**       | Google Gemini (google-generativeai SDK)                     |
| **Database** | Google Cloud Firestore (structured data, insights, auth)    |
| **Auth**     | Custom JWT (PyJWT + bcrypt)                                 |
| **Scraping** | httpx, BeautifulSoup4, lxml                                 |
| **Hosting**  | Google Cloud Run (serverless, asia-south1)                  |
| **CI/CD**    | Google Cloud Build                                          |
| **Container**| Docker (multi-stage: Node 20 + Python 3.12)                 |

---

## Project Structure

```
Vantage-GenAI-AdCopy-Agent/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, routing, static files
│   │   ├── core/
│   │   │   ├── config.py           # Pydantic settings (env vars)
│   │   │   ├── auth.py             # JWT tokens, bcrypt passwords, auth deps
│   │   │   └── database.py         # Firestore client singleton
│   │   ├── models/
│   │   │   └── schemas.py          # Pydantic request/response models
│   │   ├── routers/
│   │   │   ├── health.py           # Health check endpoint
│   │   │   ├── auth.py             # Login, logout, current user
│   │   │   ├── admin.py            # User CRUD, CSV uploads, audit, export
│   │   │   ├── generate.py         # Ad generation, refinement + cost logging
│   │   │   └── places.py           # Google Places autocomplete proxy
│   │   └── services/
│   │       ├── ad_generator.py     # Main generation pipeline (insights + AI)
│   │       ├── rag_engine.py       # Firestore insight retrieval & brand USP lookup
│   │       ├── csv_ingestion.py    # CSV parsing, ingestion & AI insight generation
│   │       ├── scraper.py          # Web scraping (1-level deep crawl)
│   │       └── reviews.py          # Google Reviews API integration
│   ├── scripts/
│   │   └── seed_admin.py           # Create initial admin user
│   ├── tests/
│   │   └── test_auth.py            # Authentication unit tests
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                        # Local env vars (git-ignored)
├── frontend/
│   ├── src/
│   │   ├── main.jsx                # React entry point
│   │   ├── App.jsx                 # Router, protected routes & layout wrappers
│   │   ├── index.css               # Global styles & theme variables
│   │   ├── contexts/
│   │   │   └── ThemeContext.jsx    # Light/dark theme context & toggle
│   │   ├── pages/
│   │   │   ├── LandingPage.jsx     # Animated canvas landing page
│   │   │   ├── Login.jsx           # Authentication form
│   │   │   ├── Dashboard.jsx       # Ad copy generation interface
│   │   │   ├── CRMWizard.jsx       # CRM marketing calendar & campaign wizard
│   │   │   └── Admin.jsx           # Admin panel (5 tabs)
│   │   ├── components/
│   │   │   ├── AppLayout.jsx       # Sidebar layout with nav, theme toggle, logout
│   │   │   ├── AppNavbar.jsx       # Top navbar (legacy, retained for compatibility)
│   │   │   ├── ContextSelector.jsx # Identity type + contextual field selector
│   │   │   ├── AdResults.jsx       # Ad copy display, carousel cards, refinement UI
│   │   │   ├── CopilotChat.jsx     # Agent-style copilot chat interface
│   │   │   ├── CRMResults.jsx      # CRM campaign results display
│   │   │   ├── BriefTracker.jsx    # Campaign brief tracking component
│   │   │   ├── BriefSummaryCard.jsx# Brief summary card UI
│   │   │   ├── CalendarView.jsx    # Calendar view for campaigns
│   │   │   ├── CampaignCalendarGrid.jsx # Campaign calendar grid display
│   │   │   ├── CampaignTableView.jsx    # Campaign table view
│   │   │   ├── ChannelFrequency.jsx     # Channel frequency settings
│   │   │   ├── EventCalendar.jsx        # Event calendar component
│   │   │   ├── TrainingWizard.jsx       # Admin training/onboarding wizard
│   │   │   └── GenerationProgress.jsx   # Animated step-by-step progress
│   │   ├── hooks/
│   │   │   └── useAuth.jsx         # Auth context & state management
│   │   └── services/
│   │       └── api.js              # Axios client with JWT interceptor
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
├── Dockerfile                      # Multi-stage Docker build
├── cloudbuild.yaml                 # GCP Cloud Build pipeline (asia-south1)
├── .gitignore
└── README.md
```

---

## Getting Started

### Prerequisites

- **Python** 3.12+
- **Node.js** 20+
- **npm** 10+
- **Google Cloud Project** with the following APIs enabled:
  - Cloud Firestore
  - Generative Language API (Gemini)
  - Places API
- **GCP Service Account** JSON key (for local development with Firestore)

### Environment Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/StielChancellor/Vantage-GenAI-AdCopy-Agent.git
   cd Vantage-GenAI-AdCopy-Agent
   ```

2. Create the backend environment file:
   ```bash
   cp backend/.env.example backend/.env
   ```

3. Edit `backend/.env` with your credentials:
   ```env
   # JWT Secret (change for production)
   JWT_SECRET_KEY=your-secure-random-secret-key

   # Firebase / GCP
   FIREBASE_PROJECT_ID=your-gcp-project-id
   GCP_PROJECT_ID=your-gcp-project-id
   FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json

   # Google Gemini AI
   GEMINI_API_KEY=your-gemini-api-key

   # Google Places API (for reviews)
   GOOGLE_PLACES_API_KEY=your-places-api-key

   # Cache
   REVIEW_CACHE_DAYS=30
   ```

### Backend Setup

```bash
# Create virtual environment
cd backend
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the development server
cd ..
uvicorn backend.app.main:app --reload --port 8080
```

The API will be available at `http://localhost:8080` with interactive docs at `/api/docs`.

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend will be available at `http://localhost:5173` (Vite default).

### Seed Admin User

Before first use, create an admin user:

```bash
# From the project root
python backend/scripts/seed_admin.py admin@vantage.com YourPassword "Admin Name"
```

---

## Deployment

### Docker (Local)

```bash
# Build the multi-stage image
docker build -t vantage-adcopy-agent .

# Run with environment variables
docker run -p 8080:8080 \
  -e GEMINI_API_KEY=your-key \
  -e GOOGLE_PLACES_API_KEY=your-key \
  -e JWT_SECRET_KEY=your-secret \
  -e FIREBASE_PROJECT_ID=your-project \
  -e GCP_PROJECT_ID=your-project \
  -e REVIEW_CACHE_DAYS=30 \
  vantage-adcopy-agent
```

### Google Cloud Run

**Option A: Automated via Cloud Build**

```bash
# Submit build (from project root)
gcloud builds submit --config=cloudbuild.yaml --project=your-project-id
```

**Option B: Manual deployment**

```bash
# Build and push
gcloud builds submit --tag gcr.io/your-project-id/vantage-adcopy-agent

# Deploy to Cloud Run (asia-south1)
gcloud run deploy vantage-adcopy-agent \
  --image gcr.io/your-project-id/vantage-adcopy-agent \
  --region asia-south1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5
```

**Important:** Environment variables must be set directly on the Cloud Run service:

```bash
gcloud run services update vantage-adcopy-agent \
  --region=asia-south1 \
  --set-env-vars="GEMINI_API_KEY=...,GOOGLE_PLACES_API_KEY=...,JWT_SECRET_KEY=...,FIREBASE_PROJECT_ID=...,GCP_PROJECT_ID=...,REVIEW_CACHE_DAYS=30"
```

---

## API Reference

Base URL: `/api/v1`

Interactive API documentation is available at:
- **Swagger UI:** `/api/docs`
- **ReDoc:** `/api/redoc`

### Endpoints

| Method | Endpoint                              | Auth   | Description                              |
|--------|---------------------------------------|--------|------------------------------------------|
| GET    | `/health`                             | None   | Health check                             |
| POST   | `/api/v1/auth/login`                  | None   | Login with email & password              |
| POST   | `/api/v1/auth/logout`                 | JWT    | Logout (audit logging)                   |
| GET    | `/api/v1/auth/me`                     | JWT    | Get current user info                    |
| POST   | `/api/v1/generate`                    | JWT    | Generate ad copy                         |
| POST   | `/api/v1/generate/refine`             | JWT    | Refine ad copy with user feedback        |
| GET    | `/api/v1/generate/url-suggestions`    | JWT    | URL autocomplete from generation history |
| GET    | `/api/v1/places/autocomplete`         | JWT    | Google Places autocomplete search        |
| POST   | `/api/v1/admin/users`                 | Admin  | Create a new user                        |
| GET    | `/api/v1/admin/users`                 | Admin  | List all users                           |
| PUT    | `/api/v1/admin/users/{id}`            | Admin  | Update a user                            |
| DELETE | `/api/v1/admin/users/{id}`            | Admin  | Delete a user                            |
| POST   | `/api/v1/admin/upload/historical-ads` | Admin  | Upload historical ads CSV                |
| POST   | `/api/v1/admin/upload/brand-usp`      | Admin  | Upload brand USP CSV                     |
| GET    | `/api/v1/admin/audit-logs`            | Admin  | View generation audit logs               |
| GET    | `/api/v1/admin/usage-stats`           | Admin  | Per-user usage statistics                |
| GET    | `/api/v1/admin/export/usage`          | Admin  | Export all usage data as CSV             |
| GET    | `/api/v1/admin/settings`              | Admin  | Get current admin settings               |
| PUT    | `/api/v1/admin/settings`              | Admin  | Update default AI model                  |

---

## Ad Generation Pipeline

```
1. HISTORICAL AD INSIGHTS
   Fetch pre-processed performance insights from Firestore (generated by
   Gemini on CSV upload). Includes top-performing headlines, descriptions,
   patterns, and actionable findings.

2. BRAND USP LOOKUP
   Fetch brand-specific USPs, positive keywords, negative keywords, and
   restricted keywords from Firestore to enforce brand guardrails.

3. WEB SCRAPING
   Scrape all user-provided reference URLs with 1-level deep crawling.
   Extracts text from relevant subpages (rooms, amenities, dining, spa, etc.).
   Maximum 5 subpages per URL, 8000 chars total output.

4. GOOGLE REVIEWS
   If Google Listing(s) are provided, fetch place details via Places API.
   Supports multiple listings. Filter to 4-5 star reviews only. AI summarizes
   themes, amenities praised, emotional keywords, and unique selling points.

5. PROMPT ASSEMBLY
   Build a structured system prompt with brand restrictions and a user prompt
   with all gathered context (scraped content, reviews, ad insights, USPs).

6. AI GENERATION
   Call Google Gemini with platform-specific character limits and format
   requirements. Parse the structured JSON response.

7. COST CALCULATION & AUDIT
   Calculate cost in INR based on input/output token usage and model pricing.
   Log complete audit entry to Firestore.

8. REFINEMENT (optional, repeatable)
   User submits feedback on generated copy. Tokens and time accumulate
   across refinement cycles. Each refinement is logged in audit trail.
```

---

## Supported Ad Platforms

| Platform              | Headlines              | Descriptions / Primary Text         |
|-----------------------|------------------------|--------------------------------------|
| **Google Search**     | 15 × 30 chars          | 4 × 90 chars                         |
| **FB Single Image**   | 5 × 27 chars           | 5 × 50-150 chars (Primary Text)      |
| **FB Carousel**       | 5 × 45 chars (per card)| 5 × 18 chars + 1 × 80 chars Primary  |
| **FB Video**          | 5 × 27 chars           | 5 × 50-150 chars (Primary Text)      |
| **Performance Max**   | 15 × 30 chars          | 5 × 90 chars                         |
| **YouTube**           | 5 × 40 chars           | 5 × 90 chars + 1 × 150 chars         |

---

## Admin Panel

The admin panel (`/admin`) provides five tabs:

1. **Users** - Create, view, edit, and delete users. Assign admin or user roles.
2. **CSV Upload** - Upload historical ad performance data and brand USP sheets.
3. **Audit & Usage** - View detailed generation logs with tokens, cost in INR, and generation time.
4. **Usage Stats** - Per-user aggregate statistics: login count, total generations, total tokens, and cost.
5. **Settings** - Select the default Gemini AI model for all generations.

---

## Cost Tracking

| Model                   | Input (USD/1M tokens) | Output (USD/1M tokens) |
|-------------------------|-----------------------|------------------------|
| Gemini 2.5 Flash        | $0.15                 | $0.60                  |
| Gemini 2.5 Flash Lite   | $0.075                | $0.30                  |
| Gemini 2.5 Pro          | $1.25                 | $10.00                 |
| Gemini 2.0 Flash Lite   | $0.075                | $0.30                  |

Costs are converted to INR (at 85.0 USD/INR) and stored per audit log entry.

---

## CSV Upload Formats

### Historical Ads CSV

| Column (flexible naming) | Description                                |
|--------------------------|--------------------------------------------|
| Hotel Name               | Property or brand name                     |
| Headline(s)              | Ad headline text                           |
| Description(s)           | Ad description/body text                   |
| CTR                      | Click-through rate (numeric or percentage) |
| CVR                      | Conversion rate (numeric or percentage)    |

### Brand USP CSV

| Column              | Description                                              |
|---------------------|----------------------------------------------------------|
| Hotel Name          | Property or brand name                                   |
| USPs                | Comma-separated unique selling points                    |
| Positive Keywords   | Keywords to encourage in ad copy                         |
| Negative Keywords   | Keywords to avoid                                        |
| Restricted Keywords | Keywords that must never appear                          |

---

## Configuration

### Environment Variables

| Variable                        | Required | Description                                  |
|---------------------------------|----------|----------------------------------------------|
| `GEMINI_API_KEY`                | Yes      | Google Generative AI API key                 |
| `JWT_SECRET_KEY`                | Yes      | Secret for signing JWT tokens                |
| `FIREBASE_PROJECT_ID`           | Yes      | GCP Firestore project ID                     |
| `GCP_PROJECT_ID`                | Yes      | Google Cloud project ID                      |
| `GOOGLE_PLACES_API_KEY`         | No       | Google Places API key (for reviews feature)  |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | No       | Path to service account JSON (local dev)     |
| `REVIEW_CACHE_DAYS`             | No       | Review cache TTL in days (default: `30`)     |

### Available AI Models

- `gemini-2.5-flash` (default) — Fast, cost-effective
- `gemini-2.5-flash-lite` — Ultra-low cost
- `gemini-2.5-pro` — Highest quality, higher cost
- `gemini-2.0-flash-lite` — Legacy low-cost option

---

## Testing

```bash
cd backend
pytest tests/ -v
```

Tests cover: password hashing, JWT token creation/decoding, invalid token handling.

---

## Known Limitations

- **Gemini API Quotas** - Free tier has limited requests per minute/day. Enable billing for production.
- **CORS** - Currently configured to allow all origins. Restrict to your domain in production.
- **Custom Domain** - asia-south1 does not support Cloud Run native domain mappings. Use a load balancer or reverse proxy for custom domains.

---

## License

This project is proprietary. All rights reserved.
