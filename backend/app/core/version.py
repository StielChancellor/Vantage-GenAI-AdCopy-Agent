"""Single source of truth for the app version on the backend.

Mirrored in `frontend/src/version.js` and `README.md`. All three are kept
in sync by `scripts/bump_version.py`.

Why a tiny module: many places need it (FastAPI metadata, /health response,
BigQuery audit rows, structured logs). Having one constant is cheaper than
threading it through env vars.
"""
APP_VERSION = "2.8.2"
APP_VERSION_DATE = "2026-05-17"   # date this version went live
