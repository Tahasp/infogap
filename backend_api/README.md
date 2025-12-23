## Local API Server

This wraps the CLI commands for the web interface.

### Setup

Use the shared virtual environment in the repo root:

```bash
cd ../infogap
python -m venv .venv                # create once
source .venv/bin/activate           # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Run

```bash
python server.py
```

Server runs on `http://localhost:8000`

### Usage

1. Clone the repo
2. Set up `.env` in `backend/` as per main README
3. Install dependencies once in the repo root (`pip install -r requirements.txt`)
4. Start this API server: `cd backend_api && python server.py`
5. Start frontend: `cd frontend && npm run dev`
6. Use the web UI to trigger jobs locally

### Deploy notes

- Deploying to Render/other hosts: set `ALLOWED_ORIGINS` (comma-separated) to your frontend origin(s) so CORS succeeds, e.g. `https://your-frontend.vercel.app`.
- Point the frontend at the hosted API with `VITE_API_URL` (e.g. `https://infogap.onrender.com`).
