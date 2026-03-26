# raven
GitHub Repository for Interswitch and Enyata Build-a-thon

## Sample DisCo Data

```json
[
  {
    "id": "5e8a6600-4f5c-4c34-836d-bb8a65b334f2",
    "name": "Port Harcourt Electricity Distribution Plc",
    "code": "PHEDC",
    "path": "https://nerc.gov.ng/wp-content/uploads/2026/03/PHED-monthly-energy-caps-Mar-2026.pdf"
  }
]
```

## NERC PDF Parsing

Two ways to import feeder data from a NERC monthly energy cap PDF:

**Option 1 — Fetch from DisCo's stored URL:**
```
POST /admin/parse-nerc/{disco_id}/fetch
```
Automatically downloads the PDF from the `path` field of the DisCo and parses it.

**Option 2 — Upload PDF manually:**
```
POST /admin/parse-nerc?disco_id={disco_id}
```
Upload a PDF file directly. Requires `disco_id` as a query param.

Both routes parse the table columns: `STATE | BUSINESS UNIT | FEEDER NAME | NON-MD SERVICE BAND | CAP (kWh)`
and upsert the data into the `feeders` table.


# HOW TO RUN BACKEND SERVER

# Install Tesseract (macOS)
brew install tesseract

brew install ccache

# Copy env and fill in your values
cp backend/.env.example backend/.env

# Start PostgreSQL with PostGIS via Docker
cd backend && docker-compose up -d db

# Install deps (in a venv)
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start the API
uvicorn app.main:app --reload
