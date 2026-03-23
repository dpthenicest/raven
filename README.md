# raven
GitHub Repository for Interswitch and Enyata Build-a-thon

# HOW TO RUN /BACKEND SERVER

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
